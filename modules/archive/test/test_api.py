import json
from http import HTTPStatus
from unittest.mock import patch

import pytest

from modules.archive import lib, Archive
from wrolpi.files.models import FileGroup
from wrolpi.test.common import skip_circleci, skip_macos

from wrolpi.common import get_relative_to_media_directory


def check_results(test_client, data, ids):
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    if not response.status_code == HTTPStatus.OK:
        raise AssertionError(str(response.json))

    if ids:
        file_groups = response.json['file_groups']
        assert file_groups, f'Expected {len(ids)} archives but did not receive any'
    assert [i['id'] for i in response.json['file_groups']] == ids, \
        f'{response.json["file_groups"][0]["id"]}..{response.json["file_groups"][-1]["id"]}'


def test_archives_search_order(test_session, archive_directory, archive_factory, test_client):
    """Search using all orders."""
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    for order_by in lib.ARCHIVE_ORDERS:
        data = {'search_str': 'foo', 'order_by': order_by}
        request, response = test_client.post('/api/archive/search', content=json.dumps(data))
        if not response.status_code == HTTPStatus.OK:
            raise AssertionError(str(response.json))

        data = {'search_str': None, 'order_by': order_by}
        request, response = test_client.post('/api/archive/search', content=json.dumps(data))
        if not response.status_code == HTTPStatus.OK:
            raise AssertionError(str(response.json))


def test_archives_search(test_session, archive_directory, archive_factory, test_client):
    """Archives can be searched by their title and their contents."""
    # Search with no archives.
    check_results(test_client, {'search_str': 'foo'}, [])

    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents
    test_session.commit()

    # 1 and 2 contain "foo".
    data = {'search_str': 'foo'}
    check_results(test_client, data, [2, 1])

    # 2 and 3 contain "baz".
    data = {'search_str': 'baz'}
    check_results(test_client, data, [3, 2])

    # 1 contains "bar".
    data = {'search_str': 'bar'}
    check_results(test_client, data, [1, ])

    # No archives contain "huzzah"
    data = {'search_str': 'huzzah'}
    check_results(test_client, data, [])

    # Only 3 contains "baz" and is in domain "example.org"
    data = {'search_str': 'baz', 'domain': 'example.org'}
    check_results(test_client, data, [3, ])

    # 1's title contains "my", this is ignored by Postgres.
    data = {'search_str': 'my'}
    check_results(test_client, data, [])

    # 3's title contains "third".
    data = {'search_str': 'third'}
    check_results(test_client, data, [3, ])

    # All contents contain "qux", but they contain different amounts.  They are ordered by the amount.
    data = {'search_str': 'qux'}
    check_results(test_client, data, [3, 2, 1])

    data = {'search_str': 'qux', 'order_by': 'bad order_by'}
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_search_archive_tags(test_session, async_client, archive_factory, tag_factory):
    """Tagged Archives can be searched."""
    tag = await tag_factory()
    archive_factory(domain='example.com', tag_names=[tag.name, ])
    test_session.commit()

    content = {'search_str': '', 'domain': 'example.com', 'tag_names': [tag.name, ]}
    request, response = await async_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups']
    assert response.json['totals']['file_groups'] == 1

    content = {'search_str': '', 'domain': 'example.com', 'tag_names': ['does not exist', ]}
    request, response = await async_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'] == []
    assert response.json['totals']['file_groups'] == 0


def test_archives_search_headline(test_session, archive_directory, archive_factory, test_client):
    """Headlines can be requested."""
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents
    test_session.commit()

    content = dict(search_str='foo')
    request, response = test_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK

    # Headlines are only fetched if requested.
    assert response.json['file_groups'][0]['d_headline'] is None
    assert response.json['file_groups'][1]['d_headline'] is None

    content = dict(search_str='foo', headline=True)
    request, response = test_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK

    # Postgresql uses <b>...</b> to highlight matching words.
    assert response.json['file_groups'][0]['d_headline'] == '<b>foo</b> baz qux qux'
    assert response.json['file_groups'][1]['d_headline'] == '<b>foo</b> bar qux'


def test_search_offset(test_session, archive_factory, test_client):
    """Archive search can be offset."""
    for i in range(500):
        archive_factory('example.com', f'https://example.com/{i}', contents='foo bar')
    test_session.commit()

    data = {'search_str': None, 'offset': 0}
    check_results(test_client, data, list(range(500, 480, -1)))
    data = {'search_str': None, 'offset': 20}
    check_results(test_client, data, list(range(480, 460, -1)))
    data = {'search_str': None, 'offset': 100}
    check_results(test_client, data, list(range(400, 380, -1)))
    data = {'search_str': None, 'offset': 200}
    check_results(test_client, data, list(range(300, 280, -1)))
    data = {'search_str': None, 'offset': 500}
    check_results(test_client, data, [])


def test_archives_search_no_query(test_session, archive_factory, test_client):
    """Archive Search API endpoint does not require data in the body."""
    # Add 100 random archives.
    for _ in range(100):
        archive_factory('example.com')
    test_session.commit()

    # All archives are returned when no `search_str` is passed.
    request, response = test_client.post('/api/archive/search', content='{}')
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == list(range(100, 80, -1))
    assert response.json['totals']['file_groups'] == 100

    # All archives are from "example.com".
    data = dict(domain='example.com')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == list(range(100, 80, -1))
    assert response.json['totals']['file_groups'] == 100

    # No archives are from "example.org".
    data = dict(domain='example.org')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == []
    assert response.json['totals']['file_groups'] == 0


def test_archive_and_domain_crud(test_session, test_client, archive_factory):
    """Getting an Archive returns it's File.  Testing deleting Archives."""
    # Can get empty results.
    request, response = test_client.get(f'/api/archive/1')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'] == []

    archive1 = archive_factory(domain='example.com', url='https://example.com/1')
    archive2 = archive_factory(domain='example.com', url='https://example.com/1')
    test_session.commit()

    # Archive1 has Archive2 as history.
    request, response = test_client.get(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_group']['id'] == archive1.id
    assert response.json['history'][0]['id'] == archive2.id

    # Archive2 has Archive1 as history.
    request, response = test_client.get(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.OK
    assert archive2.id == response.json['file_group']['id']
    assert response.json['history'][0]['id'] == archive1.id

    # Only one domain.
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'][0]['domain'] == 'example.com'
    assert response.json['domains'][0]['size'] == 254

    # Deleting works.
    request, response = test_client.delete(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Trying to delete again returns NOT_FOUND.
    request, response = test_client.delete(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Can't get deleted Archive.
    request, response = test_client.get(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Archive2 no longer has history.
    request, response = test_client.get(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_group']['id'] == archive2.id
    assert response.json['history'] == []

    # No Archives, no Domains.
    request, response = test_client.delete(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'] == []


@skip_macos
@skip_circleci
@pytest.mark.asyncio
async def test_archive_upload(test_session, async_client, singlefile_contents_factory, make_multipart_form,
                              await_switches, events_history):
    """Test converting a SingleFile from the SingleFile browser extension to an Archive."""
    singlefile_contents = singlefile_contents_factory(title='upload title', url='https://example.com/single-file-url')
    forms = [
        dict(name='url', value='https://example.com/form-url'),
        dict(name='singlefile_contents', value=singlefile_contents, filename='singlefile_contents')
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/archive/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.OK

    await await_switches()

    archive, = test_session.query(Archive).all()
    assert archive.singlefile_path.is_file(), 'Singlefile should have been saved.'
    assert archive.readability_path.is_file(), 'Readability should be extracted.'
    assert archive.readability_json_path.is_file(), 'Readability json should be extracted.'
    assert archive.screenshot_path.is_file(), 'Screenshot should have been created'
    assert archive.file_group.title == 'upload title', 'Title was not correct'
    assert archive.file_group.url == 'https://example.com/single-file-url', 'SingleFile URL should be trusted'
    events = list(events_history)
    assert events and events[0]['event'] == 'upload_archive', 'Event should have been sent.'


@pytest.mark.asyncio
async def test_archive_upload_file_tracking(test_session, async_client, archive_directory, archive_factory,
                                            await_switches, make_multipart_form, image_bytes_factory):
    """Test that uploading an info.json and image file via /api/files/upload properly tracks them in Archive and FileGroup."""
    archive = archive_factory('example.com', 'https://example.com/test-url', 'tracking test', screenshot=False)
    test_session.commit()

    # Verify Archive and FileGroup are created, but screenshot does not exist.
    file_group = archive.file_group
    assert not archive.screenshot_path, 'Screenshot should not exist yet.'
    assert file_group.files is not None, 'FileGroup should have files array'
    initial_file_count = len(file_group.files)

    # Upload info.json via /api/files/upload
    # Extract the prefix from singlefile path (e.g., "2000-01-01-00-00-01_tracking test")
    singlefile_stem = archive.singlefile_path.stem  # e.g., "2000-01-01-00-00-01_tracking test"

    # Create info.json content
    info_json_data = {
        'title': 'test',
        'url': 'https://example.com/test-url',
        'custom_field': 'value'
    }
    info_json_bytes = json.dumps(info_json_data).encode()

    # Get relative destination directory
    destination = str(get_relative_to_media_directory(archive.singlefile_path.parent))
    filename = f'{singlefile_stem}.info.json'

    # POST to /api/files/upload
    forms = [
        dict(name='destination', value=destination),
        dict(name='filename', value=filename),
        dict(name='chunkNumber', value='0'),
        dict(name='totalChunks', value='0'),
        dict(name='chunkSize', value=str(len(info_json_bytes))),
        dict(name='overwrite', value='false'),
        dict(name='chunk', value=info_json_bytes, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, f'Upload failed with status {response.status_code}: {response.json}'

    await await_switches()

    # Step 4: Verify info.json is tracked
    # Refresh the session to get updated data
    test_session.expire_all()
    archive = test_session.query(Archive).filter_by(id=archive.id).one()

    # Assert info.json properties exist
    assert archive.info_json_path is not None, 'Archive.info_json_path should exist'
    assert archive.info_json_file is not None, 'Archive.info_json_file should exist'

    # Assert FileGroup has the correct number of files.
    assert len(archive.file_group.files) == initial_file_count + 1, \
        f'FileGroup should have {initial_file_count + 1} files after adding info.json'
    assert archive.file_group.data.get('info_json_path'), \
        'Archive readability info json should be in FileGroup.data'

    # Upload an image file and verify it's added to the FileGroup.
    # Store file count before adding image
    file_count_before_image = len(archive.file_group.files)

    # Create image using factory
    image_data = image_bytes_factory()

    # Upload image with same stem as the Archive (using .jpg to avoid conflict with factory-created .png)
    image_filename = f'{singlefile_stem}.jpg'
    forms = [
        dict(name='destination', value=destination),
        dict(name='filename', value=image_filename),
        dict(name='chunkNumber', value='0'),
        dict(name='totalChunks', value='0'),
        dict(name='chunkSize', value=str(len(image_data))),
        dict(name='overwrite', value='false'),
        dict(name='chunk', value=image_data, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, f'Image upload failed with status {response.status_code}: {response.json}'

    await await_switches()

    # Refresh session to get updated data
    test_session.expire_all()
    archive = test_session.query(Archive).filter_by(id=archive.id).one()

    # Assert screenshot properties exist
    assert archive.screenshot_path is not None, 'Archive.screenshot_path should exist'
    assert archive.screenshot_file is not None, 'Archive.screenshot_file should exist'
    assert archive.file_group.data.get('screenshot_path') == archive.screenshot_path, 'Archive screenshot should be in FileGroup.data'

    # Assert image is in FileGroup.files
    file_paths = [f['path'] for f in archive.file_group.files]
    assert archive.screenshot_path in file_paths, 'Screenshot should be in FileGroup.files'

    # Assert FileGroup has correct number of files
    assert len(archive.file_group.files) == file_count_before_image + 1, \
        f'FileGroup should have {file_count_before_image + 1} files after adding image'


@pytest.mark.asyncio
async def test_archive_generate_screenshot(test_session, async_client, archive_factory, await_switches,
                                           image_bytes_factory, wrol_mode_fixture):
    """Test generating a screenshot for an Archive that doesn't have one."""
    # Mock html_screenshot to avoid Selenium dependency
    mock_screenshot_bytes = image_bytes_factory()

    with patch('modules.archive.lib.html_screenshot', return_value=mock_screenshot_bytes):
        # Test success case: Archive without screenshot
        archive = archive_factory('example.com', 'https://example.com/test', 'Test Archive', screenshot=False)
        test_session.commit()

        # Verify archive has no screenshot
        assert archive.screenshot_path is None, 'Archive should not have a screenshot yet'
        assert archive.singlefile_path is not None, 'Archive should have a singlefile'

        # Request screenshot generation
        request, response = await async_client.post(f'/api/archive/{archive.id}/generate_screenshot')
        assert response.status_code == HTTPStatus.OK
        assert response.json['message'] == 'Screenshot generation queued'

        # Wait for background processing
        await await_switches()

        # Verify screenshot was generated
        test_session.expire_all()
        archive = test_session.query(Archive).filter_by(id=archive.id).one()
        assert archive.screenshot_path is not None, 'Screenshot should have been generated'
        assert archive.screenshot_path.is_file(), 'Screenshot file should exist'
        assert archive.screenshot_file is not None, 'Screenshot file should be tracked'

    # Test error case: Archive not found
    request, response = await async_client.post('/api/archive/99999/generate_screenshot')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'not found' in response.json['error'].lower()

    # Test success case: Archive already has screenshot - should return OK and ensure tracking
    original_screenshot_path = archive.screenshot_path
    assert original_screenshot_path is not None, 'Archive should have a screenshot'
    assert original_screenshot_path.is_file(), 'Screenshot file should exist'

    # Simulate the bug: archive has screenshot file but data['screenshot_path'] is not set
    # (This could happen if the archive was created before set_screenshot was implemented)
    if archive.file_group.data and 'screenshot_path' in archive.file_group.data:
        data = dict(archive.file_group.data)
        del data['screenshot_path']
        archive.file_group.data = data
        test_session.commit()
        test_session.expire_all()
        archive = test_session.query(Archive).filter_by(id=archive.id).one()
        # Verify data was cleared but file still exists
        assert 'screenshot_path' not in (archive.file_group.data or {}), 'screenshot_path should not be in data yet'
        assert archive.screenshot_path is not None, 'But screenshot file should still exist'

    request, response = await async_client.post(f'/api/archive/{archive.id}/generate_screenshot')
    assert response.status_code == HTTPStatus.OK
    assert response.json['message'] == 'Screenshot generation queued'

    # Wait for background processing
    await await_switches()

    # Verify screenshot is still there and properly tracked
    test_session.expire_all()
    archive = test_session.query(Archive).filter_by(id=archive.id).one()
    assert archive.screenshot_path == original_screenshot_path, 'Screenshot path should be unchanged'
    assert archive.screenshot_path.is_file(), 'Screenshot file should still exist'
    assert archive.screenshot_file is not None, 'Screenshot file should still be tracked'
    # IMPORTANT: Also verify FileGroup.data was updated (this catches the bug where only files was updated)
    assert 'screenshot_path' in archive.file_group.data, \
        'screenshot_path should be in FileGroup.data after ensuring tracking'
    assert str(archive.file_group.data['screenshot_path']) == str(original_screenshot_path), \
        'screenshot_path in data should match the file path'

    # Test error case: Archive has no singlefile
    archive_no_singlefile = archive_factory('example.com', 'https://example.com/no-singlefile', screenshot=False)
    test_session.commit()
    # Delete the singlefile to simulate missing file
    if archive_no_singlefile.singlefile_path and archive_no_singlefile.singlefile_path.is_file():
        archive_no_singlefile.singlefile_path.unlink()

    request, response = await async_client.post(f'/api/archive/{archive_no_singlefile.id}/generate_screenshot')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'no singlefile' in response.json['error'].lower()

    # Test WROL mode case
    await wrol_mode_fixture(True)
    archive_wrol = archive_factory('example.com', 'https://example.com/wrol-test', screenshot=False)
    test_session.commit()

    request, response = await async_client.post(f'/api/archive/{archive_wrol.id}/generate_screenshot')
    assert response.status_code == HTTPStatus.FORBIDDEN
    await wrol_mode_fixture(False)
