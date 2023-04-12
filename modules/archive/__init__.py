import asyncio
import json
from abc import ABC
from typing import Tuple, List

from sqlalchemy import not_
from sqlalchemy.orm import Session

from wrolpi.common import logger, register_modeler, register_refresh_cleanup, limit_concurrent, split_lines_by_length, \
    slow_logger
from wrolpi.db import optional_session, get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError, InvalidArchive
from wrolpi.files.models import FileGroup
from wrolpi.vars import PYTEST
from . import lib
from .api import bp  # noqa
from .lib import is_singlefile_file, get_title_from_html
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

        archive: Archive = await lib.do_archive(download.url)

        if download.settings and (tag_names := download.settings.get('tag_names')):
            for name in tag_names:
                archive.add_tag(name)

            if session := Session.object_session(archive):
                session.commit()

        return DownloadResult(success=True, location=f'/archive/{archive.id}')

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None) -> List:
        archives = list(session.query(Archive).filter(Archive.url.in_(urls)))
        return archives


# Archive downloader is the last downloader which should be used.
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
            'archive_datetime': archive.archive_datetime,
            'domain': archive.domain.domain if archive.domain else None,
            'readability_json_path': archive.readability_json_path,
            'readability_path': archive.readability_path,
            'readability_txt_path': archive.readability_txt_path,
            'screenshot_path': archive.screenshot_path,
            'singlefile_path': archive.singlefile_path,
            'url': archive.url,
        }

        return archive
    except Exception as e:
        logger.error(f'Failed to model Archive {file_group}', exc_info=e)
        if PYTEST:
            raise


@register_modeler
async def archive_modeler():
    invalid_archives = set()

    while True:
        with get_db_session(commit=True) as session:
            results = session.query(FileGroup, Archive) \
                .filter(
                # Get all groups that contain a PDF that have not been indexed.
                FileGroup.indexed != True,
                FileGroup.mimetype == 'text/html',
            ).filter(not_(FileGroup.id.in_(list(invalid_archives)))) \
                .outerjoin(Archive, Archive.file_group_id == FileGroup.id) \
                .limit(20)

            processed = 0
            for file_group, archive in results:
                processed += 1

                with slow_logger(1, f'Modeling archive took %(elapsed)s seconds: {file_group}', logger__=logger):
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
                            # May not be a real Singlefile archive.
                            pass

                # Even if indexing fails, we mark it as indexed.  We won't retry indexing this.
                file_group.indexed = True

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
    # Process all Archives that have not been validated.  Delete any that no longer exist, or are not real Archives.
    # Validate all other Archives.
    logger.info('Searching for invalid Archives')
    offset = 0
    limit = 100
    while True:
        with get_db_session(commit=True) as session:
            archives: List[Archive] = session.query(Archive).order_by(Archive.id).limit(limit).offset(offset)
            processed = 0
            deleted = 0
            for archive in archives:
                processed += 1
                singlefile_path = archive.singlefile_path
                if not singlefile_path:
                    archive.file_group.model = None
                    session.delete(archive)
                    deleted += 1
                    continue
                if not lib.is_singlefile_file(singlefile_path):
                    # Archive is not a real archive.
                    archive.singlefile_file.model = None
                    session.delete(archive)
                    deleted += 1
            if processed < limit:
                # Validated all archives.
                break
            offset += (limit - deleted)

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
