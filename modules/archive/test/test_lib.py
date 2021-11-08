import json
import pathlib
from datetime import datetime

import mock

from modules.archive.lib import new_archive, get_or_create_domain_and_url, get_urls, get_url_count, delete_url, \
    _refresh_archives, get_domains, get_new_archive_files
from modules.archive.models import Archive, URL, Domain
from wrolpi.common import get_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidDomain, UnknownURL
from wrolpi.media_path import MediaPath
from wrolpi.root_api import CustomJSONEncoder
from wrolpi.test.common import TestAPI, wrap_test_db, wrap_media_directory


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

    @mock.patch('modules.archive.lib.now', lambda: datetime(2001, 1, 1))
    def test_get_new_archive_files(self):
        s, r, t, j, c = map(str, get_new_archive_files('https://example.com/two'))
        assert str(s).endswith('archive/example.com/2001-01-01 00:00:00.000000.html')
        assert str(r).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.html')
        assert str(t).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.txt')
        assert str(j).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.json')
        assert str(c).endswith('archive/example.com/2001-01-01 00:00:00.000000.png')

        s, r, t, j, c = get_new_archive_files('https://www.example.com/one')
        # Leading www. is removed.
        assert str(s).endswith('archive/example.com/2001-01-01 00:00:00.000000.html')
        assert str(r).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.html')
        assert str(t).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.txt')
        assert str(j).endswith('archive/example.com/2001-01-01 00:00:00.000000-readability.json')
        assert str(c).endswith('archive/example.com/2001-01-01 00:00:00.000000.png')

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
            archive = new_archive('https://example.com', sync=True)

            with get_db_session() as session:
                urls = session.query(URL).all()
                self.assertEqual(len(urls), 1)
                archives = session.query(Archive).all()
                self.assertEqual(len(archives), 1)

            self.assertIsNotNone(archive.singlefile_path)
            singlefile_path = archive.singlefile_path.path
            self.assertTrue(singlefile_path.is_file())

            url_id = archive.url.id

        # Delete the URL, all archives and all files.
        delete_url(url_id)
        self.assertFalse(singlefile_path.exists())

        # Can't delete the same URL twice.
        self.assertRaises(UnknownURL, delete_url, url_id)

        with get_db_session() as session:
            urls = session.query(URL).all()
            self.assertEqual(len(urls), 0)

        # Bad ID
        self.assertRaises(UnknownURL, delete_url, 123)

    @wrap_test_db
    def test_get_title_from_html(self):
        with wrap_media_directory():
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

    @wrap_test_db
    def test_refresh_archives(self):
        with wrap_media_directory():
            with get_db_session() as session:
                urls = session.query(URL).count()
                self.assertEqual(urls, 0)

            archive_directory = get_media_directory() / 'archive'
            archive_directory.mkdir()

            # Make some test files to refresh.
            example = archive_directory / 'example.com'
            example.mkdir()
            (example / '2021-10-05 16:20:10.346823.html').touch()
            (example / '2021-10-05 16:20:10.346823.png').touch()
            (example / '2021-10-05 16:20:10.346823-readability.txt').touch()
            (example / '2021-10-05 16:20:10.346823-readability.json').touch()
            (example / '2021-10-05 16:20:10.346823-readability.html').touch()
            with (example / '2021-10-05 16:20:10.346823-readability.json').open('wt') as fh:
                json.dump({'url': 'foo'}, fh)

            # These should log an error because they are missing the singlefile path.
            (example / '2021-10-05 16:20:10.346824-readability.html').touch()
            (example / '2021-10-05 16:20:10.346825-readability.json').touch()
            # These are not archives and should be ignored.
            (example / '2021-10-05 16:20:10.346826-something.html').touch()
            (example / 'random file').touch()
            (example / '2021-10-05 16:20:10.346827-something.html').mkdir()
            (example / '2021-10-05 16:20:10 invalid date').touch()

            # This single archive is found.
            _refresh_archives()
            with get_db_session() as session:
                self.assertEqual(session.query(URL).count(), 1)
                self.assertEqual(session.query(Archive).count(), 1)

                url: URL = session.query(URL).one()
                archive: Archive = session.query(Archive).one()
                self.assertEqual(url.latest, archive)
                # latest_datetime is set, the timestamp in the file name is assumed to be UTC.
                self.assertEqual(str(url.latest_datetime), '2021-10-05 22:20:10.346823-06:00')

            # Running the refresh does not result in a new archive.
            _refresh_archives()
            with get_db_session() as session:
                self.assertEqual(session.query(URL).count(), 1)
                self.assertEqual(session.query(Archive).count(), 1)

    @wrap_test_db
    def test_refresh_archives_delete_empty(self):
        """
        Domains or URLs with no archives should be deleted during refresh.
        """
        with wrap_media_directory():
            (get_media_directory() / 'archive').mkdir()
            with get_db_session(commit=True) as session:
                # These should not be deleted.
                domain, url = get_or_create_domain_and_url(session, 'https://example.com')
                archive = Archive(singlefile_path='foo', url_id=url.id)
                session.add(archive)

                # These should be deleted.
                domain = Domain(domain='bar')
                session.add(domain)
                session.flush()
                session.add(URL(url='bar', domain_id=domain.id))

            self.assertEqual(len(get_urls()), 2)
            self.assertEqual(len(get_domains()), 2)

            _refresh_archives()

            self.assertEqual(len(get_urls()), 1)
            self.assertEqual(len(get_domains()), 1)
