import pathlib
from dataclasses import dataclass
from http import HTTPStatus
from typing import List, Optional

from sqlalchemy.orm import Session

from modules.zim import lib
from wrolpi.common import logger, aiohttp_get, get_html_soup
from wrolpi.downloader import Downloader, Download, DownloadContext, DownloadResult

__all__ = [
    'KiwixCatalogDownloader', 'KiwixZimDownloader',
    'PreparedKiwixCatalog', 'ExecutedKiwixCatalog',
    'PreparedKiwixZim', 'ExecutedKiwixZim',
    'kiwix_zim_downloader', 'kiwix_catalog_downloader',
]

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


# ---------------------------------------------------------------------------
# KiwixCatalogDownloader
# ---------------------------------------------------------------------------


@dataclass
class PreparedKiwixCatalog:
    """Plan produced by KiwixCatalogDownloader.prepare_download.

    Splits the URL into the parent listing URL and the basename prefix used to match
    Zim files in that listing.
    """
    url: str
    parent_url: str
    name: str


@dataclass
class ExecutedKiwixCatalog:
    """Output of KiwixCatalogDownloader.execute_download.

    `latest_zim_url` is None when the listing contained no matching files; finalize
    converts that into a failure DownloadResult.
    """
    latest_zim_url: Optional[str]


class KiwixCatalogDownloader(Downloader):
    """
    Downloads the catalog of Zim files from Kiwix.  Searches for the latest Zim that matches the provided URL.

    If a newer file exists and has not been downloaded, schedule a Download.
    """

    name = 'kiwix_catalog'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedKiwixCatalog:
        """Split the download URL into the parent listing URL and the basename prefix."""
        url = download.url
        *parents, name = url.split('/')
        parent_url = '/'.join(parents)
        return PreparedKiwixCatalog(url=url, parent_url=parent_url, name=name)

    async def execute_download(self, prepared: PreparedKiwixCatalog, ctx: DownloadContext,
                               download: Download = None) -> ExecutedKiwixCatalog:
        """Fetch the parent directory listing and pick the latest matching Zim."""
        downloadable_files = await fetch_hrefs(prepared.parent_url)
        matching_zims = sorted([i for i in downloadable_files
                                if i.startswith(prepared.name) and i.endswith('.zim')])
        if not matching_zims:
            return ExecutedKiwixCatalog(latest_zim_url=None)

        logger.debug(f'Found matching Zims: {matching_zims}')
        return ExecutedKiwixCatalog(latest_zim_url=f'{prepared.parent_url}/{matching_zims[-1]}')

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedKiwixCatalog) -> DownloadResult:
        if executed.latest_zim_url is None:
            return DownloadResult(success=False, error=f'No Zim files match {str(repr(download.url))}')
        return DownloadResult(success=True, downloads=[executed.latest_zim_url])


kiwix_catalog_downloader = KiwixCatalogDownloader()


# ---------------------------------------------------------------------------
# KiwixZimDownloader
# ---------------------------------------------------------------------------


@dataclass
class PreparedKiwixZim:
    """Plan produced by KiwixZimDownloader.prepare_download: zim_directory exists on disk."""
    url: str
    zim_directory: pathlib.Path


@dataclass
class ExecutedKiwixZim:
    """Output of KiwixZimDownloader.execute_download.

    `is_valid` is False when zimcheck flagged the file as corrupt; finalize turns that
    into a failure DownloadResult.  When zimcheck is not installed (FileNotFoundError),
    we treat the file as valid (matching legacy behaviour).
    """
    output_path: pathlib.Path
    is_valid: bool


class KiwixZimDownloader(Downloader):
    """Downloads a Zim file to the zim directory."""
    name = 'kiwix_zim'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedKiwixZim:
        zim_directory = lib.get_zim_directory()
        zim_directory.mkdir(parents=True, exist_ok=True)
        return PreparedKiwixZim(url=download.url, zim_directory=zim_directory)

    async def execute_download(self, prepared: PreparedKiwixZim, ctx: DownloadContext,
                               download: Download = None) -> ExecutedKiwixZim:
        """Download the Zim file, flag any outdated zims, validate via zimcheck, and
        register the new file via upsert_file when valid.

        Note: lib.flag_outdated_zim_files (sets a Sanic flag) and upsert_file (opens its
        own DB session) are pre-existing side effects we keep on the post-download path.
        Splitting upsert_file is a future PR shared with the FileDownloader migration.
        """
        download = download if download is not None else Download(url=prepared.url)
        output_path = await self.download_file(download, prepared.url, prepared.zim_directory, ctx=ctx)

        # Notify the maintainer if outdated Zim files are lying around.
        lib.flag_outdated_zim_files()

        is_valid = True
        try:
            return_code = await lib.check_zim(output_path)
            if return_code > 0:
                # zimcheck ran, but the file is invalid.
                is_valid = False
        except FileNotFoundError:
            logger.warning(f'Not validating {output_path} because zimcheck is not installed')

        if is_valid:
            # Add the new Zim to the FileGroups, model it.
            # The model_zim() function triggers a Kiwix restart via switch when a new Zim is created.
            await upsert_file(output_path)
            logger.info(f'Successfully downloaded Zim {prepared.url} to {output_path}')

        return ExecutedKiwixZim(output_path=output_path, is_valid=is_valid)

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedKiwixZim) -> DownloadResult:
        if not executed.is_valid:
            return DownloadResult(success=False, error='Zim file is invalid')
        # Location is just the generic Kiwix viewer.
        return DownloadResult(success=True, location='/zim')


kiwix_zim_downloader = KiwixZimDownloader()
