from itertools import zip_longest
from typing import List

import mock
import pytest
from sqlalchemy.orm import Session

from wrolpi.downloader import Download, DownloadResult, Downloader, DownloadManager, RSSDownloader


class RSSHTTPDownloader(Downloader):
    name = 'rss_http'

    async def do_download(self, download: Download) -> DownloadResult:
        return DownloadResult(success=True)

    def already_downloaded(self, session: Session, *urls: List[str]):
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
        test_download_manager.create_download(test_session, 'https://example.com/feed', rss_downloader.name,
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
        test_download_manager.create_download(test_session, 'https://example.com/feed', rss_downloader.name,
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
        test_download_manager.create_download(test_session, 'https://example.com/feed', rss_downloader.name,
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


@pytest.mark.asyncio
async def test_rss_downloader_uses_destination_column(test_session, test_download_manager, await_switches):
    """RSS downloader should pass download.destination to child downloads, not settings['destination'].

    The destination column is the source of truth. settings['destination'] is legacy.
    """
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)
    http_downloader = RSSHTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(
            bozo=0,
            entries=[
                dict(link='https://example.com/a'),
                dict(link='https://example.com/b'),
            ]
        )
        # Create RSS download with destination column set, but empty settings.
        test_download_manager.create_download(
            test_session,
            'https://example.com/feed',
            rss_downloader.name,
            sub_downloader_name='rss_http',
            destination='archive/custom/path',  # destination column
            settings={},  # Empty settings - destination should come from column
        )
        await test_download_manager.wait_for_all_downloads()

    # Get all downloads
    downloads = test_session.query(Download).order_by(Download.id).all()
    assert len(downloads) == 3, 'Expected 1 RSS download + 2 child downloads'

    # The RSS download itself
    rss_download = downloads[0]
    assert rss_download.url == 'https://example.com/feed'
    assert str(rss_download.destination).endswith('archive/custom/path')

    # Child downloads should have destination in their settings (passed from RSS download.destination)
    child_a = downloads[1]
    child_b = downloads[2]
    assert child_a.url == 'https://example.com/a'
    assert child_b.url == 'https://example.com/b'
    # The destination should be passed from RSS download.destination column to child settings
    assert child_a.settings.get('destination') is not None, \
        'Child download should inherit destination from RSS download.destination column'
    assert child_a.settings['destination'].endswith('archive/custom/path'), \
        f"Expected destination ending with 'archive/custom/path', got {child_a.settings.get('destination')}"
    assert child_b.settings.get('destination') is not None, \
        'Child download should inherit destination from RSS download.destination column'
    assert child_b.settings['destination'].endswith('archive/custom/path'), \
        f"Expected destination ending with 'archive/custom/path', got {child_b.settings.get('destination')}"
