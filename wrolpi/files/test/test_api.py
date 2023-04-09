import json
from http import HTTPStatus
from unittest import mock

import pytest

from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.files import lib as files_lib
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


def test_delete_file(test_client, make_files_structure, test_directory):
    files = ['bar.txt', 'baz/']
    make_files_structure(files)

    request, response = test_client.post('/api/files/delete', content=json.dumps({'file': 'bar.txt'}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (test_directory / 'bar.txt').is_file()
    assert (test_directory / 'baz').is_dir()

    request, response = test_client.post('/api/files/delete', content=json.dumps({'file': 'baz'}))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not (test_directory / 'bar.txt').is_file()
    assert (test_directory / 'baz').is_dir()

    request, response = test_client.post('/api/files/delete', content=json.dumps({'file': 'bad file'}))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.parametrize(
    'file', [
        '',
    ]
)
def test_delete_invalid_file(test_client, file):
    with mock.patch('wrolpi.files.api.lib.delete_file') as mock_delete_file:
        request, response = test_client.post('/api/files/delete', content=json.dumps({'file': file}))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_delete_file.assert_not_called()


def test_delete_wrol_mode(test_client, wrol_mode_fixture):
    """Can't delete a file when WROL Mode is enabled."""
    wrol_mode_fixture(True)

    request, response = test_client.post('/api/files/delete', content=json.dumps({'file': 'foo'}))
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


def test_directory_search(test_client, make_files_structure):
    """Test that directories can be searched."""
    make_files_structure([
        'foo/',
        'fool/',
        'not a directory',
    ])

    def assert_directories(search_str, expected):
        body = dict(search_str=search_str)
        request, response = test_client.post('/api/files/directories', content=json.dumps(body))
        assert response.status_code == HTTPStatus.OK
        assert response.json['directories'] == expected

    # All directories are returned.
    assert_directories(None, ['foo', 'fool'])
    assert_directories('', ['foo', 'fool'])
    # Matches both directories.
    assert_directories('fo', ['foo', 'fool'])
    # Matches the one directory exactly.
    assert_directories('foo', ['foo'])
    # Does not exist.
    assert_directories('food', [])


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
