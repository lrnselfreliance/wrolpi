from abc import ABC
from typing import Tuple

from wrolpi.common import logger
from wrolpi.downloader import Downloader, Download
from wrolpi.errors import UnrecoverableDownloadError
from . import lib
from .api import bp  # noqa

PRETTY_NAME = 'Archive'

logger = logger.getChild(__name__)


class ArchiveDownloader(Downloader, ABC):
    @classmethod
    def valid_url(cls, url: str) -> Tuple[bool, None]:
        """
        Archiver will attempt to archive anything, so it should be last!
        """
        return True, None

    def do_download(self, download: Download):
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        lib.new_archive(download.url, sync=True)
        return True


# Archive downloader is the last downloader which should be used.
archive_downloader = ArchiveDownloader('archive', priority=100)
