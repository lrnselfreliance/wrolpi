import json
import pathlib
import tempfile
from datetime import datetime, timedelta
from http import HTTPStatus

import pytest
import pytz
from PIL import Image
from pytz import utc

from modules.archive import lib
from modules.archive.lib import get_or_create_domain, get_new_archive_files, delete_archives, model_archive_result, \
    get_domains
from modules.archive.models import Archive, Domain
from wrolpi.api_utils import CustomJSONEncoder
from wrolpi.common import get_wrolpi_config
from wrolpi.db import get_db_session
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.test.common import skip_circleci


def make_fake_archive_result(readability=True, screenshot=True, title=True):
    with tempfile.NamedTemporaryFile(suffix='.png') as fh:
        Image.new('RGB', (1, 1), color='grey').save(fh)
        fh.seek(0)
        image = fh.read()
    singlefile = '<html><!--\n Page saved with SingleFile-->\ntest single-file\nジにてこちら\n<title>some title</title></html>'
    r = dict(
        content=f'<html>test readability content</html>',
        textContent='test readability textContent',
        title='ジにてこちら' if title else None,
    ) if readability else None
    s = image if screenshot else None
    return singlefile, r, s


@pytest.mark.asyncio
async def test_no_screenshot(test_directory, test_session):
    singlefile, readability, screenshot = make_fake_archive_result(screenshot=False)
    archive = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    assert isinstance(archive.singlefile_path, pathlib.Path)
    assert isinstance(archive.readability_path, pathlib.Path)
    # Screenshot was empty
    assert archive.screenshot_path is None


@pytest.mark.asyncio
async def test_no_readability(test_directory, test_session):
    singlefile, readability, screenshot = make_fake_archive_result(readability=False)
    archive = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    assert isinstance(archive.singlefile_path, pathlib.Path)
    assert isinstance(archive.screenshot_path, pathlib.Path)
    # Readability empty
    assert archive.readability_path is None
    assert archive.readability_txt_path is None


@pytest.mark.asyncio
async def test_dict(test_session):
    singlefile, readability, screenshot = make_fake_archive_result()
    d = (await model_archive_result('https://example.com', singlefile, readability, screenshot)).dict()
    assert isinstance(d, dict)
    json.dumps(d, cls=CustomJSONEncoder)


@pytest.mark.asyncio
async def test_relationships(test_session, example_singlefile):
    with get_db_session(commit=True) as session:
        url = 'https://wrolpi.org:443'
        domain = get_or_create_domain(session, url)
        archive = Archive.from_paths(test_session, example_singlefile)
        archive.url = url
        archive.domain_id = domain.id
        session.add(archive)
        session.flush()

    assert archive.domain == domain


@pytest.mark.asyncio
async def test_archive_title(async_client, test_session, archive_factory, singlefile_contents_factory):
    """An Archive's title can be fetched in multiple ways.  This tests from most to least reliable."""
    # Create some test files, delete all records for a fresh refresh.
    archive_factory(
        domain='example.com',
        url='https://example.com/json-url',
        title='json title',
        singlefile_contents=singlefile_contents_factory('singlefile title', 'https://example.com/singlefile-url'),
    )

    async def reset_and_get_archive():
        test_session.query(FileGroup).delete()
        test_session.commit()
        await files_lib.refresh_files()
        return test_session.query(Archive).one()

    archive1: Archive = await reset_and_get_archive()

    assert test_session.query(FileGroup).count() == 1
    assert test_session.query(Archive).count() == 1

    # Readability JSON is trusted first.
    assert archive1.file_group.url == 'https://example.com/json-url'
    assert archive1.file_group.title == 'json title'

    # Delete JSON file.
    archive1.readability_json_path.unlink()
    archive1: Archive = await reset_and_get_archive()
    assert archive1.file_group.url == 'https://example.com/singlefile-url'
    assert archive1.file_group.title == 'singlefile title'

    # Clear out title and URL from Singlefile.
    archive1.singlefile_path.write_text(singlefile_contents_factory('', ''))
    archive1: Archive = await reset_and_get_archive()
    # No title/URL could be found.
    assert archive1.file_group.url is None
    assert archive1.file_group.title is None


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
    for path in archive2.my_paths():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=4, domain_count=1)

    # Delete archive1's files, now the URL is empty.
    for path in archive1.my_paths():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=3, domain_count=0)

    # Delete archive3, now there is now example.com domain
    for path in archive3.my_paths():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=2, domain_count=0)

    # Delete all the rest of the archives
    for path in archive4.my_paths():
        path.unlink()
    for path in archive5.my_paths():
        path.unlink()
    test_client.post('/api/files/refresh')
    check_counts(archive_count=0, domain_count=0)


@pytest.mark.asyncio
async def test_fills_contents_with_refresh(test_session, archive_factory, singlefile_contents_factory):
    """Refreshing archives fills in any missing contents."""
    archive1 = archive_factory('example.com', 'https://example.com/one')
    archive2 = archive_factory('example.com', 'https://example.com/one')
    # Title can be found in archive3's singlefile
    archive3 = archive_factory('example.org', singlefile_contents=singlefile_contents_factory('last title'))
    archive4 = archive_factory('example.org')  # has no contents

    # Clear the title, this will be filled in.
    archive1.file_group.title = archive2.file_group.title = archive3.file_group.title = archive4.file_group.title = None

    contents_title_archive = [
        ('foo bar qux', 'my archive', archive1),
        ('foo baz qux qux', 'other archive', archive2),
        ('baz qux qux qux', None, archive3),
    ]
    for contents, json_title, archive in contents_title_archive:
        archive: Archive
        readability_txt_path = archive.singlefile_path.with_suffix('.readability.txt')
        with readability_txt_path.open('wt') as fh:
            fh.write(contents)
        if json_title:
            readability_json_path = archive.singlefile_path.with_suffix('.readability.json')
            readability_json_path.write_text(json.dumps({'title': json_title, 'url': archive.url}))
    test_session.commit()

    # Contents are empty.  Archives are all missing the title.
    assert not archive1.file_group.d_text
    assert not archive2.file_group.d_text
    assert not archive3.file_group.d_text
    assert not archive4.file_group.d_text

    # Fill the contents.
    await files_lib.refresh_files()
    # The archives will be renamed with their title.
    archive1, archive2, archive3, archive4 = test_session.query(Archive).order_by(Archive.id)
    assert not archive4.file_group.d_text

    # Missing titles are filled.
    assert archive1.file_group.title == 'my archive'
    assert archive2.file_group.title == 'other archive'
    assert archive3.file_group.title == 'last title'  # from singlefile HTML


def test_delete_archive(test_session, archive_factory):
    """Archives can be deleted."""
    archive1 = archive_factory('example.com', 'https://example.com/1')
    archive2 = archive_factory('example.com', 'https://example.com/1')
    archive3 = archive_factory('example.com', 'https://example.com/1')
    test_session.commit()

    # Files are real.
    assert archive1.my_paths() and all(i.is_file() for i in archive1.my_paths())
    assert archive2.my_paths() and all(i.is_file() for i in archive2.my_paths())
    assert archive3.my_paths() and all(i.is_file() for i in archive3.my_paths())

    assert test_session.query(Archive).count() == 3
    assert test_session.query(FileGroup).count() == 3

    # Delete the oldest.
    delete_archives(archive1.id, archive3.id)
    assert test_session.query(Archive).count() == 1
    assert test_session.query(FileGroup).count() == 1
    # Files were deleted.
    assert archive1.my_paths() and not any(i.is_file() for i in archive1.my_paths())
    assert archive3.my_paths() and not any(i.is_file() for i in archive3.my_paths())
    # Archive2 is untouched
    assert archive2.my_paths() and all(i.is_file() for i in archive2.my_paths())

    # Delete the last archive.  The Domain should also be deleted.
    delete_archives(archive2.id)
    assert test_session.query(Archive).count() == 0
    domain = test_session.query(Domain).one_or_none()
    assert domain is None

    # All Files were deleted.
    assert test_session.query(FileGroup).count() == 0
    assert archive2.my_paths() and not any(i.is_file() for i in archive2.my_paths())


def test_get_domains(test_session, archive_factory):
    """
    `get_domains` gets only Domains with Archives.
    """
    archive1 = archive_factory('example.com')
    archive2 = archive_factory('example.com')
    archive3 = archive_factory('example.org')
    test_session.commit()

    assert archive1.domain
    assert archive2.domain
    assert archive3.domain

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


@skip_circleci
@pytest.mark.asyncio
async def test_new_archive(test_session, test_directory, fake_now):
    singlefile, readability, screenshot = make_fake_archive_result()
    fake_now(datetime(2000, 1, 1))
    archive1 = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    # Everything is filled out.
    assert isinstance(archive1, Archive)
    assert archive1.file_group.download_datetime is not None
    assert isinstance(archive1.singlefile_path, pathlib.Path)
    assert isinstance(archive1.readability_path, pathlib.Path)
    assert isinstance(archive1.readability_txt_path, pathlib.Path)
    assert isinstance(archive1.screenshot_path, pathlib.Path)
    assert archive1.file_group.title == 'ジにてこちら'
    assert archive1.url is not None
    assert archive1.domain is not None

    # The actual files were dumped and read correctly.  The HTML/JSON files are reformatted.
    assert archive1.singlefile_path.read_text().count('\n') >= 10
    assert archive1.readability_path.read_text().count('\n') >= 5
    with open(archive1.readability_txt_path) as fh:
        assert fh.read() == 'test readability textContent'
    assert archive1.readability_json_path.read_text() == '''{
  "title": "\\u30b8\\u306b\\u3066\\u3053\\u3061\\u3089",
  "url": "https://example.com"
}'''

    fake_now(datetime(2000, 1, 2))
    archive2 = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    # Domain is reused.
    assert archive1.domain == archive2.domain


@pytest.mark.asyncio
async def test_get_title_from_html(test_directory, test_session, fake_now):
    fake_now(datetime(2000, 1, 1))
    singlefile, readability, screenshot = make_fake_archive_result()
    archive = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    assert archive.file_group.title == 'ジにてこちら'

    singlefile = '<html>\ntest single-file\nジにてこちら\n<title>some title</title></html>'
    readability = dict(
        content=f'<html>test readability content</html>',
        textContent='<html>test readability textContent</html>',
    )
    screenshot = b'screenshot data'

    fake_now(datetime(2000, 1, 2))
    archive = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    assert archive.file_group.title == 'some title'

    singlefile = '<html></html>'
    readability = dict(
        content=f'<html>missing a title</html>',
        textContent='',
    )
    screenshot = b'screenshot data'

    fake_now(datetime(2000, 1, 3))
    archive = await model_archive_result('https://example.com', singlefile, readability, screenshot)
    assert archive.file_group.title is None


@skip_circleci
def test_get_new_archive_files_length(test_directory, fake_now):
    """Archive titles are truncated to fit file system length limit.  (255-character limit for most file systems)"""
    fake_now(datetime(2001, 1, 1))
    archive_files = get_new_archive_files('https://example.com', 'a' * 500)
    assert len(str(archive_files.singlefile.name)) == 225
    assert len(str(archive_files.readability.name)) == 237
    assert len(str(archive_files.readability_txt.name)) == 236
    assert len(str(archive_files.readability_json.name)) == 237
    assert len(str(archive_files.screenshot.name)) == 224


@skip_circleci
def test_get_new_archive_files(fake_now):
    """Archive files have a specific format, so they are sorted by datetime, and are near each other."""
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
async def test_title_in_filename(test_session, fake_now, test_directory, image_bytes_factory):
    """
    The Archive files have the title in the path.
    """
    fake_now(datetime(2000, 1, 1))

    singlefile, readability, screenshot = make_fake_archive_result()
    archive1 = await model_archive_result('https://example.com', singlefile, readability, screenshot)

    assert archive1.file_group.title == 'ジにてこちら'

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

    singlefile = '<html>\ntest single-file\nジにてこちら\n</html>'  # no title in HTML
    readability = dict(
        # No Title from Readability.
        content=f'<html>test readability content</html>',
        textContent='test readability textContent',
    )
    screenshot = image_bytes_factory()

    archive2 = await model_archive_result('https://example.com', singlefile, readability, screenshot)

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

    singlefile = '<html>\ntest single-file\nジにてこちら\n<title>dangerous ;\\//_title</html></html>'
    readability = dict(
        # No Title from Readability.
        content=f'<html>test readability content</html>',
        textContent='<html>test readability textContent</html>',
    )
    screenshot = image_bytes_factory()

    archive3 = await model_archive_result('https://example.com', singlefile, readability, screenshot)

    assert str(archive3.singlefile_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;⧸⧸_title.html'
    assert str(archive3.readability_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;⧸⧸_title.readability.html'
    assert str(archive3.readability_txt_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;⧸⧸_title.readability.txt'
    assert str(archive3.readability_json_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;⧸⧸_title.readability.json'
    assert str(archive3.screenshot_path.relative_to(test_directory)) == \
           'archive/example.com/2000-01-01-00-00-00_dangerous ;⧸⧸_title.png'


@pytest.mark.asyncio
async def test_refresh_archives(test_session, test_directory, async_client, make_files_structure):
    """Archives can be found and put in the database.  A single Archive will have multiple files."""
    # The start of a typical singlefile html file.
    singlefile_contents = '''<!DOCTYPE html> <html lang="en"><!--
 Page saved with SingleFile 
 url: https://example.com
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">'''

    make_files_structure({
        # These are all for an individual Archive.
        'archive/example.com/2021-10-05-16-20-10_NA.html': singlefile_contents,
        'archive/example.com/2021-10-05-16-20-10_NA.png': None,
        'archive/example.com/2021-10-05-16-20-10_NA.readability.txt': 'article text contents',
        'archive/example.com/2021-10-05-16-20-10_NA.readability.json': '{"url": "https://example.com"}',
        'archive/example.com/2021-10-05-16-20-10_NA.readability.html': '<html></html>',
        # These should log an error because they are missing the singlefile path.
        'archive/example.com/2021-10-05 16:20:10.readability.html': '<html></html>',
        'archive/example.com/2021-10-05 16:20:10.readability.json': None,
        # Bad files should also be ignored.
        'archive/example.com/random file': 'hello',
        'archive/example.com/2021-10-05 16:20:10 no extension': None,
    })

    # The single archive is found.
    await async_client.post('/api/files/refresh')
    assert test_session.query(Archive).count() == 1

    # Cause a re-index of the archive.
    test_session.query(FileGroup).filter_by(
        primary_path=str(test_directory / 'archive/example.com/2021-10-05-16-20-10_NA.html')).one().indexed = False
    test_session.commit()

    # Running the refresh does not result in a new archive.
    await async_client.post('/api/files/refresh')
    assert test_session.query(Archive).count() == 1

    # Archives file format was changed, lets check the new formats are found.
    make_files_structure({
        'archive/example.com/2021-10-05-16-20-11_The Title.html': '<html></html>',
        'archive/example.com/2021-10-05-16-20-11_The Title.readability.json': '{"url": "https://example.com"}',
    })
    await async_client.post('/api/files/refresh')
    # The old formatted archive above is renamed.
    assert (test_directory / 'archive/example.com/2021-10-05-16-20-10_NA.html').is_file()
    assert test_session.query(Archive).count() == 2

    content = json.dumps({'search_str': 'text', 'model': 'archive'})
    request, response = await async_client.post('/api/files/search', content=content)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'], 'No files matched "text"'
    assert response.json['file_groups'][0]['model'] == 'archive', 'Returned file was not an archive'
    assert response.json['file_groups'][0]['data'].get('readability_path') == \
           'archive/example.com/2021-10-05-16-20-10_NA.readability.html', \
        'Could not find readability html file'
    assert response.json['file_groups'][0]['data'].get('readability_txt_path') == \
           'archive/example.com/2021-10-05-16-20-10_NA.readability.txt', \
        'Could not find readability text file containing "text"'
    assert response.json['file_groups'][0]['download_datetime'], 'Archive has no datetime'


@pytest.mark.asyncio
async def test_refresh_archives_index(test_session, make_files_structure):
    """Archives are indexed using ArchiveIndexer and archive_modeler."""
    # The start of a typical singlefile html file.
    singlefile_contents = '''<!DOCTYPE html> <html lang="en"><!--
 Page saved with SingleFile 
 url: https://example.com
 saved date: Mon May 16 2022 23:51:35 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">
<script class="sf-hidden" type="application/ld+json">
 {"@context":"http://schema.org", "@type":"NewsArticle", "headline":"The headline",
  "datePublished":"2022-09-27T00:40:19.000Z", "dateModified":"2022-09-27T13:43:47.971Z",
  "author":{"@type":"Person", "name":"AUTHOR NAME", "jobTitle":""},
  "description": "The article description"}
</script>
</html>'''

    singlefile, *_ = make_files_structure({
        'archive/example.com/2021-10-05-16-20-10_NA.html': singlefile_contents,
        'archive/example.com/2021-10-05-16-20-10_NA.png': None,
        'archive/example.com/2021-10-05-16-20-10_NA.readability.txt': 'article text contents',
        'archive/example.com/2021-10-05-16-20-10_NA.readability.json':
            '{"url": "https://example.com", "title": "the title"}',
        'archive/example.com/2021-10-05-16-20-10_NA.readability.html': '<html></html>',
    })

    await files_lib.refresh_files()

    archive: Archive = test_session.query(Archive).one()
    assert archive.singlefile_path == singlefile

    assert archive.file_group.author == 'AUTHOR NAME'
    assert archive.file_group.published_datetime
    assert archive.file_group.published_modified_datetime

    assert archive.file_group.a_text == 'the title'  # from readability json
    assert archive.file_group.b_text == 'The article description'  # From application/ld+json
    assert archive.file_group.d_text == 'article text contents'  # from readability txt
    assert archive.file_group.indexed is True


@pytest.mark.asyncio
async def test_archive_meta(async_client, test_session, make_files_structure):
    # The start of a typical singlefile html file.
    singlefile_contents = '''<!DOCTYPE html> <html lang="en">
<script data-vue-meta="ssr" type="application/ld+json">
   {"@context":"https://schema.org/","@type":"NewsArticle","headline":"The Headline","description":"The Description","authors":[{"name":"A.B.C.","@type":"Person"}],"datePublished":"2021-06-20T10:00"}
  </script>
</html>'''

    singlefile, *_ = make_files_structure({
        'archive/example.com/2021-10-05-16-20-10_NA.html': singlefile_contents,
        'archive/example.com/2021-10-05-16-20-10_NA.png': None,
        'archive/example.com/2021-10-05-16-20-10_NA.readability.txt': 'article text contents',
        'archive/example.com/2021-10-05-16-20-10_NA.readability.html': '<html></html>',
    })

    await files_lib.refresh_files()

    archive: Archive = test_session.query(Archive).one()
    assert archive.singlefile_path == singlefile

    assert archive.file_group.author == 'A.B.C.'
    assert archive.file_group.published_datetime == datetime(2021, 6, 20, 10, 0, tzinfo=pytz.utc)

    assert archive.file_group.title == 'The Headline'
    assert archive.file_group.b_text == 'The Description'
    assert archive.file_group.indexed is True


@pytest.mark.asyncio
async def test_refresh_archives_deleted_singlefile(test_session, make_files_structure, singlefile_contents_factory):
    """Removing a Singlefile file from a FileGroup makes that group no longer an Archive."""
    singlefile, readability = make_files_structure({
        '2022-09-04-16-20-11_The Title.html': singlefile_contents_factory(),
        '2022-09-04-16-20-11_The Title.readability.json': '{"url": "https://example.com"}',
    })
    await files_lib.refresh_files()
    assert test_session.query(FileGroup).one().model == 'archive'
    assert test_session.query(Archive).count() == 1

    # Remove singlefile, FileGroup is no longer an Archive.
    singlefile.unlink()
    await files_lib.refresh_files()
    assert test_session.query(FileGroup).one().model is None
    assert test_session.query(Archive).count() == 0


@pytest.mark.parametrize(
    'name,expected', [
        ('foo', False),
        ('2000-01-01-00-00-00_Some NA.html', True),
        ('2000-01-01-00-00-00_Some NA.readability.html', False),
        ('2000-01-01-00-00-00_ジにてこちら.html', True),
        ('2000-01-01-00-00-00_Some Title.readability.txt', False),
        ('foo.txt', False),
        ('foo.html', True),
    ]
)
def test_is_singlefile_file(name, expected, make_files_structure, singlefile_contents_factory):
    """A Singlefile may not be created by WROLPi, an HTML file created by Singlefile can also be an Archive."""
    path, = make_files_structure({name: singlefile_contents_factory()})
    assert lib.is_singlefile_file(path) == expected


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
    archive2.file_group.download_datetime += timedelta(seconds=10)
    test_session.commit()

    assert archive2 > archive1
    assert archive1 < archive2


@pytest.mark.asyncio
async def test_archive_download_index(test_session, test_directory, image_bytes_factory):
    """An Archive is indexed when it is downloaded."""
    singlefile = '<html><title>the singlefile</title></html>'
    readability = dict(
        content='<html>the readability</html>',
        textContent='the readability',
    )
    archive = await lib.model_archive_result('https://example.com', singlefile, readability, image_bytes_factory())

    assert isinstance(archive, lib.Archive), 'Did not get an archive'
    assert archive.singlefile_path and archive.singlefile_path.exists() and \
           archive.singlefile_path.read_text() == \
           '<html>\n <head>\n  <title>\n   the singlefile\n  </title>\n </head>\n</html>\n', \
        'Singlefile was not formatted'
    assert archive.readability_path and archive.readability_path.exists()
    assert archive.readability_json_path
    assert archive.readability_txt_path and archive.readability_txt_path.exists()
    assert archive.file_group.d_text == 'the readability', 'Readability text was not indexed'
    assert archive.file_group.title == 'the singlefile', 'Did not get the title from the singlefile'
    assert archive.screenshot_path and archive.screenshot_file and archive.screenshot_path.is_file(), \
        'Did not store the screenshot'


def test_archive_history(test_session, archive_factory):
    """Archive's can have a history of other archives.

    Archive's with an empty URL are not associated."""
    archive1 = archive_factory(url='https://example.com/1')
    archive2 = archive_factory(url='https://example.com/1')
    archive3 = archive_factory(url='https://example.com/2')
    archive4 = archive_factory()
    archive5 = archive_factory()

    assert archive1 in archive2.history, 'archive1 is a history for archive2'
    assert archive2 in archive1.history, 'archive2 is a history for archive2'
    assert archive3 not in archive1.history and archive3 not in archive2.history, 'archive3 is unique'
    assert not archive3.history, 'archive3 has no history'
    assert not archive4.history, 'archive4 has no history'
    assert not archive5.history, 'archive5 has no history'

    test_session.commit()

    assert archive1 in archive2.history, 'archive1 is a history for archive2'
    assert archive2 in archive1.history, 'archive2 is a history for archive2'
    assert archive3 not in archive1.history and archive3 not in archive2.history, 'archive3 is unique'
    assert not archive3.history, 'archive3 has no history'
    assert not archive4.history, 'archive4 has no history'
    assert not archive5.history, 'archive5 has no history'


METADATA_EXAMPLE_1 = b'''
<!DOCTYPE html>
<html lang="en-US">
</html>
'''

METADATA_EXAMPLE_2 = b'''
<!DOCTYPE html>
<html lang="en-US">
 <head>
  <meta charset="utf-8"/>
  <title>This is not a meta title and should be ignored</title>
  <meta content="en_US" property="og:locale"/>
  <meta content="article" property="og:type"/>
  <meta content="The Title" property="og:title"/>
  <meta name="author" content="Author Name"/>
  <meta content="2023-10-18T04:52:23+00:00" property="article:published_time"/>
  <meta content="2023-10-19T05:53:24+00:00" property="article:modified_time"/>
 </head>
</html>
'''

METADATA_EXAMPLE_3 = b'''
<!DOCTYPE html>
<html lang="en-US">
<title>This is not a meta title and should be ignored</title>
<script class="sf-hidden" type="application/ld+json">
 {"@context":"http://schema.org", "@type":"NewsArticle", "headline":"The headline",
  "datePublished":"2022-09-27T00:40:19.000Z", "dateModified":"2022-09-27T13:43:47.971Z",
  "author":{"@type":"Person", "name":"BOBBY", "jobTitle":""},
  "creator":{"@type":"Person", "name":"OTHER BOBBY", "jobTitle":""},
  "description": "The article description"}
</script>
</html>'''

METADATA_EXAMPLE_4 = b'''
<!DOCTYPE html>
<html lang="en-US">
<title>This is not a meta title and should be ignored</title>
<a href="https://example.com" rel="author">
    Link Author
</a>
</html>'''

METADATA_EXAMPLE_5 = b'''
<!DOCTYPE html>
<html lang="en-US">
<title>This is not a meta title and should be ignored</title>
<a class='g-profile' href='https://example.com' rel='author' title='author profile'>
    <span itemprop='name'>The Span Author</span>
</a>
<time class="post-date updated" itemprop="datePublished" datetime="2023-08-25"></time>
</html>
'''


def test_parse_article_html_metadata():
    """Singlefiles may contain metadata tags."""
    # Metadata can be empty.
    metadata = lib.parse_article_html_metadata(METADATA_EXAMPLE_1)
    assert metadata.title is None
    assert metadata.published_datetime is None
    assert metadata.modified_datetime is None
    assert metadata.description is None
    assert metadata.author is None

    # Data from <meta> elements.
    metadata = lib.parse_article_html_metadata(METADATA_EXAMPLE_2)
    assert metadata.title == 'The Title'
    assert metadata.published_datetime == datetime(2023, 10, 18, 4, 52, 23, tzinfo=utc)
    assert metadata.modified_datetime == datetime(2023, 10, 19, 5, 53, 24, tzinfo=utc)
    assert metadata.description is None
    assert metadata.author == 'Author Name'

    # Data from Article structured data
    # https://developers.google.com/search/docs/appearance/structured-data/article
    metadata = lib.parse_article_html_metadata(METADATA_EXAMPLE_3)
    assert metadata.title == 'The headline'
    assert metadata.published_datetime == datetime(2022, 9, 27, 0, 40, 19, tzinfo=utc)
    assert metadata.modified_datetime == datetime(2022, 9, 27, 13, 43, 47, 971000, tzinfo=utc)
    assert metadata.description == 'The article description'
    assert metadata.author == 'BOBBY'

    # Data from author anchor element.
    metadata = lib.parse_article_html_metadata(METADATA_EXAMPLE_4)
    assert metadata.author == 'Link Author'

    # author anchor may be a list.
    metadata = lib.parse_article_html_metadata(METADATA_EXAMPLE_5)
    assert metadata.author == 'The Span Author'
    assert metadata.published_datetime == datetime(2023, 8, 25, tzinfo=pytz.UTC)


@pytest.mark.parametrize(
    'html,expected',
    [
        ('<meta content="2023-10-18T04:52:23+00:00" property="article:published_time"/>',
         datetime(2023, 10, 18, 4, 52, 23, tzinfo=utc)),
        ('<abbr class="published" itemprop="datePublished" title="2022-03-17T03:00:00-07:00">March 17, 2022</abbr>',
         datetime(2022, 3, 17, 10, 0, tzinfo=pytz.UTC)),
        ('<meta name="article.published" content="2023-04-04T21:52:00.000Z">',
         datetime(2023, 4, 4, 21, 52, tzinfo=pytz.UTC)),
        ('<meta itemprop="datePublished" content="2023-04-04T21:52:00.000Z">',
         datetime(2023, 4, 4, 21, 52, tzinfo=pytz.UTC)),
        (
                '<abbr class="published" itemprop="datePublished" title="2013-03-05T00:12:00-06:00">3/05/2013 12:12:00 AM</abbr>',
                datetime(2013, 3, 5, 6, 12, tzinfo=pytz.UTC)),
        ('<time class="post-date updated" itemprop="datePublished" datetime="2023-08-25"></time>',
         datetime(2023, 8, 25, tzinfo=pytz.UTC))
    ])
def test_published_datetime(html, expected):
    assert lib.parse_article_html_metadata(html).published_datetime == expected


@pytest.mark.parametrize(
    'html,expected',
    [
        ('<meta name="article.updated" content="2023-04-04T21:52:00.000Z">',
         datetime(2023, 4, 4, 21, 52, tzinfo=pytz.UTC)),
        ('<meta content="2023-10-19T05:53:24+00:00" property="article:modified_time"/>',
         datetime(2023, 10, 19, 5, 53, 24, tzinfo=utc)),
        (
                '<script class="sf-hidden" type="application/ld+json">{"@context":"http://schema.org","dateModified":"2022-09-27T13:43:47.971Z"}</script>',
                datetime(2022, 9, 27, 13, 43, 47, 971000, tzinfo=utc)),
    ])
def test_modified_datetime(html, expected):
    assert lib.parse_article_html_metadata(html).modified_datetime == expected


@pytest.mark.parametrize(
    'html,expected',
    [
        ('<a href="#" rel="author"><span itemprop="name">Linda</span></a></span>', 'Linda'),
        ('<meta content="Billy" property="article:author"/>', 'Billy'),
    ]
)
def test_author(html, expected):
    assert lib.parse_article_html_metadata(html).author == expected


SINGLEFILE_EXAMPLE_1 = b'''<!DOCTYPE html>
<html class="fonts-loaded" lang="en">
 <!--
 Page saved with SingleFile 
 url: https://www.example.com 
 saved date: Tue Oct 31 2023 15:57:19 GMT+0000 (Coordinated Universal Time)
-->
 <head>'''


def test_get_url_from_singlefile():
    assert lib.get_url_from_singlefile(SINGLEFILE_EXAMPLE_1) == 'https://www.example.com'


@pytest.mark.asyncio
async def test_get_custom_archive_directory(async_client, test_directory, test_wrolpi_config):
    """Custom directory can be used for archive directory."""
    # Default location.
    assert lib.get_archive_directory() == (test_directory / 'archive')

    get_wrolpi_config().archive_destination = 'custom/archives'

    assert lib.get_archive_directory() == (test_directory / 'custom/archives')
    assert lib.get_domain_directory('https://example.com') == (test_directory / 'custom/archives/example.com')
