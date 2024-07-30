import pathlib
import traceback
from abc import ABC

from wrolpi.common import get_media_directory, logger, get_download_info, \
    download_file, trim_file_name
from wrolpi.db import get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.lib import upsert_file
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

        media_directory = get_media_directory()

        # We don't know where to put the file if we don't have a destination.
        destination = download.settings.get('destination')
        if not destination:
            raise UnrecoverableDownloadError(f'Cannot download the file without a destination')

        # Create the destination only if it is within the media directory.
        destination = pathlib.Path(destination)
        if not str(destination.absolute()).startswith(str(media_directory)):
            raise UnrecoverableDownloadError(f'Cannot download outside media directory!')
        destination.mkdir(parents=True, exist_ok=True)

        info = await get_download_info(download.url)

        # TODO verify that this output_path is exclusive.
        output_path = destination / trim_file_name(info.name)

        try:
            await download_file(download.url, output_path, info)

            with get_db_session(commit=True) as session:
                fg = await upsert_file(output_path, session, download.settings.get('tag_names'))
                location = fg.location

            return DownloadResult(
                success=True,
                location=location,
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
