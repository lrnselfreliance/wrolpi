import pathlib
import traceback
from abc import ABC
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from wrolpi.common import get_media_directory, logger
from wrolpi.downloader import Downloader, Download, DownloadContext, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError, IgnoredDirectoryError
from wrolpi.files.lib import upsert_file, get_file_location_href
from wrolpi.log_levels import TRACE_LEVEL
from wrolpi.vars import PYTEST

__all__ = ['FileDownloader', 'PreparedFile', 'ExecutedFile', 'file_downloader']

logger = logger.getChild(__name__)


@dataclass
class PreparedFile:
    """Plan produced by FileDownloader.prepare_download.  Destination is absolute, has been
    bounded to the media directory, and exists on disk."""
    url: str
    destination: pathlib.Path


@dataclass
class ExecutedFile:
    """Output of FileDownloader.execute_download.

    `location` is set when the FileGroup was registered (or when the file landed in an
    ignored directory and we still want to expose a /files?... href).  `error` carries
    the formatted traceback when the download or upsert failed in a recoverable way.
    """
    output_path: pathlib.Path
    location: Optional[str] = None
    error: Optional[str] = None


class FileDownloader(Downloader, ABC):
    """A Downloader which can download an arbitrary HTTP file.

    Attempts to use the Content-Disposition name, will fail over to the path name if that's not possible.
    """
    name = 'file'
    pretty_name = 'File'
    listable = False

    def __repr__(self):
        return '<FileDownloader>'

    def prepare_download(self, session: Session, download: Download) -> PreparedFile:
        """Validate attempt cap, resolve destination, ensure it sits inside the media
        directory, and create it if missing.  session is unused — FileDownloader has no
        DB work in its prep or finalize phases."""
        if (download.attempts or 0) > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        settings = download.settings or dict()

        # We don't know where to put the file if we don't have a destination.
        destination = download.destination or settings.get('destination')
        if not destination:
            raise UnrecoverableDownloadError(f'Cannot download the file without a destination')

        if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
            logger.trace(f'FileDownloader: downloading {download.url} to {destination}')

        # Create the destination only if it is within the media directory.
        destination = pathlib.Path(destination).resolve()
        media_directory = get_media_directory()
        if not str(destination).startswith(str(media_directory)):
            raise UnrecoverableDownloadError(f'Cannot download outside media directory!')
        destination.mkdir(parents=True, exist_ok=True)

        return PreparedFile(url=download.url, destination=destination)

    async def execute_download(self, prepared: PreparedFile, ctx: DownloadContext,
                               download: Download = None) -> ExecutedFile:
        """Drive aria2c via the parent's download_file helper, threading ctx through so
        cancellation is observed by process_runner.  Then register the resulting file via
        upsert_file.

        Note: upsert_file (wrolpi/files/lib.py:1752) opens its own DB session because
        non-downloader callers (api.py:508, modules/zim/downloader.py:110) also use it.
        Splitting upsert_file is a separate future PR; for now finalize_download just
        translates ExecutedFile into a DownloadResult.
        """
        # download_file reads .id (for progress) and .url (for log messages).  Production
        # gets the real Download from the dispatch; tests may bypass and construct a stub.
        download = download if download is not None else Download(url=prepared.url)

        output_path = None
        try:
            output_path = await self.download_file(download, prepared.url, prepared.destination, ctx=ctx)
            fg = await upsert_file(output_path, tag_names=download.tag_names)
            return ExecutedFile(output_path=output_path, location=fg.location)
        except IgnoredDirectoryError:
            # `upsert_file` says this is an ignored file, that's fine.
            return ExecutedFile(
                output_path=output_path,
                location=get_file_location_href(output_path),
            )
        except Exception as e:
            logger.error(f'Failed to download {repr(str(prepared.url))}', exc_info=e)
            if PYTEST:
                raise
            return ExecutedFile(output_path=output_path, error=str(traceback.format_exc()))

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedFile) -> DownloadResult:
        """Translate the ExecutedFile into a DownloadResult.  No DB work; session is unused."""
        if executed.error:
            return DownloadResult(success=False, error=executed.error)
        return DownloadResult(success=True, location=executed.location)


file_downloader = FileDownloader()
