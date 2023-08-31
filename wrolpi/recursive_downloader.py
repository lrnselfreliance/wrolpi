import pathlib
from http import HTTPStatus
from urllib.parse import urlparse

import bs4

from wrolpi.common import aiohttp_session, logger
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.vars import DEFAULT_HTTP_HEADERS

logger = logger.getChild(__name__)


def resolve_url(parent_url: str, url: str):
    parsed_domain = urlparse(parent_url)

    parsed = urlparse(url)
    if parsed.scheme:
        # URL is absolute.
        return url
    elif parsed.path.startswith('/'):
        return f'{parsed_domain.scheme}://{parsed_domain.netloc}{url}'

    # Assume URL is relative to the parent URL page.
    parent_url = parent_url.rstrip('/')
    return f'{parent_url}/{url}'


class RecursiveHTMLDownloader(Downloader):
    """Recursively downloads HTML pages searching for files with a particular suffix.

    Stops recurring when depth is reached."""

    name = 'recursive_html'
    pretty_name = 'Recursive'
    listable = False

    def __repr__(self):
        return '<RecursiveHTMLDownloader>'

    @staticmethod
    async def fetch_http(url: str) -> str:
        async with aiohttp_session(timeout=60 * 5) as session:
            async with session.get(url, headers=DEFAULT_HTTP_HEADERS) as response:
                logger.debug(f'Got status={response.status} from {url}')
                if response.status == HTTPStatus.OK:
                    return await response.text()

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        urls = [download.url, ]
        download_urls = list()

        depth = download.settings.get('depth') or 1
        suffix = download.settings.get('suffix')
        max_pages = download.settings.get('max_pages') or 100
        destination = download.settings.get('destination')

        if 0 > depth > 10:
            raise UnrecoverableDownloadError('Depth must be between 0 and 100')
        if not suffix:
            raise UnrecoverableDownloadError(f'Suffix must be defined')
        if not destination:
            raise UnrecoverableDownloadError('Destination must be defined')
        destination = pathlib.Path(destination)
        if not destination.is_dir():
            raise UnrecoverableDownloadError(f'Destination does not exist: {destination}')

        page_count = 0

        for i in range(depth):
            # Copy the found URLs at this depth.  Accumulate all anchors (<a href>) found.
            local_urls = urls.copy()
            urls = list()
            for url in local_urls:
                content = await self.fetch_http(url)
                page_count += 1
                if not content:
                    logger.error(f'Failed to download url: {url}')
                    continue

                soup = bs4.BeautifulSoup(content, 'html.parser')
                for a in soup.find_all('a'):
                    try:
                        href: str = a['href']
                    except KeyError:
                        # Not a real anchor.
                        logger.debug(f'Not a real anchor: {a}')
                        continue
                    child_url = resolve_url(url, href)
                    if child_url and child_url.endswith(suffix):
                        # Found a file that the User requested.
                        download_urls.append(child_url)
                    else:
                        urls.append(child_url)
                if page_count >= max_pages:
                    logger.warning('Reached max page count.')
                    break

        if not download_urls:
            return DownloadResult(
                success=False,
                error=f'No files with {suffix} found in {page_count} pages!'
            )

        return DownloadResult(
            success=True,
            downloads=download_urls,
            settings=download.settings,
            error='Reached max page count.' if page_count >= max_pages else None,
            location=f'/files?folders={destination}'
        )


recursive_html_downloader = RecursiveHTMLDownloader()
