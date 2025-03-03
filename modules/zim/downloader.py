from http import HTTPStatus
from typing import List

from modules.zim import lib
from wrolpi.common import logger, aiohttp_get, get_html_soup
from wrolpi.downloader import Downloader, Download, DownloadResult

__all__ = ['KiwixCatalogDownloader', 'KiwixZimDownloader', 'kiwix_zim_downloader', 'kiwix_catalog_downloader']

from wrolpi.files.lib import upsert_file
from wrolpi.vars import DOWNLOAD_USER_AGENT

logger = logger.getChild(__name__)

# Headers to use when issuing Kiwix HTTP requests.
headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    'dnt': '1',
    'priority': 'u=0, i',
    'sec-ch-ua': '"Chromium";v="129", "Not=A?Brand";v="8"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'sec-gpc': '1',
    'upgrade-insecure-requests': '1',
    'user-agent': DOWNLOAD_USER_AGENT,
}


async def fetch_hrefs(url: str) -> List[str]:
    try:
        async with aiohttp_get(url, headers=headers, timeout=20) as response:
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

        output_path = await self.download_file(download, download.url, zim_directory)

        # Notify the maintainer if outdated Zim files are lying around.
        lib.flag_outdated_zim_files()

        try:
            return_code = await lib.check_zim(output_path)
            if return_code > 0:
                # zimcheck ran, but the file is invalid.
                return DownloadResult(success=False, error=f'Zim file is invalid')
        except FileNotFoundError:
            logger.warning(f'Not validating {output_path} because zimcheck is not installed')

        # Add the new Zim to the FileGroups, model it.
        await upsert_file(output_path)

        # Restart Kiwix serve, so it finds the new zim file.
        return_code = await lib.restart_kiwix()
        if return_code != 0:
            logger.error(f'Failed to restart kiwix')

        logger.info(f'Successfully downloaded Zim {download.url} to {output_path}')

        # Location is just the generic Kiwix viewer.
        return DownloadResult(success=True, location='/zim')


kiwix_zim_downloader = KiwixZimDownloader()
