import shutil
from pathlib import Path
from typing import List, Iterable

import pytest
from sqlalchemy.orm import Session

from modules.files import lib
from modules.files.models import File
from wrolpi.errors import InvalidFile
from wrolpi.media_path import MediaPathType
from wrolpi.vars import PROJECT_DIR


def assert_files(session: Session, expected):
    files = {str(i.path.relative) for i in session.query(File).all()}
    assert files == set(expected)


def test_list_files(make_files_structure, test_directory):
    files = [
        'archives/bar.txt',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory/',
        'videos/other video.mp4',
        'videos/some video.mp4',
    ]
    make_files_structure(files)

    def check_list_files(path, expected):
        result = lib.list_files(path)
        result = sorted(result)
        assert [str(i.relative_to(test_directory)) for i in result] == expected

    check_list_files([], ['archives', 'empty directory', 'videos'])
    # Falsey directories are ignored.
    check_list_files([None, ''], ['archives', 'empty directory', 'videos'])
    check_list_files(['empty directory'], ['archives', 'empty directory', 'videos'])
    check_list_files(['empty directory'], ['archives', 'empty directory', 'videos'])
    # Trailing slash is ignored.
    check_list_files(['empty directory/'], ['archives', 'empty directory', 'videos'])

    check_list_files(['archives'], [
        'archives',
        'archives/bar.txt',
        'archives/baz',
        'archives/foo.txt',
        'empty directory',
        'videos',
    ])
    check_list_files(['archives/baz'], [
        'archives',
        'archives/bar.txt',
        'archives/baz',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory',
        'videos',
    ])
    # Including duplicate directories does not change results.
    check_list_files(['archives/baz', 'archives'], [
        'archives',
        'archives/bar.txt',
        'archives/baz',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory',
        'videos',
    ])
    check_list_files(['videos'], [
        'archives',
        'empty directory',
        'videos',
        'videos/other video.mp4',
        'videos/some video.mp4',
    ])
    # All files and directories are listed.
    check_list_files(['videos', 'archives/baz'], [
        'archives',
        'archives/bar.txt',
        'archives/baz',
        'archives/baz/bar.txt',
        'archives/baz/foo.txt',
        'archives/foo.txt',
        'empty directory',
        'videos',
        'videos/other video.mp4',
        'videos/some video.mp4',
    ])


@pytest.mark.parametrize(
    'directories,expected', [
        ([Path('foo')], [Path('foo')]),
        ([Path('foo'), Path('bar')], [Path('foo'), Path('bar')]),
        ([Path('foo'), Path('foo/bar'), Path('baz')], [Path('foo/bar'), Path('baz')]),
        ([Path('foo/bar'), Path('foo'), Path('baz')], [Path('foo/bar'), Path('baz')]),
        ([Path('baz'), Path('foo/bar'), Path('foo')], [Path('baz'), Path('foo/bar')]),
        ([Path('foo/bar'), Path('foo'), Path('foo/bar/baz')], [Path('foo/bar/baz')]),
    ]
)
def test_filter_parent_directories(directories, expected):
    assert lib.filter_parent_directories(directories) == expected


def test_delete_file(make_files_structure, test_directory):
    """
    File in the media directory can be deleted.
    """
    files = [
        'archives/foo.txt',
        'bar.txt',
        'baz/',
    ]
    make_files_structure(files)

    lib.delete_file('bar.txt')
    assert (test_directory / 'archives/foo.txt').is_file()
    assert not (test_directory / 'bar.txt').is_file()
    assert (test_directory / 'baz').is_dir()

    lib.delete_file('archives/foo.txt')
    assert not (test_directory / 'archives/foo.txt').is_file()
    assert not (test_directory / 'bar.txt').is_file()

    with pytest.raises(InvalidFile):
        lib.delete_file('baz')
    with pytest.raises(InvalidFile):
        lib.delete_file('does not exist')

    assert (test_directory / 'baz').is_dir()


@pytest.mark.parametrize(
    'path,expected',
    [
        ('foo.mp4', ['foo']),
        ('foo bar.txt', ['foo', 'bar']),
        ('foo_bar.mp4', ['foo', 'bar']),
        ('foo-bar', ['foo-bar']),
        ('123 foo bar', ['123', 'foo', 'bar']),
        ('123foo bar', ['123foo', 'bar']),
    ]
)
def test_split_file_name(path, expected):
    assert lib.split_file_name(Path(path)) == expected


def test_refresh_files(test_session, make_files_structure, test_directory):
    files = make_files_structure([
        'foo.txt',
        'bar.txt',
        'baz.txt',
    ])
    foo, bar, baz = files

    def get_relative_strs(files_: Iterable[MediaPathType]) -> List[str]:
        return sorted([str(i.path.path.relative_to(test_directory)) for i in files_])

    lib.refresh_files()
    results = test_session.query(File)
    assert get_relative_strs(results) == ['bar.txt', 'baz.txt', 'foo.txt']

    baz.unlink()

    lib.refresh_files()
    results = test_session.query(File)
    assert get_relative_strs(results) == ['bar.txt', 'foo.txt']

    foo.unlink()
    bar.unlink()

    lib.refresh_files()
    results = test_session.query(File)
    assert get_relative_strs(results) == []


def test_mime_type(test_session, make_files_structure, test_directory):
    """Files module uses the `file` command to get the mimetype of each file."""
    from PIL import Image

    foo, bar, baz, empty = make_files_structure([
        'dir/foo text.txt',
        'dir/bar.jpeg',
        'dir/baz.mp4',
        'dir/empty',
    ])
    foo.write_text('some text')
    Image.new('RGB', (25, 25), color='grey').save(bar)
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', baz)

    lib.refresh_files()
    assert_files(test_session, ['dir/foo text.txt', 'dir/bar.jpeg', 'dir/baz.mp4', 'dir/empty'])

    foo = test_session.query(File).filter_by(path=f'{test_directory}/dir/foo text.txt').one()
    bar = test_session.query(File).filter_by(path=f'{test_directory}/dir/bar.jpeg').one()
    baz = test_session.query(File).filter_by(path=f'{test_directory}/dir/baz.mp4').one()
    empty = test_session.query(File).filter_by(path=f'{test_directory}/dir/empty').one()

    assert foo.mimetype == 'text/plain'
    assert bar.mimetype == 'image/jpeg'
    assert baz.mimetype == 'video/mp4'
    assert empty.mimetype == 'inode/x-empty'
