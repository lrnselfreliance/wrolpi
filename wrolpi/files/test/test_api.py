import json
from http import HTTPStatus
from unittest import mock

import pytest

from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.files import lib
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile
from wrolpi.test.common import assert_dict_contains
from wrolpi.vars import PROJECT_DIR


def test_list_files_api(test_session, test_client, make_files_structure, test_directory):
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

    def check_get_files(directories, expected_files):
        request, response = test_client.post('/api/files', content=json.dumps({'directories': directories}))
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
    check_get_files([], expected)
    # empty directory is empty
    expected = {
        'archives/': {'path': 'archives/', 'is_empty': False},
        'empty directory/': {'path': 'empty directory/', 'children': {}, 'is_empty': True},
        'videos/': {'path': 'videos/', 'is_empty': False}
    }
    check_get_files(['empty directory'], expected)

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
    check_get_files(['archives'], expected)

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
    check_get_files(['archives', 'archives/baz'], expected)
    # Requesting only a subdirectory also returns `archives` contents.
    check_get_files(['archives/baz'], expected)

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
    check_get_files(['archives', 'videos'], expected)
    # Order does not matter.
    check_get_files(['videos', 'archives'], expected)


def test_delete_file(test_session, test_client, make_files_structure, test_directory):
    files = ['bar.txt', 'baz/']
    make_files_structure(files)

    # Delete a file.
    request, response = test_client.post('/api/files/delete', content=json.dumps({'paths': ['bar.txt']}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'bar.txt').is_file()
    assert (test_directory / 'baz').is_dir()

    # Delete a directory.
    request, response = test_client.post('/api/files/delete', content=json.dumps({'paths': ['baz']}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'bar.txt').is_file()
    assert not (test_directory / 'baz').is_dir()

    request, response = test_client.post('/api/files/delete', content=json.dumps({'paths': ['bad file']}))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.parametrize(
    'paths', [
        [],
        ['', ],
    ]
)
def test_delete_invalid_file(test_client, paths):
    """Some paths must be passed."""
    with mock.patch('wrolpi.files.api.lib.delete') as mock_delete_file:
        request, response = test_client.post('/api/files/delete', content=json.dumps({'paths': paths}))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_delete_file.assert_not_called()


@pytest.mark.asyncio
async def test_delete_wrol_mode(test_async_client, wrol_mode_fixture):
    """Can't delete a file when WROL Mode is enabled."""
    wrol_mode_fixture(True)

    request, response = await test_async_client.post('/api/files/delete', content=json.dumps({'paths': ['foo', ]}))
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json['code'] == API_ERRORS[WROLModeEnabled]['code']


def test_files_search(test_session, test_client, make_files_structure, assert_files_search):
    # You can search an empty directory.
    assert_files_search('nothing', [])

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
    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert_files_search('foo', [dict(primary_path='foo_is_the_name.txt')])
    assert_files_search('bar', [dict(primary_path='archives/bar.txt')])
    assert_files_search('baz', [dict(primary_path='baz baz two.mp4'), dict(primary_path='baz.mp4')])
    assert_files_search('two', [dict(primary_path='baz baz two.mp4')])
    assert_files_search('nothing', [])


def test_refresh_files_list(test_session, test_client, make_files_structure, test_directory, video_bytes):
    """The user can request to refresh specific files."""
    make_files_structure({
        'bar.txt': 'hello',
        'bar.mp4': video_bytes,
    })

    # Only the single file that was refreshed is discovered.
    content = json.dumps({'paths': ['bar.txt']})
    request, response = test_client.post('/api/files/refresh', content=content)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(FileGroup).count() == 1
    group: FileGroup = test_session.query(FileGroup).one()
    assert len(group.files) == 1

    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT
    group: FileGroup = test_session.query(FileGroup).one()
    assert len(group.files) == 2


def test_file_statistics(test_session, test_client, test_directory, example_pdf, example_mobi, example_epub,
                         video_file):
    """A summary of File statistics can be fetched."""
    # Give each file a unique stem.
    video_file.rename(test_directory / 'video.mp4')
    example_pdf.rename(test_directory / 'pdf.pdf')
    example_mobi.rename(test_directory / 'mobi.mobi')
    example_epub.rename(test_directory / 'epub.epub')

    # Statistics can be fetched while empty.
    request, response = test_client.get('/api/statistics')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_statistics'] == {
        'archive_count': 0,
        'total_size': 0,
        'audio_count': 0,
        'ebook_count': 0,
        'image_count': 0,
        'pdf_count': 0,
        'total_count': 0,
        'video_count': 0,
        'zip_count': 0,
    }

    test_client.post('/api/files/refresh')

    request, response = test_client.get('/api/statistics')
    assert response.status_code == HTTPStatus.OK
    stats = response.json['file_statistics']
    stats.pop('total_size')
    assert stats == {
        'archive_count': 0,
        'audio_count': 0,
        'ebook_count': 2,
        'image_count': 0,
        'pdf_count': 1,
        'total_count': 5,  # extracted cover
        'video_count': 1,
        'zip_count': 0,
    }


def test_file_group_tag_by_primary_path(test_session, test_client, test_directory, example_singlefile, tag_factory,
                                        insert_file_group):
    singlefile = FileGroup.from_paths(test_session, example_singlefile)
    tag1 = tag_factory()
    tag2 = tag_factory()
    test_session.commit()

    # FileGroup can be tagged with its primary_path.
    content = dict(file_group_primary_path=str(singlefile.primary_path.relative_to(test_directory)), tag_name=tag1.name)
    request, response = test_client.post('/api/files/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert test_session.query(TagFile).count() == 1

    # FileGroup can be tagged with its id.
    content = dict(file_group_id=singlefile.id, tag_name=tag2.name)
    request, response = test_client.post('/api/files/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert test_session.query(TagFile).count() == 2

    # FileGroup can be untagged with its primary_path.
    content = dict(file_group_id=singlefile.id, tag_id=tag1.id)
    request, response = test_client.post('/api/files/untag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(TagFile).count() == 1

    # FileGroup can be untagged with its id.
    content = dict(file_group_id=singlefile.id, tag_name=tag2.name)
    request, response = test_client.post('/api/files/untag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(TagFile).count() == 0


def test_file_group_tag(test_client):
    request, response = test_client.post('/api/files/tag', content=json.dumps(dict(tag_id=1)))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'file_group_id' in response.json['error']

    request, response = test_client.post('/api/files/tag', content=json.dumps(dict(file_group_id=1)))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'tag_id' in response.json['error']


def test_search_directories(test_client, test_session, make_files_structure, assert_directories):
    """Directories can be searched by name."""
    make_files_structure(['foo/one.txt', 'foo/two.txt', 'bar/one.txt'])
    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert_directories({'foo', 'bar'})

    # More than one character required.
    content = dict(name='f')
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT

    content = dict(name='fo')
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['foo', ]

    # Case is ignored.
    content = dict(name='BAR')
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['bar', ]

    # Searching for something that does not exist.
    content = dict(name='does not exist')
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
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
    test_client.post('/api/files/refresh')
    content = dict(name='fo')
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == [f'f{"o" * i}' for i in range(2, 22)]


def test_post_search_directories(test_session, test_client, make_files_structure):
    """Directory names can be searched.  This endpoint also returns Channel and Domain directories."""
    channel_dir, domain_dir, _, _ = make_files_structure([
        'dir1/',
        'dir2/',
        'dir3/',
        'dir4/',
    ])
    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT

    from modules.videos.models import Channel
    channel = Channel(directory=channel_dir, name='Channel Name')
    from modules.archive.models import Domain
    domain = Domain(directory=domain_dir, domain='example.com')
    test_session.add_all([channel, domain])
    test_session.commit()

    content = {'name': 'di'}
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    # All directories contain "di".  The names of the Channel and Directory do not match.
    assert response.json['directories'] == [{'name': 'dir1', 'path': 'dir1'}, {'name': 'dir2', 'path': 'dir2'},
                                            {'name': 'dir3', 'path': 'dir3'}, {'name': 'dir4', 'path': 'dir4'}]
    assert response.json['channel_directories'] == []
    assert response.json['domain_directories'] == []

    content = {'name': 'Chan'}
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    # Channel name matches.
    assert response.json['directories'] == []
    assert response.json['channel_directories'] == [{'name': 'Channel Name', 'path': 'dir1'}]
    assert response.json['domain_directories'] == []

    content = {'name': 'exam'}
    request, response = test_client.post('/api/files/search_directories', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    # Domain name matches.
    assert response.json['directories'] == []
    assert response.json['channel_directories'] == []
    assert response.json['domain_directories'] == [{'domain': 'example.com', 'path': 'dir2'}]


def test_post_upload_directory(test_session, test_client, test_directory, make_files_structure, make_multipart_form):
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
    request, response = test_client.post('/api/files/upload', data=body,
                                         headers={
                                             'Content-Type': 'multipart/form-data; name=upload; filename="file.txt";'
                                                             ' boundary=-----sanic'})
    assert response.status_code == HTTPStatus.CREATED

    assert (test_directory / 'uploads/foo/bar.txt').is_file()
    assert (test_directory / 'uploads/foo/bar.txt').read_text() == 'foo'

    assert test_session.query(FileGroup).count() == 1


def test_post_upload(test_session, test_client, test_directory, make_files_structure, make_multipart_form):
    """A file can be uploaded in chunks directly to the destination."""
    make_files_structure(['uploads/'])

    forms = [
        dict(name='chunkNumber', value='0'),
        dict(name='filename', value='foo.txt'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value='3'),
        dict(name='chunk', value='foo', filename='chunk')
    ]
    body = make_multipart_form(forms)
    request, response = test_client.post('/api/files/upload', data=body,
                                         headers={
                                             'Content-Type': 'multipart/form-data; name=upload; filename="file.txt";'
                                                             ' boundary=-----sanic'})
    assert response.status_code == HTTPStatus.OK

    assert (test_directory / 'uploads/foo.txt').is_file()
    assert (test_directory / 'uploads/foo.txt').read_text() == 'foo'

    forms = [
        dict(name='chunkNumber', value='1'),
        dict(name='filename', value='foo.txt'),
        dict(name='totalChunks', value='1'),
        dict(name='destination', value='uploads'),
        dict(name='chunkSize', value='3'),
        dict(name='chunk', value='bar', filename='chunk')
    ]
    body = make_multipart_form(forms)
    request, response = test_client.post('/api/files/upload', data=body,
                                         headers={
                                             'Content-Type': 'multipart/form-data; name=upload; filename="file.txt";'
                                                             ' boundary=-----sanic'})
    assert response.status_code == HTTPStatus.CREATED

    assert (test_directory / 'uploads/foo.txt').is_file()
    assert (test_directory / 'uploads/foo.txt').read_text() == 'foobar'

    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_directory_crud(test_session, test_async_client, test_directory, assert_directories, assert_files):
    """A directory can be created in a subdirectory.  Errors are returned if there are conflicts."""
    foo = test_directory / 'foo'
    foo.mkdir()
    await lib.refresh_files()
    assert_directories({'foo', })

    # Create a subdirectory.
    content = dict(path='foo/bar')
    request, response = await test_async_client.post('/api/files/directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert (test_directory / 'foo/bar').is_dir()
    assert_directories({'foo', 'foo/bar'})

    # Cannot create twice.
    content = dict(path='foo/bar')
    request, response = await test_async_client.post('/api/files/directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CONFLICT
    assert (test_directory / 'foo/bar').is_dir()
    assert_directories({'foo', 'foo/bar'})

    # Create a file to be deleted.
    (test_directory / 'foo/bar/asdf.txt').write_text('asdf')

    # Can get information about a directory.
    request, response = await test_async_client.post('/api/files/get_directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['path'] == 'foo/bar'
    assert response.json['size'] == 4
    assert response.json['file_count'] == 1

    # Can rename the directory.
    content = dict(path='foo/bar', new_name='baz')
    request, response = await test_async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/bar').exists()
    assert (test_directory / 'foo/baz').exists()
    assert (test_directory / 'foo/baz/asdf.txt').exists()

    # Deletion is recursive.
    assert (test_directory / 'foo/baz/asdf.txt').is_file()
    content = dict(path='foo/baz')
    request, response = await test_async_client.post('/api/files/delete_directory', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/baz').exists()
    assert not (test_directory / 'foo/baz/asdf.txt').exists()
    # Only top directory is left.
    assert_directories({'foo', })


@pytest.mark.asyncio
async def test_move(test_session, test_directory, make_files_structure, test_async_client):
    foo, bar = make_files_structure({
        'foo/bar.txt': 'bar',
        'baz.txt': 'baz',
    })

    # qux directory does not exist
    content = dict(paths=['foo', 'baz.txt'], destination='qux')
    request, response = await test_async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NOT_FOUND

    (test_directory / 'qux').mkdir()

    # mv foo baz.txt qux
    content = dict(paths=['foo', 'baz.txt'], destination='qux')
    request, response = await test_async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not foo.exists()
    assert (test_directory / 'qux/foo/bar.txt').is_file()

    # mv foo/bar.txt qux
    content = dict(paths=['qux/foo/bar.txt', ], destination='qux')
    request, response = await test_async_client.post('/api/files/move', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not foo.exists()
    assert (test_directory / 'qux/bar.txt').is_file()
    assert (test_directory / 'qux/foo').is_dir()


@pytest.mark.asyncio
async def test_rename(test_session, test_directory, make_files_structure, test_async_client):
    foo, = make_files_structure({
        'foo/bar/baz.txt': 'asdf',
    })

    # mv foo/bar/baz.txt foo/bar/qux.txt
    content = dict(path='foo/bar/baz.txt', new_name='qux.txt')
    request, response = await test_async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not foo.exists()
    assert (test_directory / 'foo/bar/qux.txt').is_file()
    assert (test_directory / 'foo/bar/qux.txt').read_text() == 'asdf'


@pytest.mark.asyncio
async def test_rename_directory(test_session, test_directory, make_files_structure, test_async_client):
    make_files_structure({
        'foo/bar/baz.txt': 'asdf',
    })

    # mv foo/bar/baz.txt foo/bar/qux.txt
    content = dict(path='foo/bar', new_name='qux')
    request, response = await test_async_client.post('/api/files/rename', content=json.dumps(content))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'foo/bar').exists()
    assert (test_directory / 'foo/qux/baz.txt').is_file()
    assert (test_directory / 'foo/qux/baz.txt').read_text() == 'asdf'
