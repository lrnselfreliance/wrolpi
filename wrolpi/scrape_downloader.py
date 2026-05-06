import pathlib
from copy import copy
from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from wrolpi.common import logger, get_html_soup, aiohttp_get
from wrolpi.downloader import Downloader, Download, DownloadContext, DownloadResult
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


@dataclass
class PreparedScrape:
    """Plan produced by ScrapeHTMLDownloader.prepare_download."""
    url: str
    depth: int
    suffix: str           # already lowercased
    max_pages: int
    destination: pathlib.Path


@dataclass
class ExecutedScrape:
    """Output of ScrapeHTMLDownloader.execute_download: URLs collected, plus enough state
    for finalize_download to build the user-facing DownloadResult."""
    download_urls: List[str]
    page_count: int
    max_pages: int
    suffix: str
    destination: pathlib.Path


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

    def prepare_download(self, session: Session, download: Download) -> PreparedScrape:
        """Validate settings and ensure the destination directory exists.

        session is unused here — scrape has no DB work in any phase — but the API still
        requires it.
        """
        if (download.attempts or 0) > 3:
            raise UnrecoverableDownloadError(f'Max download attempts reached for {download.url}')

        settings = download.settings or {}
        depth = settings.get('depth') or 1
        suffix = settings.get('suffix')
        max_pages = settings.get('max_pages') or 100
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

        return PreparedScrape(
            url=download.url,
            depth=depth,
            suffix=suffix.lower(),
            max_pages=max_pages,
            destination=destination,
        )

    async def execute_download(self, prepared: PreparedScrape, ctx: DownloadContext) -> ExecutedScrape:
        """Crawl HTML pages up to depth, collecting links that match the configured suffix."""
        urls = [prepared.url]
        download_urls: List[str] = []
        page_count = 0

        for _ in range(prepared.depth):
            # Copy the found URLs at this depth.  Accumulate all anchors (<a href>) found.
            local_urls = urls.copy()
            urls = list()
            for url in local_urls:
                if page_count >= prepared.max_pages:
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
                    if child_url and child_url.lower().endswith(prepared.suffix):
                        # Found a file that the User requested.
                        logger.info(f'ScrapeHTMLDownloader will download {child_url}')
                        download_urls.append(child_url)
                    else:
                        logger.debug(f'ScrapeHTMLDownloader scraping {child_url}')
                        urls.append(child_url)

        return ExecutedScrape(
            download_urls=download_urls,
            page_count=page_count,
            max_pages=prepared.max_pages,
            suffix=prepared.suffix,
            destination=prepared.destination,
        )

    def finalize_download(self, session: Session, download: Download,
                          executed: ExecutedScrape) -> DownloadResult:
        """Build the DownloadResult.  No DB work; session is unused."""
        if not executed.download_urls:
            return DownloadResult(
                success=False,
                error=f'No files with {executed.suffix} found in {executed.page_count} pages!',
            )

        settings = copy(download.settings) if download.settings else {}
        settings['destination'] = str(executed.destination)  # Use str for json conversion.
        return DownloadResult(
            success=True,
            downloads=executed.download_urls,
            settings=settings,
            error='Reached max page count.' if executed.page_count >= executed.max_pages else None,
            location=f'/files?folders={executed.destination}',
        )


scrape_html_downloader = ScrapeHTMLDownloader()
