import asyncio
import pathlib
import re
import traceback
from abc import ABC
from dataclasses import dataclass
from http import HTTPStatus
from typing import List
from urllib.parse import urlparse

import aiohttp

from wrolpi.common import get_media_directory, logger, background_task
from wrolpi.db import get_db_session
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError

__all__ = ['get_download_info', 'download_file', 'FileDownloader', 'file_downloader']

from wrolpi.files.models import FileGroup

from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


@dataclass
class DownloadFileInfo:
    name: str = None
    size: int = None
    type: str = None
    accept_ranges: str = None


FILENAME_MATCHER = re.compile(r'.*filename="(.*)"')


async def get_download_info(url: str, timeout: int = 60) -> DownloadFileInfo:
    """Gets information (name, size, etc.) about a downloadable file at the provided URL."""
    timeout = aiohttp.ClientTimeout(total=timeout) if timeout is not None else None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.head(url) as response:
            info = DownloadFileInfo(
                type=response.headers.get('Content-Type'),
                size=int(response.headers['Content-Length']) * 8 if 'Content-Length' in response.headers else None,
                accept_ranges=response.headers.get('Accept-Ranges'),
            )

            disposition = response.headers.get('Content-Disposition')

            if disposition and 'filename' in disposition:
                if (match := FILENAME_MATCHER.match(disposition)) and (groups := match.groups()):
                    info.name = groups[0]
            else:
                # No Content-Disposition with filename, use the URL name.
                parsed = urlparse(url)
                info.name = parsed.path.split('/')[-1]

            return info


async def download_file(url: str, info: DownloadFileInfo, output_path: pathlib.Path):
    """Uses aiohttp to download an HTTP file.

    Attempts to resume the file if `output_path` already exists.
    """
    logger.debug(f'Starting download of file {repr(str(url))}')

    if output_path.is_file() and info.size == (output_path.stat().st_size * 8):
        logger.warning(f'Already downloaded {repr(str(url))} to {repr(str(output_path))}')
        return

    if info.accept_ranges == 'bytes' or not output_path.is_file():
        with open(output_path, 'ab') as fh:
            headers = dict()
            # Check the position of append, if it is 0 then we do not need to resume.
            position = fh.tell()
            if position:
                headers['Range'] = f'bytes={position}-'

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                        logger.warning(f'Server responded with 416, file is probably already downloaded')
                        return

                    if position and response.status != HTTPStatus.PARTIAL_CONTENT:
                        raise UnrecoverableDownloadError(
                            f'Tried to resume {repr(str(url))} but got status {response.status}')

                    # May or may not be using Range.  Append each chunk to the output file.
                    async for data in response.content.iter_any():
                        fh.write(data)

                        # TODO this cannot be canceled.
                        # Sleep to catch cancel.
                        await asyncio.sleep(0)
    elif output_path.is_file():
        # TODO support downloading files that cannot be resumed.
        raise UnrecoverableDownloadError(f'Cannot resume download {url}')


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
        output_path = destination / info.name

        try:
            await download_file(download.url, info, output_path)
            background_task(save_and_tag(output_path, download.settings.get('tag_names')))

            return DownloadResult(
                success=True,
                location=f'/download/{output_path.relative_to(media_directory)}'
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


async def save_and_tag(file: pathlib.Path, tag_names: List[str] = None):
    """Stores the file as a FileGroup.  Applies any provided Tags to the FileGroup."""
    from wrolpi.tags import Tag

    tag_names = tag_names or list()

    with get_db_session(commit=True) as session:
        file_group = FileGroup.find_by_path(file)
        if not file_group:
            file_group = FileGroup.from_paths(session, file)
            session.commit()

        if tag_names:
            tags = session.query(Tag).filter(Tag.name.in_(tag_names))
            for tag in tags:
                file_group.add_tag(tag)


file_downloader = FileDownloader()
