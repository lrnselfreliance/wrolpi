from abc import ABC

from wrolpi.common import logger
from wrolpi.downloader import Downloader, Download
from wrolpi.errors import UnrecoverableDownloadError
from . import lib
from .api import bp  # noqa

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)


class ArchiveDownloader(Downloader, ABC):
    @staticmethod
    def valid_url(url: str) -> bool:
        """
        Archiver will attempt to archive anything, so it should be last!
        """
        return True

    def do_download(self, download: Download):
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        lib.new_archive(download.url, sync=True)
        return True


# Archive downloader is the last downloader which should be used.
archive_downloader = ArchiveDownloader(priority=100)
