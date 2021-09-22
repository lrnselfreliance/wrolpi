import pathlib

import mock

from modules.archive.lib import new_archive
from modules.archive.models import Archive
from wrolpi.test.common import TestAPI, wrap_test_db


def make_fake_request_archive(readability=True, screenshot=True):
    def fake_request_archive(_):
        singlefile = b'<html>test single-file</html>'
        r = dict(
            content='<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
            title='test title',
        ) if readability else None
        s = b'foo' if screenshot else None
        return singlefile, r, s

    return fake_request_archive


class TestArchive(TestAPI):

    @wrap_test_db
    def test_new_archive(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            archive1 = new_archive('https://example.com')
            # Everything is filled out.
            self.assertIsInstance(archive1, Archive)
            self.assertIsNotNone(archive1.archive_datetime)
            self.assertIsInstance(archive1.singlefile_path, pathlib.Path)
            self.assertIsInstance(archive1.readability_path, pathlib.Path)
            self.assertIsInstance(archive1.readability_txt_path, pathlib.Path)
            self.assertIsInstance(archive1.screenshot_path, pathlib.Path)
            self.assertEqual(archive1.title, 'test title')
            self.assertIsNotNone(archive1.url)
            self.assertIsNotNone(archive1.domain)

            archive2 = new_archive('https://example.com')
            # URL and Domain are reused.
            self.assertEqual(archive1.url, archive2.url)
            self.assertEqual(archive1.domain, archive2.domain)

    @wrap_test_db
    def test_no_screenshot(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(screenshot=False)):
            archive = new_archive('https://example.com')
            self.assertIsInstance(archive.singlefile_path, pathlib.Path)
            self.assertIsInstance(archive.readability_path, pathlib.Path)
            # Screenshot was empty
            self.assertIsNone(archive.screenshot_path)

    @wrap_test_db
    def test_no_readability(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
            archive = new_archive('https://example.com')
            self.assertIsInstance(archive.singlefile_path, pathlib.Path)
            self.assertIsNone(archive.readability_path)
            self.assertIsInstance(archive.screenshot_path, pathlib.Path)
