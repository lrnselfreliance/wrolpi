from abc import ABC
from typing import Tuple

from wrolpi.common import logger
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from . import lib
from .api import bp  # noqa

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)


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

    def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        archive = lib.do_archive(download.url)
        return DownloadResult(success=True, location=f'/archive/{archive.id}')


# Archive downloader is the last downloader which should be used.
archive_downloader = ArchiveDownloader(priority=100)
