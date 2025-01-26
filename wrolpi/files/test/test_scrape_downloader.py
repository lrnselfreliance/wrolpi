from http import HTTPStatus

import mock
import pytest

from wrolpi.dates import Seconds
from wrolpi.downloader import DownloadResult
from wrolpi.files.downloader import FileDownloader
from wrolpi.scrape_downloader import ScrapeHTMLDownloader

EXAMPLE_HTTP = '''
<html>
<body>
    <p><a href="https://example.com/one">ignored</a></p>

    <p><a href="https://example.com/one.pdf">example1</a></p>
    <p><a href="/two.pdf">example2</a></p>
    <p><a href="three.pdf">example3</a></p>
    <p><a href="other.html">example4</a></p>
</body>
</html>
'''


async def fake_fetch_html(self, url: str):
    return EXAMPLE_HTTP


async def fake_file_do_download(*a, **kwargs):
    return DownloadResult(success=True)


async def test_scrape_html_downloader(test_directory, test_session, test_download_manager, assert_download_urls,
                                      await_switches):
    """User can scrape for PDF files."""
    test_download_manager.register_downloader(ScrapeHTMLDownloader())
    test_download_manager.register_downloader(FileDownloader())
    destination = test_directory / 'destination'
    destination.mkdir()

    settings = {
        'depth': 1,
        'suffix': '.PDF',  # Suffix case is ignored.
    }
    test_download_manager.create_download('https://example.com/dir', 'scrape_html', settings=settings,
                                          sub_downloader_name='file', destination=destination)
    assert_download_urls(['https://example.com/dir', ])

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html), \
            mock.patch('wrolpi.files.downloader.FileDownloader.do_download', fake_file_do_download):
        await test_download_manager.wait_for_all_downloads()
        await await_switches()

    assert_download_urls([
        'https://example.com/dir',
        'https://example.com/one.pdf',
        'https://example.com/two.pdf',
        'https://example.com/dir/three.pdf',
    ])


async def test_scrape_html_downloader_html(test_directory, test_session, test_download_manager, assert_download_urls,
                                           await_switches):
    """User can also scrape for HTML files."""
    test_download_manager.register_downloader(ScrapeHTMLDownloader())
    test_download_manager.register_downloader(FileDownloader())

    settings = {'suffix': '.html'}
    test_download_manager.create_download('https://example.com/dir', 'scrape_html', settings=settings,
                                          sub_downloader_name='file', destination=test_directory)
    assert_download_urls(['https://example.com/dir', ])

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html), \
            mock.patch('wrolpi.files.downloader.FileDownloader.do_download', fake_file_do_download):
        await test_download_manager.wait_for_all_downloads()
        await await_switches()

    assert_download_urls([
        'https://example.com/dir',
        'https://example.com/dir/other.html',
    ])


@pytest.mark.asyncio
async def test_scrape_html_downloader_api(async_client, test_session, test_download_manager):
    """Scrape Download cannot be recurring."""
    body = dict(
        urls=['https://example.com'],
        destination='uploads',
        downloader='scrape_html',
        sub_downloader='file',
        frequency=Seconds.week,
        tag_names=[],
        settings=dict(depth=1, max_pages=1, suffix='.mp4'))
    request, response = await async_client.post('/api/download', json=body)
    assert response.status == HTTPStatus.BAD_REQUEST
