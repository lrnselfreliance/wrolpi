from http import HTTPStatus
from typing import List

from modules.zim import lib
from wrolpi.common import logger, aiohttp_get, background_task, get_html_soup
from wrolpi.downloader import Downloader, Download, DownloadResult

__all__ = ['KiwixCatalogDownloader', 'KiwixZimDownloader', 'kiwix_zim_downloader', 'kiwix_catalog_downloader']

from wrolpi.files.lib import refresh_files
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


async def fetch_hrefs(url: str) -> List[str]:
    try:
        async with aiohttp_get(url, timeout=20) as response:
            status = response.status
            content = await response.content.read()
        if status != HTTPStatus.OK:
            raise RuntimeError(f'Failed to fetch Zim file catalog: {url}')
    except TimeoutError:
        raise TimeoutError(f'Timeout while fetching Zim file catalog: {url}')

    soup = get_html_soup(content)
    downloads = list()
    for a in soup.find_all('a'):
        downloads.append(a['href'])
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
        zim_directory = lib.get_zim_directory()
        zim_directory.mkdir(parents=True, exist_ok=True)

        output_path = await self.download_file(download.id, download.url, zim_directory)

        # Notify the maintainer if outdated Zim files are lying around.
        lib.flag_outdated_zim_files()

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

        logger.info(f'Successfully downloaded Zim {download.url} to {output_path}')

        # Location is just the generic Kiwix viewer.
        return DownloadResult(success=True, location='/zim')


kiwix_zim_downloader = KiwixZimDownloader()
