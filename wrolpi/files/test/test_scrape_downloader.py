from http import HTTPStatus

import mock
import pytest

from wrolpi.dates import Seconds
from wrolpi.downloader import Download, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.downloader import FileDownloader
from wrolpi.scrape_downloader import (
    ExecutedScrape,
    PreparedScrape,
    ScrapeHTMLDownloader,
    scrape_html_downloader,
)

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
    test_download_manager.create_download(test_session, 'https://example.com/dir', 'scrape_html', settings=settings,
                                          sub_downloader_name='file', destination=destination)
    assert_download_urls(['https://example.com/dir', ])

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html), \
            mock.patch('wrolpi.files.downloader.FileDownloader.execute_download', fake_file_do_download):
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
    test_download_manager.create_download(test_session, 'https://example.com/dir', 'scrape_html', settings=settings,
                                          sub_downloader_name='file', destination=test_directory)
    assert_download_urls(['https://example.com/dir', ])

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html), \
            mock.patch('wrolpi.files.downloader.FileDownloader.execute_download', fake_file_do_download):
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


# ---------------------------------------------------------------------------
# Phase-split unit tests.
#
# These exercise prepare_download / execute_download / finalize_download in
# isolation — no async_client, no test_download_manager, no
# wait_for_all_downloads polling.  They reuse make_test_ctx from the archive
# conftest so we don't need to duplicate the helper.
# ---------------------------------------------------------------------------

from modules.archive.conftest import make_test_ctx  # noqa: E402


def test_prepare_max_attempts_raises(test_session):
    """prepare_download enforces the attempt cap before any I/O."""
    download = Download(
        url='https://example.com/x',
        downloader='scrape_html',
        attempts=4,
        destination='/tmp/dest',
        settings={'suffix': '.pdf'},
    )

    with pytest.raises(UnrecoverableDownloadError):
        scrape_html_downloader.prepare_download(test_session, download)


def test_prepare_requires_suffix(test_session, test_directory):
    """Missing settings['suffix'] is unrecoverable."""
    download = Download(
        url='https://example.com/x',
        downloader='scrape_html',
        destination=str(test_directory / 'dest'),
        settings={},
    )

    with pytest.raises(UnrecoverableDownloadError, match='Suffix'):
        scrape_html_downloader.prepare_download(test_session, download)


def test_prepare_requires_destination(test_session):
    """Missing destination is unrecoverable."""
    download = Download(
        url='https://example.com/x',
        downloader='scrape_html',
        settings={'suffix': '.pdf'},
    )

    with pytest.raises(UnrecoverableDownloadError, match='Destination'):
        scrape_html_downloader.prepare_download(test_session, download)


def test_prepare_lowercases_suffix_and_creates_destination(test_session, test_directory):
    """Suffix is normalised to lowercase and the destination directory is created."""
    dest = test_directory / 'new_dest'
    assert not dest.exists()
    download = Download(
        url='https://example.com/x',
        downloader='scrape_html',
        destination=str(dest),
        settings={'suffix': '.PDF', 'depth': 2, 'max_pages': 50},
    )

    prepared = scrape_html_downloader.prepare_download(test_session, download)

    assert isinstance(prepared, PreparedScrape)
    assert prepared.suffix == '.pdf'
    assert prepared.depth == 2
    assert prepared.max_pages == 50
    assert prepared.destination == dest
    assert dest.is_dir()


@pytest.mark.asyncio
async def test_execute_collects_matching_urls(test_directory):
    """execute_download walks pages and returns URLs matching the suffix.  No DB,
    no Sanic, no DownloadManager — the I/O phase is fully isolated."""
    prepared = PreparedScrape(
        url='https://example.com/dir',
        depth=1,
        suffix='.pdf',
        max_pages=100,
        destination=test_directory,
    )

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html):
        executed = await scrape_html_downloader.execute_download(prepared, make_test_ctx())

    assert isinstance(executed, ExecutedScrape)
    assert sorted(executed.download_urls) == sorted([
        'https://example.com/one.pdf',
        'https://example.com/two.pdf',
        'https://example.com/dir/three.pdf',
    ])
    assert executed.page_count == 1
    assert executed.suffix == '.pdf'


@pytest.mark.asyncio
async def test_execute_respects_max_pages(test_directory):
    """max_pages caps the crawl; deeper pages are skipped after the limit."""
    prepared = PreparedScrape(
        url='https://example.com/dir',
        depth=3,
        suffix='.html',          # links to other.html mean each page yields more pages
        max_pages=1,
        destination=test_directory,
    )

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', fake_fetch_html):
        executed = await scrape_html_downloader.execute_download(prepared, make_test_ctx())

    assert executed.page_count == 1
    assert executed.max_pages == 1
    # Only the first page was crawled, but its other.html link should still be collected.
    assert 'https://example.com/dir/other.html' in executed.download_urls


def test_finalize_returns_failure_when_no_urls_found(test_session, test_directory):
    """No matching URLs → DownloadResult with success=False and a descriptive error."""
    executed = ExecutedScrape(
        download_urls=[],
        page_count=5,
        max_pages=100,
        suffix='.pdf',
        destination=test_directory,
    )
    download = Download(url='https://example.com/x', downloader='scrape_html', settings={'suffix': '.pdf'})

    result = scrape_html_downloader.finalize_download(test_session, download, executed)

    assert result.success is False
    assert '.pdf' in (result.error or '')
    assert '5 pages' in (result.error or '')


def test_finalize_returns_success_with_downloads_and_settings(test_session, test_directory):
    """Populated executed → success result; settings get destination injected; max_pages
    triggers the warning."""
    executed = ExecutedScrape(
        download_urls=['https://example.com/a.pdf', 'https://example.com/b.pdf'],
        page_count=10,
        max_pages=10,            # equal to page_count → warning is set
        suffix='.pdf',
        destination=test_directory / 'dest',
    )
    download = Download(
        url='https://example.com/x',
        downloader='scrape_html',
        settings={'suffix': '.pdf', 'depth': 1},
    )

    result = scrape_html_downloader.finalize_download(test_session, download, executed)

    assert result.success is True
    assert result.downloads == executed.download_urls
    assert result.settings['destination'] == str(executed.destination)
    assert result.settings['suffix'] == '.pdf'    # original setting preserved
    assert result.error == 'Reached max page count.'
    assert result.location == f'/files?folders={executed.destination}'


# ---------------------------------------------------------------------------
# render_js (real-browser crawl) tests.  PYTEST routes crawl() through the archive
# service client (_request_crawl), which is mocked here — no real browser runs.
# ---------------------------------------------------------------------------


async def fake_crawl(self, prepared, ctx, download=None):
    return {
        'found_urls': ['https://example.com/a.mp4', 'https://example.com/sub/b.mp4'],
        'pages_visited': 3,
        'capped': False,
    }


def test_prepare_sets_render_js(test_session, test_directory):
    """render_js setting flows into PreparedScrape (default False when absent)."""
    dest = test_directory / 'dest'
    base = dict(url='https://example.com/x', downloader='scrape_html', destination=str(dest))

    off = scrape_html_downloader.prepare_download(test_session, Download(settings={'suffix': '.mp4'}, **base))
    assert off.render_js is False

    on = scrape_html_downloader.prepare_download(
        test_session, Download(settings={'suffix': '.mp4', 'render_js': True}, **base))
    assert on.render_js is True


@pytest.mark.asyncio
async def test_execute_render_js_uses_crawl(test_directory):
    """With render_js, execute_download returns the crawl's found_urls and ignores raw fetch_html."""
    prepared = PreparedScrape(
        url='https://example.com/dir',
        depth=2,
        suffix='.mp4',
        max_pages=100,
        destination=test_directory,
        render_js=True,
    )

    async def boom(self, url):
        raise AssertionError('fetch_html must not be called when render_js is enabled')

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.crawl', fake_crawl), \
            mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.fetch_html', boom):
        executed = await scrape_html_downloader.execute_download(prepared, make_test_ctx())

    assert isinstance(executed, ExecutedScrape)
    assert sorted(executed.download_urls) == ['https://example.com/a.mp4', 'https://example.com/sub/b.mp4']
    assert executed.page_count == 3
    assert executed.suffix == '.mp4'


@pytest.mark.asyncio
async def test_crawl_routes_to_archive_service_under_pytest(test_directory):
    """Under PYTEST the crawl() seam calls the archive-service client, not a local browser."""
    prepared = PreparedScrape(
        url='https://example.com/dir', depth=1, suffix='.mp4', max_pages=5,
        destination=test_directory, render_js=True,
    )
    expected = {'found_urls': ['https://example.com/x.mp4'], 'pages_visited': 1, 'capped': False}

    async def fake_request_crawl(p):
        assert p is prepared
        return expected

    with mock.patch('wrolpi.scrape_downloader._request_crawl', fake_request_crawl):
        result = await scrape_html_downloader.crawl(prepared, make_test_ctx())

    assert result == expected


async def test_render_js_end_to_end(test_directory, test_session, test_download_manager, assert_download_urls,
                                    await_switches):
    """A render_js scrape hands the browser-discovered files to the FileDownloader."""
    test_download_manager.register_downloader(ScrapeHTMLDownloader())
    test_download_manager.register_downloader(FileDownloader())
    destination = test_directory / 'destination'
    destination.mkdir()

    settings = {'depth': 1, 'suffix': '.mp4', 'render_js': True}
    test_download_manager.create_download(test_session, 'https://example.com/dir', 'scrape_html', settings=settings,
                                          sub_downloader_name='file', destination=destination)
    assert_download_urls(['https://example.com/dir', ])

    with mock.patch('wrolpi.scrape_downloader.ScrapeHTMLDownloader.crawl', fake_crawl), \
            mock.patch('wrolpi.files.downloader.FileDownloader.execute_download', fake_file_do_download):
        await test_download_manager.wait_for_all_downloads()
        await await_switches()

    assert_download_urls([
        'https://example.com/dir',
        'https://example.com/a.mp4',
        'https://example.com/sub/b.mp4',
    ])
