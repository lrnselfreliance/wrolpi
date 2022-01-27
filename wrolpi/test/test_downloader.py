from abc import ABC
from datetime import datetime
from itertools import zip_longest
from unittest import mock
from unittest.mock import MagicMock

import pytest

from wrolpi import downloader
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_context
from wrolpi.downloader import Downloader, Download, DownloadFrequency
from wrolpi.errors import UnrecoverableDownloadError, InvalidDownload, WROLModeEnabled
from wrolpi.test.common import wrap_test_db, TestAPI


class PermissiveDownloader(Downloader):
    """
    A testing Downloader which always says it's valid.
    """
    name = 'permissive'

    def __repr__(self):
        return '<TESTING Permissive Downloader>'

    def valid_url(self, url: str):
        return True, None


class HTTPDownloader(Downloader):
    """
    A testing Downloader which says its valid when a URL starts with http/https
    """
    name = 'http'

    def __repr__(self):
        return '<TESTING HTTP Downloader>'

    def valid_url(self, url: str):
        return url.startswith('https://') or url.startswith('http://'), None


class TestDownloader(TestAPI):
    def setUp(self) -> None:
        super().setUp()
        self.mgr = downloader.DownloadManager()
        PermissiveDownloader.do_download = MagicMock()
        HTTPDownloader.do_download = MagicMock()

    def test_register_downloader(self):
        """
        Downloaders can be registered and have specific priorities.
        """
        self.assertEqual(self.mgr.instances, tuple())

        http_downloader = HTTPDownloader()
        self.mgr.register_downloader(http_downloader)
        self.assertEqual(self.mgr.instances, (http_downloader,))

        # PermissiveDownloader is first priority.
        permissive_downloader = PermissiveDownloader(priority=0)
        self.mgr.register_downloader(permissive_downloader)
        self.assertEqual(self.mgr.instances, (permissive_downloader, http_downloader))

        self.assertRaises(ValueError, self.mgr.register_downloader, http_downloader)
        self.assertRaises(ValueError, self.mgr.register_downloader, permissive_downloader)

    @wrap_test_db
    def test_ensure_download(self):
        _, session = get_db_context()

        self.assertEqual(len(self.mgr.get_downloads(session)), 0)

        http_downloader = HTTPDownloader()
        http_downloader.do_download.return_value = False
        self.mgr.register_downloader(http_downloader)

        self.mgr.create_download('https://example.com', session)
        download = self.mgr.get_download(session, 'https://example.com')
        self.assertEqual(download.url, 'https://example.com')

        self.assertEqual(len(self.mgr.get_downloads(session)), 1)
        self.assertIsNotNone(self.mgr.get_download(session, 'https://example.com'))
        self.assertIsNone(self.mgr.get_download(session, 'https://example.com/not downloading'))

    @wrap_test_db
    def test_do_downloads(self):
        _, session = get_db_context()

        http_downloader = HTTPDownloader()
        http_downloader.do_download.return_value = True
        self.mgr.register_downloader(http_downloader)

        permissive_downloader = PermissiveDownloader(priority=100)
        permissive_downloader.do_download.return_value = False  # returns a failure
        self.mgr.register_downloader(permissive_downloader)

        # https is handled by the HTTP Downloader.
        self.mgr.create_download('https://example.com', session)
        http_downloader.do_download.assert_called_once()
        permissive_downloader.do_download.assert_not_called()
        self.assertIsNotNone(self.mgr.get_download(session, 'https://example.com'))

        http_downloader.do_download.reset_mock()

        # try the permissive download, which returns a failure.
        self.mgr.create_download('foo', session)
        http_downloader.do_download.assert_not_called()
        permissive_downloader.do_download.assert_called_once()
        download = self.mgr.get_download(session, 'foo')
        self.assertEqual(download.attempts, 1)

        # try again
        self.mgr.create_download('foo', session)
        self.mgr._do_downloads(session)
        download = self.mgr.get_download(session, 'foo')
        self.assertEqual(download.attempts, 2)

        # finally success
        permissive_downloader.do_download.return_value = True
        self.mgr.create_download('foo', session)
        self.mgr._do_downloads(session)
        download = self.mgr.get_download(session, 'foo')
        self.assertEqual(download.status, 'complete')

        # No downloads left.
        self.assertEqual(list(self.mgr.get_new_downloads(session)), [])

    @wrap_test_db
    def test_max_attempts(self):
        """
        A Download will only be attempted so many times, it will eventually be deleted.
        """
        _, session = get_db_context()

        http_downloader = HTTPDownloader()
        http_downloader.do_download.return_value = False
        self.mgr.register_downloader(http_downloader)

        self.mgr.create_download('https://example.com', session)
        download = session.query(Download).one()
        self.assertEqual(download.attempts, 1)

        self.mgr.create_download('https://example.com', session)
        download = session.query(Download).one()
        self.assertEqual(download.attempts, 2)

        # There are no further attempts.
        http_downloader.do_download.side_effect = UnrecoverableDownloadError()
        self.mgr.create_download('https://example.com', session)
        download = session.query(Download).one()
        self.assertEqual(download.attempts, 3)
        self.assertEqual(download.status, 'failed')

    @wrap_test_db
    def test_recurring_downloads(self):
        """
        A recurring Download should be downloaded repeatedly forever.
        """
        _, session = get_db_context()

        http_downloader = HTTPDownloader()
        http_downloader.do_download.return_value = True
        http_downloader.do_download: MagicMock  # noqa
        self.mgr.register_downloader(http_downloader)

        # Download every hour.
        self.mgr.recurring_download('https://example.com', 3600, skip_download=True)

        # One download is scheduled.
        downloads = self.mgr.get_new_downloads(session)
        self.assertEqual(
            [(i.url, i.frequency) for i in downloads],
            [('https://example.com', 3600)]
        )

        with mock.patch('wrolpi.downloader.now') as mock_now:
            now = local_timezone(datetime(2020, 1, 1, 0, 0, 0))
            mock_now.return_value = now

            # Download is processed and successful, no longer "new".
            self.mgr.do_downloads_sync()
            http_downloader.do_download.assert_called_once()
            self.assertEqual(list(self.mgr.get_new_downloads(session)), [])
            downloads = list(self.mgr.get_recurring_downloads(session))
            self.assertEqual(len(downloads), 1)
            download = downloads[0]
            expected = local_timezone(datetime(2020, 1, 1, 0, 0, 0))
            self.assertEqual(download.next_download, expected)
            self.assertEqual(download.last_successful_download, now)

            # Download is not due for an hour.
            self.mgr.renew_recurring_downloads(session)
            self.assertEqual(list(self.mgr.get_new_downloads(session)), [])
            self.assertEqual(download.last_successful_download, now)

            # Download is due an hour later.
            mock_now.return_value = local_timezone(datetime(2020, 1, 1, 2, 0, 1))
            self.mgr.renew_recurring_downloads(session)
            downloads = list(self.mgr.get_new_downloads(session))
            self.assertEqual(len(downloads), 1)
            download = downloads[0]
            # Download is "new" but has not been done a second time.
            self.assertEqual(download.next_download, expected)
            self.assertEqual(download.last_successful_download, now)

            # Try the download, but it fails.
            http_downloader.do_download.reset_mock()
            http_downloader.do_download.return_value = False
            self.mgr.do_downloads_sync()
            http_downloader.do_download.assert_called_once()
            download = session.query(Download).one()
            # Download is deferred, last successful download remains the same.
            self.assertEqual(download.status, 'deferred')
            self.assertEqual(download.last_successful_download, now)
            # Download should be retried after the DEFAULT_RETRY_FREQUENCY.
            expected = local_timezone(datetime(2020, 1, 1, 3, 0, 1))
            self.assertEqual(download.next_download, expected)

            # Try the download again, it finally succeeds.
            http_downloader.do_download.reset_mock()
            now = local_timezone(datetime(2020, 1, 1, 4, 0, 1))
            mock_now.return_value = now
            http_downloader.do_download.return_value = True
            self.mgr.renew_recurring_downloads(session)
            self.mgr.do_downloads_sync()
            http_downloader.do_download.assert_called_once()
            download = session.query(Download).one()
            self.assertEqual(download.status, 'complete')
            self.assertEqual(download.last_successful_download, now)
            # Floats cause slightly wrong date.
            self.assertEqual(download.next_download, local_timezone(datetime(2020, 1, 1, 4, 0, 0, 997200)))

    @wrap_test_db
    @mock.patch('wrolpi.downloader.now', lambda: local_timezone(datetime(2020, 6, 5, 0, 0)))
    def test_delete_old_once_downloads(self):
        """
        Once-downloads over a month old should be deleted.
        """
        permissive_downloader = PermissiveDownloader(priority=0)
        self.mgr.register_downloader(permissive_downloader)

        _, session = get_db_context()
        # Recurring downloads should not be deleted.
        d1 = self.mgr.create_download('https://example.com/1', session, skip_download=True)
        d2 = self.mgr.create_download('https://example.com/2', session, skip_download=True)
        d1.frequency = 1
        d2.frequency = 1
        d2.started()
        # Should be deleted.
        d3 = self.mgr.create_download('https://example.com/3', session, skip_download=True)
        d4 = self.mgr.create_download('https://example.com/4', session, skip_download=True)
        d3.complete()
        d4.complete()
        d3.last_successful_download = local_timezone(datetime(2020, 1, 1, 0, 0, 0))
        d4.last_successful_download = local_timezone(datetime(2020, 5, 1, 0, 0, 0))
        # Not a month old.
        d5 = self.mgr.create_download('https://example.com/5', session, skip_download=True)
        d5.last_successful_download = local_timezone(datetime(2020, 6, 1, 0, 0, 0))
        # An old, but pending download should not be deleted.
        d6 = self.mgr.create_download('https://example.com/6', session, skip_download=True)
        d6.last_successful_download = local_timezone(datetime(2020, 4, 1, 0, 0, 0))
        d6.started()

        self.mgr.delete_old_once_downloads()

        # Two old downloads are deleted.
        downloads = self.mgr._downloads_sorter(session.query(Download).all())
        expected = [
            dict(url='https://example.com/2', frequency=1, attempts=1, status='pending'),
            dict(url='https://example.com/6', attempts=1, status='pending'),
            dict(url='https://example.com/1', frequency=1, attempts=0, status='new'),
            dict(url='https://example.com/5', attempts=0, status='new'),
        ]
        for download, expected in zip_longest(downloads, expected):
            self.assertDictContains(download.dict(), expected)

    @wrap_test_db
    def test_create_downloads(self):
        """
        Multiple downloads can be scheduled using DownloadManager.create_downloads.
        """
        http_downloader = HTTPDownloader(priority=0)
        self.mgr.register_downloader(http_downloader)

        _, session = get_db_context()

        # Both URLs are valid and are scheduled.
        self.mgr.create_downloads(['https://example.com/1', 'https://example.com/2'], skip_download=True)
        downloads = self.mgr.get_downloads(session)
        self.assertEqual({i.url for i in downloads}, {'https://example.com/1', 'https://example.com/2'})

        # One URL is bad, neither should be scheduled.
        self.assertRaises(InvalidDownload, self.mgr.create_downloads, ['https://example.com/3', 'bad url should fail'],
                          skip_download=True)
        downloads = self.mgr.get_downloads(session)
        self.assertEqual({i.url for i in downloads}, {'https://example.com/1', 'https://example.com/2'})


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
        test_download_manager.do_downloads_sync()
    with pytest.raises(WROLModeEnabled):
        await test_download_manager.do_downloads_sync()


def test_download_get_downloader(test_session, test_download_manager):
    """
    A Download can find it's Downloader.
    """
    permissive_downloader = PermissiveDownloader()
    http_downloader = HTTPDownloader()
    test_download_manager.register_downloader(permissive_downloader)
    test_download_manager.register_downloader(http_downloader)

    download1 = test_download_manager.create_download('https://example.com', test_session, skip_download=True)
    assert download1.get_downloader() == permissive_downloader

    download2 = test_download_manager.create_download('https://example.com', test_session, skip_download=True)
    download2.downloader = 'bad downloader'
    assert download2.get_downloader() is None


def test_get_next_download(test_session, test_download_manager, fake_now):
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
        result = test_download_manager.get_next_download(download)
        assert result == expected, f'{attempts} != {result}'

    d1 = Download(url='https://example.com/1', frequency=DownloadFrequency.weekly)
    d2 = Download(url='https://example.com/2', frequency=DownloadFrequency.weekly)
    d3 = Download(url='https://example.com/3', frequency=DownloadFrequency.weekly)
    test_session.add_all([d1, d2, d3])
    test_session.commit()
    assert test_download_manager.get_next_download(d1) == local_timezone(datetime(2000, 1, 1))
    assert test_download_manager.get_next_download(d2) == local_timezone(datetime(2000, 1, 4, 12))
    assert test_download_manager.get_next_download(d3) == local_timezone(datetime(2000, 1, 2, 18))
