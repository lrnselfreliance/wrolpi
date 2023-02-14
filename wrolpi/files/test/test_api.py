import json
from http import HTTPStatus
from itertools import zip_longest
from unittest import mock

import pytest

from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.files.models import File
from wrolpi.test.common import assert_dict_contains
from wrolpi.vars import PROJECT_DIR
from wrolpi.files import lib as files_lib


def test_list_files_api(test_client, make_files_structure, test_directory):
    files = [
        'archives/bar.txt',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory/',
        'videos/other video.mp4',
        'videos/some video.mp4',
        'lost+found/', # Should always be ignored.
    ]
    files = make_files_structure(files)
    files[0].write_text('bar contents')

    def check_get_files(directories, expected_files):
        request, response = test_client.post('/api/files', content=json.dumps({'directories': directories}))
        assert not response.json.get('errors')
        # The first dict is the media directory.
        children = response.json['files']
        assert children == expected_files
        # Clear caches before next call.
        files_lib._get_file_dict.cache_clear()
        files_lib._get_directory_dict.cache_clear()

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


def do_search(test_client, search_str, total, expected):
    content = json.dumps({'search_str': search_str})
    request, response = test_client.post('/api/files/search', content=content)
    assert response.json['totals']['files'] == total
    for file, expected in zip_longest(response.json['files'], expected):
        assert_dict_contains(file, expected)
        # FileBrowser in React requires a key.  We use the path.
        assert file['path'] == file['key']


def test_files_search(test_session, test_client, make_files_structure):
    # You can search an empty directory.
    do_search(test_client, 'nothing', 0, [])

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

    do_search(test_client, 'foo', 1, [dict(path='foo_is_the_name.txt', mimetype='text/plain', size=12)])
    do_search(test_client, 'bar', 1, [dict(path='archives/bar.txt', mimetype='text/plain', size=16)])
    do_search(test_client, 'baz', 2, [
        dict(path='baz baz two.mp4', mimetype='video/mp4', size=1056318),
        dict(path='baz.mp4', mimetype='video/mp4', size=1056318),
    ])
    do_search(test_client, 'two', 1, [dict(path='baz baz two.mp4', mimetype='video/mp4', size=1056318)])
    do_search(test_client, 'nothing', 0, [])

    # No search string returns all Files.
    do_search(test_client, None, 4, [
        dict(path='archives/bar.txt'),
        dict(path='baz baz two.mp4'),
        dict(path='baz.mp4'),
        dict(path='foo_is_the_name.txt'),
    ])


def test_associated_files(test_session, test_client, make_files_structure):
    mp4, png, j, txt = make_files_structure([
        'video.mp4',
        'video.png',
        'video.info.json',
        'not a video.txt',
    ])
    test_client.post('/api/files/refresh')
    mp4_file = test_session.query(File).filter_by(path=mp4).one()
    png_file = test_session.query(File).filter_by(path=png).one()
    j_file = test_session.query(File).filter_by(path=j).one()
    txt_file = test_session.query(File).filter_by(path=txt).one()

    def check_files_search(content, expected):
        request, response = test_client.post('/api/files/search', content=json.dumps(content))
        assert response.status_code == HTTPStatus.OK
        assert [{'path': i['path']} for i in response.json['files']] == expected

    check_files_search(
        {'search_str': 'video'},
        [
            {'path': 'not a video.txt'},
            {'path': 'video.info.json'},
            {'path': 'video.mp4'},
            {'path': 'video.png'},
        ]
    )

    mp4_file.associated = False  # the modeled file
    png_file.associated = True
    j_file.associated = True
    test_session.commit()

    # Associated files are last.
    check_files_search(
        {'search_str': 'video'},
        [
            {'path': 'not a video.txt'},
            {'path': 'video.mp4'},
        ]
    )


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


def test_refresh_files_list(test_session, test_client, make_files_structure):
    """The user can request to refresh specific files."""
    make_files_structure(['bar.txt', 'bar.mp4'])

    # Video file near `bar.txt` can be ignored.
    content = json.dumps({'files': ['bar.txt'], 'include_files_near': False})
    request, response = test_client.post('/api/files/refresh/list', content=content)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(File).count() == 1


def test_file_statistics(test_session, test_client, example_pdf, example_mobi, example_epub, video_file):
    """A summary of File statistics can be fetched."""
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
        'total_count': 5,
        'video_count': 1,
        'zip_count': 0,
    }
