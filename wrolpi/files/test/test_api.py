import hashlib
import json
from datetime import datetime, timezone
from http import HTTPStatus
from unittest import mock

import pytest

from modules.videos import Video
from wrolpi.common import get_wrolpi_config
from wrolpi.files import lib
from wrolpi.files.worker import file_worker
from wrolpi.files.lib import get_mimetype
from wrolpi.files.models import FileGroup, Directory
from wrolpi.tags import TagFile
from wrolpi.test.common import assert_dict_contains
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_list_files_api(test_session, async_client, make_files_structure, test_directory):
    files = [
        'archives/bar.txt',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory/',
        'videos/other video.mp4',
        'videos/some video.mp4',
        'lost+found/',  # Should always be ignored.
    ]
    files = make_files_structure(files)
    files[0].write_text('bar contents')

    async def check_get_files(directories, expected_files):
        request, response = await async_client.post('/api/files', content=json.dumps({'directories': directories}))
        assert response.status_code == HTTPStatus.OK
        assert not response.json.get('errors')
        # The first dict is the media directory.
        children = response.json['files']
        assert_dict_contains(children, expected_files)

    # Requesting no directories results in the top-level results.
    expected = {
        'archives/': {'path': 'archives/', 'is_empty': False},
        'empty directory/': {'path': 'empty directory/', 'is_empty': True},
        'videos/': {'path': 'videos/', 'is_empty': False}
    }
    await check_get_files([], expected)
    # empty directory is empty
    expected = {
        'archives/': {'path': 'archives/', 'is_empty': False},
        'empty directory/': {'path': 'empty directory/', 'children': {}, 'is_empty': True},
        'videos/': {'path': 'videos/', 'is_empty': False}
    }
    await check_get_files(['empty directory'], expected)

    expected = {
        'archives/': {
            'path': 'archives/',
            'children': {
                'foo.txt': {'path': 'archives/foo.txt', 'size': 0, 'mimetype': 'inode/x-empty'},
                'bar.txt': {'path': 'archives/bar.txt', 'size': 12, 'mimetype': 'text/plain'},
                'baz/': {'path': 'archives/baz/', 'is_empty': False},
            },
            'is_empty': False,
        },
        'empty directory/': {'path': 'empty directory/', 'is_empty': True},
        'videos/': {'path': 'videos/', 'is_empty': False}
    }
    await check_get_files(['archives'], expected)

    # Sub-directories are supported.
    expected = {
        'archives/': {
            'path': 'archives/',
            'children': {
                'foo.txt': {'path': 'archives/foo.txt', 'size': 0, 'mimetype': 'inode/x-empty'},
                'bar.txt': {'path': 'archives/bar.txt', 'size': 12, 'mimetype': 'text/plain'},
                'baz/': {
                    'path': 'archives/baz/',
                    'children': {
                        'bar.txt': {'path': 'archives/baz/bar.txt', 'size': 0, 'mimetype': 'inode/x-empty'},
                        'foo.txt': {'path': 'archives/baz/foo.txt', 'size': 0, 'mimetype': 'inode/x-empty'},
                    },
                    'is_empty': False,
                }
            },
            'is_empty': False
        },
        'empty directory/': {'path': 'empty directory/', 'is_empty': True},
        'videos/': {'path': 'videos/', 'is_empty': False},
    }
    await check_get_files(['archives', 'archives/baz'], expected)
    # Requesting only a subdirectory also returns `archives` contents.
    await check_get_files(['archives/baz'], expected)

    expected = {
        'archives/': {
            'path': 'archives/',
            'children': {
                'foo.txt': {'path': 'archives/foo.txt', 'size': 0, 'mimetype': 'inode/x-empty'},
                'bar.txt': {'path': 'archives/bar.txt', 'size': 12, 'mimetype': 'text/plain'},
                'baz/': {'path': 'archives/baz/', 'is_empty': False},
            }, 'is_empty': False
        },
        'empty directory/': {'path': 'empty directory/', 'is_empty': True},
        'videos/': {
            'path': 'videos/',
            'children': {
                'other video.mp4': {'path': 'videos/other video.mp4', 'size': 0, 'mimetype': 'inode/x-empty'},
                'some video.mp4': {'path': 'videos/some video.mp4', 'size': 0, 'mimetype': 'inode/x-empty'},
            },
            'is_empty': False
        }
    }
    await check_get_files(['archives', 'videos'], expected)
    # Order does not matter.
    await check_get_files(['videos', 'archives'], expected)


@pytest.mark.asyncio
async def test_delete_file(test_session, async_client, make_files_structure, test_directory):
    files = ['bar.txt', 'baz/', 'foo']
    make_files_structure(files)

    # Delete a file.
    request, response = await async_client.post('/api/files/delete', content=json.dumps({'paths': ['bar.txt']}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'bar.txt').is_file()
    assert (test_directory / 'baz').is_dir()

    # Delete a directory.
    request, response = await async_client.post('/api/files/delete', content=json.dumps({'paths': ['baz']}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'bar.txt').is_file()
    assert not (test_directory / 'baz').is_dir()

    request, response = await async_client.post('/api/files/delete', content=json.dumps({'paths': ['bad file']}))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'paths', [
        [],
        ['', ],
    ]
)
async def test_delete_invalid_file(async_client, paths):
    """Some paths must be passed."""
    with mock.patch('wrolpi.files.api.lib.delete') as mock_delete_file:
        request, response = await async_client.post('/api/files/delete', content=json.dumps({'paths': paths}))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_delete_file.assert_not_called()


@pytest.mark.asyncio
async def test_delete_wrol_mode(async_client, wrol_mode_fixture):
    """Can't delete a file when WROL Mode is enabled."""
    await wrol_mode_fixture(True)

    request, response = await async_client.post('/api/files/delete', content=json.dumps({'paths': ['foo', ]}))
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json['code'] == 'WROL_MODE_ENABLED'


@pytest.mark.asyncio
async def test_files_search_recent(test_session, test_directory, async_client, video_file_factory):
    """File search can return the most recently viewed files."""
    video_file_factory(test_directory / 'foo.mp4'), video_file_factory(test_directory / 'bar.mp4')
    baz = (test_directory / 'baz.txt')
    baz.write_text('baz contents')
    await file_worker.run_queue_to_completion()

    # baz is most recently viewed, foo has not been viewed.
    bar, baz, foo = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    bar.set_viewed(datetime(2000, 1, 1, 1, 1, 1, tzinfo=timezone.utc))
    baz.set_viewed(datetime(2000, 1, 1, 1, 1, 2, tzinfo=timezone.utc))
    test_session.commit()

    # Results match the viewed order.  foo is not viewed.
    body = dict(order='viewed')
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'], response.json
    assert [i['name'] for i in response.json['file_groups']] == ['baz.txt', 'bar.mp4']

    # Results match the reverse viewed order.  foo is not viewed.
    body = dict(order='-viewed')
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'], response.json
    assert [i['name'] for i in response.json['file_groups']] == ['bar.mp4', 'baz.txt']

    # foo is included because `search_str` has a value.
    body = dict(search_str='foo', order='viewed')
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'], response.json
    assert [i['name'] for i in response.json['file_groups']] == ['foo.mp4']


@pytest.mark.asyncio
async def test_files_search(test_session, async_client, make_files_structure, assert_files_search):
    # You can search an empty directory.
    await assert_files_search('nothing', [])

    # Create files in the temporary directory.  Add some contents so the mimetype can be tested.
    files = [
        'foo_is_the_name.txt',
        'archives/bar.txt',
        'baz.mp4',
        'baz baz two.mp4'
    ]
    foo, bar, baz, baz2 = make_files_structure(files)
    foo.write_text('foo contents')
    bar.write_text('the bar contents')
    baz.write_bytes((PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4').read_bytes())
    baz2.write_bytes((PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4').read_bytes())

    # Refresh so files can be searched.
    await file_worker.run_queue_to_completion()

    await assert_files_search('foo', [dict(primary_path='foo_is_the_name.txt')])
    await assert_files_search('bar', [dict(primary_path='archives/bar.txt')])
    await assert_files_search('baz', [dict(primary_path='baz baz two.mp4'), dict(primary_path='baz.mp4')])
    await assert_files_search('two', [dict(primary_path='baz baz two.mp4')])
    await assert_files_search('nothing', [])


@pytest.mark.asyncio
async def test_files_search_any_tag(async_client, test_session, make_files_structure, tag_factory):
    one, two = await tag_factory(), await tag_factory()
    files = [
        'foo.txt',
        'foo bar.txt',
        'bar.txt',
    ]
    make_files_structure(files)
    await file_worker.run_queue_to_completion()
    bar, foobar, foo = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    assert bar.primary_path.name == 'bar.txt' \
           and foo.primary_path.name == 'foo.txt' \
           and foobar.primary_path.name == 'foo bar.txt'
    foo.add_tag(test_session, one.id)
    foobar.add_tag(test_session, two.id)
    test_session.commit()

    # Only `foo` is tagged with `one`
    body = dict(search_str='foo', tag_names=['one'])
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert {i['primary_path'] for i in response.json['file_groups']} == {'foo.txt'}

    # Both `foo bar` and `foo` are tagged.
    body = dict(search_str='foo', any_tag=True)
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert {i['primary_path'] for i in response.json['file_groups']} == {'foo.txt', 'foo bar.txt'}

    # `bar` is not tagged.
    body = dict(search_str='bar', any_tag=True)
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert {i['primary_path'] for i in response.json['file_groups']} == {'foo bar.txt'}

    # Cannot search for any_tag, and tag names.
    body = dict(search_str='foo', tag_names=['one'], any_tag=True)
    request, response = await async_client.post('/api/files/search', json=body)
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_refresh_files_list(test_session, async_client, make_files_structure, test_directory, video_bytes):
    """The user can request to refresh specific files."""
    make_files_structure({
        'bar.txt': 'hello',
        'bar.mp4': video_bytes,
    })

    # Only the single file that was refreshed is discovered.
    bar_txt = test_directory / 'bar.txt'
    await file_worker.run_queue_to_completion([bar_txt])
    assert test_session.query(FileGroup).count() == 1
    group: FileGroup = test_session.query(FileGroup).one()
    assert len(group.files) == 1

    # Refresh all files - should group bar.txt and bar.mp4 together
    await file_worker.run_queue_to_completion()
    test_session.expire_all()
    group: FileGroup = test_session.query(FileGroup).one()
    assert len(group.files) == 2


@pytest.mark.asyncio
async def test_refresh_api_returns_job_id(async_client, test_directory, make_files_structure, file_worker):
    """The refresh API returns a job_id for tracking progress."""
    make_files_structure({'test.txt': 'content'})

    # Refresh specific paths
    content = json.dumps({'paths': ['test.txt']})
    request, response = await async_client.post('/api/files/refresh', content=content)
    assert response.status_code == HTTPStatus.OK
    assert 'job_id' in response.json
    assert response.json['success'] is True

    # Global refresh
    file_worker.clear()  # Clear deduplication
    request, response = await async_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.OK
    assert 'job_id' in response.json
    assert response.json['success'] is True


@pytest.mark.asyncio
async def test_file_statistics(test_session, async_client, test_directory, example_pdf, example_mobi, example_epub,
                               video_file):
    """A summary of File statistics can be fetched."""
    # Give each file a unique stem.
    video_file.rename(test_directory / 'video.mp4')
    example_pdf.rename(test_directory / 'pdf.pdf')
    example_mobi.rename(test_directory / 'mobi.mobi')
    example_epub.rename(test_directory / 'epub.epub')

    # Statistics can be fetched while empty.
    request, response = await async_client.get('/api/statistics')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_statistics'] == {
        'archive_count': 0,
        'audio_count': 0,
        'ebook_count': 0,
        'image_count': 0,
        'pdf_count': 0,
        'tagged_files': 0,
        'tagged_zims': 0,
        'tags_count': 0,
        'total_count': 0,
        'total_size': 0,
        'video_count': 0,
        'zip_count': 0,
    }

    await file_worker.run_queue_to_completion()

    request, response = await async_client.get('/api/statistics')
    assert response.status_code == HTTPStatus.OK
    stats = response.json['file_statistics']
    stats.pop('total_size')
    assert stats == {
        'archive_count': 0,
        'audio_count': 0,
        'ebook_count': 2,
        'image_count': 0,
        'pdf_count': 1,
        'tagged_files': 0,
        'tagged_zims': 0,
        'tags_count': 0,
        'total_count': 5,  # extracted cover
        'video_count': 1,
        'zip_count': 0,
    }


@pytest.mark.asyncio
async def test_file_group_tag_by_primary_path(test_session, async_client, test_directory, example_singlefile,
                                              tag_factory, insert_file_group):
    singlefile = FileGroup.from_paths(test_session, example_singlefile)
    tag1 = await tag_factory()
    tag2 = await tag_factory()
    test_session.commit()

    # FileGroup can be tagged with its primary_path.
    content = dict(file_group_primary_path=str(singlefile.primary_path.relative_to(test_directory)), tag_name=tag1.name)
    request, response = await async_client.post('/api/files/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert test_session.query(TagFile).count() == 1

    # FileGroup can be tagged with its id.
    content = dict(file_group_id=singlefile.id, tag_name=tag2.name)
    request, response = await async_client.post('/api/files/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert test_session.query(TagFile).count() == 2

    # FileGroup can be untagged with its primary_path.
    content = dict(file_group_id=singlefile.id, tag_id=tag1.id)
    request, response = await async_client.post('/api/files/untag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(TagFile).count() == 1

    # FileGroup can be untagged with its id.
    content = dict(file_group_id=singlefile.id, tag_name=tag2.name)
    request, response = await async_client.post('/api/files/untag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(TagFile).count() == 0


@pytest.mark.asyncio
async def test_file_group_tag(async_client):
    request, response = await async_client.post('/api/files/tag', content=json.dumps(dict(tag_id=1)))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'file_group_id' in response.json['error']

    request, response = await async_client.post('/api/files/tag', content=json.dumps(dict(file_group_id=1)))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'tag_id' in response.json['error']


@pytest.mark.asyncio
async def test_search_directories(async_client, test_session, test_directory, make_files_structure,
                                  assert_directories):
    """Directories can be searched by name."""
    make_files_structure(['foo/one.txt', 'foo/two.txt', 'bar/one.txt'])
    await file_worker.run_queue_to_completion()
    assert_directories({'foo', 'bar'})
    # Create directory that was not refreshed.
    (test_directory / 'baz').mkdir()

    # More than one character required.
    content = dict(path='f')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK, response.content
    assert response.json['directories'] == []
    assert response.json['is_dir'] is False

    # Can search using partial directory name.
    content = dict(path='fo')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['foo', ]
    assert response.json['is_dir'] is False

    # Searching directory exactly.
    content = dict(path='foo')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['foo', ]
    assert response.json['is_dir'] is True

    # Case is ignored.
    content = dict(path='BAR')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['bar', ]
    assert response.json['is_dir'] is False

    # Can search directories not yet in DB.
    content = dict(path='ba')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['bar', 'baz']
    assert response.json['is_dir'] is False

    # Searching for something that does not exist.
    content = dict(path='does not exist')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == []

    # Only first 20 "foo" are returned.
    make_files_structure([
        'fooo/',
        'foooo/',
        'fooooo/',
        'foooooo/',
        'fooooooo/',
        'foooooooo/',
        'fooooooooo/',
        'foooooooooo/',
        'fooooooooooo/',
        'foooooooooooo/',
        'fooooooooooooo/',
        'foooooooooooooo/',
        'fooooooooooooooo/',
        'foooooooooooooooo/',
        'fooooooooooooooooo/',
        'foooooooooooooooooo/',
        'fooooooooooooooooooo/',
        'foooooooooooooooooooo/',
        'fooooooooooooooooooooo/',
        'foooooooooooooooooooooo/',
        'fooooooooooooooooooooooo/',
    ])
    await async_client.post('/api/files/refresh')
    content = dict(path='fo')
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == [f'f{"o" * i}' for i in range(2, 22)]


@pytest.mark.asyncio
async def test_post_search_directories(test_session, async_client, make_files_structure):
    """Directory names can be searched.  This endpoint also returns Channel and Domain directories."""
    channel1_dir, channel2_dir, domain_dir, _ = make_files_structure([
        'dir1/',
        'dir2/',
        'dir3/',
        'dir4/',
    ])
    await file_worker.run_queue_to_completion()

    from modules.videos.models import Channel
    # Use from_config to create channels properly (creates Collection first)
    channel1 = Channel.from_config(test_session, {'directory': channel1_dir, 'name': 'Channel Name'})
    channel2 = Channel.from_config(test_session, {'directory': channel2_dir, 'name': 'OtherChannel'})
    from wrolpi.collections import Collection
    domain_collection = Collection(directory=domain_dir, name='example.com', kind='domain')
    test_session.add(domain_collection)
    test_session.commit()

    # All directories contain "di".  The names of the Channel and Directory do not match.
    content = {'path': 'di'}
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['directories'] == [{'name': 'dir1', 'path': 'dir1'}, {'name': 'dir2', 'path': 'dir2'},
                                            {'name': 'dir3', 'path': 'dir3'}, {'name': 'dir4', 'path': 'dir4'}]
    assert response.json['channel_directories'] == []
    assert response.json['domain_directories'] == []

    # Channel name matches.
    content = {'path': 'Chan'}
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['directories'] == []
    assert response.json['channel_directories'] == [
        {'name': 'Channel Name', 'path': 'dir1'},
        {'name': 'OtherChannel', 'path': 'dir2'},
    ]
    assert response.json['domain_directories'] == []

    # "OtherChannel" matches even though the case is wrong, and it has a space.
    content = {'path': 'other channel'}
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    # Channel name matches.
    assert response.json['directories'] == []
    assert response.json['channel_directories'] == [{'name': 'OtherChannel', 'path': 'dir2'}]
    assert response.json['domain_directories'] == []

    content = {'path': 'exam'}
    request, response = await async_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    # Domain name matches.
    assert response.json['directories'] == []
    assert response.json['channel_directories'] == []
    assert response.json['domain_directories'] == [{'domain': 'example.com', 'path': 'dir3'}]


@pytest.mark.asyncio
async def test_post_upload_directory(test_session, async_client, test_directory, make_files_structure,
                                     make_multipart_form):
    """A file can be uploaded in a directory in the destination."""
    make_files_structure(['uploads/'])

    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='/foo/bar.txt'),  # notice the directory
        dict(name='totalChunks', value='0'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value='3'),
        dict(name='chunk', value='foo', filename='chunk')
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED

    assert (test_directory / 'uploads/foo/bar.txt').is_file()
    assert (test_directory / 'uploads/foo/bar.txt').read_text() == 'foo'

    assert test_session.query(FileGroup).count() == 1
    assert test_session.query(Directory).count() == 2
    assert {i for i, in test_session.query(Directory.path)} == {
        test_directory / 'uploads',
        test_directory / 'uploads/foo',
    }


@pytest.mark.asyncio
async def test_post_upload(test_session, async_client, test_directory, make_files_structure, make_multipart_form,
                           tag_factory, video_bytes):
    """A file can be uploaded in chunks directly to the destination."""
    make_files_structure(['uploads/'])
    tag1, tag2 = await tag_factory(), await tag_factory()

    part1, part2 = video_bytes[:1_000_000], video_bytes[1_000_000:]
    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=1_000_000),
        dict(name='tagNames', value=tag1.name),
        dict(name='tagNames', value=tag2.name),
        dict(name='chunk', value=part1, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    output = test_directory / 'uploads/video.mp4'
    assert output.is_file()
    assert output.stat().st_size == 1_000_000

    forms = [
        dict(name='chunkNumber', value='1'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=56318),
        dict(name='tagNames', value=tag1.name),
        dict(name='tagNames', value=tag2.name),
        dict(name='chunk', value=part2, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, response.content.decode()

    assert output.is_file()
    assert get_mimetype(output) == 'video/mp4'
    assert output.stat().st_size == len(video_bytes)
    assert output.read_bytes() == video_bytes
    assert hashlib.md5(output.read_bytes()).hexdigest() == '2738c53bd7c01b01d408da11a55bfa36'

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.mimetype == 'video/mp4'
    assert set(file_group.tag_names) == {tag1.name, tag2.name}, 'Two tags should be applied.'
    assert file_group.indexed, 'File should be indexed after upload.'
    assert file_group.model, 'File should be modeled'
    # Video was modeled, but has no Channel.
    video: Video = test_session.query(Video).one()
    assert video.video_path
    assert not video.info_json_path
    assert not video.channel and not video.channel_id

    # Can't upload again because the file already exists.
    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=1_000_000),
        dict(name='chunk', value=part1, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.content.decode()
    assert response.json['error'] == 'File already exists!'

    # FileGroup was not deleted.
    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group

    # Remove Tag so file can be uploaded again.
    file_group.set_tags(test_session, [])

    # An existing file can be overwritten.
    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=1_000_000),
        dict(name='chunk', value=part1, filename='chunk'),
        dict(name='overwrite', value=True),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    file_group: FileGroup = test_session.query(FileGroup).one_or_none()
    assert not file_group, 'Old FileGroup should be deleted when new upload starts.'

    # Upload the second part of the file again.
    forms = [
        dict(name='chunkNumber', value='1'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=56318),
        dict(name='chunk', value=part2, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, response.content.decode()

    # Make the same checks as those done above because the file was uploaded again.
    assert output.is_file()
    assert get_mimetype(output) == 'video/mp4'
    assert output.stat().st_size == len(video_bytes)
    assert output.read_bytes() == video_bytes
    assert hashlib.md5(output.read_bytes()).hexdigest() == '2738c53bd7c01b01d408da11a55bfa36'

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.mimetype == 'video/mp4'
    assert not file_group.tag_names, 'No tags this time.'
    assert file_group.indexed, 'File should be indexed after upload.'
    assert file_group.model, 'File should be modeled'
    assert isinstance(file_group.get_model_record(), Video)
    assert file_group.location == '/videos/video/2'
    # Video was modeled, but has no Channel.
    video: Video = test_session.query(Video).one()
    assert video.video_path
    assert video.file_group == file_group
    assert not video.info_json_path
    assert not video.channel and not video.channel_id


@pytest.mark.asyncio
async def test_post_upload_text(test_session, async_client, test_directory, make_files_structure, make_multipart_form):
    """A file that cannot be modeled can still be uploaded, and is indexed."""
    make_files_structure(['uploads/'])

    contents = 'hello'
    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='the title.txt'),
        dict(name='totalChunks', value='0'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value=5),
        dict(name='chunk', value=contents, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.CREATED, response.content.decode()

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.indexed is True
    assert file_group.size == 5
    assert file_group.a_text == 'the title txt'
    assert file_group.d_text == 'hello'


@pytest.mark.asyncio
async def test_post_upload_new_directory(test_session, async_client, test_directory, make_files_structure,
                                         make_multipart_form,
                                         tag_factory, video_bytes):
    """User can create a new directory when uploading."""
    tag1, tag2 = await tag_factory(), await tag_factory()

    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='video.mp4'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='some new directory'),
        dict(name='mkdir', value=True),
        dict(name='chunkSize', value=len(video_bytes)),
        dict(name='tagNames', value=tag1.name),
        dict(name='tagNames', value=tag2.name),
        dict(name='chunk', value=video_bytes, filename='chunk'),
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/files/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    assert (test_directory / 'some new directory').is_dir()
    assert (test_directory / 'some new directory/video.mp4').is_file()
    assert (test_directory / 'some new directory/video.mp4').read_bytes() == video_bytes


@pytest.mark.asyncio
async def test_directory_crud(test_session, async_client, test_directory, assert_directories, assert_files):
    """A directory can be created in a subdirectory.  Errors are returned if there are conflicts."""
    foo = test_directory / 'foo'
    foo.mkdir()
    await file_worker.run_queue_to_completion()
    assert_directories({'foo', })

    # Create a subdirectory.
    content = dict(path='foo/bar')
    request, response = await async_client.post('/api/files/directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert (test_directory / 'foo/bar').is_dir()
    assert_directories({'foo', 'foo/bar'})

    # Cannot create twice.
    content = dict(path='foo/bar')
    request, response = await async_client.post('/api/files/directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CONFLICT
    assert (test_directory / 'foo/bar').is_dir()
    assert_directories({'foo', 'foo/bar'})

    # Create a file to be deleted.
    (test_directory / 'foo/bar/asdf.txt').write_text('asdf')

    # Can get information about a directory.
    request, response = await async_client.post('/api/files/get_directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['path'] == 'foo/bar'
    assert response.json['size'] == 4
    assert response.json['file_count'] == 1

    # Can rename the directory.
    content = dict(path='foo/bar', new_name='baz')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/bar').exists()
    assert (test_directory / 'foo/baz').exists()
    assert (test_directory / 'foo/baz/asdf.txt').exists()

    # Deletion is recursive.
    assert (test_directory / 'foo/baz/asdf.txt').is_file()
    content = dict(paths=['foo/baz', ])
    request, response = await async_client.post('/api/files/delete', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/baz').exists()
    assert not (test_directory / 'foo/baz/asdf.txt').exists()
    # Only top directory is left.
    assert_directories({'foo', })


@pytest.mark.asyncio
async def test_move(test_session, test_directory, make_files_structure, async_client):
    """Files can be moved up and down the media directory.  Destination directories should already exist."""
    baz, bar = make_files_structure({
        'foo/bar.txt': 'bar',
        'baz.txt': 'baz',
    })

    # qux directory does not exist
    content = dict(paths=['foo', 'baz.txt'], destination='qux')
    request, response = await async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NOT_FOUND

    (test_directory / 'qux').mkdir()
    (test_directory / 'quux/quuz').mkdir(parents=True)

    # mv foo baz.txt qux
    content = dict(paths=['foo', 'baz.txt'], destination='qux')
    request, response = await async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not bar.exists()
    assert (test_directory / 'qux/foo/bar.txt').is_file()

    # mv foo/bar.txt qux
    content = dict(paths=['qux/foo/bar.txt', ], destination='qux')
    request, response = await async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not bar.exists()
    assert (test_directory / 'qux/bar.txt').is_file()
    assert (test_directory / 'qux/foo').is_dir()

    # mv qux/bar.txt ./
    content = dict(paths=['qux/bar.txt', ], destination='')
    request, response = await async_client.post('/api/files/move', json=content)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert (test_directory / 'bar.txt').is_file()

    # mv bar.txt quux/quuz/bar.txt
    content = dict(paths=['bar.txt', ], destination='quux/quuz')
    request, response = await async_client.post('/api/files/move', json=content)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert (test_directory / 'quux/quuz/bar.txt').is_file()

    # mv quux/quuz/bar.txt quux/bar.txt
    content = dict(paths=['quux/quuz/bar.txt', ], destination='quux')
    request, response = await async_client.post('/api/files/move', json=content)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert (test_directory / 'quux/bar.txt').is_file()
    assert (test_directory / 'qux/foo').is_dir()
    assert (test_directory / 'quux/quuz').is_dir()


@pytest.mark.asyncio
async def test_rename_file(test_session, test_directory, make_files_structure, async_client):
    """A FileGroup can be renamed.  The title and search index is updated."""
    foo_file, = make_files_structure({
        'foo/bar/baz.txt': 'asdf',
    })
    await file_worker.run_queue_to_completion()
    foo_fg = test_session.query(FileGroup).one()
    assert foo_fg.a_text == 'baz txt'
    assert foo_fg.d_text == 'asdf'

    # mv foo/bar/baz.txt foo/bar/qux.txt
    content = dict(path='foo/bar/baz.txt', new_name='qux.txt')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not foo_file.exists()
    assert (test_directory / 'foo/bar/qux.txt').is_file()
    assert (test_directory / 'foo/bar/qux.txt').read_text() == 'asdf'
    assert foo_fg.a_text == 'qux txt'
    assert foo_fg.d_text == 'asdf'


@pytest.mark.asyncio
async def test_rename_file_with_associated_files_via_api(test_session, test_directory, make_files_structure,
                                                          async_client, video_bytes, srt_text):
    """Renaming a FileGroup via API should rename all associated files.

    Regression test: When renaming "example.mp4" to "example 2.mp4" and back via API,
    associated files like "example.srt" should also be renamed both times.
    """
    video, srt = make_files_structure({
        'example.mp4': video_bytes,
        'example.srt': srt_text,
    })
    await file_worker.run_queue_to_completion()

    # Verify initial state
    fg = test_session.query(FileGroup).one()
    assert fg.primary_path == video
    assert len(fg.files) == 2

    # First rename via API: "example.mp4" -> "example 2.mp4"
    content = dict(path='example.mp4', new_name='example 2.mp4')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Verify first rename - both files should be renamed
    new_video_1 = test_directory / 'example 2.mp4'
    new_srt_1 = test_directory / 'example 2.srt'
    assert new_video_1.is_file(), "Video should be renamed to 'example 2.mp4'"
    assert new_srt_1.is_file(), "SRT should be renamed to 'example 2.srt'"
    assert not video.exists(), "Old video should not exist"
    assert not srt.exists(), "Old SRT should not exist"

    # Verify FileGroup is updated
    test_session.expire_all()
    fg = test_session.query(FileGroup).one()
    assert fg.primary_path == new_video_1
    file_names = [f['path'] for f in fg.files]
    assert 'example 2.mp4' in file_names
    assert 'example 2.srt' in file_names
    assert len(fg.files) == 2

    # Second rename via API: "example 2.mp4" -> "example.mp4"
    content = dict(path='example 2.mp4', new_name='example.mp4')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Verify second rename - BOTH files should be renamed back
    final_video = test_directory / 'example.mp4'
    final_srt = test_directory / 'example.srt'
    assert final_video.is_file(), "Video should be renamed back to 'example.mp4'"
    assert final_srt.is_file(), "SRT should be renamed back to 'example.srt'"
    assert not new_video_1.exists(), "'example 2.mp4' should not exist"
    assert not new_srt_1.exists(), "'example 2.srt' should not exist"

    # Verify FileGroup is updated
    test_session.expire_all()
    fg = test_session.query(FileGroup).one()
    assert fg.primary_path == final_video
    file_names = [f['path'] for f in fg.files]
    assert 'example.mp4' in file_names
    assert 'example.srt' in file_names
    assert len(fg.files) == 2


@pytest.mark.asyncio
async def test_rename_directory(test_session, test_directory, make_files_structure, async_client):
    make_files_structure({
        'foo/bar/baz.txt': 'asdf',
    })
    await file_worker.run_queue_to_completion()
    bar, foo = test_session.query(Directory).order_by(Directory.name).all()
    assert foo.name == 'foo' and bar.name == 'bar'

    # mv foo/bar foo/qux
    content = dict(path='foo/bar', new_name='qux')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/bar').exists()
    assert (test_directory / 'foo/qux/baz.txt').is_file()
    assert (test_directory / 'foo/qux/baz.txt').read_text() == 'asdf'
    foo, qux = test_session.query(Directory).order_by(Directory.name).all()
    assert foo.name == 'foo' and qux.name == 'qux'


@pytest.mark.asyncio
async def test_rename_collection_directory(test_session, test_directory, make_files_structure, async_client):
    """Renaming a Collection's directory updates the Collection.directory."""
    from wrolpi.collections.models import Collection

    # Create a collection with a directory
    collection_dir = test_directory / 'my_collection'
    collection_dir.mkdir()
    (collection_dir / 'file.txt').write_text('contents')
    collection = Collection(name='Test Collection', kind='channel', directory=collection_dir)
    test_session.add(collection)
    test_session.commit()
    collection_id = collection.id

    await file_worker.run_queue_to_completion()

    # Rename the directory
    content = dict(path='my_collection', new_name='renamed_collection')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Verify Collection.directory was updated
    test_session.expire_all()
    collection = test_session.query(Collection).filter_by(id=collection_id).one()
    assert collection.directory == test_directory / 'renamed_collection'
    assert not (test_directory / 'my_collection').exists()
    assert (test_directory / 'renamed_collection' / 'file.txt').is_file()


@pytest.mark.asyncio
async def test_rename_directory_with_nested_collections(test_session, test_directory, async_client):
    """Renaming a parent directory updates nested Collection directories and download destinations."""
    from wrolpi.collections.models import Collection
    from wrolpi.downloader import Download

    # Create parent directory with nested collection directories
    parent_dir = test_directory / 'videos'
    parent_dir.mkdir()

    channel_a_dir = parent_dir / 'channel_a'
    channel_a_dir.mkdir()
    (channel_a_dir / 'video1.mp4').write_bytes(b'fake video 1')

    channel_b_dir = parent_dir / 'channel_b'
    channel_b_dir.mkdir()
    (channel_b_dir / 'video2.mp4').write_bytes(b'fake video 2')

    # Create two channel collections for the nested directories
    coll_a = Collection(name='Channel A', kind='channel', directory=channel_a_dir)
    coll_b = Collection(name='Channel B', kind='channel', directory=channel_b_dir)
    test_session.add_all([coll_a, coll_b])
    test_session.commit()

    # Create a download associated with channel_a
    download = Download(url='https://example.com/channel_a', destination=channel_a_dir, collection_id=coll_a.id)
    test_session.add(download)
    test_session.commit()
    coll_a_id, coll_b_id, download_id = coll_a.id, coll_b.id, download.id

    await file_worker.run_queue_to_completion()

    # Rename the parent directory
    content = dict(path='videos', new_name='my_videos')
    request, response = await async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Verify nested Collection directories were updated
    test_session.expire_all()
    coll_a = test_session.query(Collection).filter_by(id=coll_a_id).one()
    coll_b = test_session.query(Collection).filter_by(id=coll_b_id).one()

    assert coll_a.directory == test_directory / 'my_videos' / 'channel_a'
    assert coll_b.directory == test_directory / 'my_videos' / 'channel_b'

    # Verify download destination was updated
    download = test_session.query(Download).filter_by(id=download_id).one()
    assert download.destination == test_directory / 'my_videos' / 'channel_a'

    # Verify files were moved
    assert (test_directory / 'my_videos' / 'channel_a' / 'video1.mp4').exists()
    assert (test_directory / 'my_videos' / 'channel_b' / 'video2.mp4').exists()
    assert not (test_directory / 'videos').exists()


@pytest.mark.asyncio
async def test_delete_directory_recursive(test_session, test_directory, make_files_structure, async_client,
                                          assert_files):
    make_files_structure(['dir/foo', 'dir/bar', 'empty'])
    await file_worker.run_queue_to_completion()
    assert test_session.query(FileGroup).count() == 3

    content = {'paths': ['dir/', ]}
    request, response = await async_client.post('/api/files/delete', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(FileGroup).count() == 1

    empty = test_session.query(FileGroup).one()
    assert empty.primary_path.name == 'empty'


@pytest.mark.asyncio
async def test_get_file(test_session, async_client, test_directory, make_files_structure, await_background_tasks,
                        await_switches):
    """Can get info about a single file."""
    make_files_structure({'foo/bar.txt': 'foo contents'})
    await file_worker.run_queue_to_completion()

    content = dict(file='foo/bar.txt')
    request, response = await async_client.post('/api/files/file', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['file']
    assert response.json['file']['path'] == 'foo/bar.txt'

    # Wait for `viewed` to be set in background task.
    await await_background_tasks()

    fg, = test_session.query(FileGroup).all()
    assert fg.primary_path == test_directory / 'foo/bar.txt'
    assert isinstance(fg.viewed, datetime)


@pytest.mark.asyncio
async def test_ignore_directory(test_session, async_client, test_directory, make_files_structure, test_wrolpi_config,
                                await_switches):
    """A maintainer can ignore/un-ignore directories.  The files in the directory should not be refreshed."""
    # Remove any default ignored directories.
    get_wrolpi_config().ignored_directories = []

    foo, bar, baz = make_files_structure(['foo/foo.txt', 'foo/bar.txt', 'baz/baz.txt'])
    assert len(get_wrolpi_config().ignored_directories) == 0

    # Ignore baz/
    content = dict(path=str(baz.parent))
    request, response = await async_client.post('/api/files/ignore_directory', json=content)
    assert response.status_code == HTTPStatus.OK
    assert len(get_wrolpi_config().ignored_directories) == 1

    await file_worker.run_queue_to_completion()

    files = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    assert {i.primary_path.name for i in files} == {'foo.txt', 'bar.txt', 'wrolpi.yaml'}

    # Un-ignore baz/
    request, response = await async_client.post('/api/files/unignore_directory', json=content)
    assert response.status_code == HTTPStatus.OK
    assert len(get_wrolpi_config().ignored_directories) == 0

    await file_worker.run_queue_to_completion()

    files = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    # Ignore configs.
    files = {i for i in files if not i.primary_path.name.endswith('.yaml')}
    assert {i.primary_path.name for i in files} == {'foo.txt', 'bar.txt', 'baz.txt'}

    # Cannot ignore special directories.
    content = dict(path=str(test_directory / 'videos'))
    request, response = await async_client.post('/api/files/ignore_directory', json=content)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert len(get_wrolpi_config().ignored_directories) == 0


# --- Bulk Tagging API Tests ---


@pytest.mark.asyncio
async def test_bulk_tag_preview_api(test_session, async_client, make_files_structure, tag_factory):
    """The bulk tag preview endpoint returns file count and shared tags."""
    foo, bar, baz = make_files_structure({
        'foo.txt': 'foo',
        'bar.txt': 'bar',
        'baz.txt': 'baz',
    })

    # Create FileGroups
    fg_foo = FileGroup.from_paths(test_session, foo)
    fg_bar = FileGroup.from_paths(test_session, bar)
    fg_baz = FileGroup.from_paths(test_session, baz)
    test_session.commit()

    # Add shared and non-shared tags
    tag1 = await tag_factory('shared_tag')
    tag2 = await tag_factory('only_foo')
    fg_foo.add_tag(test_session, tag1.id)
    fg_foo.add_tag(test_session, tag2.id)
    fg_bar.add_tag(test_session, tag1.id)
    fg_baz.add_tag(test_session, tag1.id)
    test_session.commit()

    content = {'paths': ['foo.txt', 'bar.txt', 'baz.txt']}
    request, response = await async_client.post('/api/files/bulk_tag/preview', json=content)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_count'] == 3
    assert 'shared_tag' in response.json['shared_tag_names']
    assert 'only_foo' not in response.json['shared_tag_names']


@pytest.mark.asyncio
async def test_bulk_tag_preview_empty(test_session, async_client):
    """The bulk tag preview endpoint handles empty paths."""
    content = {'paths': []}
    request, response = await async_client.post('/api/files/bulk_tag/preview', json=content)
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_count'] == 0
    assert response.json['shared_tag_names'] == []


@pytest.mark.asyncio
async def test_bulk_tag_apply_api(test_session, async_client, make_files_structure, tag_factory):
    """The bulk tag apply endpoint queues a tagging job."""
    foo, bar = make_files_structure({
        'foo.txt': 'foo',
        'bar.txt': 'bar',
    })

    # Create FileGroups
    FileGroup.from_paths(test_session, foo)
    FileGroup.from_paths(test_session, bar)
    test_session.commit()

    # Create a tag
    tag = await tag_factory('api_tag')
    test_session.commit()

    content = {
        'paths': ['foo.txt', 'bar.txt'],
        'add_tag_names': ['api_tag'],
        'remove_tag_names': [],
    }
    request, response = await async_client.post('/api/files/bulk_tag/apply', json=content)
    assert response.status_code == HTTPStatus.ACCEPTED


@pytest.mark.asyncio
async def test_bulk_tag_progress_api(test_session, async_client):
    """The bulk tag progress endpoint returns progress information."""
    request, response = await async_client.get('/api/files/bulk_tag/progress')
    assert response.status_code == HTTPStatus.OK
    assert 'status' in response.json
    assert 'total' in response.json
    assert 'completed' in response.json
    assert 'queued_jobs' in response.json
