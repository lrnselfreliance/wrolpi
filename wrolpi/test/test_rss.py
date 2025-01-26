from itertools import zip_longest
from typing import List

import mock
import pytest

from wrolpi.db import optional_session
from wrolpi.downloader import Download, DownloadResult, Downloader, DownloadManager, RSSDownloader


class RSSHTTPDownloader(Downloader):
    name = 'rss_http'

    async def do_download(self, download: Download) -> DownloadResult:
        return DownloadResult(success=True)

    @optional_session
    def already_downloaded(self, *urls: List[str], session=None):
        downloads = list(session.query(Download).filter(Download.url.in_(urls)))
        return downloads


@pytest.mark.asyncio
async def test_rss_download(test_session, test_download_manager, await_switches):
    """An RSS Downloader will create new Downloads for every link in the feed."""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)
    http_downloader = RSSHTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    def check_downloads(expected: List[dict]):
        downloads = test_session.query(Download).order_by(Download.id).all()
        for download, expected in zip_longest(downloads, expected):
            assert download.id == expected['id'], 'Download id does not match'
            assert download.status == expected['status'], 'Download status does not match'
            assert download.url == expected['url'], 'Download URL does not match'
            assert download.attempts == expected['attempts'], 'Download attempts do not match'

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(
            bozo=0,
            entries=[
                dict(link='https://example.com/a'),
                dict(link='https://example.com/b'),
                dict(link='https://example.com/c'),
            ]
        )
        test_download_manager: DownloadManager
        test_download_manager.create_download('https://example.com/feed', rss_downloader.name,
                                              sub_downloader_name='rss_http')
        await test_download_manager.wait_for_all_downloads()

    # Feed download is complete.
    check_downloads([
        dict(id=1, status='complete', url='https://example.com/feed', attempts=1),
        dict(id=2, status='complete', url='https://example.com/a', attempts=1),
        dict(id=3, status='complete', url='https://example.com/b', attempts=1),
        dict(id=4, status='complete', url='https://example.com/c', attempts=1),
    ])

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(
            bozo=0,
            entries=[
                dict(link='https://example.com/a'),
                dict(link='https://example.com/d'),
            ]
        )
        test_download_manager.create_download('https://example.com/feed', rss_downloader.name,
                                              sub_downloader_name='rss_http')
        await test_download_manager.wait_for_all_downloads()

    # Only the new URLs are Archived.
    check_downloads([
        dict(id=1, status='complete', url='https://example.com/feed', attempts=2),
        dict(id=2, status='complete', url='https://example.com/a', attempts=1),
        dict(id=3, status='complete', url='https://example.com/b', attempts=1),
        dict(id=4, status='complete', url='https://example.com/c', attempts=1),
        dict(id=5, status='complete', url='https://example.com/d', attempts=1),
    ])


@pytest.mark.asyncio
async def test_rss_no_entries(test_session, test_download_manager, await_switches):
    """An RSS feed with no entries is handled."""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)
    http_downloader = RSSHTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(bozo=0, )  # missing `entries`
        test_download_manager.create_download('https://example.com/feed', rss_downloader.name, test_session,
                                              sub_downloader_name='rss_http')
        await test_download_manager.wait_for_all_downloads()

    (download,) = test_download_manager.get_downloads(test_session)
    assert download.is_deferred
    assert 'entries' in download.error


@pytest.mark.asyncio
async def test_rss_downloader_filter_titles(test_session):
    rss_downloader = RSSDownloader()

    entries = [
        dict(link='https://example.com/a', title='A'),  # Case should be ignored.
        dict(link='https://example.com/b', title='b'),
        dict(link='https://example.com/c', title='c'),
    ]

    download = Download(url='https://example.com/feed', settings=dict(title_include='a'))
    assert rss_downloader.filter_entries(download, entries) == [
        dict(link='https://example.com/a', title='A'),
    ]

    download = Download(url='https://example.com/feed', settings=dict(title_include='b'))
    assert rss_downloader.filter_entries(download, entries) == [
        dict(link='https://example.com/b', title='b'),
    ]

    download = Download(url='https://example.com/feed', settings=dict(title_exclude='C'))
    assert rss_downloader.filter_entries(download, entries) == [
        dict(link='https://example.com/a', title='A'),
        dict(link='https://example.com/b', title='b'),
    ]
