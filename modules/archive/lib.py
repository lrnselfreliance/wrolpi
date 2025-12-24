import base64
import gzip
import json
import os
import pathlib
import re
import shlex
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
from typing import Optional, Tuple, List, Union
from urllib.parse import urlparse

import pytz
from sqlalchemy import asc, func, BigInteger
from sqlalchemy.orm import Session

from modules.archive.models import Archive
from wrolpi import dates
from wrolpi.cmd import READABILITY_BIN, run_command
from wrolpi.collections import Collection
from wrolpi.common import get_media_directory, get_relative_to_media_directory, logger, extract_domain, \
    escape_file_name, aiohttp_post, format_html_string, split_lines_by_length, get_html_soup, get_title_from_html, \
    get_wrolpi_config, html_screenshot, ConfigFile
from wrolpi.dates import now, Seconds
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import UnknownArchive, InvalidOrderBy, InvalidDatetime
from wrolpi.events import Events
from wrolpi.files.lib import handle_file_group_search_results
from wrolpi.files.models import FileGroup
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.tags import tag_append_sub_select_where
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)

__all__ = ['DomainsConfig', 'domains_config', 'get_domains_config', 'save_domains_config', 'import_domains_config']

ARCHIVE_SERVICE = 'http://archive:8080'


@dataclass
class DomainsConfigValidator:
    """Validator for domains config file."""
    version: int = 0
    collections: List[dict] = field(default_factory=list)


class DomainsConfig(ConfigFile):
    """
    Config file for Domain Collections.

    This is a specialized config that manages domain collections
    (Collections with kind='domain'). It maintains a domains.yaml file for
    backward compatibility and user convenience.

    Format:
        collections:
          - name: "example.com"
            kind: "domain"
            description: "Archives from example.com"
          - name: "wikipedia.org"
            kind: "domain"

    Note: Domain collections can have optional directories for tagging support.
    Items are managed dynamically when Archives are indexed.
    """
    file_name = 'domains.yaml'
    validator = DomainsConfigValidator
    default_config = dict(
        version=0,
        collections=[],
    )
    # Use wider width to accommodate longer paths
    width = 120

    def __getitem__(self, item):
        return self._config[item]

    def __setitem__(self, key, value):
        self._config[key] = value

    @property
    def collections(self) -> List[dict]:
        """Get list of collection configs."""
        return self._config.get('collections', [])

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Import domain collections from config file into database using batch operations."""
        file = file or self.get_file()
        file_str = str(get_relative_to_media_directory(file))

        # If config file doesn't exist, mark import as successful (nothing to import)
        if not file.is_file():
            logger.info('No domains config file, skipping import')
            self.successful_import = True
            return

        ConfigFile.import_config(self, file, send_events)

        collections_data = self._config.get('collections', [])

        # Empty collections list = never delete DB records
        if not collections_data:
            logger.info(f'No domain collections in config, preserving existing DB domain collections')
            self.successful_import = True
            return

        logger.info(f'Importing {len(collections_data)} domain collections from {file_str}')

        try:
            with get_db_session(commit=True) as session:
                # Validate and prepare data first
                valid_data_list = []
                for idx, collection_data in enumerate(collections_data):
                    try:
                        name = collection_data.get('name')
                        if not name:
                            logger.error(f'Domain collection at index {idx} has no name, skipping')
                            continue

                        # Validate domain name format before batching
                        if not Collection.is_valid_domain_name(name):
                            logger.error(
                                f"Domain collection at index {idx} has invalid name '{name}' "
                                f"(must contain at least one '.' and not start/end with '.'), skipping"
                            )
                            continue

                        # Ensure kind is 'domain'
                        collection_data = collection_data.copy()
                        collection_data['kind'] = 'domain'

                        # Note: Collections can now be tagged even without a directory
                        # Tags enable UI search/filtering for directory-less collections

                        valid_data_list.append(collection_data)
                    except Exception as e:
                        logger.error(f'Failed to validate domain collection at index {idx}', exc_info=e)
                        continue

                # Batch create/update collections
                imported_domains = set()
                if valid_data_list:
                    collections = Collection.batch_from_config(session, valid_data_list)
                    imported_domains = {c.name for c in collections}

                # Delete domain collections that are no longer in config
                all_domain_collections = session.query(Collection).filter_by(kind='domain').all()
                for collection in all_domain_collections:
                    if collection.name not in imported_domains:
                        logger.info(f'Deleting domain collection {repr(collection.name)} (no longer in config)')
                        session.delete(collection)

            logger.info(f'Successfully imported {len(imported_domains)} domain collections from {file_str}')
            self.successful_import = True

        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {file_str} config!'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_import_failed(message)
            raise

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all domain collections from database to config file."""
        logger.info('Dumping domain collections to config')

        with get_db_session() as session:
            # Get only domain collections, ordered by name
            collections = session.query(Collection).filter_by(kind='domain').order_by(Collection.name).all()

            # Use to_config to export each collection
            collections_data = [collection.to_config() for collection in collections]

            self._config['collections'] = collections_data

        logger.info(f'Dumping {len(collections_data)} domain collections to config')
        self.save(file, send_events, overwrite)


# Global instance
domains_config = DomainsConfig()


def get_domains_config() -> DomainsConfig:
    """Get the global domains config instance."""
    return domains_config


# Switch handler for saving domains config
@register_switch_handler('save_domains_config')
def save_domains_config():
    """Save the domains config when the switch is activated."""
    domains_config.background_dump.activate_switch()


# Explicit type for activate_switch helper
save_domains_config: ActivateSwitchMethod


def import_domains_config():
    """Import domain collections from config file into database."""
    logger.info('Importing domains config')
    domains_config.import_config()

    # Link downloads to domain collections after import
    with get_db_session() as session:
        link_domain_and_downloads(session)

    logger.info('Importing domains config completed')


@dataclass
class ArchiveDownloaderConfigValidator:
    """Validator for archives_downloader.yaml config."""
    file_name_format: str
    version: int = 0

    def __post_init__(self):
        # Validate file_name_format contains required %(title)s variable
        if '%(title)s' not in self.file_name_format:
            raise ValueError('file_name_format must contain %(title)s')


class ArchiveDownloaderConfig(ConfigFile):
    """
    Config file for Archive Downloader settings.

    This config mirrors videos_downloader.yaml and holds settings for how
    archives are downloaded and named.

    Format:
        version: 0
        file_name_format: '%(download_date)s_%(title)s'

    Variables available in file_name_format:
        - %(title)s - Page title (extracted from HTML)
        - %(download_datetime)s - Full download datetime (YYYY-MM-DD-HH-MM-SS)
        - %(download_date)s - Download date only (YYYY-MM-DD)
        - %(download_year)s - Download year
        - %(download_month)s - Download month (zero-padded)
        - %(download_day)s - Download day (zero-padded)
        - %(domain)s - Domain name

    Subdirectories can be included in the format, e.g.:
        '%(download_year)s/%(download_datetime)s_%(title)s'
    """
    file_name = 'archives_downloader.yaml'
    validator = ArchiveDownloaderConfigValidator
    default_config = dict(
        version=0,
        file_name_format='%(download_datetime)s_%(title)s',
    )

    @property
    def file_name_format(self) -> str:
        return self._config['file_name_format']

    def import_config(self, file: pathlib.Path = None, send_events=False):
        super().import_config(file, send_events)
        self.successful_import = True


# Global instance for archive downloader config
ARCHIVE_DOWNLOADER_CONFIG: ArchiveDownloaderConfig = ArchiveDownloaderConfig()


def get_archive_downloader_config() -> ArchiveDownloaderConfig:
    """Get the global archive downloader config instance."""
    return ARCHIVE_DOWNLOADER_CONFIG


def format_archive_filename(
        title: str,
        domain: str = None,
        download_date: datetime = None,
) -> str:
    """Format archive filename using config template.

    This function formats the filename (and optional subdirectory path) for an archive
    using the file_name_format from archives_downloader.yaml.

    Args:
        title: Page title (extracted from HTML)
        domain: Domain name of the archived URL
        download_date: Date of download (defaults to now)

    Returns:
        Formatted filename/path (without .html extension, added later)

    Example:
        format_archive_filename("My Article", "example.com")
        # With default format: "2025-12-22_My Article"
        # With "%(download_year)s/%(title)s": "2025/My Article"
    """
    config = get_archive_downloader_config()
    template = config.file_name_format

    download_date = download_date or now()

    variables = dict(
        title=escape_file_name(title) if title else 'untitled',
        domain=domain or '',
        download_datetime=archive_strftime(download_date),
        download_date=download_date.strftime('%Y-%m-%d'),
        download_year=str(download_date.year),
        download_month=f'{download_date.month:02d}',
        download_day=f'{download_date.day:02d}',
    )

    try:
        return template % variables
    except KeyError as e:
        logger.error(f'Invalid variable in archive file_name_format: {e}')
        # Fallback to default format
        return f'{archive_strftime(download_date)}_{escape_file_name(title) if title else "untitled"}'


def preview_archive_filename(file_name_format: str) -> str:
    """Preview the archive filename using sample data.

    Args:
        file_name_format: The format template to preview

    Returns:
        A preview string showing what the filename would look like

    Raises:
        RuntimeError: If the format is invalid or missing required variables
    """
    if '%(title)s' not in file_name_format:
        raise RuntimeError('file_name_format must contain %(title)s')

    sample_date = now()
    variables = dict(
        title='Example Page Title',
        domain='example.com',
        download_datetime=archive_strftime(sample_date),
        download_date=sample_date.strftime('%Y-%m-%d'),
        download_year=str(sample_date.year),
        download_month=f'{sample_date.month:02d}',
        download_day=f'{sample_date.day:02d}',
    )

    try:
        preview = file_name_format % variables
        return f'{preview}.html'
    except KeyError as e:
        raise RuntimeError(f'Invalid variable: {e}')
    except ValueError as e:
        raise RuntimeError(f'Invalid format: {e}')


@dataclass
class ArchiveFiles:
    """Every Archive will have some of these files."""
    singlefile: pathlib.Path = None
    readability: pathlib.Path = None
    readability_txt: pathlib.Path = None
    readability_json: pathlib.Path = None
    screenshot: pathlib.Path = None

    def __repr__(self):
        singlefile = str(self.singlefile.relative_to(get_archive_directory())) if self.singlefile else None
        readability = str(self.readability.relative_to(get_archive_directory())) if self.readability else None
        readability_txt = str(
            self.readability_txt.relative_to(get_archive_directory())) if self.readability_txt else None
        readability_json = str(
            self.readability_json.relative_to(get_archive_directory())) if self.readability_json else None
        screenshot = str(self.screenshot.relative_to(get_archive_directory())) if self.screenshot else None
        return f'<ArchiveFiles {singlefile=} {readability=} {readability_txt=} {readability_json=} {screenshot=}>'


def get_archive_directory() -> pathlib.Path:
    archive_destination = get_wrolpi_config().archive_destination
    variables = dict(domain='', year='', month='', day='')
    archive_destination = archive_destination % variables
    archive_directory = get_media_directory() / archive_destination
    return archive_directory


# File names include domain and datetime.
MAXIMUM_ARCHIVE_FILE_CHARACTER_LENGTH = 200


def get_new_archive_files(url: str, title: Optional[str], destination: pathlib.Path = None) -> ArchiveFiles:
    """Create a list of archive files using a shared name schema.  Raise an error if any of them exist.

    Args:
        url: The URL being archived (used to derive domain if no destination)
        title: Title for the archive files
        destination: Optional directory to save files to. If provided, files go here instead of archive/<domain>
    """
    domain = extract_domain(url)
    if destination:
        directory = destination
    else:
        # Fallback to archive/<domain>/ when no destination provided
        directory = get_archive_directory() / domain
    directory.mkdir(parents=True, exist_ok=True)

    # Use the configured file format template
    title = title or 'NA'
    title = title[:MAXIMUM_ARCHIVE_FILE_CHARACTER_LENGTH]
    prefix = format_archive_filename(title, domain=domain)

    # Handle subdirectories in the format (e.g., "%(download_year)s/%(title)s")
    if '/' in prefix:
        # Prefix includes subdirectories, create them relative to base directory
        full_path = directory / prefix
        full_path.parent.mkdir(parents=True, exist_ok=True)
        singlefile_path = full_path.with_suffix('.html')
        readability_path = full_path.parent / f'{full_path.name}.readability.html'
        readability_txt_path = full_path.parent / f'{full_path.name}.readability.txt'
        readability_json_path = full_path.parent / f'{full_path.name}.readability.json'
        screenshot_path = full_path.with_suffix('.png')
    else:
        singlefile_path = directory / f'{prefix}.html'
        readability_path = directory / f'{prefix}.readability.html'
        readability_txt_path = directory / f'{prefix}.readability.txt'
        readability_json_path = directory / f'{prefix}.readability.json'
        screenshot_path = directory / f'{prefix}.png'

    paths = (singlefile_path, readability_path, readability_txt_path, readability_json_path, screenshot_path)

    for path in paths:
        if path.exists():
            raise FileExistsError(f'New archive file already exists: {path}')

    archive_files = ArchiveFiles(
        singlefile_path,
        readability_path,
        readability_txt_path,
        readability_json_path,
        screenshot_path,
    )
    return archive_files


ARCHIVE_TIMEOUT = Seconds.minute * 10  # Wait at most 10 minutes for response.


async def request_archive(url: str, singlefile: str = None) -> Tuple[str, Optional[dict], Optional[str]]:
    """Send a request to the archive service to archive the URL."""
    logger.info(f'Sending archive request to archive service: {url}')

    data = dict(url=url, singlefile=singlefile)
    try:
        async with aiohttp_post(f'{ARCHIVE_SERVICE}/json', json_=data, timeout=ARCHIVE_TIMEOUT) as response:
            status = response.status
            contents = await response.json()
        if contents and (error := contents.get('error')):
            # Report the error from the archive service.
            raise Exception(f'Received error from archive service: {error}')

        readability = contents.get('readability')
        # Compressed base64
        singlefile = contents['singlefile']
        screenshot = contents['screenshot']

        logger.debug(f'archive request status code {status}')
    except Exception as e:
        logger.error('Error when requesting archive', exc_info=e)
        raise

    if not (screenshot or singlefile or readability):
        raise Exception('singlefile response was empty!')

    if not readability:
        logger.info(f'Failed to get readability for {url=}')

    # Decode and decompress.
    singlefile = base64.b64decode(singlefile)
    singlefile = gzip.decompress(singlefile)
    singlefile = singlefile.decode()

    if not screenshot:
        logger.info(f'Failed to get screenshot for {url=}')
    else:
        # Decode and decompress.
        screenshot = base64.b64decode(screenshot)
        screenshot = gzip.decompress(screenshot)

    return singlefile, readability, screenshot


async def request_screenshot(url: str, singlefile_path: pathlib.Path) -> Optional[bytes]:
    """Send a request to the archive service to generate a screenshot from the singlefile."""
    logger.info(f'Sending screenshot request to archive service: {url}')

    # Read, compress, and encode the singlefile
    singlefile_contents = singlefile_path.read_bytes()
    singlefile_compressed = gzip.compress(singlefile_contents)
    singlefile_b64 = base64.b64encode(singlefile_compressed).decode()

    data = dict(url=url, singlefile=singlefile_b64)
    try:
        async with aiohttp_post(f'{ARCHIVE_SERVICE}/screenshot', json_=data, timeout=ARCHIVE_TIMEOUT) as response:
            status = response.status
            contents = await response.json()
        if contents and (error := contents.get('error')):
            # Report the error from the archive service.
            raise Exception(f'Received error from archive service: {error}')

        # Compressed base64
        screenshot = contents.get('screenshot')
        if not screenshot:
            logger.warning(f'Failed to get screenshot for {url=}')
            return None

        logger.debug(f'screenshot request status code {status}')
    except Exception as e:
        logger.error('Error when requesting screenshot', exc_info=e)
        raise

    # Decode and decompress.
    screenshot = base64.b64decode(screenshot)
    screenshot = gzip.decompress(screenshot)

    return screenshot


async def model_archive_result(url: str, singlefile: str, readability: dict, screenshot: bytes,
                               destination: pathlib.Path = None) -> Archive:
    """
    Convert results from ArchiveDownloader into real files.  Create Archive record.

    Args:
        url: The URL that was archived
        singlefile: The HTML content from SingleFile
        readability: The readability extraction results
        screenshot: The screenshot bytes
        destination: Optional directory to save files to. If provided, files go here instead of archive/<domain>
    """
    readability = readability.copy() if readability else readability
    # First try to get the title from Readability.
    title = readability.get('title') if readability else None

    if not title and singlefile:
        # Try to get the title ourselves from the HTML.
        title = get_title_from_html(singlefile, url=url)
        if readability:
            # Readability could not find title, lets use ours.
            readability['title'] = title

    archive_files = get_new_archive_files(url, title, destination=destination)

    if readability:
        # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
        with archive_files.readability.open('wt') as fp:
            content = format_html_string(readability.pop('content'))
            fp.write(content)
        with archive_files.readability_txt.open('wt') as fp:
            readability_txt = readability.pop('textContent')
            readability_txt = split_lines_by_length(readability_txt)
            fp.write(readability_txt)
    else:
        # No readability was returned, so there are no files.
        archive_files.readability_txt = archive_files.readability = None

    # Store the single-file HTML in its own file.
    singlefile = format_html_string(singlefile)
    archive_files.singlefile.write_text(singlefile)

    if screenshot:
        archive_files.screenshot.write_bytes(screenshot)
    else:
        archive_files.screenshot = None

    # Always write a JSON file that contains at least the URL.
    readability = readability or {}
    readability['url'] = url
    with archive_files.readability_json.open('wt') as fp:
        json.dump(readability, fp, indent=2, sort_keys=True)

    # Create any File models that we can, index them all.
    paths = (
        archive_files.singlefile, archive_files.readability, archive_files.readability_json,
        archive_files.readability_txt,
        archive_files.screenshot)
    paths = list(filter(None, paths))

    with get_db_session(commit=True) as session:
        archive = Archive.from_paths(session, *paths)
        archive.file_group.download_datetime = now()
        archive.url = url
        archive.collection = get_or_create_domain_collection(session, url)
        archive.flush()

    return archive


def detect_domain_directory(session: Session, collection: Collection) -> Optional[pathlib.Path]:
    """
    Detect if all archives for a domain collection share a common directory.

    Args:
        collection: The domain collection to analyze
        session: Database session

    Returns:
        Path (relative to media directory) if all archives share a common directory within archive media directory.
        None if archives are scattered across different directories or if collection has no archives.
    """
    if collection.kind != 'domain':
        return None

    # Query all archives for this domain collection
    archives = session.query(Archive).filter_by(collection_id=collection.id).all()

    if not archives:
        # No archives yet, can't determine directory
        return None

    # Get all archive file paths
    paths = []
    for archive in archives:
        if archive.file_group and archive.file_group.primary_path:
            paths.append(pathlib.Path(archive.file_group.primary_path))

    if not paths:
        return None

    # Find common ancestor directory
    # Start with the first path's parent directory
    common_dir = paths[0].parent

    # Check if all other paths are under this directory
    for path in paths[1:]:
        try:
            # Check if path is relative to common_dir
            path.relative_to(common_dir)
        except ValueError:
            # Path is not under common_dir, find the common ancestor
            # Walk up until we find a common parent
            while common_dir != common_dir.parent:  # Stop at root
                try:
                    path.relative_to(common_dir)
                    break  # Found common ancestor
                except ValueError:
                    common_dir = common_dir.parent

    # Check if common directory is within the media directory
    media_dir = get_media_directory()
    try:
        relative_path = common_dir.relative_to(media_dir)
    except ValueError:
        # Common directory is outside media directory
        return None

    # Check if it's within the archive directory structure
    archive_base = get_archive_directory()
    try:
        archive_base.relative_to(media_dir)  # Verify archive_base is under media_dir
        common_dir.relative_to(archive_base.parent)  # Verify common_dir is under archive structure
    except ValueError:
        # Not in the archive directory structure
        return None

    logger.debug(f'Detected directory for domain {collection.name}: {relative_path}')
    return relative_path


def update_domain_directories(session: Session = None) -> int:
    """
    One-time update to detect and set directories for existing domain collections.

    This should be run once to fix domain collections that were created without directories
    but have all their archives in a common location.

    Args:
        session: Database session

    Returns:
        Number of domain collections updated
    """
    if session is None:
        with get_db_session(commit=True) as session:
            return update_domain_directories(session)

    # Find all domain collections without directories
    collections = session.query(Collection).filter_by(kind='domain', directory=None).all()

    updated_count = 0
    for collection in collections:
        detected_dir = detect_domain_directory(session, collection)
        if detected_dir:
            collection.directory = detected_dir
            session.flush([collection])
            updated_count += 1
            logger.info(f'Updated domain {collection.name} with directory: {detected_dir}')

    session.commit()
    logger.info(f'Updated {updated_count} domain collection(s) with auto-detected directories')
    return updated_count


def get_or_create_domain_collection(session: Session, url, directory: pathlib.Path = None) -> Collection:
    """
    Get or create the domain Collection for this archive.

    Args:
        session: Database session
        url: URL of the archive
        directory: Optional directory to restrict this domain collection.
                  If None, creates unrestricted collection (default).
                  If provided, archives will be placed in this directory and collection can be tagged.

    Returns:
        Collection with kind='domain' for the domain extracted from the URL
    """
    domain_name = extract_domain(url)

    # Try to find existing domain collection
    collection = session.query(Collection).filter_by(
        name=domain_name,
        kind='domain'
    ).one_or_none()

    if not collection:
        # Create new domain collection
        collection = Collection(
            name=domain_name,
            kind='domain',
            directory=directory,  # Can be None (unrestricted) or a Path (restricted)
        )
        session.add(collection)
        session.flush()
        # Trigger domain config save for new domain
        save_domains_config.activate_switch()
        if directory:
            logger.info(f'Created domain collection with directory: {domain_name} -> {directory}')
        else:
            logger.info(f'Created unrestricted domain collection: {domain_name}')

    # Auto-detect directory if not explicitly set and collection doesn't have one
    if not directory and not collection.directory:
        detected_dir = detect_domain_directory(session, collection)
        if detected_dir:
            collection.directory = detected_dir
            session.flush()
            # Trigger domain config save when directory is auto-detected
            save_domains_config.activate_switch()
            logger.info(f'Auto-detected directory for domain {domain_name}: {detected_dir}')

    return collection


def link_domain_and_downloads(session: Session):
    """Associate any Download related to a Domain Collection.

    Downloads are linked to Collections (via collection_id).
    This function finds Domain Collections and links their Downloads.

    Matching criteria:
    - Recurring downloads whose destination is within the domain collection's directory (including subdirectories)
    - RSS downloads with sub_downloader='archive' (matched by URL domain)
    """
    # Local import to avoid circular import: downloader -> archive -> downloader
    from wrolpi.downloader import Download

    # Only Downloads with a frequency can be a Collection Download.
    downloads = list(session.query(Download).filter(Download.frequency.isnot(None)).all())

    # Get domain collections that have a directory
    domain_collections = session.query(Collection).filter(
        Collection.kind == 'domain',
        Collection.directory.isnot(None)
    ).all()

    need_commit = False

    # Match downloads by destination directory (including subdirectories)
    downloads_with_destination = [d for d in downloads if (d.settings or {}).get('destination')]
    for collection in domain_collections:
        # Ensure directory ends with / for proper prefix matching
        directory = str(collection.directory)
        directory_prefix = directory if directory.endswith('/') else directory + '/'
        for download in downloads_with_destination:
            dest = download.settings['destination']
            # Match if destination equals directory or is a subdirectory
            if not download.collection_id and (dest == directory or dest.startswith(directory_prefix)):
                download.collection_id = collection.id
                need_commit = True

    # Match RSS downloads with archive sub_downloader by URL domain
    rss_archive_downloads = [
        d for d in downloads
        if d.downloader == 'rss' and d.sub_downloader == 'archive' and not d.collection_id
    ]
    for download in rss_archive_downloads:
        # Extract domain from the RSS URL and find matching domain collection
        domain_name = extract_domain(download.url)
        collection = session.query(Collection).filter_by(
            name=domain_name,
            kind='domain'
        ).one_or_none()
        if collection:
            download.collection_id = collection.id
            need_commit = True

    if need_commit:
        session.commit()


SINGLEFILE_URL_EXTRACTOR = re.compile(r'Page saved with SingleFile \s+url: (http.+?)\n')


def get_url_from_singlefile(html: bytes | str) -> str:
    """Extract URL from SingleFile contents."""
    html = html.decode() if isinstance(html, bytes) else html
    if SINGLEFILE_HEADER not in html:
        raise RuntimeError(f'Not a singlefile!')

    url, = SINGLEFILE_URL_EXTRACTOR.findall(html)
    url = url.strip()

    if not url.startswith('http'):
        raise RuntimeError('URL did not start with http')

    # Verify that the URL can be parsed.
    urlparse(url)
    return url


@dataclass
class ArticleMetadata:
    title: str = None
    published_datetime: datetime = None
    modified_datetime: datetime = None
    description: str = None
    author: str = None


def parse_article_html_metadata(html: Union[bytes, str], assume_utc: bool = True) -> ArticleMetadata:
    """
    Read the data from the <meta> tags, extract any data relevant to the article.  This function also reads the
    <script type="application/ld+json"> data.
    """
    metadata = ArticleMetadata()

    soup = get_html_soup(html)

    def get_meta_by_property(prop: str):
        return soup.find('meta', attrs={'property': prop})

    # <meta content="2023-10-18T04:52:23+00:00" property="article:published_time"/>
    if meta_published_time := get_meta_by_property('article:published_time'):
        metadata.published_datetime = dates.strpdate(meta_published_time.attrs['content'])
    # <meta name="article.published" content="2023-04-04T21:52:00.000Z">
    if meta_article_published := soup.find('meta', attrs={'name': 'article.published'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(
            meta_article_published.attrs['content'])
    # <meta itemprop="datePublished" content="2023-04-04T21:52:00.000Z">
    if meta_item_published := soup.find('meta', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(
            meta_item_published.attrs['content'])
    # <time itemprop="datePublished" datetime="2023-08-25">
    if time := soup.find('time', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(time.attrs['datetime'])
    # <abbr class="published" itemprop="datePublished" title="2022-03-17T03:00:00-07:00">March 17, 2022</abbr>
    if abbr := soup.find('abbr', attrs={'itemprop': 'datePublished'}):
        metadata.published_datetime = metadata.published_datetime or dates.strpdate(abbr.attrs['title'])

    # <meta content="2023-10-19T05:53:24+00:00" property="article:modified_time"/>
    if meta_modified_time := get_meta_by_property('article:modified_time'):
        metadata.modified_datetime = dates.strpdate(meta_modified_time.attrs['content'])
    # <meta name="article.updated" content="2023-04-04T21:52:00.000Z">
    if meta_article_updated := soup.find('meta', attrs={'name': 'article.updated'}):
        metadata.modified_datetime = metadata.modified_datetime or dates.strpdate(meta_article_updated.attrs['content'])

    # <meta content="The Title" property="og:title"/>
    if meta_title := get_meta_by_property('og:title'):
        metadata.title = meta_title.attrs['content']

    # <meta name="author" content="Author Name"/>
    if meta_author := soup.find('meta', attrs={'name': 'author'}):
        metadata.author = meta_author.attrs['content']
    # <meta content="Billy" property="article:author"/>
    if meta_property_author := get_meta_by_property('article:author'):
        metadata.author = metadata.author or meta_property_author.attrs['content']
    # <a href="https://example.com" rel="author">
    if link_author := soup.find('a', attrs={'rel': 'author'}):
        metadata.author = metadata.author or link_author.text.strip()

    # <script class="sf-hidden" type="application/ld+json">
    if (ld_script := soup.find('script', attrs={'type': 'application/ld+json'})) and ld_script.contents:
        try:
            schema = json.loads(ld_script.text)
        except json.decoder.JSONDecodeError:
            # Was not valid JSON.
            schema = None
        if isinstance(schema, dict) and (context := schema.get('@context')) and '://schema.org' in context:
            # Found https://schema.org/
            if headline := schema.get('headline'):
                metadata.title = metadata.title or headline
            if datePublished := schema.get('datePublished'):
                try:
                    metadata.published_datetime = metadata.published_datetime or dates.strpdate(datePublished)
                except InvalidDatetime as e:
                    # Invalid date, ignore.
                    logger.error('Invalid datetime', exc_info=e)
                    if PYTEST:
                        raise
            if dateModified := schema.get('dateModified'):
                try:
                    metadata.modified_datetime = metadata.modified_datetime or dates.strpdate(dateModified)
                except InvalidDatetime as e:
                    # Invalid date, ignore.
                    logger.error('Invalid datetime', exc_info=e)
                    if PYTEST:
                        raise
            if description := schema.get('description'):
                metadata.description = description
            if author := schema.get('author'):
                if isinstance(author, list) and len(author) >= 1:
                    # Use the first Author.
                    author = author[0]

                if isinstance(author, dict):
                    author = author.get('name') or author

                if isinstance(author, str):
                    metadata.author = author
                else:
                    logger.warning(f'Unable to parse author schema: {author}')
            elif authors := schema.get('authors'):
                # Use the first Author.
                author = authors[0]

                if isinstance(author, dict):
                    author = author.get('name') or author

                if isinstance(author, str):
                    metadata.author = author
                else:
                    logger.warning(f'Unable to parse author schema: {author}')

    # Assume UTC if no timezone.
    if metadata.published_datetime and not metadata.published_datetime.tzinfo and assume_utc:
        logger.debug(f'Assuming UTC for {metadata.published_datetime=}')
        metadata.published_datetime = metadata.published_datetime.replace(tzinfo=pytz.UTC)
    if metadata.modified_datetime and not metadata.modified_datetime.tzinfo and assume_utc:
        logger.debug(f'Assuming UTC for {metadata.modified_datetime=}')
        metadata.modified_datetime = metadata.modified_datetime.replace(tzinfo=pytz.UTC)

    return metadata


def get_archive(session: Session, archive_id: int) -> Archive:
    """Get an Archive."""
    archive = Archive.find_by_id(session, archive_id)
    archive.file_group.set_viewed()
    return archive


def delete_archives(*archive_ids: List[int]):
    """Delete an Archive and all of its files."""
    with get_db_session(commit=True) as session:
        archives: List[Archive] = list(session.query(Archive).filter(Archive.id.in_(archive_ids)))
        if not archives:
            raise UnknownArchive(f'Unknown Archives with IDs: {", ".join(map(str, archive_ids))}')

        # Delete any files associated with this URL.
        for archive in archives:
            archive.delete()


def archive_strftime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d-%H-%M-%S')


ARCHIVE_MATCHER = re.compile(r'\d{4}(-\d\d){5}_.*$')
SINGLEFILE_HEADER = '''<!--
 Page saved with SingleFile'''


def is_singlefile_file(path: pathlib.Path) -> bool:
    """
    Archive singlefile files are expected to start with the following: %Y-%m-%d-%H-%M-%S
    they must end with .html, but never with .readability.html.
    """
    if not path.is_file() or \
            path.suffix.lower() != '.html' or \
            path.name.lower().endswith('.readability.html') or \
            path.stat().st_size == 0:
        return False
    if ARCHIVE_MATCHER.match(path.name):
        # A file name matching exactly the Archive format from WROLPi should always be an Archive.
        return True
    with path.open('rt') as fh:
        # Lastly, try to read the header of this HTML file.  Read a large part of the head because URLs can be long.
        header = fh.read(1000)
        if SINGLEFILE_HEADER in header:
            return True
    return False


def get_domains():
    """
    Get all domain collections with their archive statistics.

    This is a thin wrapper around Collection queries that adds archive-specific statistics.
    Returns a list of dicts with collection id, domain name, url_count, and total size.
    """
    with get_db_session() as session:
        # Query all domain collections with archive statistics in a single query
        # This uses ORM for better maintainability while keeping performance
        query = (
            session.query(
                Collection.id,
                Collection.name.label('domain'),
                func.count(Archive.id).label('url_count'),
                func.sum(FileGroup.size).cast(BigInteger).label('size')
            )
            .outerjoin(Archive, Collection.id == Archive.collection_id)
            .outerjoin(FileGroup, FileGroup.id == Archive.file_group_id)
            .filter(Collection.kind == 'domain')
            .group_by(Collection.id, Collection.name)
            .order_by(Collection.name)
        )

        domains = [
            {
                'id': row.id,
                'domain': row.domain,
                'url_count': row.url_count or 0,
                'size': row.size or 0,
            }
            for row in query.all()
        ]

        return domains


def get_domain(domain_id: int) -> dict:
    """
    Get a single domain collection by ID with its archive statistics.

    Returns a dict with collection details including id, domain name, url_count, size,
    tag_name, directory (relative to media directory), and description.

    Raises UnknownArchive if domain not found.
    """
    # Get the collection using find_by_id
    with get_db_session() as session:
        try:
            collection = Collection.find_by_id(session, domain_id)
        except Exception:
            # Collection.find_by_id raises UnknownCollection, but we want UnknownArchive
            raise UnknownArchive(f"Domain collection with ID {domain_id} not found")

        if collection.kind != 'domain':
            raise UnknownArchive(f"Collection {domain_id} is not a domain")

        # Get base domain data from __json__()
        domain_data = collection.__json__()

    # Get archive statistics for this domain
    with get_db_curs() as curs:
        stmt = '''
               SELECT COUNT(a.id) AS url_count, SUM(fg.size)::BIGINT AS size
               FROM archive a
                        LEFT JOIN file_group fg on fg.id = a.file_group_id
               WHERE a.collection_id = %(domain_id)s
               '''
        curs.execute(stmt, {'domain_id': domain_id})
        stats = dict(curs.fetchone())

    # Enhance with archive stats
    domain_data['url_count'] = stats['url_count'] or 0
    domain_data['size'] = stats['size'] or 0

    # Use 'domain' key for domain collections instead of 'name'
    domain_data['domain'] = domain_data.pop('name')

    return domain_data


ARCHIVE_ORDERS = {
    # Sometimes we don't have a published_datetime.  This is equivalent to COALESCE(fg.published_datetime, fg.download_datetime)
    'published_datetime': (date := 'fg.effective_datetime ASC NULLS LAST'),
    '-published_datetime': (_date := 'fg.effective_datetime DESC NULLS LAST'),
    'published_modified_datetime': f'fg.published_modified_datetime ASC NULLS LAST, {date}',
    '-published_modified_datetime': f'fg.published_modified_datetime DESC NULLS LAST, {_date}',
    'download_datetime': 'fg.download_datetime ASC NULLS LAST',
    '-download_datetime': 'fg.download_datetime DESC NULLS LAST',
    'rank': f'2 DESC, {_date}',
    '-rank': f'2 ASC, {date}',
    'size': 'fg.size ASC, LOWER(fg.primary_path) ASC',
    '-size': 'fg.size DESC NULLS LAST, LOWER(fg.primary_path) DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
}
ORDER_GROUP_BYS = {
    'published_datetime': 'fg.effective_datetime',
    '-published_datetime': 'fg.effective_datetime',
    'published_modified_datetime': 'fg.published_modified_datetime, fg.published_datetime, fg.download_datetime',
    '-published_modified_datetime': 'fg.published_modified_datetime, fg.published_datetime, fg.download_datetime',
    'download_datetime': 'fg.download_datetime',
    '-download_datetime': 'fg.download_datetime',
    'rank': 'fg.published_datetime, fg.download_datetime',
    '-rank': 'fg.published_datetime, fg.download_datetime',
    'size': 'fg.size, fg.published_datetime, fg.primary_path',
    '-size': 'fg.size, fg.published_datetime, fg.primary_path',
    'viewed': 'fg.viewed',
    '-viewed': 'fg.viewed',
}
NO_NULL_ORDERS = {
    'viewed': 'fg.viewed IS NOT NULL',
    '-viewed': 'fg.viewed IS NOT NULL',
    'published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
    '-published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
}


def search_archives(search_str: str, domain: str, limit: int, offset: int, order: str, tag_names: List[str],
                    headline: bool = False) \
        -> Tuple[List[dict], int]:
    # Always filter FileGroups to Archives.
    wheres = []
    group_by = 'fg.effective_datetime, a.file_group_id'

    params = dict(search_str=search_str, offset=int(offset), limit=int(limit))
    order_by = ARCHIVE_ORDERS['-published_datetime']

    select_columns = ''
    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select_columns = 'ts_rank(fg.textsearch, websearch_to_tsquery(%(search_str)s)) AS rank,' \
                         ' COUNT(*) OVER() AS total'
        wheres.append('fg.textsearch @@ websearch_to_tsquery(%(search_str)s)')
        params['search_str'] = search_str
        group_by = f'{group_by}, rank'

    if order:
        try:
            order_by = ARCHIVE_ORDERS[order]
            group_by = f'{group_by}, {ORDER_GROUP_BYS[order]}'
        except KeyError:
            raise InvalidOrderBy(f'Invalid order byy {order}')
        if order in NO_NULL_ORDERS:
            wheres.append(NO_NULL_ORDERS[order])

    wheres, params = tag_append_sub_select_where(wheres, params, tag_names)

    if search_str and headline:
        headline = ''',
                ts_headline(fg.title, websearch_to_tsquery(%(search_str)s)) AS "title_headline",
                ts_headline(fg.b_text, websearch_to_tsquery(%(search_str)s)) AS "b_headline",
                ts_headline(fg.c_text, websearch_to_tsquery(%(search_str)s)) AS "c_headline",
                ts_headline(fg.d_text, websearch_to_tsquery(%(search_str)s)) AS "d_headline"'''
        group_by = f'{group_by}, title_headline, b_headline, c_headline, d_headline'
    else:
        headline = ''

    if domain:
        params['domain'] = domain
        # Use LIMIT 1 to handle potential duplicate domain collections with the same name
        wheres.append(
            "a.collection_id = (select id from collection where collection.name = %(domain)s and collection.kind = 'domain' LIMIT 1)")

    select_columns = f", {select_columns}" if select_columns else ""
    wheres = '\n AND '.join(wheres)
    where = f'WHERE\n{wheres}' if wheres else ''
    stmt = f'''
            SELECT
                a.file_group_id AS id, -- always get `file_group.id` for `handle_file_group_search_results`
                COUNT(*) OVER() AS total
                {select_columns}
                {headline}
            FROM archive a
            LEFT JOIN file_group fg ON fg.id = a.file_group_id
            {where}
            GROUP BY {group_by}
            ORDER BY {order_by}
            OFFSET %(offset)s LIMIT %(limit)s
        '''.strip()
    logger.debug(stmt, params)

    results, total = handle_file_group_search_results(stmt, params)
    return results, total


async def search_domains_by_name(session: Session, name: str, limit: int = 5) -> List[dict]:
    """
    Search for domain collections by name.

    Args:
        session: Database session
        name: Search string to match against collection names
        limit: Maximum number of results to return

    Returns:
        List of domain dicts matching the search (in old Domain format for backward compatibility)
    """
    collections = session.query(Collection) \
        .filter(Collection.kind == 'domain') \
        .filter(Collection.name.ilike(f'%{name}%')) \
        .order_by(asc(Collection.name)) \
        .limit(limit) \
        .all()

    # Convert to old Domain format for backward compatibility
    archive_dir = get_archive_directory()
    return [
        {
            'id': c.id,
            'domain': c.name,
            # Domain collections can have explicit directories or use default archive path
            'directory': get_relative_to_media_directory(c.directory) if c.directory else str(
                (archive_dir / c.name).relative_to(get_media_directory())),
        }
        for c in collections
    ]


async def html_to_readability(html: str | bytes, url: str, timeout: int = 120):
    """Extract the readability dict from the provided HTML."""
    with tempfile.NamedTemporaryFile('wb', suffix='.html') as singlefile_file:
        singlefile_file.write(html.encode() if isinstance(html, str) else html)
        singlefile_file.flush()
        os.fsync(singlefile_file.fileno())

        cmd = ('/usr/bin/nice', '-n15',  # Nice above map importing, but very low priority.
               READABILITY_BIN, singlefile_file.name, shlex.quote(url))
        # Docker containers may not have this directory. But, this directory is necessary on RPi.
        cwd = '/home/wrolpi' if os.path.isdir('/home/wrolpi') else None
        result = await run_command(cmd, cwd=cwd, timeout=timeout)

        logger.debug(f'readability for {url} exited with {result.return_code}')
        stdout, stderr = result.stdout.decode(), result.stderr.decode()
        if result.return_code == 0:
            if not stdout:
                raise RuntimeError('readability stdout was empty')
            try:
                readability = json.loads(stdout)
            except TypeError or JSONDecodeError:
                # JSON was invalid.
                e = ChildProcessError(stdout if stdout else 'No stdout')
                if stderr:
                    e = ChildProcessError(stderr)
                raise RuntimeError(f'Failed to extract readability from {url}') from e
            logger.debug(f'done readability for {url}')
            return readability
        else:
            logger.error(f'Failed to extract readability for {url}')
            e = ChildProcessError(stdout if stdout else 'No stdout')
            if stderr:
                e = ChildProcessError(stderr)
            raise RuntimeError(f'Failed to extract readability for {url} got {result.return_code}') from e


async def singlefile_to_archive(singlefile: bytes, destination: pathlib.Path = None) -> Archive:
    """
    Convert a SingleFile to an Archive.

    This is done by extracting readability, creating a screenshot, then attaching them to an Archive/FileGroup.

    Args:
        singlefile: The SingleFile HTML bytes
        destination: Optional directory to save files to. If provided, files go here instead of archive/<domain>
    """
    # Get URL first because it does some simple checking of `singlefile`
    url = get_url_from_singlefile(singlefile)
    singlefile = singlefile.encode() if isinstance(singlefile, str) else singlefile

    if DOCKERIZED:
        # Perform the archive in the Archive docker container.  (Typically in the development environment).
        singlefile = base64.b64encode(singlefile).decode()
        logger.debug(f'singlefile_to_archive sending to archive service: {url}')
        singlefile, readability, screenshot = await request_archive(url, singlefile=singlefile)
    else:
        # JSON from readability-extractor
        readability = dict()
        try:
            logger.debug(f'singlefile_to_archive extracting readability: {url}')
            readability = await html_to_readability(singlefile, url)
        except RuntimeError as e:
            logger.error(f'Failed to extract readability from: {url}', exc_info=e)

        screenshot = None
        try:
            logger.debug(f'singlefile_to_archive creating screenshot: {url}')
            screenshot = html_screenshot(singlefile)
        except Exception as e:
            logger.error(f'Failed to extract screenshot from: {url}', exc_info=e)

    logger.trace(f'singlefile_to_archive modeling: {url}')
    archive: Archive = await model_archive_result(url, singlefile, readability, screenshot, destination=destination)
    return archive


async def generate_archive_screenshot(archive_id: int) -> pathlib.Path:
    """
    Generate a screenshot for an existing Archive that doesn't have one.
    If the Archive already has a screenshot, verify it exists and ensure it's tracked in the FileGroup.

    Returns the path to the generated screenshot.

    Raises:
        ValueError: If Archive has no singlefile
        RuntimeError: If screenshot generation fails
    """
    with get_db_session() as session:
        archive = Archive.find_by_id(session, archive_id)

        if not archive.singlefile_path:
            raise ValueError(f'Cannot generate screenshot for Archive {archive_id}: no singlefile')

        # Check if screenshot already exists
        if archive.screenshot_path:
            # Verify the screenshot file actually exists on disk
            if archive.screenshot_path.is_file():
                logger.info(f'Archive {archive_id} already has a screenshot, ensuring it is tracked')
                # Ensure the screenshot is tracked in FileGroup.files and FileGroup.data
                with get_db_session(commit=True) as tracking_session:
                    archive = Archive.find_by_id(tracking_session, archive_id)
                    file_group = archive.file_group
                    # append_files uses unique_by_predicate, so this is safe even if already tracked
                    file_group.append_files(archive.screenshot_path)

                    # Also update FileGroup.data (same pattern as set_screenshot)
                    data = dict(file_group.data) if file_group.data else {}
                    data['screenshot_path'] = str(archive.screenshot_path)
                    file_group.data = data

                    archive.validate()
                    tracking_session.flush()
                return archive.screenshot_path
            else:
                logger.warning(f'Archive {archive_id} has screenshot_path but file does not exist, regenerating')

        singlefile_path = archive.singlefile_path
        url = archive.file_group.url

    # Request screenshot from Archive docker service or generate locally
    if DOCKERIZED:
        logger.debug(f'Requesting screenshot from archive service for Archive {archive_id}')
        screenshot_bytes = await request_screenshot(url, singlefile_path)
    else:
        logger.debug(f'Generating screenshot locally for Archive {archive_id}')
        singlefile_contents = singlefile_path.read_bytes()
        screenshot_bytes = html_screenshot(singlefile_contents)

    if not screenshot_bytes:
        raise RuntimeError(f'Failed to generate screenshot for Archive {archive_id}')

    # Save screenshot next to singlefile with same naming pattern
    screenshot_path = singlefile_path.with_suffix('.png')
    screenshot_path.write_bytes(screenshot_bytes)
    logger.info(f'Generated screenshot for Archive {archive_id}: {screenshot_path}')

    # Update the Archive to include the new screenshot file
    with get_db_session(commit=True) as session:
        archive = Archive.find_by_id(session, archive_id)
        archive.set_screenshot(screenshot_path)
        session.flush()

    return screenshot_path
