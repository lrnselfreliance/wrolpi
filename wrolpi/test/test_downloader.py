import unittest
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock

from wrolpi import downloader
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_context
from wrolpi.downloader import Downloader, get_downloads, get_download, Download
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.test.common import wrap_test_db


class PermissiveDownloader(Downloader):
    """
    A testing Downloader which always says it's valid.
    """

    def valid_url(self, url: str):
        return True


class HTTPDownloader(Downloader):
    """
    A testing Downloader which says its valid when a URL starts with http/https
    """

    def valid_url(self, url: str):
        return url.startswith('https://') or url.startswith('http://')


class TestDownloader(unittest.TestCase):
    def setUp(self) -> None:
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

    def test_valid_url(self):
        # No downloaders available.
        self.assertFalse(self.mgr.valid_url('foo'))
        self.assertFalse(self.mgr.valid_url('https://example.com'))

        http_downloader = HTTPDownloader()
        self.mgr.register_downloader(http_downloader)
        self.assertFalse(self.mgr.valid_url('foo'))
        self.assertTrue(self.mgr.valid_url('https://example.com'))
        self.assertEqual(self.mgr.get_downloader('https://example.com'), http_downloader)

        # Last priority.
        permissive_downloader = PermissiveDownloader(priority=100)
        self.mgr.register_downloader(permissive_downloader)
        self.assertTrue(self.mgr.valid_url('foo'))
        self.assertEqual(self.mgr.get_downloader('foo'), permissive_downloader)
        self.assertTrue(self.mgr.valid_url('https://example.com'))
        self.assertEqual(self.mgr.get_downloader('https://example.com'), http_downloader)

    @wrap_test_db
    def test_ensure_download(self):
        _, session = get_db_context()

        self.assertEqual(len(get_downloads()), 0)

        http_downloader = HTTPDownloader()
        http_downloader.do_download.return_value = False
        self.mgr.register_downloader(http_downloader)

        self.mgr.create_download('https://example.com', session)
        download = get_download('https://example.com', session)
        self.assertEqual(download.url, 'https://example.com')

        self.assertEqual(len(get_downloads()), 1)
        self.assertIsNotNone(get_download('https://example.com', session))
        self.assertIsNone(get_download('https://example.com/not downloading', session))

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
        self.assertIsNotNone(get_download('https://example.com', session))

        http_downloader.do_download.reset_mock()

        # try the permissive download, which returns a failure.
        self.mgr.create_download('foo', session)
        http_downloader.do_download.assert_not_called()
        permissive_downloader.do_download.assert_called_once()
        download = get_download('foo', session)
        self.assertEqual(download.attempts, 1)

        # try again
        self.mgr.create_download('foo', session)
        self.mgr._do_downloads(session)
        download = get_download('foo', session)
        self.assertEqual(download.attempts, 2)

        # finally success
        permissive_downloader.do_download.return_value = True
        self.mgr.create_download('foo', session)
        self.mgr._do_downloads(session)
        download = get_download('foo', session)
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
            expected = local_timezone(datetime(2020, 1, 1, 1, 0, 0))
            self.assertEqual(download.next_download, expected)
            self.assertEqual(download.last_successful_download, now)

            # Download is not due for an hour.
            self.mgr.renew_recurring_downloads(session)
            self.assertEqual(list(self.mgr.get_new_downloads(session)), [])
            self.assertEqual(download.last_successful_download, now)

            # Download is due an hour later.
            mock_now.return_value = local_timezone(datetime(2020, 1, 1, 1, 0, 0))
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
            self.assertEqual(download.next_download, expected + timedelta(hours=1))

            # Try the download again, it finally succeeds.
            http_downloader.do_download.reset_mock()
            now = local_timezone(datetime(2020, 1, 1, 3, 0, 0))
            mock_now.return_value = now
            http_downloader.do_download.return_value = True
            self.mgr.renew_recurring_downloads(session)
            self.mgr.do_downloads_sync()
            http_downloader.do_download.assert_called_once()
            download = session.query(Download).one()
            self.assertEqual(download.status, 'complete')
            self.assertEqual(download.last_successful_download, now)
            self.assertEqual(download.next_download, local_timezone(datetime(2020, 1, 1, 4, 0, 0)))
