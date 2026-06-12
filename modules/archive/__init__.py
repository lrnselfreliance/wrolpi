import asyncio
import json
import os
import pathlib
from abc import ABC
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Iterable

from sqlalchemy import not_
from sqlalchemy.orm import Session

from wrolpi.cmd import SINGLE_FILE_BIN, CHROMIUM, FIREFOX, DENO_BIN, SINGLE_FILE_DENO_SCRIPT
from wrolpi.collections import Collection
from wrolpi.common import logger, register_modeler, register_refresh_cleanup, limit_concurrent, split_lines_by_length, \
    slow_logger, get_title_from_html, TRACE_LEVEL
from wrolpi.db import get_db_session
from wrolpi.downloader import Downloader, Download, DownloadContext, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, DOCKERIZED, DOWNLOAD_USER_AGENT, PROJECT_DIR
from . import lib
from .api import archive_bp  # noqa
from .errors import InvalidArchive
from .lib import is_singlefile_file, request_archive, SINGLEFILE_HEADER, get_url_from_singlefile, \
    SinglefileArtifacts, WrittenArchiveFiles, extract_singlefile_artifacts, register_archive, write_archive_files
from .models import Archive

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)

__all__ = ['ArchiveDownloader', 'archive_downloader', 'model_archive']


@dataclass
class PreparedArchive:
    """Plan produced by ArchiveDownloader.prepare_download.

    Holds everything execute_download needs (URL, destination, settings) so the I/O
    phase has no DB session.
    """
    url: str
    destination: Optional[pathlib.Path]
    settings: dict


@dataclass
class ExecutedArchive:
    """Output of ArchiveDownloader.execute_download: files are on disk and ready to register."""
    written: WrittenArchiveFiles


class ArchiveDownloader(Downloader, ABC):
    name = 'archive'
    pretty_name = 'Archive'
    # A page that has not finished archiving after this long is hung; the config-level
    # download_timeout still takes precedence when set.
    timeout = 10 * 60

    def __repr__(self):
        return f'<ArchiveDownloader>'

    def already_downloaded(self, session: Session, *urls: List[str]) -> List:
        file_groups = list(session.query(FileGroup).filter(FileGroup.url.in_(urls), FileGroup.model == 'archive'))
        return file_groups

    def prepare_download(self, session: Session, download: Download) -> PreparedArchive:
        """Resolve destination directory.  Caller commits (or rolls back on raise)."""
        if (download.attempts or 0) > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        settings = download.settings or dict()
        # Destination from settings (e.g. set by the RSS sub-downloader) wins over collection lookup.
        destination = pathlib.Path(settings['destination']) if settings.get('destination') else None

        if not destination:
            collection = lib.get_or_create_domain_collection(session, download.url)
            if collection:
                destination = collection.get_or_set_directory(session)

        return PreparedArchive(url=download.url, destination=destination, settings=settings)

    async def execute_download(self, prepared: PreparedArchive, ctx: DownloadContext,
                               download: Download = None) -> ExecutedArchive:
        """Run the archive container or local singlefile + readability/screenshot extraction,
        then write the artifacts to disk.  No DB."""
        compress = bool(prepared.settings.get('compress_singlefile'))
        if DOCKERIZED or PYTEST:
            singlefile, readability, screenshot = await request_archive(prepared.url, compress=compress)
            artifacts = SinglefileArtifacts(url=prepared.url, singlefile=singlefile,
                                            readability=readability, screenshot=screenshot)
        else:
            singlefile_bytes = await self.do_singlefile(prepared, ctx, download=download)
            artifacts = await extract_singlefile_artifacts(singlefile_bytes)

        written = write_archive_files(artifacts.url, artifacts.singlefile, artifacts.readability,
                                      artifacts.screenshot, destination=prepared.destination)
        return ExecutedArchive(written=written)

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedArchive) -> DownloadResult:
        """Register the Archive record, apply tags, persist parent_download_url. Caller commits."""
        archive = register_archive(session, executed.written)

        if tag_names := download.tag_names:
            for name in tag_names:
                archive.add_tag(session, name)

        settings = download.settings or dict()
        if parent_download_url := settings.get('parent_download_url'):
            try:
                archive.file_group.update_wrolpi_json({'parent_download_url': parent_download_url})
            except ValueError as e:
                logger.warning(f'Failed to update wrolpi json for {archive}: {e}')

        logger.info(f'Successfully downloaded Archive {download.url} {archive}')
        return DownloadResult(success=True, location=archive.location)

    async def do_singlefile(self, prepared: PreparedArchive, ctx: DownloadContext,
                            download: Download = None) -> bytes:
        """Create a Singlefile from the archive's URL.

        download is the original Download row when called via the manager dispatch; tests
        may omit it and a stub is built so process_runner has a url for log messages.
        """
        # Get browser settings from config
        config = lib.get_archive_downloader_config()

        # Determine browser executable
        browser_executable = config.browser_executable
        if browser_executable:
            # Use configured browser path
            browser = browser_executable
        else:
            # Auto-detect: prefer Chromium, fallback to Firefox
            browser = CHROMIUM or FIREFOX
            if not browser:
                raise RuntimeError('No browser found. Install Chromium or Firefox, or configure browser_executable.')

        # Get browser args and user agent from config
        browser_args = config.browser_args or '["--no-sandbox"]'
        user_agent = config.user_agent or DOWNLOAD_USER_AGENT

        env = None
        browser_wrapper = PROJECT_DIR / 'scripts/singlefile_browser_wrapper.sh'
        if DENO_BIN and SINGLE_FILE_DENO_SCRIPT and browser_wrapper.is_file():
            # single-file-cli is designed for Deno.  Under node 18 (Debian 12/RPi OS) it cannot
            # reach the browser CDP on IPv6-enabled hosts ("localhost" resolves to ::1 first with
            # no IPv4 fallback) and it never exits after a successful save.
            runtime = (str(DENO_BIN), 'run', '--node-modules-dir=manual',
                       '--allow-read', '--allow-write', '--allow-net', '--allow-env', '--allow-run',
                       str(SINGLE_FILE_DENO_SCRIPT))
            # single-file pipes the browser's stderr but never reads it; under Deno >= 2.3 that
            # kills the browser during startup.  The wrapper discards the browser's stderr.
            env = {**os.environ, 'WROLPI_BROWSER': str(browser)}
            browser = browser_wrapper
        else:
            logger.warning('deno not found, running single-file under node.  Upgrade this WROLPi to install deno.')
            runtime = (str(SINGLE_FILE_BIN),)
            # node 18 has no IPv4 fallback when "localhost" resolves to ::1 first; without this
            # single-file cannot reach the browser CDP and fails with "fetch failed".
            env = {**os.environ, 'NODE_OPTIONS': '--enable-network-family-autoselection'}

        cmd = ('/usr/bin/nice', '-n15',  # Nice above map importing, but very low priority.
               *runtime,
               '--browser-executable-path', str(browser),
               '--browser-args', browser_args,
               '--user-agent', user_agent,
               '--dump-content',
               '--load-deferred-images-dispatch-scroll-event',
               # Create a compressed (SingleFileZ) self-extracting HTML file.
               *(('--compress-content',) if prepared.settings.get('compress_singlefile') else ()),
               prepared.url,
               )
        cwd = pathlib.Path('/home/wrolpi')
        cwd = cwd if cwd.is_dir() else None
        # cancel_wrapper reads cancellation from ctx; the Download is forwarded so
        # the real download id is used for unkill cleanup and log attribution.
        # start_new_session reaps the browser single-file leaves behind (it does not close it).
        result = await self.process_runner(download or Download(url=prepared.url),
                                           cmd, cwd, env=env, start_new_session=True, ctx=ctx)

        stderr = result.stderr.decode()
        # stdout may be a binary ZIP when --compress-content is used.
        log_output = stderr or result.stdout.decode(errors='replace') or 'No stderr or stdout!'

        if result.return_code != 0:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'singlefile exited with {result.return_code}') from e

        if not result.stdout:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'Singlefile created was empty: {prepared.url}') from e

        if SINGLEFILE_HEADER.encode() not in result.stdout:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'Singlefile created was invalid: {prepared.url}') from e

        return result.stdout


archive_downloader = ArchiveDownloader()


def model_archive(session: Session, file_group: FileGroup) -> Archive:
    """
    Models an Archive from a given FileGroup.

    This function takes in a FileGroup and attempts to create an Archive object.
    It does this by checking for the presence of HTML files within the FileGroup,
    determining if any of these are SingleFiles, and then extracting relevant data
    (title, contents) from either the JSON or text readability files.

    Args:
        session: Database session.
        file_group: The FileGroup to model as an Archive.

    Returns:
        An Archive object representing the modeled archive.

    Raises:
        InvalidArchive: If no HTML SingleFile is found in the FileGroup, or if
            any other error occurs during modeling.
    """
    file_group_id = file_group.id
    if not file_group_id:
        session.flush([file_group])
        file_group_id = file_group.id

    # All Archives have an HTML Singlefile.  Singlefile may be text HTML, or bytes HTML.
    html_paths = file_group.my_html_paths()
    if not html_paths:
        logger.error('Query returned a group without an HTML file!')
        raise InvalidArchive('FileGroup does not contain any html files')

    # All Archives have a Singlefile.
    singlefile_path = None
    for file in html_paths:
        try:
            if is_singlefile_file(file):
                singlefile_path = file
                break
        except Exception as e:
            if PYTEST:
                raise
            logger.debug(f'Cannot check is_singlefile_file of {repr(file)}', exc_info=e)

    if singlefile_path is None:
        logger.debug(f'No Archive singlefile found in {file_group}')
        raise InvalidArchive('FileGroup does not contain a singlefile')

    readability_json_path = None
    json_files = file_group.my_json_files()
    for json_file in json_files:
        path = json_file['path']
        if path.name.endswith('.readability.json'):
            readability_json_path = path
            break

    readability_txt_path = None
    text_files = file_group.my_text_files()
    for text_file in text_files:
        path = text_file['path']
        if path.name.endswith('.readability.txt'):
            readability_txt_path = path
            break

    try:
        file_group.model = 'archive'
        file_group.primary_path = singlefile_path

        title = None
        if readability_json_path:
            title = get_title(readability_json_path)
        if not title:
            title = get_title_from_html(lib.read_singlefile_html(singlefile_path))

        contents = None
        if readability_txt_path:
            contents = get_article(readability_txt_path)

        # Check if an Archive already exists for this FileGroup
        archive = session.query(Archive).filter_by(file_group_id=file_group_id).one_or_none()
        if not archive:
            # Create new Archive if it doesn't exist
            archive = Archive(file_group_id=file_group_id, file_group=file_group)

            # Set collection_id BEFORE adding to session to avoid autoflush constraint violation
            from modules.archive.lib import get_or_create_domain_collection

            if file_group.url:
                # URL is already set on the FileGroup
                collection = get_or_create_domain_collection(session, file_group.url)
                archive.collection_id = collection.id if collection else None
            else:
                # No URL - try to extract from singlefile
                try:
                    url = get_url_from_singlefile(singlefile_path.read_bytes())
                    file_group.url = url
                    collection = get_or_create_domain_collection(session, url)
                    archive.collection_id = collection.id if collection else None
                except (RuntimeError, ValueError) as e:
                    # Could not extract URL from singlefile - archive will have no collection
                    logger.debug(f'Could not extract URL from singlefile: {e}')
                    archive.collection_id = None

            session.add(archive)

        archive.validate()
        archive.flush()

        # Note: We intentionally do NOT clear collection.directory when archive is outside it.
        # Archives are associated with domain collections based on URL, not file location.
        # The collection's directory should remain intact for other archives.

        file_group.title = file_group.a_text = title or archive.file_group.title
        file_group.d_text = contents
        archive.rebuild_data()

        return archive
    except Exception as e:
        logger.error('Failed to model Archive', exc_info=e)
        raise InvalidArchive(f'Failed to model Archive {file_group}') from e


@register_modeler
async def archive_modeler(progress_callback: Callable[[int], None] = None):
    """Searches DB for FileGroups that contain an HTML file.  If the HTML file is a SingleFile, we model it as an
    Archive."""
    invalid_archives = set()
    total_processed = 0

    while True:
        with get_db_session(commit=True) as session:
            results = session.query(FileGroup, Archive) \
                .filter(
                # Get all groups that contain an HTML file that have not been indexed.
                FileGroup.indexed != True,
                FileGroup.mimetype == 'text/html',
            ).filter(not_(FileGroup.id.in_(list(invalid_archives)))) \
                .outerjoin(Archive, Archive.file_group_id == FileGroup.id) \
                .limit(20)
            results: Iterable[Tuple[FileGroup, Archive]]
            results_list = list(results)

            processed = 0
            for processed, (file_group, archive) in enumerate(results_list):
                with slow_logger(1, f'Modeling archive took %(elapsed)s seconds: {file_group}',
                                 logger__=logger):
                    if archive:
                        try:
                            archive_id = archive.id
                            archive.validate()
                            # Successfully validated, mark as indexed
                            file_group.indexed = True
                        except Exception as e:
                            logger.error(f'Unable to validate Archive {archive_id}')
                            # Don't mark as indexed - will retry later
                            if PYTEST:
                                raise
                    else:
                        try:
                            model_archive(session, file_group)
                            # Successfully modeled, mark as indexed
                            file_group.indexed = True
                        except InvalidArchive:
                            # It was not a real Archive.  Many HTML files will not be an Archive.
                            file_group.indexed = False
                            invalid_archives.add(file_group.id)
                        except Exception as e:
                            # Some other error occurred during modeling - don't mark as indexed so we can retry
                            logger.error(f'Failed to model Archive for FileGroup {file_group.id}: {e}')
                            if PYTEST:
                                raise

            session.commit()

            # Report batch progress
            batch_count = len(results_list)
            total_processed += batch_count
            if progress_callback and batch_count > 0:
                progress_callback(total_processed)

            if processed < 19:
                # Did not reach limit (enumerate is 0-indexed, so 19 = 20 items), do not query again.
                if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
                    logger.trace(f'archive_modeler: DONE (processed {processed + 1} files)')
                break

        # Sleep to catch cancel.
        await asyncio.sleep(0)


@register_refresh_cleanup
@limit_concurrent(1)
def archive_cleanup():
    with get_db_session(commit=True) as session:
        # Remove any domain Collections without any Archives.
        # Get all collection_ids that have archives
        collection_ids = [i[0] for i in session.execute('SELECT DISTINCT collection_id FROM archive') if i[0]]
        # Find domain collections that have no archives
        for collection in session.query(Collection).filter_by(kind='domain'):
            if collection.id not in collection_ids:
                logger.info(f'Deleting empty domain collection: {collection.name}')
                session.delete(collection)


def get_title(path):
    with path.open('rt') as fh:
        try:
            return json.load(fh)['title']
        except Exception:
            if not PYTEST:
                logger.warning(f'Archive readability json file exists, but cannot get title. {path}')
            return None


def get_article(path):
    if path.is_file():
        text = path.read_text()
        text = split_lines_by_length(text)
        return text
