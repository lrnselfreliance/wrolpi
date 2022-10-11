import json
from abc import ABC
from datetime import datetime
from http import HTTPStatus
from itertools import zip_longest
from unittest import mock
from unittest.mock import MagicMock

import pytest

from wrolpi.dates import local_timezone, Seconds
from wrolpi.db import get_db_context
from wrolpi.downloader import Downloader, Download, DownloadFrequency, DownloadResult
from wrolpi.errors import UnrecoverableDownloadError, InvalidDownload, WROLModeEnabled
from wrolpi.test.common import assert_dict_contains


class PermissiveDownloader(Downloader):
    """A testing Downloader which always says it's valid."""
    name = 'permissive'

    def __repr__(self):
        return '<TESTING Permissive Downloader>'

    def valid_url(self, url: str):
        return True, None


class HTTPDownloader(Downloader):
    """A testing Downloader which says its valid when a URL starts with http/https"""
    name = 'http'

    def __repr__(self):
        return '<TESTING HTTP Downloader>'

    def valid_url(self, url: str):
        return url.startswith('https://') or url.startswith('http://'), None


@pytest.mark.asyncio
def test_register_downloader(test_session, test_download_manager):
    """Downloaders can be registered and have specific priorities."""
    assert test_download_manager.instances == tuple()

    http_downloader = HTTPDownloader()
    test_download_manager.register_downloader(http_downloader)
    assert test_download_manager.instances == (http_downloader,)

    # PermissiveDownloader is first priority.
    permissive_downloader = PermissiveDownloader(priority=0)
    test_download_manager.register_downloader(permissive_downloader)
    assert test_download_manager.instances == (permissive_downloader, http_downloader)

    with pytest.raises(ValueError):
        test_download_manager.register_downloader(http_downloader)
    with pytest.raises(ValueError):
        test_download_manager.register_downloader(permissive_downloader)


@pytest.mark.asyncio
async def test_delete_old_once_downloads(test_session, test_download_manager):
    """Once-downloads over a month old should be deleted."""
    with mock.patch('wrolpi.downloader.now') as mock_now:
        mock_now.return_value = local_timezone(datetime(2020, 6, 5, 0, 0))
        permissive_downloader = PermissiveDownloader(priority=0)
        test_download_manager.register_downloader(permissive_downloader)

        # Recurring downloads should not be deleted.
        d1 = test_download_manager.create_download('https://example.com/1')
        d2 = test_download_manager.create_download('https://example.com/2')
        d1.frequency = 1
        d2.frequency = 1
        d2.started()
        # Should be deleted.
        d3 = test_download_manager.create_download('https://example.com/3')
        d4 = test_download_manager.create_download('https://example.com/4')
        d3.complete()
        d4.complete()
        d3.last_successful_download = local_timezone(datetime(2020, 1, 1, 0, 0, 0))
        d4.last_successful_download = local_timezone(datetime(2020, 5, 1, 0, 0, 0))
        # Not a month old.
        d5 = test_download_manager.create_download('https://example.com/5')
        d5.last_successful_download = local_timezone(datetime(2020, 6, 1, 0, 0, 0))
        # An old, but pending download should not be deleted.
        d6 = test_download_manager.create_download('https://example.com/6')
        d6.last_successful_download = local_timezone(datetime(2020, 4, 1, 0, 0, 0))
        d6.started()

        test_download_manager.delete_old_once_downloads()

        # Two old downloads are deleted.
        downloads = test_session.query(Download).order_by(Download.id).all()
        expected = [
            dict(url='https://example.com/1', frequency=1, attempts=0, status='new'),
            dict(url='https://example.com/2', frequency=1, attempts=1, status='pending'),
            dict(url='https://example.com/5', attempts=0, status='new'),
            dict(url='https://example.com/6', attempts=1, status='pending'),
        ]
        for download, expected in zip_longest(downloads, expected):
            assert_dict_contains(download.dict(), expected)


@pytest.mark.asyncio
async def test_ensure_download(test_session, test_download_manager):
    assert len(test_download_manager.get_downloads(test_session)) == 0

    http_downloader = HTTPDownloader()
    http_downloader.do_download = MagicMock()
    http_downloader.do_download.return_value = DownloadResult(success=True)
    test_download_manager.register_downloader(http_downloader)

    test_download_manager.create_download('https://example.com')
    download = test_download_manager.get_download(test_session, 'https://example.com')
    assert download.url == 'https://example.com'

    assert len(test_download_manager.get_downloads(test_session)) == 1
    assert test_download_manager.get_download(test_session, 'https://example.com') is not None
    assert test_download_manager.get_download(test_session, 'https://example.com/not downloading') is None


@pytest.mark.asyncio
async def test_create_downloads(test_session, test_download_manager):
    """Multiple downloads can be scheduled using DownloadManager.create_downloads."""
    http_downloader = HTTPDownloader(priority=0)
    test_download_manager.register_downloader(http_downloader)

    # Both URLs are valid and are scheduled.
    test_download_manager.create_downloads(['https://example.com/1', 'https://example.com/2'])
    downloads = test_download_manager.get_downloads(test_session)
    assert {i.url for i in downloads} == {'https://example.com/1', 'https://example.com/2'}

    # One URL is bad, neither should be scheduled.
    with pytest.raises(InvalidDownload):
        test_download_manager.create_downloads(['https://example.com/3', 'bad url should fail'])

    downloads = test_download_manager.get_downloads(test_session)
    assert {i.url for i in downloads} == {'https://example.com/1', 'https://example.com/2'}


def test_downloader_must_have_name():
    """
    A Downloader class must have a name.
    """
    with pytest.raises(NotImplementedError):
        Downloader()

    class D(Downloader, ABC):
        pass

    with pytest.raises(NotImplementedError):
        D()


@mock.patch('wrolpi.common.wrol_mode_enabled', lambda: True)
@pytest.mark.asyncio
async def test_download_wrol_mode(test_session, test_download_manager):
    with pytest.raises(WROLModeEnabled):
        await test_download_manager.do_downloads()
    with pytest.raises(WROLModeEnabled):
        await test_download_manager.do_downloads()


@pytest.mark.asyncio
async def test_download_get_downloader(test_session, test_download_manager):
    """
    A Download can find it's Downloader.
    """
    permissive_downloader = PermissiveDownloader()
    http_downloader = HTTPDownloader()
    test_download_manager.register_downloader(permissive_downloader)
    test_download_manager.register_downloader(http_downloader)

    download1 = test_download_manager.create_download('https://example.com')
    assert download1.get_downloader() == permissive_downloader

    download2 = test_download_manager.create_download('https://example.com')
    download2.downloader = 'bad downloader'
    assert download2.get_downloader() is None


@pytest.mark.asyncio
def test_calculate_next_download(test_session, test_download_manager, fake_now):
    fake_now(datetime(2000, 1, 1))
    download = Download()
    download.frequency = DownloadFrequency.weekly
    download.status = 'deferred'

    # next_download slowly increases as we accumulate attempts.  Largest gap is the download frequency.
    attempts_expected = [
        (0, local_timezone(datetime(2000, 1, 1, 3))),
        (1, local_timezone(datetime(2000, 1, 1, 3))),
        (2, local_timezone(datetime(2000, 1, 1, 9))),
        (3, local_timezone(datetime(2000, 1, 2, 3))),
        (4, local_timezone(datetime(2000, 1, 4, 9))),
        (5, local_timezone(datetime(2000, 1, 8))),
        (6, local_timezone(datetime(2000, 1, 8))),
    ]
    for attempts, expected in attempts_expected:
        download.attempts = attempts
        result = test_download_manager.calculate_next_download(download)
        assert result == expected, f'{attempts} != {result}'

    d1 = Download(url='https://example.com/1', frequency=DownloadFrequency.weekly)
    d2 = Download(url='https://example.com/2', frequency=DownloadFrequency.weekly)
    d3 = Download(url='https://example.com/3', frequency=DownloadFrequency.weekly)
    test_session.add_all([d1, d2, d3])
    test_session.commit()
    # Downloads are spread out over the next week.
    assert test_download_manager.calculate_next_download(d1) == local_timezone(datetime(2000, 1, 8))
    assert test_download_manager.calculate_next_download(d2) == local_timezone(datetime(2000, 1, 11, 12))
    assert test_download_manager.calculate_next_download(d3) == local_timezone(datetime(2000, 1, 9, 18))


@pytest.mark.asyncio
async def test_recurring_downloads(test_session, test_download_manager, fake_now):
    """A recurring Download should be downloaded forever."""
    http_downloader = HTTPDownloader()
    http_downloader.do_download = MagicMock()
    http_downloader.do_download.return_value = DownloadResult(success=True)
    test_download_manager.register_downloader(http_downloader)

    # Download every hour.
    test_download_manager.recurring_download('https://example.com', Seconds.hour)

    # One download is scheduled.
    downloads = test_download_manager.get_new_downloads(test_session)
    assert [(i.url, i.frequency) for i in downloads] == [('https://example.com', Seconds.hour)]

    now_ = fake_now(datetime(2020, 1, 1, 0, 0, 0))

    # Download is processed and successful, no longer "new".
    await test_download_manager.wait_for_all_downloads()
    http_downloader.do_download.assert_called_once()
    assert list(test_download_manager.get_new_downloads(test_session)) == []
    downloads = list(test_download_manager.get_recurring_downloads(test_session))
    assert len(downloads) == 1
    download = downloads[0]
    expected = local_timezone(datetime(2020, 1, 1, 1, 0, 0))
    assert download.next_download == expected
    assert download.last_successful_download == now_

    # Download is not due for an hour.
    test_download_manager.renew_recurring_downloads(test_session)
    await test_download_manager.wait_for_all_downloads()
    assert list(test_download_manager.get_new_downloads(test_session)) == []
    assert download.last_successful_download == now_

    # Download is due an hour later.
    fake_now(datetime(2020, 1, 1, 2, 0, 1))
    test_download_manager.renew_recurring_downloads(test_session)
    (download,) = list(test_download_manager.get_new_downloads(test_session))
    # Download is "new" but has not been downloaded a second time.
    assert download.next_download == expected
    assert download.last_successful_download == now_
    assert download.status == 'new'

    # Try the download, but it fails.
    http_downloader.do_download.reset_mock()
    http_downloader.do_download.return_value = DownloadResult(success=False)
    await test_download_manager.wait_for_all_downloads()
    http_downloader.do_download.assert_called_once()
    download = test_session.query(Download).one()
    # Download is deferred, last successful download remains the same.
    assert download.status == 'deferred'
    assert download.last_successful_download == now_
    # Download should be retried after the DEFAULT_RETRY_FREQUENCY.
    expected = local_timezone(datetime(2020, 1, 1, 3, 0, 0, 997200))
    assert download.next_download == expected

    # Try the download again, it finally succeeds.
    http_downloader.do_download.reset_mock()
    now_ = fake_now(datetime(2020, 1, 1, 4, 0, 1))
    http_downloader.do_download.return_value = DownloadResult(success=True)
    test_download_manager.renew_recurring_downloads(test_session)
    await test_download_manager.wait_for_all_downloads()
    http_downloader.do_download.assert_called_once()
    download = test_session.query(Download).one()
    assert download.status == 'complete'
    assert download.last_successful_download == now_
    # Floats cause slightly wrong date.
    assert download.next_download == local_timezone(datetime(2020, 1, 1, 5, 0, 0, 997200))


@pytest.mark.asyncio
async def test_max_attempts(test_session, test_download_manager):
    """A Download will only be attempted so many times, it will eventually be deleted."""
    _, session = get_db_context()

    http_downloader = HTTPDownloader()
    http_downloader.do_download = MagicMock()
    http_downloader.do_download.return_value = DownloadResult(success=True)
    test_download_manager.register_downloader(http_downloader)

    test_download_manager.create_download('https://example.com')
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 1

    test_download_manager.create_download('https://example.com')
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 2

    # There are no further attempts.
    http_downloader.do_download.side_effect = UnrecoverableDownloadError()
    test_download_manager.create_download('https://example.com')
    await test_download_manager.wait_for_all_downloads()
    download = session.query(Download).one()
    assert download.attempts == 3
    assert download.status == 'failed'


@pytest.mark.asyncio
async def test_skip_urls(test_session, test_download_manager, test_client, assert_download_urls):
    """The DownloadManager will not create downloads for URLs in it's skip list."""
    _, session = get_db_context()
    from wrolpi.downloader import DOWNLOAD_MANAGER_CONFIG
    DOWNLOAD_MANAGER_CONFIG.skip_urls = ['https://example.com/skipme']

    http_downloader = HTTPDownloader()
    http_downloader.do_download = MagicMock()
    http_downloader.do_download.return_value = DownloadResult(success=True)
    test_download_manager.register_downloader(http_downloader)

    test_download_manager.create_downloads([
        'https://example.com/1',
        'https://example.com/skipme',
        'https://example.com/2',
    ], downloader=HTTPDownloader.name)
    await test_download_manager.wait_for_all_downloads()
    assert_download_urls({'https://example.com/1', 'https://example.com/2'})
    assert DOWNLOAD_MANAGER_CONFIG.skip_urls == ['https://example.com/skipme']

    test_download_manager.delete_completed()

    # The user can start a download even if the URL is in the skip list.
    test_download_manager.create_download('https://example.com/skipme', reset_attempts=True)
    assert_download_urls({'https://example.com/skipme'})
    assert DOWNLOAD_MANAGER_CONFIG.skip_urls == []


@pytest.mark.asyncio
async def test_process_runner_timeout(test_directory):
    """A Downloader can cancel it's download using a timeout."""
    # Default timeout of 3 seconds.
    downloader = Downloader(0, 'downloader', timeout=3)

    # Default timeout is obeyed.
    start = datetime.now()
    await downloader.process_runner('https://example.com', ('sleep', '8'), test_directory)
    elapsed = datetime.now() - start
    assert 3 < elapsed.total_seconds() < 4

    # One-off timeout is obeyed.
    start = datetime.now()
    await downloader.process_runner('https://example.com', ('sleep', '8'), test_directory, timeout=1)
    elapsed = datetime.now() - start
    assert 1 < elapsed.total_seconds() < 2

    # Global timeout is obeyed.
    from wrolpi.common import WROLPI_CONFIG
    WROLPI_CONFIG.download_timeout = 3
    start = datetime.now()
    await downloader.process_runner('https://example.com', ('sleep', '8'), test_directory)
    elapsed = datetime.now() - start
    assert 2 < elapsed.total_seconds() < 4


def test_crud_download(test_client, test_session, test_download_manager):
    """Test the ways that Downloads can be created."""
    http_downloader = HTTPDownloader()
    test_download_manager.register_downloader(http_downloader)

    body = dict(
        urls='https://example.com',
        downloader=http_downloader.name,
        frequency=DownloadFrequency.weekly,
        excluded_urls='example.org,something',
    )
    request, response = test_client.post('/api/download', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT, response.body

    download: Download = test_session.query(Download).one()
    assert download.id
    assert download.url == 'https://example.com'
    assert download.downloader == 'http'
    assert download.frequency == DownloadFrequency.weekly
    assert download.settings['excluded_urls'] == ['example.org', 'something']

    request, response = test_client.get('/api/download')
    assert response.status_code == HTTPStatus.OK
    assert 'recurring_downloads' in response.json
    assert [i['url'] for i in response.json['recurring_downloads']] == ['https://example.com']

    request, response = test_client.delete(f'/api/download/{download.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(Download).count() == 0
