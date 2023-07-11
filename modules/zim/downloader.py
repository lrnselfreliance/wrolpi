from http import HTTPStatus
from typing import List

import bs4

from modules.zim import lib
from wrolpi.common import logger, aiohttp_get, get_download_info, download_file, background_task
from wrolpi.downloader import Downloader, Download, DownloadResult

__all__ = ['KiwixCatalogDownloader', 'KiwixZimDownloader', 'kiwix_zim_downloader', 'kiwix_catalog_downloader']

from wrolpi.files.lib import refresh_files
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


async def fetch_hrefs(url: str) -> List[str]:
    content, status = await aiohttp_get(url, timeout=20)
    if status != HTTPStatus.OK:
        raise RuntimeError(f'Failed to fetch file catalog')

    soup = bs4.BeautifulSoup(content, 'html.parser')
    downloads = list()
    for a_ in soup.find_all('a'):
        downloads.append(a_['href'])
    return downloads


class KiwixCatalogDownloader(Downloader):
    """
    Downloads the catalog of Zim files from Kiwix.  Searches for the latest Zim that matches the provided URL.

    If a newer file exists and has not been downloaded, schedule a Download.
    """

    name = 'kiwix_catalog'
    listable = False

    async def do_download(self, download: Download) -> DownloadResult:
        url = download.url

        # Get the parent directory of the file to be downloaded
        *parents, name = url.split('/')
        parent_url = '/'.join(parents)

        # Find the latest Zim that has the correct name.
        downloadable_files = await fetch_hrefs(parent_url)
        matching_zims = sorted([i for i in downloadable_files if i.startswith(name) and i.endswith('.zim')])
        if not matching_zims:
            return DownloadResult(success=False, error=f'No Zim files match {str(repr(url))}')

        logger.debug(f'Found matching Zims: {matching_zims}')
        latest_zim = f'{parent_url}/{matching_zims[-1]}'

        return DownloadResult(
            success=True,
            downloads=[latest_zim, ],
        )


kiwix_catalog_downloader = KiwixCatalogDownloader()


class KiwixZimDownloader(Downloader):
    """Downloads a Zim file to the zim directory."""
    name = 'kiwix_zim'
    listable = False

    async def do_download(self, download: Download) -> DownloadResult:
        url = download.url

        download_info = await get_download_info(url)

        zim_directory = lib.get_zim_directory()
        zim_directory.mkdir(parents=True, exist_ok=True)
        output_path = zim_directory / f'{download_info.name}'

        if output_path.is_file():
            output_size = output_path.stat().st_size
            if download_info.size and download_info.size == output_size:
                # File is already downloaded.
                return DownloadResult(success=True)

        logger.info(f'Downloading Zim {url} to {output_path} of size {download_info.size}')
        await download_file(url, output_path=output_path, info=download_info)

        # Notify the maintainer if outdated Zim files are lying around.
        lib.flag_outdated_zim_files()

        output_size = output_path.stat().st_size
        if download_info.size and output_size != download_info.size:
            return DownloadResult(
                success=False,
                error=f'Download size does not match: {output_size} != {download_info.size}')

        return_code = await lib.check_zim(output_path)
        if return_code == 127:
            logger.warning(f'Not validating {output_path} because zimcheck is not installed')
        elif return_code > 0:
            return DownloadResult(success=False, error=f'Zim file is invalid')

        # Add the new Zim to the FileGroups, model it.
        if PYTEST:
            await refresh_files([output_path, ])
        else:
            background_task(refresh_files([output_path, ]))

        # Restart Kiwix serve, so it finds the new zim file.
        return_code = await lib.restart_kiwix()
        if return_code != 0:
            logger.error(f'Failed to restart kiwix')

        # Location is just the generic Kiwix viewer.
        return DownloadResult(success=True, location='/zim')


kiwix_zim_downloader = KiwixZimDownloader()
