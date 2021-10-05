import json
import pathlib

import mock

from modules.archive.lib import new_archive, get_or_create_domain_and_url, get_urls, get_url_count, delete_url
from modules.archive.models import Archive, URL
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidDomain, UnknownURL
from wrolpi.media_path import MediaPath
from wrolpi.root_api import CustomJSONEncoder
from wrolpi.test.common import TestAPI, wrap_test_db, test_media_directory


def make_fake_request_archive(readability=True, screenshot=True, title=True):
    def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        r = dict(
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
            title='ジにてこちら' if title else None,
        ) if readability else None
        s = b'screenshot data' if screenshot else None
        return singlefile, r, s

    return fake_request_archive


class TestArchive(TestAPI):

    def setUp(self) -> None:
        super().setUp()
        (pathlib.Path(self.tmp_dir.name) / 'archive').mkdir(exist_ok=True)

    @wrap_test_db
    def test_new_archive(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            archive1 = new_archive('https://example.com', sync=True)
            # Everything is filled out.
            self.assertIsInstance(archive1, Archive)
            self.assertIsNotNone(archive1.archive_datetime)
            self.assertIsInstance(archive1.singlefile_path, MediaPath)
            self.assertIsInstance(archive1.readability_path, MediaPath)
            self.assertIsInstance(archive1.readability_txt_path, MediaPath)
            self.assertIsInstance(archive1.screenshot_path, MediaPath)
            self.assertEqual(archive1.title, 'ジにてこちら')
            self.assertIsNotNone(archive1.url)
            self.assertIsNotNone(archive1.domain)

            # The actual files were dumped and read correctly.
            with open(archive1.singlefile_path.path) as fh:
                self.assertEqual(fh.read(), '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>')
            with open(archive1.readability_path.path) as fh:
                self.assertEqual(fh.read(), '<html>test readability content</html>')
            with open(archive1.readability_txt_path.path) as fh:
                self.assertEqual(fh.read(), '<html>test readability textContent</html>')
            with open(archive1.readability_json_path.path) as fh:
                self.assertEqual(json.load(fh), {'title': 'ジにてこちら', 'url': 'https://example.com'})

            archive2 = new_archive('https://example.com')
            # URL and Domain are reused.
            self.assertEqual(archive1.url, archive2.url)
            self.assertEqual(archive1.domain, archive2.domain)

    @wrap_test_db
    def test_no_screenshot(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(screenshot=False)):
            archive = new_archive('https://example.com', sync=True)
            self.assertIsInstance(archive.singlefile_path, MediaPath)
            self.assertIsInstance(archive.readability_path, MediaPath)
            # Screenshot was empty
            self.assertIsNone(archive.screenshot_path)

    @wrap_test_db
    def test_no_readability(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
            archive = new_archive('https://example.com', sync=True)
            self.assertIsInstance(archive.singlefile_path, MediaPath)
            self.assertIsInstance(archive.screenshot_path, MediaPath)
            # Readability empty
            self.assertIsNone(archive.readability_path)
            self.assertIsNone(archive.readability_txt_path)

    @wrap_test_db
    def test_dict(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            d = new_archive('https://example.com', sync=True).dict()
            self.assertIsInstance(d, dict)
            json.dumps(d, cls=CustomJSONEncoder)

    @wrap_test_db
    def test_relationships(self):
        with get_db_session(commit=True) as session:
            domain, url = get_or_create_domain_and_url(session, 'https://wrolpi.org:443')
            archive = Archive(
                singlefile_path=f'{self.tmp_dir.name}/wrolpi.org:443/foo',
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
                latest=dict(singlefile_path=self.tmp_path / 'wrolpi.org:443/foo'),
                domain_id=1,
                domain=dict(directory=self.tmp_path / 'archive/wrolpi.org:443', domain='wrolpi.org:443'),
            )
        )

    @wrap_test_db
    def test_get_urls(self):
        # No URLs yet.
        urls = get_urls()
        self.assertEqual([], urls)

        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
            # One set of duplicate URLs
            new_archive('https://wrolpi.org/one', sync=True)
            new_archive('https://wrolpi.org/one', sync=True)

            # Unique URLs
            new_archive('https://wrolpi.org/two', sync=True)
            new_archive('https://wrolpi.org/three', sync=True)
            new_archive('https://example.com/one', sync=True)

        urls = get_urls()
        # There are only 4 because one set is duplicate.
        self.assertEqual(len(urls), 4)
        self.assertEqual(
            ['https://example.com/one', 'https://wrolpi.org/three',
             'https://wrolpi.org/two', 'https://wrolpi.org/one'],
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
        self.assertEqual(['https://wrolpi.org/two', 'https://wrolpi.org/one'], [i['url'] for i in urls])

        # First two of this domain.
        urls = get_urls(2, 0, 'wrolpi.org')
        self.assertEqual(['https://wrolpi.org/two', 'https://wrolpi.org/one'], [i['url'] for i in urls])
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
            new_archive('https://example.com', sync=True)
            self.assertEqual(get_url_count(), 1)
            new_archive('https://example.com', sync=True)
            self.assertEqual(get_url_count(), 1)
            new_archive('https://example.org', sync=True)
            self.assertEqual(get_url_count(), 2)
            new_archive('https://example.org', sync=True)
            self.assertEqual(get_url_count('example.org'), 1)

    @wrap_test_db
    def test_delete_url(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            archive = new_archive('https://example.com')

            with get_db_session() as session:
                urls = session.query(URL).all()
                self.assertEqual(len(urls), 1)
                archives = session.query(Archive).all()
                self.assertEqual(len(archives), 1)

        delete_url(archive.url.id)

        with get_db_session() as session:
            urls = session.query(URL).all()
            self.assertEqual(len(urls), 0)

        # Bad ID
        self.assertRaises(UnknownURL, delete_url, 123)

    @wrap_test_db
    def test_get_title_from_html(self):
        with test_media_directory():
            with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
                archive = new_archive('example.com', sync=True)
                self.assertEqual(archive.title, 'ジにてこちら')

            def fake_request_archive(_):
                singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
                r = dict(
                    content=f'<html>test readability content</html>',
                    textContent='<html>test readability textContent</html>',
                )
                s = b'screenshot data'
                return singlefile, r, s

            with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
                archive = new_archive('example.com', sync=True)
                self.assertEqual(archive.title, 'some title')

            def fake_request_archive(_):
                singlefile = '<html></html>'
                r = dict(
                    content=f'<html>missing a title</html>',
                    textContent='',
                )
                s = b'screenshot data'
                return singlefile, r, s

            with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
                archive = new_archive('example.com', sync=True)
                self.assertIsNone(archive.title)
