import base64
import gzip
import io
import json
import os
import pathlib
import re
import secrets
import shlex
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
from typing import Optional, Tuple, List, Union, Dict, Set
from urllib.parse import urlparse

import pytz
from sqlalchemy import asc
from sqlalchemy.orm import Session

from modules.archive.models import Archive, MATCH_DATE, parse_singlefile_saved_date, read_singlefile_header
from wrolpi import dates
from wrolpi import fts
from wrolpi.cmd import READABILITY_BIN, run_command
from wrolpi.collections import Collection
from wrolpi.common import get_media_directory, get_relative_to_media_directory, logger, extract_domain, \
    escape_file_name, aiohttp_post, format_html_string, split_lines_by_length, get_html_soup, get_title_from_html, \
    get_wrolpi_config, html_screenshot, html_file_screenshot, ConfigFile, trim_file_name, chunks
from wrolpi.collections.models import validate_collection_directory
from wrolpi.config_import import ConfigSection, Unreadable, media_relative
from wrolpi.dates import now, Seconds
from wrolpi.db import get_db_session, session_curs
from wrolpi.errors import UnknownArchive, InvalidOrderBy, InvalidDatetime
from wrolpi.events import Events
from wrolpi.files.lib import handle_file_group_search_results, cached_search_total, \
    search_filter_cache_key, count_file_groups, get_kv_value, set_kv_value
from wrolpi.files.models import FileGroup
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.tags import Tag, tag_append_sub_select_where, unknown_tag_names
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)

__all__ = ['DomainsConfig', 'domains_config', 'get_domains_config', 'save_domains_config', 'import_domains_config']

ARCHIVE_SERVICE = 'http://archive:8080'


def _domain_row(description, directory, tag_name, file_format) -> dict:
    return dict(
        description=description or None,
        directory=media_relative(directory) if directory else None,
        tag_name=tag_name or None,
        file_format=file_format or None,
    )


class DomainsSection(ConfigSection):
    """domains.yaml's domain Collections, keyed by name.  (Their Downloads are linked after the import, see
    `domain_download_links`.)"""
    name = 'domains'

    def file_rows(self, config: dict) -> Tuple[Dict[str, dict], Set[str]]:
        rows, invalid = dict(), set()
        for position, data in enumerate(config.get('collections') or []):
            name = data.get('name') if isinstance(data, dict) else None
            if not name or not isinstance(name, str):
                logger.error(f'Domain collection at index {position} has no name, skipping: {data!r}')
                # Counted as skipped (see `Unreadable`).
                invalid.add(Unreadable(position))
                continue
            try:
                if not Collection.is_valid_domain_name(name):
                    raise ValueError(f"Invalid domain name {name!r} (must contain at least one '.' and not start/end"
                                     f" with '.')")
                if name in rows:
                    raise ValueError(f'Another entry has the same domain: {name!r}')
                directory = validate_collection_directory(data['directory']) if data.get('directory') else None
                rows[name] = _domain_row(data.get('description'), directory, data.get('tag_name'),
                                         data.get('file_format'))
            except Exception as e:
                logger.error(f'Skipping invalid domain collection at index {position}', exc_info=e)
                invalid.add(name)
        return rows, invalid

    def db_rows(self, session: Session) -> Dict[str, dict]:
        query = session.query(Collection.name, Collection.description, Collection.directory, Tag.name,
                              Collection.file_format) \
            .outerjoin(Tag, Tag.id == Collection.tag_id) \
            .filter(Collection.kind == 'domain')
        return {name: _domain_row(*values) for name, *values in query}

    def upsert(self, session: Session, rows: Dict[str, dict]):
        existing = {i.name: i for i in
                    session.query(Collection).filter(Collection.kind == 'domain', Collection.name.in_(list(rows)))}
        tags = {i.name: i for i in
                session.query(Tag).filter(Tag.name.in_(list({i['tag_name'] for i in rows.values()} - {None})))}
        for name, row in rows.items():
            if not (collection := existing.get(name)):
                logger.info(f'Creating domain collection {name!r}')
                collection = Collection(name=name, kind='domain')
                session.add(collection)
            collection.description = row['description']
            collection.directory = get_media_directory() / row['directory'] if row['directory'] else None
            collection.tag = tags.get(row['tag_name'])
            collection.file_format = row['file_format']
        session.flush()

    def delete(self, session: Session, keys: Set[str]):
        """A domain with Archives is reset to its default settings (a refresh of its Archives would re-create it,
        and deleting it would delete them); any other is deleted."""
        with_archives = {i for i, in session.query(Archive.collection_id).distinct()}
        for collection in session.query(Collection).filter(Collection.kind == 'domain',
                                                           Collection.name.in_(list(keys))):
            if collection.id in with_archives:
                logger.warning(f'Resetting domain collection {collection.name!r} which is not in the config, because'
                               f' it has archives')
                collection.description = collection.directory = collection.tag = collection.file_format = None
            else:
                logger.info(f'Deleting domain collection {collection.name!r} (no longer in config)')
                session.delete(collection)


@dataclass
class DomainsConfigValidator:
    """Validator for domains config file."""
    version: int = 0
    collections: List[dict] = field(default_factory=list)


# The fields a domains.yaml entry must have (see `DomainsSection`).
DOMAIN_FIELDS = dict(required=('name',), optional=('directory',))


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
    sections = (DomainsSection(),)
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

    def prepare(self, diffs: dict):
        """A Tag that no longer exists (it was removed) is dropped, and the config is saved without it.  A removed
        domain with Archives which is already reset (see `DomainsSection.delete`) is left as it is; one which is not
        is reset, and the config is saved with it."""
        diff = diffs['domains']
        if diff.removed:
            with get_db_session() as session:
                with_archives = {name for name, in session.query(Collection.name).join(
                    Archive, Archive.collection_id == Collection.id).filter(
                    Collection.kind == 'domain', Collection.name.in_(list(diff.removed))).distinct()}
            reset = _domain_row(None, None, None, None)
            for name in with_archives:
                if self.import_db_rows['domains'][name] == reset:
                    diff.removed.discard(name)
                else:
                    self._config_outdated = True

        rows = [*diff.added.values(), *diff.changed.values()]
        unknown = unknown_tag_names({i['tag_name'] for i in rows if i['tag_name']})
        for row in rows:
            if row['tag_name'] in unknown:
                logger.warning(f'Removing unknown Tag {row["tag_name"]!r} from a domain')
                row['tag_name'] = None
                self._config_outdated = True

    def import_config(self, file: pathlib.Path = None, send_events=False):
        self._config_outdated = False
        super().import_config(file, send_events)

    def after_import(self, diffs: dict):
        if self._config_outdated:
            self.background_dump.activate_switch()

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all domain collections from database to config file."""
        logger.info('Dumping domain collections to config')

        with get_db_session() as session:
            version = self.db_version_for_dump(session)
            # Get only domain collections, ordered by name
            collections = session.query(Collection).filter_by(kind='domain').order_by(Collection.name).all()

            # Use to_config to export each collection
            collections_data = [collection.to_config() for collection in collections]

        if not collections_data and self._config.get('collections'):
            logger.warning('Refusing to save empty domains config because domains exist in the config file!')
            return

        self._config['collections'] = collections_data
        self._config['version'] = version

        logger.info(f'Dumping {len(collections_data)} domain collections to config')
        self.save(file, send_events, overwrite)

    def preview_backup_import(self, backup_date: str, mode: str) -> dict:
        backup_file = self._get_backup_file(backup_date)
        backup_data = self.read_config_file(backup_file)
        current_data = self.read_config_file() if self.get_file().is_file() else dict(collections=[], version=0)

        backup_collections = self.backup_entries(backup_data, 'collections', backup_file, **DOMAIN_FIELDS)
        current_collections = self.backup_entries(current_data, 'collections', self.get_file(), **DOMAIN_FIELDS)

        # Identity key for domains is the directory (if present) or name
        def get_key(c):
            return c.get('directory') or c.get('name', '')

        current_keys = {get_key(c) for c in current_collections}
        backup_keys = {get_key(c) for c in backup_collections}

        add = []
        remove = []
        unchanged = 0

        for c in backup_collections:
            key = get_key(c)
            if key not in current_keys:
                add.append(dict(type='domain', name=c.get('name', ''), directory=c.get('directory', '')))
            else:
                unchanged += 1
        if mode == 'overwrite':
            current_key_to_coll = {get_key(c): c for c in current_collections}
            for key in sorted(current_keys - backup_keys):
                c = current_key_to_coll[key]
                remove.append(dict(type='domain', name=c.get('name', ''), directory=c.get('directory', '')))

        return dict(mode=mode, add=add, remove=remove, unchanged=unchanged)

    def import_backup(self, backup_date: str, mode: str, send_events: bool = False):
        self._preserve_current_config()
        import shutil
        backup_file = self._get_backup_file(backup_date)
        config_file = self.get_file()

        if mode == 'overwrite':
            config_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, config_file)
        elif mode == 'merge':
            backup_data = self.read_config_file(backup_file)
            current_data = self.read_config_file() if config_file.is_file() else dict(collections=[], version=0)

            def get_key(c):
                return c.get('directory') or c.get('name', '')

            current_collections = self.backup_entries(current_data, 'collections', config_file, **DOMAIN_FIELDS)
            backup_collections = self.backup_entries(backup_data, 'collections', backup_file, **DOMAIN_FIELDS)
            current_keys = {get_key(c) for c in current_collections}
            merged_collections = list(current_collections)
            for c in backup_collections:
                if get_key(c) not in current_keys:
                    merged_collections.append(c)

            merged_data = dict(
                collections=merged_collections,
                version=current_data.get('version', 0) + 1,
            )
            config_file.parent.mkdir(parents=True, exist_ok=True)
            self.write_config_data(merged_data, config_file)

        # Importing a backup is the user's choice: apply it whatever the versions.
        self.import_forced(send_events=send_events)


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
    """Import domain collections from config file into database, then link their Downloads (a short write, only
    when there is something to link)."""
    logger.info('Importing domains config')
    domains_config.import_config()
    if domains_config.import_skipped:
        # Linking changes domains.yaml, which cannot be saved while it has skipped entries: the database would be
        # newer than the file, and the next startup would save over them.
        logger.warning('Not linking Downloads to domains while domains.yaml has skipped entries')
        return

    with get_db_session() as session:
        links = domain_download_links(session)
    if links:
        with get_db_session(commit=True) as session:
            _link_downloads(session, links)
        save_domains_config.activate_switch()

    logger.info('Importing domains config completed')


@dataclass
class ArchiveDownloaderConfigValidator:
    """Validator for archives_downloader.yaml config."""
    file_name_format: str
    version: int = 0
    # Browser settings (only used on native deployments, not Docker)
    browser_executable: str = None  # None means auto-detect, or absolute path
    browser_args: str = '["--no-sandbox"]'  # JSON array of browser arguments
    user_agent: str = None  # None means use system default

    def __post_init__(self):
        # Validate file_name_format ends with .%(ext)s (like video format)
        if not self.file_name_format.endswith('.%(ext)s'):
            raise ValueError('file_name_format must end with .%(ext)s')

        # Validate browser_args is valid JSON array
        if self.browser_args:
            import json
            try:
                args = json.loads(self.browser_args)
                if not isinstance(args, list):
                    raise ValueError('browser_args must be a JSON array')
            except json.JSONDecodeError as e:
                raise ValueError(f'browser_args must be valid JSON: {e}')


class ArchiveDownloaderConfig(ConfigFile):
    """
    Config file for Archive Downloader settings.

    This config mirrors videos_downloader.yaml and holds settings for how
    archives are downloaded and named.

    Format:
        version: 0
        file_name_format: '%(download_date)s_%(title)s.%(ext)s'
        browser_executable: null  # null for auto-detect, or absolute path
        browser_args: '["--no-sandbox"]'  # JSON array of browser arguments
        user_agent: null  # null for system default

    Variables available in file_name_format:
        - %(title)s - Page title (extracted from HTML)
        - %(download_datetime)s - Full download datetime (YYYY-MM-DD-HH-MM-SS)
        - %(download_date)s - Download date only (YYYY-MM-DD)
        - %(download_year)s - Download year
        - %(download_month)s - Download month (zero-padded)
        - %(download_day)s - Download day (zero-padded)
        - %(domain)s - Domain name
        - %(ext)s - File extension (required, must be at end)

    Subdirectories can be included in the format, e.g.:
        '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

    Browser settings (only used on native deployments, not Docker):
        - browser_executable: Path to browser or null for auto-detect
        - browser_args: JSON array of arguments passed to browser
        - user_agent: Custom user agent string or null for default
    """
    file_name = 'archives_downloader.yaml'
    validator = ArchiveDownloaderConfigValidator
    default_config = dict(
        version=0,
        file_name_format='%(download_datetime)s_%(title)s.%(ext)s',
        browser_executable=None,
        browser_args='["--no-sandbox"]',
        user_agent=None,
    )

    @property
    def file_name_format(self) -> str:
        return self._config['file_name_format']

    @property
    def browser_executable(self) -> Optional[str]:
        """Get the configured browser executable path, or None for auto-detect."""
        return self._config.get('browser_executable')

    @property
    def browser_args(self) -> str:
        """Get the browser arguments as a JSON string."""
        return self._config.get('browser_args', '["--no-sandbox"]')

    @property
    def user_agent(self) -> Optional[str]:
        """Get the custom user agent, or None for system default."""
        return self._config.get('user_agent')


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
        Formatted filename/path (with .html extension included)

    Example:
        format_archive_filename("My Article", "example.com")
        # With default format: "2025-12-22_My Article.html"
        # With "%(download_year)s/%(title)s.%(ext)s": "2025/My Article.html"
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
        ext='html',
    )

    try:
        result = template % variables
        # Trim the filename portion if it's too long (may include subdirectory paths)
        if '/' in result:
            # Has subdirectories - only trim the filename part
            parts = result.rsplit('/', 1)
            subdir = parts[0]
            filename = trim_file_name(parts[1])
            return f'{subdir}/{filename}'
        else:
            return trim_file_name(result)
    except KeyError as e:
        logger.error(f'Invalid variable in archive file_name_format: {e}')
        # Fallback to default format
        return trim_file_name(
            f'{archive_strftime(download_date)}_{escape_file_name(title) if title else "untitled"}.html')


def preview_archive_filename(file_name_format: str) -> str:
    """Preview the archive filename using sample data.

    Args:
        file_name_format: The format template to preview

    Returns:
        A preview string showing what the filename would look like

    Raises:
        RuntimeError: If the format is invalid or missing required variables
    """
    if not file_name_format.endswith('.%(ext)s'):
        raise RuntimeError('file_name_format must end with .%(ext)s')

    sample_date = now()
    variables = dict(
        title='Example Page Title',
        domain='example.com',
        download_datetime=archive_strftime(sample_date),
        download_date=sample_date.strftime('%Y-%m-%d'),
        download_year=str(sample_date.year),
        download_month=f'{sample_date.month:02d}',
        download_day=f'{sample_date.day:02d}',
        ext='html',
    )

    try:
        return file_name_format % variables
    except KeyError as e:
        raise RuntimeError(f'Invalid variable: {e}')
    except ValueError as e:
        raise RuntimeError(f'Invalid format: {e}')


def format_archive_filename_from_archive(
        archive: Archive,
        file_name_format: str = None,
) -> str:
    """Single source of truth for archive filenames when reorganizing.

    Formats an archive filename using the configured file_name_format template.
    Used by collection reorganization to compute new file paths.

    Args:
        archive: Archive model with metadata
        file_name_format: Optional override, defaults to config value

    Returns:
        Formatted filename (may include subdirectory path like "2025/My Article.html")
    """
    config = get_archive_downloader_config()
    template = file_name_format or config.file_name_format

    file_group = archive.file_group

    # Get download date from file_group
    download_date = file_group.download_datetime or file_group.published_datetime or now()

    # Get title
    title = file_group.title or 'untitled'

    # Get domain from URL
    domain = ''
    if file_group.url:
        try:
            domain = extract_domain(file_group.url)
        except Exception:
            pass

    variables = dict(
        title=escape_file_name(title) if title else 'untitled',
        domain=domain,
        download_datetime=archive_strftime(download_date),
        download_date=download_date.strftime('%Y-%m-%d'),
        download_year=str(download_date.year),
        download_month=f'{download_date.month:02d}',
        download_day=f'{download_date.day:02d}',
        ext='html',
    )

    try:
        result = template % variables
        # Trim the filename portion if it's too long (may include subdirectory paths)
        if '/' in result:
            # Has subdirectories - only trim the filename part
            parts = result.rsplit('/', 1)
            subdir = parts[0]
            filename = trim_file_name(parts[1])
            return f'{subdir}/{filename}'
        else:
            return trim_file_name(result)
    except KeyError as e:
        logger.error(f'Invalid variable in archive file_name_format: {e}')
        # Fallback to default format
        return trim_file_name(
            f'{archive_strftime(download_date)}_{escape_file_name(title) if title else "untitled"}.html')


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
    variables = dict(domain='', domain_tag='', year='', month='', day='')
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

    # Use the configured file format template (returns full filename with .html extension)
    title = title or 'NA'
    title = title[:MAXIMUM_ARCHIVE_FILE_CHARACTER_LENGTH]
    formatted_filename = format_archive_filename(title, domain=domain)

    # Handle subdirectories in the format (e.g., "%(download_year)s/%(title)s.%(ext)s")
    if '/' in formatted_filename:
        # Filename includes subdirectories, create them relative to base directory
        full_path = directory / formatted_filename
        full_path.parent.mkdir(parents=True, exist_ok=True)
        singlefile_path = full_path
        stem = full_path.stem
        parent_dir = full_path.parent
        readability_path = trim_file_name(parent_dir / f'{stem}.readability.html')
        readability_txt_path = trim_file_name(parent_dir / f'{stem}.readability.txt')
        readability_json_path = trim_file_name(parent_dir / f'{stem}.readability.json')
        screenshot_path = trim_file_name(parent_dir / f'{stem}.png')
    else:
        singlefile_path = directory / formatted_filename
        stem = singlefile_path.stem
        readability_path = trim_file_name(directory / f'{stem}.readability.html')
        readability_txt_path = trim_file_name(directory / f'{stem}.readability.txt')
        readability_json_path = trim_file_name(directory / f'{stem}.readability.json')
        screenshot_path = trim_file_name(directory / f'{stem}.png')

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


async def request_archive(url: str, singlefile: str = None, compress: bool = False) \
        -> Tuple[str | bytes, Optional[dict], Optional[str]]:
    """Send a request to the archive service to archive the URL."""
    logger.info(f'Sending archive request to archive service: {url}')

    data = dict(url=url, singlefile=singlefile, compress=compress)
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
    # A compressed (SingleFileZ) singlefile is binary and must stay bytes; only decode regular singlefiles.
    if not is_compressed_singlefile(singlefile):
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


@dataclass
class WrittenArchiveFiles:
    """The on-disk artifacts produced by write_archive_files."""
    url: str
    paths: List[pathlib.Path]


def write_archive_files(url: str, singlefile: str | bytes, readability: Optional[dict],
                        screenshot: Optional[bytes],
                        destination: Optional[pathlib.Path] = None) -> WrittenArchiveFiles:
    """Pure I/O: write the singlefile/readability/screenshot/json files to disk.

    Returns the URL and the list of paths to register, leaving DB work to register_archive.
    """
    compressed = isinstance(singlefile, bytes) and is_compressed_singlefile(singlefile)

    readability = readability.copy() if readability else readability
    # First try to get the title from Readability.
    title = readability.get('title') if readability else None

    if not title and singlefile:
        # Try to get the title ourselves from the HTML.  A compressed singlefile contains the
        # uncompressed page as index.html.
        title = get_title_from_html(get_compressed_singlefile_index(singlefile) if compressed else singlefile, url=url)
        if readability:
            # Readability could not find title, lets use ours.
            readability['title'] = title

    archive_files = get_new_archive_files(url, title, destination=destination)

    if readability:
        # Write the readability parts to their own files.  Write what is left after pops to the JSON file.
        with archive_files.readability.open('wt') as fp:
            content = readability.pop('content')
            if compressed:
                # Readability extracted from the ZIP's index.html references images by relative
                # ZIP paths; inline them so the readability file is self-contained.
                content = inline_compressed_singlefile_resources(content, singlefile, url)
            content = format_html_string(content)
            fp.write(content)
        with archive_files.readability_txt.open('wt') as fp:
            readability_txt = readability.pop('textContent')
            readability_txt = split_lines_by_length(readability_txt)
            fp.write(readability_txt)
    else:
        # No readability was returned, so there are no files.
        archive_files.readability_txt = archive_files.readability = None

    # Store the single-file HTML in its own file.
    if compressed:
        # A compressed (SingleFileZ) singlefile is a binary ZIP; prettifying would corrupt it.
        archive_files.singlefile.write_bytes(singlefile)
    elif isinstance(singlefile, bytes) and b'<html data-sfz' in singlefile[:200]:
        # Marked as compressed but the ZIP is unreadable (e.g. truncated); prettifying would
        # destroy whatever remains, so store it verbatim.
        logger.warning(f'Singlefile of {url} is marked compressed but is not a valid ZIP!')
        archive_files.singlefile.write_bytes(singlefile)
    else:
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

    return WrittenArchiveFiles(url=url, paths=paths)


def register_archive(session: Session, written: WrittenArchiveFiles) -> Archive:
    """Pure DB: create the Archive record from already-written files. Caller commits."""
    archive = Archive.from_paths(session, *written.paths)
    archive.file_group.download_datetime = now()
    archive.url = written.url
    archive.collection = get_or_create_domain_collection(session, written.url)

    # Update collection's file_format to track the format used for this file
    config = get_archive_downloader_config()
    if archive.collection and config.file_name_format:
        if not archive.collection.file_format:
            # Set initial file_format on collection
            archive.collection.file_format = config.file_name_format
            save_domains_config.activate_switch()

    archive.flush()
    return archive


def detect_domain_directory(collection: Collection) -> Optional[pathlib.Path]:
    """
    Detect directory for domain collection using format_destination template.

    Computes the expected domain directory using the collection's format_destination()
    method and checks if that directory exists on the filesystem.

    Args:
        collection: The domain collection to analyze

    Returns:
        Path (relative to media directory) if the expected directory exists.
        None if collection is not a domain or directory doesn't exist.
    """
    if collection.kind != 'domain':
        return None

    # Get the tag name if collection has a tag
    tag_name = collection.tag.name if collection.tag else None

    # Compute expected directory using archive_destination template
    expected_directory = collection.format_destination(tag_name)

    # Simply check if the directory exists
    if expected_directory.is_dir():
        relative_path = get_relative_to_media_directory(expected_directory)
        logger.debug(f'Detected directory for domain {collection.name}: {relative_path}')
        return relative_path

    return None


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
        detected_dir = detect_domain_directory(collection)
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
        detected_dir = detect_domain_directory(collection)
        if detected_dir:
            collection.directory = detected_dir
            session.flush()
            # Trigger domain config save when directory is auto-detected
            save_domains_config.activate_switch()
            logger.info(f'Auto-detected directory for domain {domain_name}: {detected_dir}')

    return collection


def domain_download_links(session: Session) -> Dict[int, int]:
    """The Downloads to link to a Domain Collection: {Download id: Collection id}.

    Matching criteria (only recurring Downloads without a Collection):
    - a destination within the domain collection's directory (including subdirectories)
    - RSS downloads with sub_downloader='archive' (matched by URL domain)
    """
    # Local import to avoid circular import: downloader -> archive -> downloader
    from wrolpi.downloader import Download

    domains = session.query(Collection.id, Collection.name, Collection.directory) \
        .filter(Collection.kind == 'domain').all()
    by_name = {name: id_ for id_, name, _ in domains}
    # Ensure each directory ends with / for proper prefix matching.
    directories = [(id_, str(directory), str(directory).rstrip('/') + '/')
                   for id_, _, directory in domains if directory]

    links = dict()
    downloads = session.query(Download.id, Download.url, Download.downloader, Download.sub_downloader,
                              Download.destination, Download.settings) \
        .filter(Download.frequency.isnot(None), Download.collection_id.is_(None))
    for id_, url, downloader, sub_downloader, destination, settings in downloads:
        # An old Download kept its destination in its settings.
        destination = str(destination) if destination else (settings or dict()).get('destination')
        if destination:
            for collection_id, directory, prefix in directories:
                if destination == directory or destination.startswith(prefix):
                    links[id_] = collection_id
                    break
        if id_ not in links and downloader == 'rss' and sub_downloader == 'archive':
            if collection_id := by_name.get(extract_domain(url)):
                links[id_] = collection_id
    return links


def _link_downloads(session: Session, links: Dict[int, int]):
    # Local import to avoid circular import: downloader -> archive -> downloader
    from wrolpi.downloader import Download
    for ids in chunks(list(links), 500):
        for download in session.query(Download).filter(Download.id.in_(ids)):
            download.collection_id = links[download.id]
    session.flush()


SINGLEFILE_URL_EXTRACTOR = re.compile(r'Page saved with SingleFile \s+url: (http.+?)\n')

COMPRESSED_SINGLEFILE_INDEX = 'index.html'


def is_compressed_singlefile(singlefile: bytes) -> bool:
    """A compressed (SingleFileZ) singlefile is a self-extracting HTML file which is also a valid ZIP
    containing the uncompressed page as index.html."""
    buf = io.BytesIO(singlefile)
    if not zipfile.is_zipfile(buf):
        return False
    try:
        with zipfile.ZipFile(buf) as zip_:
            return COMPRESSED_SINGLEFILE_INDEX in zip_.namelist()
    except zipfile.BadZipFile:
        return False


def get_compressed_singlefile_index(singlefile: bytes) -> bytes:
    """Extract the uncompressed page (index.html) from a compressed (SingleFileZ) singlefile."""
    with zipfile.ZipFile(io.BytesIO(singlefile)) as zip_:
        return zip_.read(COMPRESSED_SINGLEFILE_INDEX)


def read_singlefile_html(path: pathlib.Path) -> bytes:
    """Read the page HTML of the singlefile at `path`; extract the uncompressed page when the
    singlefile is compressed (SingleFileZ)."""
    contents = path.read_bytes()
    if is_compressed_singlefile(contents):
        return get_compressed_singlefile_index(contents)
    return contents


def inline_compressed_singlefile_resources(html: str, singlefile: bytes, url: str) -> str:
    """Inline the images of a compressed (SingleFileZ) singlefile into the provided HTML.

    The index.html inside a compressed singlefile references its resources by relative ZIP paths
    (e.g. images/0.jpg); HTML extracted from it (readability) dangles those references — either
    still relative, or absolutized against the page URL by readability-extractor
    (https://example.com/images/0.jpg).  Replace them with data URIs read from the ZIP, like an
    uncompressed singlefile would contain."""
    import mimetypes
    from urllib.parse import urljoin, unquote

    # readability-extractor resolves relative srcs against the page URL.
    url_base = urljoin(url, '.')

    soup = get_html_soup(html)
    with zipfile.ZipFile(io.BytesIO(singlefile)) as zip_:
        names = set(zip_.namelist())
        changed = False
        for img in soup.find_all('img'):
            src = img.get('src') or ''
            name = src.removeprefix('./')
            if src.startswith(url_base):
                name = unquote(src[len(url_base):])
            if not name or name not in names:
                continue
            mimetype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            img['src'] = f'data:{mimetype};base64,{base64.b64encode(zip_.read(name)).decode()}'
            # The ZIP-path srcset entries are dangling too; the inlined src replaces them.
            if img.get('srcset'):
                del img['srcset']
            changed = True
    return str(soup) if changed else html


def get_url_from_singlefile(html: bytes | str) -> str:
    """Extract URL from SingleFile contents."""
    # Ignore decode errors; a compressed singlefile has a plain-text prelude but a binary ZIP tail.
    html = html.decode(errors='ignore') if isinstance(html, bytes) else html
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


def get_archive(session: Session, archive_id: int, skip_viewed: bool = False) -> Archive:
    """Get an Archive."""
    archive = Archive.find_by_id(session, archive_id)
    if not skip_viewed:
        archive.file_group.set_viewed()
    return archive


def get_archive_by_file_group_id(session: Session, file_group_id: int, skip_viewed: bool = False) -> Archive:
    """Get an Archive by its FileGroup ID."""
    archive = session.query(Archive).options(*Archive.json_options()) \
        .filter_by(file_group_id=file_group_id).one_or_none()
    if not archive:
        raise UnknownArchive(f'Unknown Archive with FileGroup ID: {file_group_id}')
    if not skip_viewed:
        archive.file_group.set_viewed()
    return archive


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
    with path.open('rb') as fh:
        # Lastly, try to read the header of this HTML file.  Read a large part of the head because URLs can be long.
        # Read bytes because a compressed (SingleFileZ) singlefile has a binary ZIP tail.
        header = fh.read(1000).decode(errors='ignore')
        if SINGLEFILE_HEADER in header:
            return True
    return False


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
    'size': 'fg.size ASC, fg.id ASC',
    '-size': 'fg.size DESC NULLS LAST, fg.id DESC',
    'viewed': 'fg.viewed ASC',
    '-viewed': 'fg.viewed DESC',
}
NO_NULL_ORDERS = {
    'viewed': 'fg.viewed IS NOT NULL',
    '-viewed': 'fg.viewed IS NOT NULL',
    'published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
    '-published_modified_datetime': 'fg.published_modified_datetime IS NOT NULL',
}


def search_archives(session: Session, search_str: str, domain: str, limit: int, offset: int, order: str,
                    tag_names: List[str], headline: bool = False, deep: bool = False) \
        -> Tuple[List[dict], int]:
    # Always filter FileGroups to Archives.
    wheres = []

    # Explicit JSON nulls bypass the schema defaults; SQLite rejects LIMIT/OFFSET NULL.
    params = dict(search_str=search_str, offset=int(offset) if offset else 0, limit=int(limit) if limit else 20)
    order_by = ARCHIVE_ORDERS['-published_datetime']

    select_columns = ''
    fts_join = ''
    headline_columns = ''
    # The fast (deep=False) search only matches the a/b/c FTS columns; deep also matches d
    # (page contents).  `file_group_search` returns None when the search string is unusable, in
    # which case we behave as if no search was requested.
    file_group_search = fts.file_group_search(search_str, deep=deep) if search_str else None
    if file_group_search:
        # A search_str was provided by the user, modify the query to filter by it.  Rank and
        # snippets come from a subquery (FTS5 auxiliary functions cannot mix with some SELECT shapes).
        headline_selects = fts.file_group_headline_selects() if headline else ''
        fts_join = f'''JOIN (
                SELECT fts.rowid AS id, {file_group_search.rank_select}{headline_selects}
                FROM file_group_fts fts
                WHERE {file_group_search.where}
            ) fts ON fts.id = fg.id'''
        select_columns = 'fts.ts_rank AS ts_rank'  # positive, higher is better.
        params.update(file_group_search.params)
        if headline:
            # b/c/d headlines come from the FTS index.  `title` is not an FTS column; select it
            # plainly and highlight it in Python below.
            headline_columns = ''',
                fts.b_headline, fts.c_headline, fts.d_headline,
                fg.title AS title_headline'''

    null_filter = None
    if order:
        try:
            order_by = ARCHIVE_ORDERS[order]
        except KeyError:
            raise InvalidOrderBy(f'Invalid order byy {order}')
        if order in NO_NULL_ORDERS:
            null_filter = NO_NULL_ORDERS[order]
            wheres.append(null_filter)

    if not file_group_search and order in ('rank', '-rank'):
        # Rank without a search used to ORDER BY the windowed total (a constant).
        order_by = ARCHIVE_ORDERS['-published_datetime'] if order == 'rank' \
            else ARCHIVE_ORDERS['published_datetime']

    tag_names = tag_names or []
    wheres, params = tag_append_sub_select_where(wheres, params, tag_names)

    if domain:
        params['domain'] = domain
        # Use LIMIT 1 to handle potential duplicate domain collections with the same name
        wheres.append(
            "a.collection_id = (select id from collection where collection.name = :domain and collection.kind = 'domain' LIMIT 1)")

    select_columns = f"{select_columns}," if select_columns else ""
    where = ('WHERE\n' + '\n AND '.join(wheres)) if wheres else ''
    if where or fts_join:
        from_clause = f'''FROM archive a
            LEFT JOIN file_group fg ON fg.id = a.file_group_id
            {fts_join}'''
    else:
        # Browse (no filters): CROSS JOIN pins file_group as the outer table so SQLite walks its
        # date index and probes archive's covering index -- both sides stay index-only.  Driving
        # from archive probes every (large) file_group row for the sort key, which takes ~90
        # seconds cold on a Pi with 124k archives.
        from_clause = 'FROM file_group fg CROSS JOIN archive a ON a.file_group_id = fg.id'

    stmt = f'''
            SELECT
                a.file_group_id AS id, -- always get `file_group.id` for `handle_file_group_search_results`
                {select_columns}
                fg.id AS _fg_id
                {headline_columns}
            {from_clause}
            {where}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        '''.strip()
    logger.debug(f'{stmt} {params}')

    unfiltered = not search_str and not tag_names and not domain and not null_filter
    if unfiltered:
        total = cached_search_total(
            search_filter_cache_key('archives'),
            lambda: count_file_groups(session, 'SELECT COUNT(*) AS total FROM archive', dict()),
        )
    else:
        if file_group_search:
            # An inner join lets SQLite start from the FTS matches; a LEFT JOIN pins `archive` as the outer
            # table, which runs the MATCH once per Archive.
            count_from = f'''FROM archive a
            JOIN file_group fg ON fg.id = a.file_group_id
            {file_group_search.join}'''
            count_wheres = list(wheres)
            count_wheres.append(file_group_search.where)
            count_where = ('WHERE\n' + '\n AND '.join(count_wheres)) if count_wheres else ''
            count_stmt = f'SELECT COUNT(*) AS total {count_from} {count_where}'
        else:
            # Same filters as the page, but do not walk the date index just to count.
            count_from = '''FROM archive a
            LEFT JOIN file_group fg ON fg.id = a.file_group_id'''
            count_stmt = f'SELECT COUNT(*) AS total {count_from} {where}'
        cache_key = search_filter_cache_key(
            'archives', search_str=search_str, domain=domain, tag_names=tag_names,
            deep=deep, null_filter=null_filter,
        )
        total = cached_search_total(cache_key, lambda: count_file_groups(session, count_stmt, params))

    results, total = handle_file_group_search_results(session, stmt, params, total=total)

    if file_group_search and headline and results:
        # Highlight the plain titles like the FTS snippets above (Postgres used ts_headline).
        titles = [i.get('title_headline') for i in results]
        highlighted = fts.headline_texts(titles, search_str)
        for result, title, (title_headline, _) in zip(results, titles, highlighted):
            if title is not None:
                result['title_headline'] = title_headline

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
    name = name or ''
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


# The prefix and payload of a base64 data URI.  Keep in sync with docker/archive/main.py.
BASE64_DATA_URI = re.compile(rb'(data:[^,;\s"\'()]*(?:;[^,;\s"\'()]*)*;base64,)([A-Za-z0-9+/]+=*)')
DATA_URI_PLACEHOLDER = re.compile(r'WROLPIDATAURI[0-9a-f]{160}N\d+X')


def strip_data_uris(html: bytes) -> Tuple[bytes, Dict[str, bytes]]:
    """Replace each base64 data URI payload with a placeholder; readability-extractor takes minutes on a
    page of large inline images (SingleFile inlines every image).  Returns the HTML and the payloads by
    placeholder.  The placeholder holds a random token, so text in the page cannot be mistaken for one."""
    # At least 133 characters: Readability drops a shorter base64 `src` as a lazy-load placeholder when another
    # attribute names an image file (e.g. alt="cat.png").
    token = secrets.token_hex(80)
    payloads = dict()

    def replace(match):
        placeholder = f'WROLPIDATAURI{token}N{len(payloads)}X'
        payloads[placeholder] = match.group(2)
        return match.group(1) + placeholder.encode()

    return BASE64_DATA_URI.sub(replace, html), payloads


def restore_data_uris(readability: dict, payloads: Dict[str, bytes]) -> dict:
    """Put the payloads removed by `strip_data_uris` back into the readability output."""
    for key, value in readability.items():
        if isinstance(value, str):
            readability[key] = DATA_URI_PLACEHOLDER.sub(
                lambda m: payloads[m.group(0)].decode() if m.group(0) in payloads else m.group(0), value)
    return readability


async def html_to_readability(html: str | bytes, url: str, timeout: int = 120):
    """Extract the readability dict from the provided HTML."""
    html, data_uri_payloads = strip_data_uris(html.encode() if isinstance(html, str) else html)
    with tempfile.NamedTemporaryFile('wb', suffix='.html') as singlefile_file:
        singlefile_file.write(html)
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
            return restore_data_uris(readability, data_uri_payloads)
        else:
            logger.error(f'Failed to extract readability for {url}')
            e = ChildProcessError(stdout if stdout else 'No stdout')
            if stderr:
                e = ChildProcessError(stderr)
            raise RuntimeError(f'Failed to extract readability for {url} got {result.return_code}') from e


@dataclass
class SinglefileArtifacts:
    """Pure-data result of running a singlefile through readability + screenshot extraction."""
    url: str
    singlefile: bytes
    readability: dict
    screenshot: Optional[bytes]


async def extract_singlefile_artifacts(singlefile: bytes) -> SinglefileArtifacts:
    """Pure async I/O: extract readability and screenshot from a singlefile. No DB."""
    # Get URL first because it does some simple checking of `singlefile`.
    url = get_url_from_singlefile(singlefile)
    singlefile = singlefile.encode() if isinstance(singlefile, str) else singlefile

    # A compressed (SingleFileZ) singlefile contains the uncompressed page as index.html; use that
    # for readability and screenshot, but keep the compressed bytes as the singlefile.
    compressed = is_compressed_singlefile(singlefile)
    extractable = get_compressed_singlefile_index(singlefile) if compressed else singlefile

    if DOCKERIZED:
        # Perform the archive in the Archive docker container.  (Typically in the development environment).
        encoded = base64.b64encode(singlefile).decode()
        logger.debug(f'extract_singlefile_artifacts sending to archive service: {url}')
        singlefile, readability, screenshot = await request_archive(url, singlefile=encoded, compress=compressed)
        singlefile = singlefile.encode() if isinstance(singlefile, str) else singlefile
    else:
        # JSON from readability-extractor
        readability = dict()
        try:
            logger.debug(f'extract_singlefile_artifacts extracting readability: {url}')
            readability = await html_to_readability(extractable, url)
        except RuntimeError as e:
            logger.error(f'Failed to extract readability from: {url}', exc_info=e)

        screenshot = None
        try:
            logger.debug(f'extract_singlefile_artifacts creating screenshot: {url}')
            if compressed:
                # Extract the whole ZIP so the page's relative resources (images, fonts) render.
                with tempfile.TemporaryDirectory(prefix='wrolpi-singlefile-screenshot-') as tmp_dir:
                    with zipfile.ZipFile(io.BytesIO(singlefile)) as zip_:
                        zip_.extractall(tmp_dir)
                    screenshot = html_file_screenshot(pathlib.Path(tmp_dir) / COMPRESSED_SINGLEFILE_INDEX)
            else:
                screenshot = html_screenshot(extractable)
        except Exception as e:
            logger.error(f'Failed to extract screenshot from: {url}', exc_info=e)

    return SinglefileArtifacts(url=url, singlefile=singlefile, readability=readability, screenshot=screenshot)


@dataclass(frozen=True)
class UploadedArchive:
    """The Archive `singlefile_to_archive` created.  Plain values: its Session is gone once it returns."""
    file_group_id: int
    name: str
    url: Optional[str]
    location: str


async def singlefile_to_archive(singlefile: bytes, destination: pathlib.Path = None) -> UploadedArchive:
    """
    Convert a SingleFile to an Archive.

    Thin wrapper around extract_singlefile_artifacts + write_archive_files + register_archive
    that opens its own transaction.  New code should call the helpers directly so the caller
    controls the session.

    Args:
        singlefile: The SingleFile HTML bytes
        destination: Optional directory to save files to. If provided, files go here instead of archive/<domain>
    """
    artifacts = await extract_singlefile_artifacts(singlefile)
    logger.trace(f'singlefile_to_archive modeling: {artifacts.url}')
    written = write_archive_files(artifacts.url, artifacts.singlefile, artifacts.readability,
                                  artifacts.screenshot, destination=destination)
    with get_db_session(commit=True) as session:
        archive = register_archive(session, written)
        file_group = archive.file_group
        return UploadedArchive(file_group_id=file_group.id, name=file_group.title or file_group.url,
                               url=file_group.url, location=archive.location)


async def get_statistics(session: Session):
    """Get statistics about Archives and Domain Collections."""
    with session_curs(session) as curs:
        curs.execute('''
                     SELECT
                         -- total archives
                         COUNT(a.id)                                                                            AS "archives",
                         -- total archives downloaded over the past week/month/year
                         COUNT(a.id) FILTER (WHERE fg.download_datetime >= datetime('now', '-7 days'))          AS "week",
                         COUNT(a.id)
                         FILTER (WHERE fg.download_datetime >= datetime('now', '-1 month'))                     AS "month",
                         COUNT(a.id) FILTER (WHERE fg.download_datetime >= datetime('now', '-1 year'))          AS "year",
                         -- sum of all archive file sizes
                         COALESCE(SUM(fg.size), 0)                                                              AS "sum_size",
                         -- largest archive
                         COALESCE(MAX(fg.size), 0)                                                              AS "max_size"
                     FROM archive a
                              LEFT JOIN file_group fg on a.file_group_id = fg.id
                     ''')
        archive_stats = dict(curs.fetchone())

        # Get the total archives downloaded every month for the past two years (excluding the
        # current month, like the old generate_series query).
        curs.execute('''
                     SELECT strftime('%Y-%m-01 00:00:00', fg.download_datetime) AS "date_trunc",
                            COUNT(archive.id)                                   AS "count",
                            SUM(fg.size)                                        AS "size"
                     FROM archive
                              LEFT JOIN file_group fg on archive.file_group_id = fg.id
                     WHERE fg.download_datetime IS NOT NULL
                       AND fg.download_datetime >= datetime('now', 'start of month', '-24 months')
                       AND fg.download_datetime < datetime('now', 'start of month')
                     GROUP BY 1
                     ORDER BY 1
                     ''')
        monthly_archives = []
        for row in curs.fetchall():
            row = dict(row)
            # Convert the month strings back to datetimes so the JSON response shape is unchanged.
            row['date_trunc'] = datetime.strptime(row['date_trunc'], '%Y-%m-%d %H:%M:%S')
            monthly_archives.append(row)

        historical_stats = dict(monthly_archives=monthly_archives)
        historical_stats['average_count'] = (sum(i['count'] for i in monthly_archives) // len(monthly_archives)) \
            if monthly_archives else 0
        historical_stats['average_size'] = (sum(i['size'] for i in monthly_archives) // len(monthly_archives)) \
            if monthly_archives else 0

        curs.execute('''
                     SELECT COUNT(c.id)                                         AS "domains",
                            COUNT(c.id) FILTER ( WHERE col.tag_id IS NOT NULL ) AS "tagged_domains"
                     FROM collection c
                              LEFT JOIN collection col on col.id = c.id
                     WHERE c.kind = 'domain'
                     ''')
        domain_stats = dict(curs.fetchone())
    ret = dict(statistics=dict(
        archives=archive_stats,
        domains=domain_stats,
        historical=historical_stats,
    ))
    return ret


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
        if is_compressed_singlefile(singlefile_contents):
            # Extract the whole ZIP so the page's relative resources (images, fonts) render.
            with tempfile.TemporaryDirectory(prefix='wrolpi-singlefile-screenshot-') as tmp_dir:
                with zipfile.ZipFile(io.BytesIO(singlefile_contents)) as zip_:
                    zip_.extractall(tmp_dir)
                screenshot_bytes = html_file_screenshot(pathlib.Path(tmp_dir) / COMPRESSED_SINGLEFILE_INDEX)
        else:
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


# Bump to run `repair_singlefile_saved_dates` again.
SAVED_DATE_REPAIR_VERSION = '1'
SAVED_DATE_REPAIR_KEY = 'archive_saved_date_repair_version'


def repair_singlefile_saved_dates() -> int:
    """Correct each Archive whose download_datetime is its SingleFile "saved date" local time read as UTC.

    The saved date was once parsed without its offset.  Only a download_datetime equal to that misread value, from a
    saved date with a non-zero offset, is changed; any other download_datetime is never touched.  Runs once per
    SAVED_DATE_REPAIR_VERSION, and is not marked done while any Archive could not be read.  A missing file is a
    deleted Archive, not a failure.  Returns the number of Archives corrected."""
    if get_kv_value(SAVED_DATE_REPAIR_KEY) == SAVED_DATE_REPAIR_VERSION:
        return 0

    with get_db_session() as session:
        rows = session.query(FileGroup.id, FileGroup.primary_path, FileGroup.download_datetime) \
            .join(Archive, Archive.file_group_id == FileGroup.id) \
            .filter(FileGroup.download_datetime.isnot(None)) \
            .all()

    corrections = dict()
    missing = failed = 0
    for file_group_id, path, download_datetime in rows:
        try:
            head = read_singlefile_header(path)
        except FileNotFoundError:
            missing += 1
            continue
        except OSError as e:
            logger.warning(f'Could not read the SingleFile header of {path}', exc_info=e)
            failed += 1
            continue
        if not head or not (match := MATCH_DATE.search(head)):
            continue
        saved_date = match.group(1).strip()
        try:
            corrected = parse_singlefile_saved_date(saved_date)
            # The value the offset-dropping parser stored.
            misread = dates.strpdate(' '.join(saved_date.split(' ')[:5])).replace(tzinfo=pytz.timezone('GMT'))
        except Exception:
            continue
        if corrected and corrected != misread and download_datetime == misread:
            corrections[file_group_id] = corrected

    for chunk in chunks(list(corrections.items()), 500):
        with get_db_session(commit=True) as session:
            for file_group in session.query(FileGroup).filter(FileGroup.id.in_([i for i, _ in chunk])):
                file_group.download_datetime = corrections[file_group.id]

    logger.info(f'Corrected the download datetime of {len(corrections)} Archives from their SingleFile saved date'
                f' ({missing} missing)')
    if failed:
        logger.warning(f'Could not read {failed} Archives; their download datetimes will be repaired later')
    else:
        set_kv_value(SAVED_DATE_REPAIR_KEY, SAVED_DATE_REPAIR_VERSION)
    return len(corrections)
