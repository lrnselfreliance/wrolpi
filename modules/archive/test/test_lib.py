import json
import pathlib
from datetime import datetime

import mock

from modules.archive.lib import get_or_create_domain, _refresh_archives, \
    get_new_archive_files, delete_archive, do_archive
from modules.archive.models import Archive, Domain
from wrolpi.common import get_media_directory
from wrolpi.db import get_db_session
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
            archive1 = do_archive('https://example.com')
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

            archive2 = do_archive('https://example.com')
            # Domain is reused.
            self.assertEqual(archive1.domain, archive2.domain)

    @wrap_test_db
    def test_no_screenshot(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(screenshot=False)):
            archive = do_archive('https://example.com')
            self.assertIsInstance(archive.singlefile_path, MediaPath)
            self.assertIsInstance(archive.readability_path, MediaPath)
            # Screenshot was empty
            self.assertIsNone(archive.screenshot_path)

    @wrap_test_db
    def test_no_readability(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
            archive = do_archive('https://example.com')
            self.assertIsInstance(archive.singlefile_path, MediaPath)
            self.assertIsInstance(archive.screenshot_path, MediaPath)
            # Readability empty
            self.assertIsNone(archive.readability_path)
            self.assertIsNone(archive.readability_txt_path)

    @wrap_test_db
    def test_dict(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            d = do_archive('https://example.com').dict()
            self.assertIsInstance(d, dict)
            json.dumps(d, cls=CustomJSONEncoder)

    @wrap_test_db
    def test_relationships(self):
        with get_db_session(commit=True) as session:
            url = 'https://wrolpi.org:443'
            domain = get_or_create_domain(session, url)
            archive = Archive(
                singlefile_path=f'{self.tmp_dir.name}/wrolpi.org:443/foo',
                title='bar',
                url=url,
                domain_id=domain.id,
            )
            session.add(archive)
            session.flush()

        self.assertEqual(archive.domain, domain)

    @wrap_test_db
    def test_validate_paths(self):
        with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
            archive = do_archive('https://example.com')
            try:
                with get_db_session(commit=True):
                    archive.singlefile_path = 'asdf'
            except ValueError as e:
                self.assertIn('relative', str(e), f'Relative path error was not raised')

    @wrap_test_db
    def test_get_title_from_html(self):
        with wrap_media_directory():
            with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
                archive = do_archive('example.com')
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
                archive = do_archive('example.com')
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
                archive = do_archive('example.com')
                self.assertIsNone(archive.title)

    @wrap_test_db
    def test_refresh_archives(self):
        with wrap_media_directory():
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
                self.assertEqual(session.query(Archive).count(), 1)

            # Running the refresh does not result in a new archive.
            _refresh_archives()
            with get_db_session() as session:
                self.assertEqual(session.query(Archive).count(), 1)


def test_archive_refresh_deleted_archive(test_session, archive_directory, archive_factory):
    """
    Archives/Domains should be deleted when archive files are deleted.
    """
    archive1 = archive_factory('example.com', 'https://example.com/1')
    archive2 = archive_factory('example.com', 'https://example.com/1')
    archive3 = archive_factory('example.com')
    archive4 = archive_factory('example.org')
    archive5 = archive_factory()

    # Empty directories should be ignored.
    empty = archive_directory / 'empty'
    empty.mkdir()

    def check_counts(archive_count, domain_count):
        assert test_session.query(Archive).count() == archive_count
        assert test_session.query(Domain).count() == domain_count

    # All 3 archives are already in the DB.
    check_counts(archive_count=5, domain_count=3)
    _refresh_archives()
    check_counts(archive_count=5, domain_count=3)

    # Delete archive2's files, it's the latest for 'https://example.com/1'
    for path in archive2.my_paths():
        path.unlink()
    _refresh_archives()
    check_counts(archive_count=4, domain_count=3)

    # Delete archive1's files, now the URL is empty.
    for path in archive1.my_paths():
        path.unlink()
    _refresh_archives()
    check_counts(archive_count=3, domain_count=3)

    # Delete archive3, now there is now example.com domain
    for path in archive3.my_paths():
        path.unlink()
    _refresh_archives()
    check_counts(archive_count=2, domain_count=2)

    # Delete all the rest of the archives
    for path in archive4.my_paths():
        path.unlink()
    for path in archive5.my_paths():
        path.unlink()
    _refresh_archives()
    check_counts(archive_count=0, domain_count=0)


def test_refresh_archives_fills_contents(test_session, archive_factory, test_client):
    """
    Refreshing archives fills in any missing contents.
    """
    archive1 = archive_factory('example.com', 'https://example.com/one')
    archive2 = archive_factory('example.com', 'https://example.com/one')
    archive3 = archive_factory('example.org')
    archive4 = archive_factory('example.org')  # has no contents

    contents_title_archive = [
        ('foo bar qux', 'my archive', archive1),
        ('foo baz qux qux', 'other archive', archive2),
        ('baz qux qux qux', 'archive third', archive3),
    ]
    for contents, title, archive in contents_title_archive:
        with archive.readability_txt_path.path.open('wt') as fh:
            archive.title = title
            fh.write(contents)
    test_session.commit()

    # Contents are empty.
    assert not archive1.contents
    assert not archive2.contents
    assert not archive3.contents
    assert not archive4.contents

    # Fill the contents.
    _refresh_archives()
    assert archive1.contents
    assert archive2.contents
    assert archive3.contents
    assert not archive4.contents


def test_delete_archive(test_session, archive_factory):
    archive1 = archive_factory('example.com', 'https://example.com/1')
    archive2 = archive_factory('example.com', 'https://example.com/1')
    archive3 = archive_factory('example.com', 'https://example.com/1')

    # Delete the oldest.
    delete_archive(archive1.id)

    # Delete the latest.
    delete_archive(archive3.id)

    # Delete the last archive.  The Domain should also be deleted.
    delete_archive(archive2.id)
    domain = test_session.query(Domain).one_or_none()
    assert domain is None
