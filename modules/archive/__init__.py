import asyncio
import json
import pathlib
import tempfile
from abc import ABC
from typing import List, Tuple

from selenium import webdriver
from sqlalchemy import not_
from sqlalchemy.orm import Session

from wrolpi.cmd import SINGLE_FILE_BIN, CHROMIUM, READABILITY_BIN
from wrolpi.common import logger, register_modeler, register_refresh_cleanup, limit_concurrent, split_lines_by_length, \
    slow_logger, html_screenshot, get_title_from_html
from wrolpi.db import optional_session, get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST, DOCKERIZED
from . import lib
from .api import bp  # noqa
from .errors import InvalidArchive
from .lib import is_singlefile_file, request_archive, SINGLEFILE_HEADER
from .models import Archive, Domain

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)

__all__ = ['ArchiveDownloader', 'archive_downloader']


class ArchiveDownloader(Downloader, ABC):
    name = 'archive'
    pretty_name = 'Archive'

    def __repr__(self):
        return f'<ArchiveDownloader>'

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        if DOCKERIZED or PYTEST:
            # Perform the archive in the Archive docker container.  (Typically in the development environment).
            singlefile, readability, screenshot = await request_archive(download.url)
        else:
            # Perform the archive using locally installed executables.
            singlefile, readability, screenshot = await self.do_archive(download)

        archive: Archive = await lib.model_archive_result(download.url, singlefile, readability, screenshot)

        if download.settings and (tag_names := download.settings.get('tag_names')):
            for name in tag_names:
                archive.add_tag(name)

            if session := Session.object_session(archive):
                session.commit()

        logger.info(f'Successfully downloaded Archive {download.url} {archive}')

        return DownloadResult(success=True, location=f'/archive/{archive.id}')

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None) -> List:
        file_groups = list(session.query(FileGroup).filter(FileGroup.url.in_(urls), FileGroup.model == 'archive'))
        return file_groups

    async def do_singlefile(self, download: Download) -> bytes:
        """Create a Singlefile from the archive's URL."""
        cmd = (str(SINGLE_FILE_BIN),
               download.url,
               '--browser-executable-path', CHROMIUM,
               '--browser-args', '["--no-sandbox"]',
               '--dump-content')
        return_code, _, stdout = await self.process_runner(
            download.url,
            cmd,
            pathlib.Path('/home/wrolpi'),
        )
        if return_code != 0:
            raise RuntimeError(f'Archive singlefile exited with {return_code}')

        return stdout

    async def do_readability(self, download: Download, html: bytes) -> dict:
        """Extract the readability dict from the provided HTML."""
        with tempfile.NamedTemporaryFile('wb', suffix='.html') as fh:
            fh.write(html)

            cmd = (READABILITY_BIN, fh.name, download.url)
            logger.debug(f'readability cmd: {cmd}')
            return_code, logs, stdout = await self.process_runner(
                download.url,
                cmd,
                pathlib.Path('/home/wrolpi'),
            )
            if return_code == 0:
                readability = json.loads(stdout)
                logger.debug(f'done readability for {download.url}')
                return readability
            else:
                logger.error(f'Failed to extract readability for {download.url}')
                raise RuntimeError(f'Failed to extract readability for {download.url}')

    @staticmethod
    async def do_screenshot_url(download: Download) -> bytes:
        """Use Chromium to get a screenshot of the Download's URL."""
        # Set Chromium to headless.  Use a wide window size so that screenshot will be the "desktop" version of
        # the page.
        options = webdriver.ChromeOptions()
        options.add_argument('headless')
        options.add_argument('disable-gpu')
        options.add_argument('window-size=1280x720')

        driver = webdriver.Chrome(chrome_options=options)
        driver.get(download.url)
        screenshot = driver.get_screenshot_as_png()
        return screenshot

    async def do_archive(self, download: Download) -> Tuple[bytes, dict, bytes]:
        """Use locally installed executables to create an Archive.

        Creates a Singlefile, readability file, and screenshot file.

        @warning: Will not raise errors if readability or screenshot cannot be extracted.
        """
        singlefile = await self.do_singlefile(download)

        if SINGLEFILE_HEADER.encode() not in singlefile[:1000]:
            raise RuntimeError(f'Singlefile created was invalid: {download.url}')

        # Extract Readability from the Singlefile.
        try:
            readability = await self.do_readability(download, singlefile)
        except RuntimeError:
            # Readability is not required.
            readability = None

        screenshot = b''
        try:
            # Screenshot the Singlefile first.
            screenshot = html_screenshot(singlefile)
        except Exception as e:
            logger.error(f'Failed to screenshot file for {download.url}', exc_info=e)

        if not screenshot:
            # Screenshot of singlefile failed.  Download the URL again.
            try:
                screenshot = await self.do_screenshot_url(download)
            except Exception as e:
                # Screenshot failed.
                logger.error(f'Failed to screenshot {download.url}', exc_info=e)

        singlefile_len = len(singlefile) if singlefile else None
        readability_len = len(readability) if readability else None
        screenshot_len = len(screenshot) if screenshot else None
        logger.debug(f'do_archive of {download.url} finished: {singlefile_len=} {readability_len=} {screenshot_len=}')

        return singlefile, readability, screenshot


archive_downloader = ArchiveDownloader()


def model_archive(file_group: FileGroup, session: Session = None) -> Archive:
    file_group_id = file_group.id
    if not file_group_id:
        session.flush([file_group])
        file_group_id = file_group.id

    # All Archives have an HTML Singlefile.
    html_paths = file_group.my_paths('text/html')
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
        session.flush([archive])

        file_group.title = file_group.a_text = title
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

            processed = 0
            for file_group, archive in results:
                processed += 1

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

                with slow_logger(1, f'Modeling archive took %(elapsed)s seconds: {file_group}',
                                 logger__=logger):
                    if archive:
                        archive: Archive
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
