import json
import pathlib
from datetime import datetime, timedelta
from http import HTTPStatus

import mock
import pytest

from modules.archive import lib
from modules.archive.lib import get_or_create_domain, get_new_archive_files, delete_archives, do_archive, get_domains, \
    group_archive_files, ArchiveFiles
from modules.archive.models import Archive, Domain
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_session
from wrolpi.files.models import File
from wrolpi.root_api import CustomJSONEncoder
from wrolpi.test.common import skip_circleci


def make_fake_request_archive(readability=True, screenshot=True, title=True):
    async def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        r = dict(
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
            title='ジにてこちら' if title else None,
        ) if readability else None
        s = b'screenshot data' if screenshot else None
        return singlefile, r, s

    return fake_request_archive


@pytest.mark.asyncio
async def test_no_screenshot(test_session):
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(screenshot=False)):
        archive = await do_archive('https://example.com')
        assert isinstance(archive.singlefile_path, pathlib.Path)
        assert isinstance(archive.readability_path, pathlib.Path)
        # Screenshot was empty
        assert archive.screenshot_path is None


@pytest.mark.asyncio
async def test_no_readability(test_session):
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive(readability=False)):
        archive = await do_archive('https://example.com')
        assert isinstance(archive.singlefile_path, pathlib.Path)
        assert isinstance(archive.screenshot_path, pathlib.Path)
        # Readability empty
        assert archive.readability_path is None
        assert archive.readability_txt_path is None


@pytest.mark.asyncio
async def test_dict(test_session):
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        d = (await do_archive('https://example.com')).dict()
        assert isinstance(d, dict)
        json.dumps(d, cls=CustomJSONEncoder)


@pytest.mark.asyncio
async def test_relationships(test_session, test_directory):
    with get_db_session(commit=True) as session:
        url = 'https://wrolpi.org:443'
        domain = get_or_create_domain(session, url)
        archive = Archive(
            singlefile_file=File(path=test_directory / 'wrolpi.org:443/foo'),
            title='bar',
            url=url,
            domain_id=domain.id,
        )
        session.add(archive)
        session.flush()

    assert archive.domain == domain


def test_archive_refresh_deleted_archive(test_client, test_session, archive_directory, archive_factory):
    """Archives/Domains should be deleted when archive files are deleted."""
    archive1 = archive_factory('example.com', 'https://example.com/1')
    archive2 = archive_factory('example.com', 'https://example.com/1')
    archive3 = archive_factory('example.com')
    archive4 = archive_factory('example.org')
    archive5 = archive_factory()
    test_session.commit()

    # Empty directories should be ignored.
    (archive_directory / 'empty').mkdir()

    def check_counts(archive_count, domain_count):
        assert test_session.query(Archive).count() == archive_count, 'Archive count does not match'
        assert test_session.query(Domain).count() == domain_count, 'Domain count does not match'

    # All 5 archives are already in the DB.
    check_counts(archive_count=5, domain_count=2)
    test_client.post('/api/files/refresh')
    check_counts(archive_count=5, domain_count=1)

    # Delete archive2's files, it's the latest for 'https://example.com/1'
    for path in archive2.my_files():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=4, domain_count=1)

    # Delete archive1's files, now the URL is empty.
    for path in archive1.my_files():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=3, domain_count=0)

    # Delete archive3, now there is now example.com domain
    for path in archive3.my_files():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=2, domain_count=0)

    # Delete all the rest of the archives
    for path in archive4.my_files():
        path.unlink()
    for path in archive5.my_files():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=0, domain_count=0)


def test_fills_contents_with_refresh(test_client, test_session, archive_factory):
    """Refreshing archives fills in any missing contents."""
    archive1 = archive_factory('example.com', 'https://example.com/one')
    archive2 = archive_factory('example.com', 'https://example.com/one')
    # Title can be found in archive3's singlefile
    archive3 = archive_factory('example.org',
                               singlefile_contents='<html> some stuff<title>last title</title> other stuff</html>')
    archive4 = archive_factory('example.org')  # has no contents

    # Clear the title, this will be filled in.
    archive1.title = archive2.title = archive3.title = archive4.title = None

    contents_title_archive = [
        ('foo bar qux', 'my archive', archive1),
        ('foo baz qux qux', 'other archive', archive2),
        ('baz qux qux qux', None, archive3),
    ]
    for contents, json_title, archive in contents_title_archive:
        with archive.readability_txt_path.open('wt') as fh:
            fh.write(contents)
        if json_title:
            archive.readability_json_path.write_text(json.dumps({'title': json_title, 'url': archive.url}))
    test_session.commit()

    # Contents are empty.  Archives are all missing the title.
    assert not archive1.singlefile_file.d_text
    assert not archive2.singlefile_file.d_text
    assert not archive3.singlefile_file.d_text
    assert not archive4.singlefile_file.d_text

    # Fill the contents.
    test_client.post('/api/files/refresh')
    # The archives will be renamed with their title.
    archive1, archive2, archive3, archive4 = test_session.query(Archive).order_by(Archive.id)
    assert archive1.singlefile_file.title
    assert archive2.singlefile_file.title
    assert archive3.singlefile_file.title
    assert not archive4.singlefile_file.d_text

    # Missing title is filled.
    assert archive1.title == 'my archive'
    assert archive2.title == 'other archive'
    assert archive3.title == 'last title'  # from json


def test_delete_archive(test_session, archive_factory):
    """Archives can be deleted."""
    archive1 = archive_factory('example.com', 'https://example.com/1')
    archive2 = archive_factory('example.com', 'https://example.com/1')
    archive3 = archive_factory('example.com', 'https://example.com/1')
    test_session.commit()

    assert test_session.query(Archive).count() == 3

    # Delete the oldest.
    delete_archives(archive1.id, archive3.id)
    assert test_session.query(Archive).count() == 1

    # Delete the last archive.  The Domain should also be deleted.
    delete_archives(archive2.id)
    domain = test_session.query(Domain).one_or_none()
    assert domain is None


def test_get_domains(test_session, archive_factory):
    """
    `get_domains` gets only Domains with Archives.
    """
    archive1 = archive_factory('example.com')
    archive2 = archive_factory('example.com')
    archive3 = archive_factory('example.org')
    test_session.commit()

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


@pytest.mark.asycio
async def test_new_archive(test_session, fake_now):
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        fake_now(datetime(2000, 1, 1))
        archive1 = await do_archive('https://example.com')
        # Everything is filled out.
        assert isinstance(archive1, Archive)
        assert archive1.archive_datetime is not None
        assert isinstance(archive1.singlefile_path, pathlib.Path)
        assert isinstance(archive1.readability_path, pathlib.Path)
        assert isinstance(archive1.readability_txt_path, pathlib.Path)
        assert isinstance(archive1.screenshot_path, pathlib.Path)
        assert archive1.title == 'ジにてこちら'
        assert archive1.url is not None
        assert archive1.domain is not None

        # The actual files were dumped and read correctly.
        with open(archive1.singlefile_path) as fh:
            assert fh.read() == '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        with open(archive1.readability_path) as fh:
            assert fh.read() == '<html>test readability content</html>'
        with open(archive1.readability_txt_path) as fh:
            assert fh.read() == '<html>test readability textContent</html>'
        with open(archive1.readability_json_path) as fh:
            assert json.load(fh) == {'title': 'ジにてこちら', 'url': 'https://example.com'}

        fake_now(datetime(2000, 1, 2))
        archive2 = await do_archive('https://example.com')
        # Domain is reused.
        assert archive1.domain == archive2.domain


@pytest.mark.asyncio
async def test_get_title_from_html(test_session, fake_now):
    fake_now(datetime(2000, 1, 1))
    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        archive = await do_archive('https://example.com')
        assert archive.title == 'ジにてこちら'

    async def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
        r = dict(
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    fake_now(datetime(2000, 1, 2))
    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive = await do_archive('https://example.com')
        assert archive.title == 'some title'

    async def fake_request_archive(_):
        singlefile = '<html></html>'
        r = dict(
            content=f'<html>missing a title</html>',
            textContent='',
        )
        s = b'screenshot data'
        return singlefile, r, s

    fake_now(datetime(2000, 1, 3))
    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive = await do_archive('https://example.com')
        assert archive.title is None


@skip_circleci
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


@skip_circleci
@pytest.mark.asyncio
async def test_title_in_filename(test_session, fake_now, test_directory):
    """
    The Archive files have the title in the path.
    """
    fake_now(datetime(2000, 1, 1))

    with mock.patch('modules.archive.lib.request_archive', make_fake_request_archive()):
        archive1 = await do_archive('https://example.com')

    assert archive1.title == 'ジにてこちら'

    assert str(archive1.singlefile_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_ジにてこちら.html'
    assert str(archive1.readability_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_ジにてこちら.readability.html'
    assert str(archive1.readability_txt_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_ジにてこちら.readability.txt'
    assert str(archive1.readability_json_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_ジにてこちら.readability.json'
    assert str(archive1.screenshot_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_ジにてこちら.png'

    async def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n</html>'  # no title in HTML
        r = dict(
            # No Title from Readability.
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive2 = await do_archive('https://example.com')

    assert str(archive2.singlefile_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_NA.html'
    assert str(archive2.readability_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_NA.readability.html'
    assert str(archive2.readability_txt_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_NA.readability.txt'
    assert str(archive2.readability_json_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_NA.readability.json'
    assert str(archive2.screenshot_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_NA.png'

    async def fake_request_archive(_):
        singlefile = '<html>\ntest single-file\nジにてこちら\n<title>dangerous ;\\//_title</html></html>'
        r = dict(
            # No Title from Readability.
            content=f'<html>test readability content</html>',
            textContent='<html>test readability textContent</html>',
        )
        s = b'screenshot data'
        return singlefile, r, s

    with mock.patch('modules.archive.lib.request_archive', fake_request_archive):
        archive3 = await do_archive('https://example.com')

    assert str(archive3.singlefile_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;_title.html'
    assert str(archive3.readability_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;_title.readability.html'
    assert str(archive3.readability_txt_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;_title.readability.txt'
    assert str(archive3.readability_json_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;_title.readability.json'
    assert str(archive3.screenshot_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;_title.png'


@skip_circleci
def test_refresh_archives(test_session, test_directory, test_client, make_files_structure):
    """
    Archives can be found and put in the database.  A single Archive will have multiple files.
    """
    # The start of a typical singlefile html file.
    singlefile_contents = '''<!DOCTYPE html> <html lang="en"><!--
 Page saved with SingleFile 
 url: https://example.com
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">'''

    make_files_structure({
        # These are all for an individual Archive.
        'archive/example.com/2021-10-05 16:20:10.346823.html': singlefile_contents,  # renames to 2021-10-05-16-20-10_NA
        'archive/example.com/2021-10-05 16:20:10.346823.png': None,
        'archive/example.com/2021-10-05 16:20:10.346823-readability.txt': 'article text contents',
        'archive/example.com/2021-10-05 16:20:10.346823-readability.json': '{"url": "https://example.com"}',
        'archive/example.com/2021-10-05 16:20:10.346823-readability.html': '<html></html>',
        # These should log an error because they are missing the singlefile path.
        'archive/example.com/2021-10-05 16:20:10.readability.html': '<html></html>',
        'archive/example.com/2021-10-05 16:20:10.readability.json': None,
        # Bad files should also be ignored.
        'archive/example.com/random file': 'hello',
        'archive/example.com/2021-10-05 16:20:10 no extension': None,
    })

    # The single archive is found.
    test_client.post('/api/files/refresh')
    assert test_session.query(Archive).count() == 1

    # Running the refresh does not result in a new archive.
    test_client.post('/api/files/refresh')
    assert test_session.query(Archive).count() == 1

    # Archives file format was changed, lets check the new formats are found.
    make_files_structure({
        'archive/example.com/2021-10-05-16-20-11_The Title.html': '<html></html>',
        'archive/example.com/2021-10-05-16-20-11_The Title.readability.json': '{"url": "https://example.com"}',
    })
    test_client.post('/api/files/refresh')
    # The old formatted archive above is renamed.
    assert (test_directory / 'archive/example.com/2021-10-05-16-20-10_NA.html').is_file()
    assert test_session.query(Archive).count() == 2

    content = json.dumps({'search_str': 'text', 'model': 'archive'})
    request, response = test_client.post('/api/files/search', content=content)
    assert response.status_code == HTTPStatus.OK
    assert response.json['files'], 'No files matched "text"'
    assert response.json['files'][0]['model'] == 'archive', 'Returned file was not an archive'
    assert response.json['files'][0].get('path') == 'archive/example.com/2021-10-05-16-20-10_NA.html', \
        'Could not find readability text file containing "text"'
    assert response.json['files'][0]['archive']['archive_datetime'], 'Archive has no datetime'


def test_refresh_archives_invalid_file(test_session, test_directory, test_client, make_files_structure):
    """
    Invalid Archives should be removed during refresh.
    """
    *_, bogus_path = make_files_structure({
        '2022-09-04-16-20-11_The Title.html': '<html></html>',
        '2022-09-04-16-20-11_The Title.readability.json': '{"url": "https://example.com"}',
        'bogus file': None,
    })
    test_client.post('/api/files/refresh')
    assert test_session.query(File).count() == 3  # Three files total.
    assert test_session.query(Archive).count() == 1  # Only one real archive.

    # Create an invalid Archive, it should be removed during refresh.
    test_session.add(Archive(singlefile_path=bogus_path))
    # Claim the bogus file as an Archive, this should be removed.
    bogus_file: File = test_session.query(File).filter_by(path=bogus_path).one()
    bogus_file.model = 'archive'
    test_session.commit()
    assert test_session.query(File).count() == 3
    assert test_session.query(Archive).count() == 2

    test_client.post('/api/files/refresh')
    assert test_session.query(File).count() == 3, 'More files in DB than we created'
    assert test_session.query(Archive).count() == 1, 'The bogus Archive was not removed'
    assert bogus_file.model is None, 'Model was not removed'


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


@skip_circleci
def test_migrate_archive_files(test_session, archive_directory, archive_factory):
    """Test that migration of all old Archive formatted files are migrated."""
    # Create some updated archives that should be ignored.
    archive1 = archive_factory('example.com', title='the title')
    archive2 = archive_factory('example.com')
    archive3 = archive_factory('example.org')
    test_session.commit()
    assert archive1.singlefile_path.is_file()
    assert archive2.singlefile_path.is_file()
    assert archive3.singlefile_path.is_file()

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
    path.write_text(json.dumps({'title': 'A' * 500}))  # Really long file name.

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
         pathlib.Path('example.org/2000-01-01-00-00-00_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.html')),
        (pathlib.Path('example.org/2000-01-01 00:00:00.000000.readability.json'),
         pathlib.Path(
             'example.org/2000-01-01-00-00-00_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.readability.json')),
    ]
    # New Archive files still exist.
    assert all(i.is_file() for i in archive1.my_files())
    assert all(i.is_file() for i in archive2.my_files())
    assert all(i.is_file() for i in archive3.my_files())


def test_archive_files(test_directory):
    af = lib.ArchiveFiles(
        singlefile=test_directory / 'archive/singlefile.html',
    )
    assert repr(af) == \
           "<ArchiveFiles singlefile='singlefile.html' readability=None readability_txt=None readability_json=None" \
           " screenshot=None>"


def test_archive_order(test_session, test_directory, archive_factory):
    archive1 = archive_factory()
    archive2 = archive_factory()
    archive2.archive_datetime += timedelta(seconds=10)
    test_session.commit()

    assert archive2 > archive1
    assert archive1 < archive2


@pytest.mark.asyncio
async def test_archive_download_index(test_session, test_directory, image_file):
    """An Archive is indexed when it is downloaded."""
    with mock.patch('modules.archive.lib.request_archive') as mock_request_archive:
        singlefile = '<html><title>the singlefile</title></html>'
        readability = dict(
            content='<html>the readability</html>',
            textContent='the readability',
        )
        mock_request_archive.return_value = (singlefile, readability, image_file.read_bytes())
        archive = await lib.do_archive('https://example.com')

    assert isinstance(archive, lib.Archive), 'Did not get an archive'
    assert archive.singlefile_path and archive.singlefile_path.exists() and \
           archive.singlefile_path.read_text() == singlefile, 'Singlefile was not stored'
    assert archive.readability_path and archive.readability_path.exists()
    assert archive.readability_json_path
    assert archive.readability_txt_path and archive.readability_txt_path.exists()
    assert archive.readability_txt_file.d_text == '{the,readability}', 'Readability text was not indexed'
    assert archive.title == 'the singlefile', 'Did not get the title from the singlefile'
    assert archive.screenshot_path and archive.screenshot_file and archive.screenshot_path.is_file(), \
        'Did not store the screenshot'
