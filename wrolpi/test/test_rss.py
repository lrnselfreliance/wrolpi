import json
from http import HTTPStatus
from itertools import zip_longest
from typing import List

import mock

from wrolpi.db import optional_session
from wrolpi.downloader import Download, DownloadResult, RSSDownloader
from wrolpi.test.test_downloader import HTTPDownloader


class RSSHTTPDownloader(HTTPDownloader):
    def do_download(self, download: Download) -> DownloadResult:
        return DownloadResult(success=True)

    @optional_session
    def already_downloaded(self, url: str, session=None):
        download = session.query(Download).filter_by(url=url).one_or_none()
        return download


def test_rss_download_invalid(test_session, test_download_manager):
    """Feeds are not downloaded when FeedParser reports an issue."""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)


def test_rss_download(test_session, test_download_manager, test_download_manager_config):
    """An RSS Downloader will create new Downloads for every link in the feed."""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)
    http_downloader = RSSHTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    def check_downloads(expected: List[dict]):
        downloads = test_session.query(Download).order_by(Download.id).all()
        for download, expected in zip_longest(downloads, expected):
            assert download.id == expected['id'] \
                   and download.status == expected['status'] \
                   and download.url == expected['url'] \
                   and download.attempts == expected['attempts'], f'{download} != {expected}'

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(
            bozo=0,
            entries=[
                dict(link='https://example.com/a'),
                dict(link='https://example.com/b'),
                dict(link='https://example.com/c'),
            ]
        )
        test_download_manager.create_download('https://example.com/feed', test_session, sub_downloader='http')

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
        test_download_manager.create_download('https://example.com/feed', test_session, sub_downloader='http')

    # Only the new URLs are Archived.
    check_downloads([
        dict(id=1, status='complete', url='https://example.com/feed', attempts=2),
        dict(id=2, status='complete', url='https://example.com/a', attempts=1),
        dict(id=3, status='complete', url='https://example.com/b', attempts=1),
        dict(id=4, status='complete', url='https://example.com/c', attempts=1),
        dict(id=5, status='complete', url='https://example.com/d', attempts=1),
    ])


def test_post_rss_download(test_session, test_client, test_download_manager, test_download_manager_config):
    """An RSS can be downloaded in the UI"""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)
    http_downloader = RSSHTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(bozo=0, entries=[])
        content = dict(urls='https://example.com/feed', downloader='rss', frequency=100)
        request, response = test_client.post('/api/download', content=json.dumps(content))
        assert response.status == HTTPStatus.NO_CONTENT

    # Download was attempted.
    (download,) = test_download_manager.get_downloads(test_session)
    assert download.url == 'https://example.com/feed'
    assert download.frequency == 100
    assert download.downloader == 'rss'
    assert download.attempts == 1


def test_rss_no_entries(test_session, test_download_manager, test_download_manager_config):
    """An RSS feed with no entries is handled."""
    rss_downloader = RSSDownloader()
    test_download_manager.register_downloader(rss_downloader)

    with mock.patch('wrolpi.downloader.parse_feed') as mock_parse_feed:
        mock_parse_feed.return_value = dict(bozo=0, )  # missing `entries`
        test_download_manager.create_download('https://example.com/feed', test_session, sub_downloader='http')

    (download,) = test_download_manager.get_downloads(test_session)
    assert 'entries' in download.error
