import pathlib
from copy import copy
from urllib.parse import urlparse

from wrolpi.common import logger, get_html_soup, aiohttp_get
from wrolpi.downloader import Downloader, Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError

logger = logger.getChild(__name__)


def resolve_url(parent_url: str, url: str):
    parsed_domain = urlparse(parent_url)

    parsed = urlparse(url)
    if parsed.scheme:
        # URL is complete or external.
        return url
    elif parsed.path.startswith('/'):
        # URL is absolute from domain.
        return f'{parsed_domain.scheme}://{parsed_domain.netloc}{url}'

    # Assume URL is relative to the parent URL page.
    parent_url = parent_url.rstrip('/')
    return f'{parent_url}/{url}'


class ScrapeHTMLDownloader(Downloader):
    """Scrape downloads HTML pages searching for files with a particular suffix.

    Stops recurring when depth is reached."""

    name = 'scrape_html'
    pretty_name = 'Scrape'
    listable = False

    def __repr__(self):
        return '<ScrapeHTMLDownloader>'

    @staticmethod
    async def fetch_html(url: str) -> str:
        async with aiohttp_get(url, timeout=60 * 5) as response:
            return await response.text()

    async def do_download(self, download: Download) -> DownloadResult:
        if download.attempts > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        urls = [download.url, ]
        download_urls = list()

        depth = download.settings.get('depth') or 1
        suffix = download.settings.get('suffix')
        max_pages = download.settings.get('max_pages') or 100
        destination = download.destination

        if 0 > depth > 10:
            raise UnrecoverableDownloadError('Depth must be between 0 and 100')
        if not suffix:
            raise UnrecoverableDownloadError(f'Suffix must be defined')
        if not destination:
            raise UnrecoverableDownloadError('Destination must be defined')
        destination = pathlib.Path(destination)
        if not destination.is_dir():
            destination.mkdir(parents=True)

        suffix = suffix.lower()

        page_count = 0

        for i in range(depth):
            # Copy the found URLs at this depth.  Accumulate all anchors (<a href>) found.
            local_urls = urls.copy()
            urls = list()
            for url in local_urls:
                if page_count >= max_pages:
                    logger.warning('Reached max page count.')
                    break

                # Get the HTML of the URL.
                content = await self.fetch_html(url)
                page_count += 1
                if not content:
                    logger.error(f'Failed to download url: {url}')
                    continue

                # Find all anchors, search for matching files, and more URLs to search.
                try:
                    soup = get_html_soup(content)
                except Exception as e:
                    logger.error(f'Failed to parse HTML from {url}', exc_info=e)
                    continue

                for a in soup.find_all('a'):
                    try:
                        href: str = a['href']
                    except KeyError:
                        # Not a real anchor.
                        logger.debug(f'Not a real anchor: {a}')
                        continue
                    child_url = resolve_url(url, href)
                    if child_url and child_url.lower().endswith(suffix):
                        # Found a file that the User requested.
                        logger.info(f'ScrapeHTMLDownloader will download {child_url}')
                        download_urls.append(child_url)
                    else:
                        logger.debug(f'ScrapeHTMLDownloader scraping {child_url}')
                        urls.append(child_url)

        if not download_urls:
            return DownloadResult(
                success=False,
                error=f'No files with {suffix} found in {page_count} pages!'
            )

        settings = copy(download.settings)
        settings['destination'] = str(download.destination)  # Use str for json conversion.
        return DownloadResult(
            success=True,
            downloads=download_urls,
            settings=settings,
            error='Reached max page count.' if page_count >= max_pages else None,
            location=f'/files?folders={destination}'
        )


scrape_html_downloader = ScrapeHTMLDownloader()
