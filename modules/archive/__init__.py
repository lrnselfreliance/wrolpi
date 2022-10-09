import itertools
import json
import pathlib
from abc import ABC
from typing import Tuple, Dict, List

from sqlalchemy.orm import Session

from wrolpi.common import logger, register_modeler, register_after_refresh, limit_concurrent
from wrolpi.db import optional_session, get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.indexers import register_indexer, Indexer
from wrolpi.files.models import File
from wrolpi.vars import PYTEST
from . import lib
from .api import bp  # noqa
from .lib import match_archive_files
from .models import Archive, Domain

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)

__all__ = ['ArchiveDownloader', 'archive_downloader']


class ArchiveDownloader(Downloader, ABC):
    name = 'archive'
    pretty_name = 'Archive'

    def __repr__(self):
        return f'<ArchiveDownloader>'

    @classmethod
    def valid_url(cls, url: str) -> Tuple[bool, None]:
        """
        Archiver will attempt to archive anything, so it should be last!
        """
        return True, None

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        archive = await lib.do_archive(download.url)
        return DownloadResult(success=True, location=f'/archive/{archive.id}')

    @optional_session
    def already_downloaded(self, *urls: List[str], session: Session = None) -> List:
        archives = list(session.query(Archive).filter(Archive.url.in_(urls)))
        return archives


# Archive downloader is the last downloader which should be used.
archive_downloader = ArchiveDownloader(priority=100)


@register_modeler
def archive_modeler(groups: Dict[str, List[File]], session: Session):
    archive_groups = {}
    for stem, group in groups.items():
        if any(lib.is_singlefile_file(i.path) for i in group):
            archive_groups[stem] = group

    count = itertools.cycle(range(101))
    for stem, group in archive_groups.items():
        readability_file, singlefile_file, readability_json_file, readability_txt_file, screenshot_file = \
            match_archive_files(group)
        archive: Archive = Archive.find_by_path(singlefile_file.path, session)
        if not archive:
            archive = Archive(singlefile_file=singlefile_file)
            session.add(archive)
        archive.readability_file = readability_file
        archive.readability_json_file = readability_json_file
        archive.readability_txt_file = readability_txt_file
        archive.screenshot_file = screenshot_file

        if archive.readability_file:
            archive.readability_file.associated = True
            archive.readability_file.do_index()
        if archive.readability_json_file:
            archive.readability_json_file.associated = True
            archive.readability_json_file.do_index()
        if archive.readability_txt_file:
            archive.readability_txt_file.associated = True
            archive.readability_txt_file.do_index()
        if archive.screenshot_file:
            archive.screenshot_file.associated = True
            archive.screenshot_file.do_index()

        archive.singlefile_file.model = Archive.__tablename__

        archive.singlefile_file.do_index()
        archive.validate()

        # Remove this group, it will not be processed by other modelers.
        del groups[stem]

        if next(count) == 100:
            # Commit occasionally.
            session.commit()


@register_after_refresh
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
                if not lib.is_singlefile_file(archive.singlefile_path):
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
        deleted = 0
        for domain in session.query(Domain):
            if domain.id not in domain_ids:
                deleted += 1
                session.delete(domain)


@register_indexer('text/html')
class ArchiveIndexer(Indexer, ABC):

    @staticmethod
    def get_title(file: File):
        singlefile_path: pathlib.Path = file.path.path if hasattr(file.path, 'path') else file.path
        readability_json_path = singlefile_path.with_suffix('.readability.json')
        if readability_json_path.is_file():
            with readability_json_path.open('rt') as fh:
                try:
                    return json.load(fh)['title']
                except Exception:
                    if not PYTEST:
                        logger.warning(f'Archive readability json file exists, but cannot get title. {file}')
                    return None

    @staticmethod
    def get_article(file: File):
        singlefile_path: pathlib.Path = file.path.path if hasattr(file.path, 'path') else file.path
        readability_txt_path = singlefile_path.with_suffix('.readability.txt')
        if readability_txt_path.is_file():
            return readability_txt_path.read_text()

    @classmethod
    def create_index(cls, file: File) -> Tuple:
        """
        Index an Archive file and it's associated files.  This mimetype matches non-archive (non-singlefile) html files,
        so this index will return empty if a readability file is found.

        a = title
        b = <empty>
        c = <empty>
        d = readability article
        """
        if file.path.name.endswith('.readability.html'):
            # Readability files are not the primary Archive file.
            return None, None, None, None
        a = cls.get_title(file)
        d = cls.get_article(file)
        return a, None, None, d
