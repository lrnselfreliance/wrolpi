import asyncio
import json
import pathlib
from abc import ABC
from typing import List, Tuple, Iterable

from sqlalchemy import not_
from sqlalchemy.orm import Session

from wrolpi.cmd import SINGLE_FILE_BIN, CHROMIUM
from wrolpi.common import logger, register_modeler, register_refresh_cleanup, limit_concurrent, split_lines_by_length, \
    slow_logger, get_title_from_html
from wrolpi.db import optional_session, get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, DOCKERIZED, DOWNLOAD_USER_AGENT
from . import lib
from .api import archive_bp  # noqa
from .errors import InvalidArchive
from .lib import is_singlefile_file, request_archive, SINGLEFILE_HEADER
from .models import Archive, Domain

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)

__all__ = ['ArchiveDownloader', 'archive_downloader', 'model_archive']


class ArchiveDownloader(Downloader, ABC):
    name = 'archive'
    pretty_name = 'Archive'

    def __repr__(self):
        return f'<ArchiveDownloader>'

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None) -> List:
        file_groups = list(session.query(FileGroup).filter(FileGroup.url.in_(urls), FileGroup.model == 'archive'))
        return file_groups

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        if DOCKERIZED or PYTEST:
            # Perform the archive in the Archive docker container.  (Typically in the development environment).
            singlefile, readability, screenshot = await request_archive(download.url)
            archive: Archive = await lib.model_archive_result(download.url, singlefile, readability, screenshot)
            archive_id = archive.id
        else:
            # Perform the archive using locally installed executables.
            singlefile = await self.do_singlefile(download)
            archive = await lib.singlefile_to_archive(singlefile)
            archive_id = archive.id

        with get_db_session() as session:
            archive = Archive.find_by_id(archive_id, session)
            need_commit = False
            if tag_names := download.tag_names:
                for name in tag_names:
                    archive.add_tag(name, session)
                    need_commit = True

                if need_commit:
                    session.commit()

            logger.info(f'Successfully downloaded Archive {download.url} {archive}')

            return DownloadResult(success=True, location=f'/archive/{archive.id}')

    async def do_singlefile(self, download: Download) -> bytes:
        """Create a Singlefile from the archive's URL."""
        cmd = ('/usr/bin/nice', '-n15',  # Nice above map importing, but very low priority.
               str(SINGLE_FILE_BIN),
               '--browser-executable-path', CHROMIUM,
               '--browser-args', '["--no-sandbox"]',
               '--user-agent', DOWNLOAD_USER_AGENT,
               '--dump-content',
               '--load-deferred-images-dispatch-scroll-event',
               download.url,
               )
        cwd = pathlib.Path('/home/wrolpi')
        cwd = cwd if cwd.is_dir() else None
        result = await self.process_runner(download, cmd, cwd)

        stderr = result.stderr.decode()
        log_output = stderr or result.stdout.decode() or 'No stderr or stdout!'

        if result.return_code != 0:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'singlefile exited with {result.return_code}') from e

        if not result.stdout:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'Singlefile created was empty: {download.url}') from e

        if SINGLEFILE_HEADER.encode() not in result.stdout:
            e = ChildProcessError(log_output[:1000])
            raise RuntimeError(f'Singlefile created was invalid: {download.url}') from e

        return result.stdout


archive_downloader = ArchiveDownloader()


def model_archive(file_group: FileGroup, session: Session = None) -> Archive:
    """
    Models an Archive from a given FileGroup.

    This function takes in a FileGroup and attempts to create an Archive object.
    It does this by checking for the presence of HTML files within the FileGroup,
    determining if any of these are SingleFiles, and then extracting relevant data
    (title, contents) from either the JSON or text readability files.

    Args:
        file_group: The FileGroup to model as an Archive.
        session: An optional database session for committing changes.

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
    for file in html_paths:
        try:
            if is_singlefile_file(file):
                singlefile_path = file
                break
        except Exception as e:
            if PYTEST:
                raise
            logger.debug(f'Cannot check is_singlefile_file of {repr(file)}', exc_info=e)
    else:
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
            title = get_title_from_html(singlefile_path.read_text())

        contents = None
        if readability_txt_path:
            contents = get_article(readability_txt_path)

        archive = Archive(file_group_id=file_group_id, file_group=file_group)
        session.add(archive)
        archive.validate()
        archive.flush()

        file_group.title = file_group.a_text = title or archive.file_group.title
        file_group.d_text = contents
        file_group.data = {
            'id': archive.id,
            'domain': archive.domain.domain if archive.domain else None,
            'readability_json_path': archive.readability_json_path,
            'readability_path': archive.readability_path,
            'readability_txt_path': archive.readability_txt_path,
            'screenshot_path': archive.screenshot_path,
            'singlefile_path': archive.singlefile_path,
        }

        return archive
    except Exception as e:
        logger.error('Failed to model Archive', exc_info=e)
        raise InvalidArchive(f'Failed to model Archive {file_group}') from e


@register_modeler
async def archive_modeler():
    """Searches DB for FileGroups that contain an HTML file.  If the HTML file is a SingleFile, we model it as an
    Archive."""
    invalid_archives = set()

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

            processed = 0
            for processed, (file_group, archive) in enumerate(results):

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

                with slow_logger(1, f'Modeling archive took %(elapsed)s seconds: {file_group}',
                                 logger__=logger):
                    if archive:
                        try:
                            archive_id = archive.id
                            archive.validate()
                        except Exception:
                            logger.error(f'Unable to validate Archive {archive_id}')
                            if PYTEST:
                                raise
                    else:
                        try:
                            model_archive(file_group, session=session)
                        except InvalidArchive:
                            # It was not a real Archive.  Many HTML files will not be an Archive.
                            file_group.indexed = False
                            invalid_archives.add(file_group.id)

            session.commit()

            if processed < 20:
                # Did not reach limit, do not query again.
                break

            logger.debug(f'Modeled {processed} Archives')

        # Sleep to catch cancel.
        await asyncio.sleep(0)


@register_refresh_cleanup
@limit_concurrent(1)
def archive_cleanup():
    with get_db_session(commit=True) as session:
        # Remove any Domains without any Archives.
        domain_ids = [i[0] for i in session.execute('SELECT DISTINCT domain_id FROM archive') if i[0]]
        for domain in session.query(Domain):
            if domain.id not in domain_ids:
                session.delete(domain)


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
