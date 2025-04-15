import pathlib
import traceback
from abc import ABC

from wrolpi.common import get_media_directory, logger, TRACE_LEVEL
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError, IgnoredDirectoryError
from wrolpi.files.lib import upsert_file, get_file_location_href
from wrolpi.vars import PYTEST

__all__ = ['FileDownloader', 'file_downloader']

logger = logger.getChild(__name__)


class FileDownloader(Downloader, ABC):
    """A Downloader which can download an arbitrary HTTP file.

    Attempts to use the Content-Disposition name, will fail over to the path name if that's not possible.
    """
    name = 'file'
    pretty_name = 'File'
    listable = False

    def __repr__(self):
        return '<FileDownloader>'

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        settings = download.settings or dict()

        # We don't know where to put the file if we don't have a destination.
        destination = download.destination or settings.get('destination')
        if not destination:
            raise UnrecoverableDownloadError(f'Cannot download the file without a destination')

        if logger.isEnabledFor(TRACE_LEVEL):
            logger.trace(f'FileDownloader: downloading {download.url} to {destination}')

        # Create the destination only if it is within the media directory.
        destination = pathlib.Path(destination).resolve()
        media_directory = get_media_directory()
        if not str(destination).startswith(str(media_directory)):
            raise UnrecoverableDownloadError(f'Cannot download outside media directory!')
        destination.mkdir(parents=True, exist_ok=True)

        output_path = None
        try:
            output_path = await self.download_file(download, download.url, destination)
            fg = await upsert_file(output_path, tag_names=download.tag_names)
            location = fg.location
            return DownloadResult(
                success=True,
                location=location,
            )
        except IgnoredDirectoryError:
            # `upsert_file` says this is an ignored file, that's fine.
            return DownloadResult(
                success=True,
                location=get_file_location_href(output_path)
            )
        except Exception as e:
            logger.error(f'Failed to download {repr(str(download.url))}', exc_info=e)
            if PYTEST:
                raise

            error = str(traceback.format_exc())
            return DownloadResult(
                success=False,
                error=error,
            )


file_downloader = FileDownloader()
