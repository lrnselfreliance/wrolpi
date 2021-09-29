import json
import pathlib
import tempfile

import mock

from modules.archive.lib import new_archive, get_or_create_domain_and_url, get_urls, get_url_count
from modules.archive.models import Archive
from wrolpi.common import CustomJSONEncoder
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidDomain
from wrolpi.test.common import TestAPI, wrap_test_db


def make_fake_request_archive(readability=True, screenshot=True):
    def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n</html>'
        r = dict(
            content='<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
            title='ジにてこちら',
        ) if readability else None
        s = b'foo' if screenshot else None
        return singlefile, r, s

    return fake_request_archive


class TestArchive(TestAPI):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_dir = pathlib.Path(self.tmp_dir.name)
        self.domain_directory_patch = mock.patch('modules.archive.lib.get_archive_directory', lambda: tmp_dir)
        self.domain_directory_patch.start()

    def tearDown(self) -> None:
        self.domain_directory_patch.stop()
        self.tmp_dir.cleanup()

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
            self.assertEqual(archive1.title, 'ジにてこちら')
            self.assertIsNotNone(archive1.url)
            self.assertIsNotNone(archive1.domain)

            # The actual files were dumped and read correctly.
            with open(archive1.singlefile_path) as fh:
                self.assertEqual(fh.read(), '<html>\ntest single-file\nジにてこちら\n</html>')
            with open(archive1.readability_path) as fh:
                self.assertEqual(fh.read(), '<html>test readability content</html>')
            with open(archive1.readability_txt_path) as fh:
                self.assertEqual(fh.read(), '<html>test readability textContent</html>')
            with open(archive1.readability_json_path) as fh:
                self.assertEqual(json.load(fh), {'title': 'ジにてこちら'})

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
            self.assertIsInstance(archive.screenshot_path, pathlib.Path)
            # Readability empty
            self.assertIsNone(archive.readability_path)
            self.assertIsNone(archive.readability_txt_path)

            self.assertIsNone(archive.title)

    @wrap_test_db
    def test_dict(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            d = new_archive('https://example.com').dict()
            self.assertIsInstance(d, dict)
            json.dumps(d, cls=CustomJSONEncoder)

    @wrap_test_db
    def test_relationships(self):
        with get_db_session(commit=True) as session:
            domain, url = get_or_create_domain_and_url(session, 'https://wrolpi.org:443')
            archive = Archive(
                singlefile_path='foo',
                title='bar',
                url_id=url.id,
                domain_id=domain.id,
            )
            session.add(archive)
            session.flush()

            url.latest_id = archive.id

        self.assertEqual(archive.domain, domain)
        self.assertEqual(archive.url, url)

        # Relationships are added in the dict() method.
        self.assertDictContains(
            url.dict(),
            dict(
                id=1,
                url='https://wrolpi.org:443',
                latest_id=1,
                latest=dict(singlefile_path=pathlib.Path('foo')),
                domain_id=1,
                domain=dict(directory=f'{self.tmp_dir.name}/wrolpi.org:443', domain='wrolpi.org:443'),
            )
        )

    @wrap_test_db
    def test_get_urls(self):
        # No URLs yet.
        urls = get_urls()
        self.assertEqual([], urls)

        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
            # One set of duplicate URLs
            new_archive('https://wrolpi.org/one')
            new_archive('https://wrolpi.org/one')

            new_archive('https://wrolpi.org/two')
            new_archive('https://wrolpi.org/three')
            new_archive('https://example.com/one')

        urls = get_urls()
        # There are only 4 because one set is duplicate.
        self.assertEqual(len(urls), 4)
        self.assertEqual(
            ['https://wrolpi.org/one', 'https://wrolpi.org/two', 'https://wrolpi.org/three', 'https://example.com/one'],
            [i['url'] for i in urls],
        )

        # Only one URL for this domain.
        urls = get_urls(domain='example.com')
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0]['url'], 'https://example.com/one')

        # Bad domain requested.
        self.assertRaises(InvalidDomain, get_urls, domain='bad_domain.com')

        # Limit to 3, but with an offset of 2 there are only 2.
        urls = get_urls(3, 2)
        self.assertEqual(['https://wrolpi.org/three', 'https://example.com/one'], [i['url'] for i in urls])

        # First two of this domain.
        urls = get_urls(2, 0, 'wrolpi.org')
        self.assertEqual(['https://wrolpi.org/one', 'https://wrolpi.org/two'], [i['url'] for i in urls])
        # Last two of this domain, but there is only 1.
        urls = get_urls(2, 2, 'wrolpi.org')
        self.assertEqual(['https://wrolpi.org/three'], [i['url'] for i in urls])

    @wrap_test_db
    def test_validate_paths(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            archive = new_archive('https://example.com')
            try:
                with get_db_session(commit=True):
                    archive.singlefile_path = 'asdf'
            except ValueError as e:
                self.assertIn('relative', str(e), f'Relative path error was not raised')

    @wrap_test_db
    def test_get_url_count(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            self.assertRaises(InvalidDomain, get_url_count, 'bad domain')

            self.assertEqual(get_url_count(), 0)
            new_archive('https://example.com')
            self.assertEqual(get_url_count(), 1)
            new_archive('https://example.com')
            self.assertEqual(get_url_count(), 1)
            new_archive('https://example.org')
            self.assertEqual(get_url_count(), 2)
            new_archive('https://example.org')
            self.assertEqual(get_url_count('example.org'), 1)
