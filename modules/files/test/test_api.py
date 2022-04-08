import json
from http import HTTPStatus
from itertools import zip_longest
from unittest import mock

import pytest

from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.test.common import assert_dict_contains
from wrolpi.vars import PROJECT_DIR


def test_list_files_api(test_client, make_files_structure, test_directory):
    files = [
        'archives/bar.txt',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory/',
        'videos/other video.mp4',
        'videos/some video.mp4',
    ]
    files = make_files_structure(files)
    files[0].write_text('bar contents')

    def check_get_files(directories, expected_files):
        request, response = test_client.post('/api/files', content=json.dumps({'directories': directories}))
        assert not response.json.get('errors')
        results = sorted(response.json['files'], key=lambda i: i['key'])
        for f1, f2 in zip_longest(results, expected_files):
            if f1 is None or f2 is None:
                assert f1 == f2
            for key in f2.keys():
                assert f1[key] == f2[key], f'{f1} != {f2}'

    # Requesting no directories results in the top-level results.
    expected = [dict(key='archives/'), dict(key='empty directory/'), dict(key='videos/')]
    check_get_files([], expected)
    # empty directory is empty
    check_get_files(['empty directory'], expected)

    expected = [
        dict(key='archives/'),
        dict(key='archives/bar.txt', size=12),
        dict(key='archives/baz/'),
        dict(key='archives/foo.txt'),
        dict(key='empty directory/'),
        dict(key='videos/'),
    ]
    check_get_files(['archives'], expected)

    # Sub-directories are supported.
    expected = [
        dict(key='archives/'),
        dict(key='archives/bar.txt', size=12),
        dict(key='archives/baz/'),
        dict(key='archives/baz/bar.txt'),
        dict(key='archives/baz/foo.txt'),
        dict(key='archives/foo.txt'),
        dict(key='empty directory/'),
        dict(key='videos/'),
    ]
    check_get_files(['archives/baz'], expected)

    expected = [
        dict(key='archives/'),
        dict(key='archives/bar.txt', size=12),
        dict(key='archives/baz/'),
        dict(key='archives/foo.txt'),
        dict(key='empty directory/'),
        dict(key='videos/'),
        dict(key='videos/other video.mp4'),
        dict(key='videos/some video.mp4'),
    ]
    check_get_files(['archives', 'videos'], expected)
    # Order does not matter.
    check_get_files(['archives', 'videos', 'empty directory'], expected)
    check_get_files(['archives', 'empty directory', 'videos'], expected)


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
    with mock.patch('modules.files.api.lib.delete_file') as mock_delete_file:
        request, response = test_client.post('/api/files/delete', content=json.dumps({'file': file}))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_delete_file.assert_not_called()


def test_delete_wrol_mode(test_client):
    """
    Can't delete a file when WROL Mode is enabled.
    """
    with mock.patch('wrolpi.common.wrol_mode_enabled', lambda: True):
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
        dict(path='baz.mp4', mimetype='video/mp4', size=1055736),
        dict(path='baz baz two.mp4', mimetype='video/mp4', size=1055736),
    ])
    do_search(test_client, 'two', 1, [dict(path='baz baz two.mp4', mimetype='video/mp4', size=1055736)])
    do_search(test_client, 'nothing', 0, [])
