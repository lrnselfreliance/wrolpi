import json
import pathlib
from datetime import datetime

import mock
import pytest

from modules.archive import lib
from modules.archive.lib import get_or_create_domain, _refresh_archives, \
    get_new_archive_files, delete_archive, do_archive, get_domains, get_archive_directory, group_archive_files, \
    ArchiveFiles
from modules.archive.models import Archive, Domain
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_session
from wrolpi.media_path import MediaPath
from wrolpi.root_api import CustomJSONEncoder
from wrolpi.test.common import TestAPI, wrap_test_db


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


def test_fills_contents_with_refresh(test_session, archive_factory, test_client):
    """Refreshing archives fills in any missing contents."""
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
    # The archives will be renamed with their title.
    archive1, archive2, archive3, archive4 = test_session.query(Archive).order_by(Archive.id)
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


def test_get_domains(test_session, archive_factory):
    """
    `get_domains` gets only Domains with Archives.
    """
    archive1 = archive_factory('example.com')
    archive2 = archive_factory('example.com')
    archive3 = archive_factory('example.org')

    assert [i['domain'] for i in get_domains()] == ['example.com', 'example.org']

    archive2.delete()
    test_session.commit()
    assert [i['domain'] for i in get_domains()] == ['example.com', 'example.org']

    archive1.delete()
    test_session.commit()
    assert [i['domain'] for i in get_domains()] == ['example.org']

    archive3.delete()
    test_session.commit()
    assert [i['domain'] for i in get_domains()] == []


def test_new_archive(test_session, fake_now):
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        fake_now(datetime(2000, 1, 1))
        archive1 = do_archive('https://example.com')
        # Everything is filled out.
        assert isinstance(archive1, Archive)
        assert archive1.archive_datetime is not None
        assert isinstance(archive1.singlefile_path, MediaPath)
        assert isinstance(archive1.readability_path, MediaPath)
        assert isinstance(archive1.readability_txt_path, MediaPath)
        assert isinstance(archive1.screenshot_path, MediaPath)
        assert archive1.title == 'ジにてこちら'
        assert archive1.url is not None
        assert archive1.domain is not None

        # The actual files were dumped and read correctly.
        with open(archive1.singlefile_path.path) as fh:
            assert fh.read() == '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        with open(archive1.readability_path.path) as fh:
            assert fh.read() == '<html>test readability content</html>'
        with open(archive1.readability_txt_path.path) as fh:
            assert fh.read() == '<html>test readability textContent</html>'
        with open(archive1.readability_json_path.path) as fh:
            assert json.load(fh) == {'title': 'ジにてこちら', 'url': 'https://example.com'}

        fake_now(datetime(2000, 1, 2))
        archive2 = do_archive('https://example.com')
        # Domain is reused.
        assert archive1.domain == archive2.domain


def test_get_title_from_html(test_session, fake_now):
    fake_now(datetime(2000, 1, 1))
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        archive = do_archive('example.com')
        assert archive.title == 'ジにてこちら'

    def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        r = dict(
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    fake_now(datetime(2000, 1, 2))
    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive = do_archive('example.com')
        assert archive.title == 'some title'

    def fake_request_archive(_):
        singlefile = '<html></html>'
        r = dict(
            content=f'<html>missing a title</html>',
            textContent='',
        )
        s = b'screenshot data'
        return singlefile, r, s

    fake_now(datetime(2000, 1, 3))
    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive = do_archive('example.com')
        assert archive.title is None


def test_get_new_archive_files(fake_now):
    """Archive files have a specific format so they are sorted by datetime, and are near each other."""
    fake_now(datetime(2001, 1, 1))
    archive_files = get_new_archive_files('https://example.com/two', None)
    assert str(archive_files.singlefile).endswith('archive/example.com/2001-01-01-00-00-00_NA.html')
    assert str(archive_files.readability).endswith('archive/example.com/2001-01-01-00-00-00_NA.readability.html')
    assert str(archive_files.readability_txt).endswith('archive/example.com/2001-01-01-00-00-00_NA.readability.txt')
    assert str(archive_files.readability_json).endswith('archive/example.com/2001-01-01-00-00-00_NA.readability.json')
    assert str(archive_files.screenshot).endswith('archive/example.com/2001-01-01-00-00-00_NA.png')

    archive_files = get_new_archive_files('https://www.example.com/one', 'Title')
    # Leading www. is removed.
    assert str(archive_files.singlefile).endswith('archive/example.com/2001-01-01-00-00-00_Title.html')
    assert str(archive_files.readability).endswith('archive/example.com/2001-01-01-00-00-00_Title.readability.html')
    assert str(archive_files.readability_txt).endswith('archive/example.com/2001-01-01-00-00-00_Title.readability.txt')
    assert str(archive_files.readability_json).endswith(
        'archive/example.com/2001-01-01-00-00-00_Title.readability.json')
    assert str(archive_files.screenshot).endswith('archive/example.com/2001-01-01-00-00-00_Title.png')


def test_title_in_filename(test_session, fake_now, test_directory):
    """
    The Archive files have the title in the path.
    """
    fake_now(datetime(2000, 1, 1))

    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        archive1 = do_archive('example.com')

    assert archive1.title == 'ジにてこちら'

    assert str(archive1.singlefile_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_ジにてこちら.html'
    assert str(archive1.readability_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_ジにてこちら.readability.html'
    assert str(archive1.readability_txt_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_ジにてこちら.readability.txt'
    assert str(archive1.readability_json_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_ジにてこちら.readability.json'
    assert str(archive1.screenshot_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_ジにてこちら.png'

    def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n</html>'  # no title in HTML
        r = dict(
            # No Title from Readability.
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive2 = do_archive('example.com')

    assert str(archive2.singlefile_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_NA.html'
    assert str(archive2.readability_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_NA.readability.html'
    assert str(archive2.readability_txt_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_NA.readability.txt'
    assert str(archive2.readability_json_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_NA.readability.json'
    assert str(archive2.screenshot_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_NA.png'

    def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>dangerous ;\\//_title</html></html>'
        r = dict(
            # No Title from Readability.
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive3 = do_archive('example.com')

    assert str(archive3.singlefile_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_dangerous ;_title.html'
    assert str(archive3.readability_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_dangerous ;_title.readability.html'
    assert str(archive3.readability_txt_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_dangerous ;_title.readability.txt'
    assert str(archive3.readability_json_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_dangerous ;_title.readability.json'
    assert str(archive3.screenshot_path.path.relative_to(test_directory)) == \
           'archive/2000-01-01-00-00-00_dangerous ;_title.png'


def test_refresh_archives(test_session, test_directory):
    """Archives can be found and put in the database.  A single Archive will have multiple files."""
    archive_directory = get_archive_directory()

    # Make some test files to refresh.
    example_dir = archive_directory / 'example.com'
    example_dir.mkdir()
    (example_dir / '2021-10-05 16:20:10.346823.html').touch()  # renames to 2021-10-05-16-20-10_NA.html
    (example_dir / '2021-10-05 16:20:10.346823.png').touch()
    (example_dir / '2021-10-05 16:20:10.346823-readability.txt').touch()
    (example_dir / '2021-10-05 16:20:10.346823-readability.json').touch()
    (example_dir / '2021-10-05 16:20:10.346823-readability.html').touch()
    with (example_dir / '2021-10-05 16:20:10.346823-readability.json').open('wt') as fh:
        json.dump({'url': 'foo'}, fh)

    # These should log an error because they are missing the singlefile path.
    (example_dir / '2021-10-05 16:20:10.readability.html').touch()
    (example_dir / '2021-10-05 16:20:11.readability.json').touch()
    # Bad files should also be ignored.
    (example_dir / 'random file').touch()
    (example_dir / '2021-10-05 16:20:10.346827-something.html').mkdir()
    (example_dir / '2021-10-05 16:20:10 no extension').touch()

    # The single archive is found.
    _refresh_archives()
    with get_db_session() as session:
        assert session.query(Archive).count() == 1

    # Running the refresh does not result in a new archive.
    _refresh_archives()
    with get_db_session() as session:
        assert session.query(Archive).count() == 1

    # Archives file format was changed, lets check the new formats are found.
    (example_dir / '2021-10-05-16-20-11_The Title.html').touch()
    (example_dir / '2021-10-05-16-20-11_The Title.readability.json').write_text(json.dumps({'url': 'bar'}))
    _refresh_archives()
    # The old formatted archive above is renamed.
    assert (example_dir / '2021-10-05-16-20-10_NA.html').is_file()
    with get_db_session() as session:
        assert session.query(Archive).count() == 2


def test_group_archive_files(test_directory):
    """Archive files should be grouped together when they are the same Archive."""
    files = [
        pathlib.Path('2021-10-05 16:20:10.346823.html'),
        pathlib.Path('2021-10-05 16:20:10.346823.readability.json'),
        pathlib.Path('2000-01-01-00-00-00_Title.html'),
        pathlib.Path('2000-01-01-00-00-00_Title.readability.json'),
        pathlib.Path('not an archive'),
        pathlib.Path('2000-01-01-00-00-01_Missing a singlefile.readability.json'),
    ]

    group1 = ArchiveFiles(
        singlefile=pathlib.Path('2000-01-01-00-00-00_Title.html'),
        readability_json=pathlib.Path('2000-01-01-00-00-00_Title.readability.json')
    )
    group2 = ArchiveFiles(
        singlefile=pathlib.Path('2021-10-05 16:20:10.346823.html'),
        readability_json=pathlib.Path('2021-10-05 16:20:10.346823.readability.json'),
    )
    assert list(group_archive_files(files)) == [
        (local_timezone(datetime(2000, 1, 1, 0, 0, 0)), group1),
        (local_timezone(datetime(2021, 10, 5, 16, 20, 10)), group2),
    ]


@pytest.mark.parametrize(
    'name,expected', [
        ('foo', False),
        ('2000-01-01-00-00-00_Some Title.html', True),
        ('2000-01-01-00-00-00_Some Title.readability.json', True),
        ('2000-01-01-00-00-00_Some Title.readability.html', True),
        ('2000-01-01-00-00-00_Some Title.readability.txt', True),
        ('2000-01-01-00-00-00_Some Title.png', True),
        ('2000-01-01-00-00-00_Some Title.jpg', True),
        ('2000-01-01-00-00-00_Some Title.jpeg', True),
        ('2000-01-01-00-00-00_Some NA.html', True),
        ('2000-01-01-00-00-00_NA.readability.json', True),
        ('2000-01-01-00-00-00_NA.readability.html', True),
        ('2000-01-01-00-00-00_NA.readability.txt', True),
        ('2000-01-01-00-00-00_NA.png', True),
        ('2000-01-01-00-00-00_NA.jpg', True),
        ('2000-01-01-00-00-00_NA.jpeg', True),
        ('2000-01-01-00-00-00_ジにてこちら.html', True),
        ('2000-01-01-00-00-00no underscore.html', False),
    ]
)
def test_is_archive_file(name, expected, test_directory):
    path = test_directory / name
    path.touch()
    assert lib.is_archive_file(path) == expected


def test_migrate_archive_files(test_session, archive_directory, archive_factory):
    """Test that migration of all old Archive formatted files are migrated."""
    # Create some updated archives that should be ignored.
    archive1 = archive_factory('example.com', title='the title')
    archive2 = archive_factory('example.com')
    archive3 = archive_factory('example.org')
    assert archive1.singlefile_path.path.is_file()
    assert archive2.singlefile_path.path.is_file()
    assert archive3.singlefile_path.path.is_file()

    example_com_directory = archive_directory / 'example.com'
    example_org_directory = archive_directory / 'example.org'

    # Archive4
    (example_com_directory / '2021-10-05 16:20:10.346823.html').touch()
    path = example_com_directory / '2021-10-05 16:20:10.346823.readability.json'
    path.write_text(json.dumps({'title': 'my title'}))
    # Archive5
    (example_com_directory / '2000-01-01 00:00:00.000000.html').touch()
    path = example_com_directory / '2000-01-01 00:00:00.000000.readability.json'
    path.write_text(json.dumps({'title': 'invalid#*: title'}))
    # Archive6
    (example_org_directory / '2000-01-01 00:00:00.000000.html').touch()
    path = example_org_directory / '2000-01-01 00:00:00.000000.readability.json'
    path.write_text(json.dumps({'title': 'invalid#*: title'}))

    # Migration forms a plan, then performs it.
    plan = lib.migrate_archive_files()
    for old, new in plan:
        # All files are moved.
        assert not old.is_file()
        assert new.is_file()
    # Check that only the outdated files are moved.
    plan = [(i.relative_to(archive_directory), j.relative_to(archive_directory)) for i, j in plan]
    assert plan == [
        (pathlib.Path('example.com/2000-01-01 00:00:00.000000.html'),
         pathlib.Path('example.com/2000-01-01-00-00-00_invalid# title.html')),
        (pathlib.Path('example.com/2000-01-01 00:00:00.000000.readability.json'),
         pathlib.Path('example.com/2000-01-01-00-00-00_invalid# title.readability.json')),
        (pathlib.Path('example.com/2021-10-05 16:20:10.346823.html'),
         pathlib.Path('example.com/2021-10-05-16-20-10_my title.html')),
        (pathlib.Path('example.com/2021-10-05 16:20:10.346823.readability.json'),
         pathlib.Path('example.com/2021-10-05-16-20-10_my title.readability.json')),
        (pathlib.Path('example.org/2000-01-01 00:00:00.000000.html'),
         pathlib.Path('example.org/2000-01-01-00-00-00_invalid# title.html')),
        (pathlib.Path('example.org/2000-01-01 00:00:00.000000.readability.json'),
         pathlib.Path('example.org/2000-01-01-00-00-00_invalid# title.readability.json')),
    ]
    # New Archive files still exist.
    assert all(i.is_file() for i in archive1.my_paths())
    assert all(i.is_file() for i in archive2.my_paths())
    assert all(i.is_file() for i in archive3.my_paths())
