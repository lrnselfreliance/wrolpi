import json
import shutil
import zipfile
from pathlib import Path
from typing import List

import mock
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from modules import videos
from wrolpi.common import get_media_directory
from wrolpi.errors import InvalidFile
from wrolpi.files import lib, indexers
from wrolpi.files.models import File
from wrolpi.vars import PROJECT_DIR


def assert_files(session: Session, expected):
    files = {str(i.path.relative_to(get_media_directory())) for i in session.query(File).all()}
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
def test_split_file_name_into_words(path, expected):
    assert lib.split_file_name_into_words(Path(path)) == expected


@pytest.mark.parametrize(
    'path,expected',
    [
        ('foo', ('foo', '')),
        ('foo.mp4', ('foo', '.mp4')),
        ('foo.info.json', ('foo', '.info.json')),
        ('foo.something.info.json', ('foo.something', '.info.json')),
        ('foo-something.info.json', ('foo-something', '.info.json')),
        ('/absolute/foo-something.info.json', ('foo-something', '.info.json')),
        ('/absolute/foo', ('foo', '')),
        ('/absolute/foo.bar', ('foo', '.bar')),
    ]
)
def test_split_path_stem_and_suffix(path, expected):
    assert lib.split_path_stem_and_suffix(Path(path)) == expected


@pytest.mark.asyncio
async def test_refresh_files(test_session, make_files_structure, test_directory):
    """All files in the media directory should be found when calling `refresh_files`"""
    files = make_files_structure([
        'foo.txt',
        'bar.txt',
        'baz.txt',
    ])
    foo, bar, baz = files

    await lib.refresh_files()
    assert_files(test_session, ['bar.txt', 'baz.txt', 'foo.txt'])

    baz.unlink()

    await lib.refresh_files()
    assert_files(test_session, ['bar.txt', 'foo.txt'])

    foo.unlink()
    bar.unlink()

    await lib.refresh_files()
    assert_files(test_session, [])


@pytest.mark.asyncio
async def test_refresh_files_in_directory(test_session, make_files_structure, test_directory):
    """A subdirectory can be refreshed, files above it can be ignored."""
    ignored, foo, similar = make_files_structure([
        'ignored.txt',
        'subdir/foo.txt',
        'subdir-similarly-named.mp4',
    ])

    await lib.refresh_directory_files_recursively(test_directory / 'subdir')
    assert_files(test_session, ['subdir/foo.txt'])

    await lib.refresh_directory_files_recursively(test_directory)
    assert_files(test_session, ['ignored.txt', 'subdir/foo.txt', 'subdir-similarly-named.mp4'])

    # The similarly named file is not deleted when refreshing the directory which shares the name.
    foo.unlink()
    await lib.refresh_directory_files_recursively(test_directory / 'subdir')
    assert_files(test_session, ['ignored.txt', 'subdir-similarly-named.mp4'])


@pytest.mark.asyncio
async def test_mime_type(test_session, make_files_structure, test_directory):
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

    await lib.refresh_files()
    assert_files(test_session, ['dir/foo text.txt', 'dir/bar.jpeg', 'dir/baz.mp4', 'dir/empty'])

    foo = test_session.query(File).filter_by(path=f'{test_directory}/dir/foo text.txt').one()
    bar = test_session.query(File).filter_by(path=f'{test_directory}/dir/bar.jpeg').one()
    baz = test_session.query(File).filter_by(path=f'{test_directory}/dir/baz.mp4').one()
    empty = test_session.query(File).filter_by(path=f'{test_directory}/dir/empty').one()

    assert foo.mimetype == 'text/plain'
    assert bar.mimetype == 'image/jpeg'
    assert baz.mimetype == 'video/mp4'
    assert empty.mimetype == 'inode/x-empty'


@pytest.mark.asyncio
async def test_files_indexer(test_session, make_files_structure):
    """An Indexer is provided for each file based on it's mimetype or contents."""
    source_files: List[str] = [
        'a bzip file.bzip',
        'a gzip file.gzip',
        'a text file.txt',
        'a zip file.zip',
        'images/an image file.jpeg',
        'unknown file',
        'videos/a video file.info.json',
        'videos/a video file.mp4',
    ]
    bzip_path, gzip_path, text_path, zip_path, image_path, unknown_path, info_json_path, video_path \
        = make_files_structure(source_files)
    text_path.write_text('text file contents')
    Image.new('RGB', (25, 25), color='grey').save(image_path)
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        zip_file.write(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4')
    with zipfile.ZipFile(bzip_path, 'w') as bzip_file:
        bzip_file.write(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4')
    with zipfile.ZipFile(gzip_path, 'w') as gzip_file:
        gzip_file.write(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4')
    info_json_path.write_text(json.dumps({'description': 'the video description'}))

    # Enable slow feature for testing.
    # TODO can this be sped up to always be included?
    with mock.patch('modules.videos.EXTRACT_SUBTITLES', True):
        await lib._refresh_all_files()

    bzip_file, gzip_file, text_file, zip_file, image_file, unknown_file, info_json_file, video_file \
        = test_session.query(File).order_by(File.path)

    # Indexers are detected correctly.
    assert bzip_file.path.suffix == '.bzip' and bzip_file.indexer == indexers.ZipIndexer
    assert gzip_file.path.suffix == '.gzip' and gzip_file.indexer == indexers.ZipIndexer
    assert text_file.path.suffix == '.txt' and text_file.indexer == indexers.TextIndexer
    assert zip_file.path.suffix == '.zip' and zip_file.indexer == indexers.ZipIndexer
    assert image_file.path.suffix == '.jpeg' and image_file.indexer == indexers.DefaultIndexer
    assert unknown_file.path.suffix == '' and unknown_file.indexer == indexers.DefaultIndexer
    assert info_json_file.path.suffix == '.json' and info_json_file.indexer == indexers.DefaultIndexer
    assert video_file.path.suffix == '.mp4' and video_file.indexer == videos.VideoIndexer

    # Path suffix is copied to File.suffix.
    assert bzip_file.suffix == '.bzip'
    assert gzip_file.suffix == '.gzip'
    assert text_file.suffix == '.txt'
    assert zip_file.suffix == '.zip'
    assert image_file.suffix == '.jpeg'
    assert unknown_file.suffix == ''
    assert info_json_file.suffix == '.info.json'
    assert video_file.suffix == '.mp4'

    # File are indexed by their titles and contents.
    files, total = lib.file_search('file', 10, 0)
    assert total == len(source_files), 'All files contain "file" in their file name.'
    files, total = lib.file_search('image', 10, 0)
    assert total == 1 and files[0]['title'] == 'an image file.jpeg', 'The image file title contains "image".'
    files, total = lib.file_search('contents', 10, 0)
    assert total == 1 and files[0]['title'] == 'a text file.txt', 'The text file contains "contents".'
    files, total = lib.file_search('video', 10, 0)
    assert total == 2 and {i['title'] for i in files} == {'a video file.info.json', 'a video file.mp4'}, \
        'The video files contains "video".'
    files, total = lib.file_search('yawn', 10, 0)
    assert total == 1 and files[0]['title'] == 'a video file.mp4', 'The video file captions contain "yawn".'
    files, total = lib.file_search('bunny', 10, 0)
    assert total == 3 and {i['title'] for i in files} == {'a zip file.zip', 'a bzip file.bzip', 'a gzip file.gzip'}, \
        'The zip files contain a file with "bunny" in the title.'

    with mock.patch('modules.videos.VideoIndexer.create_index') as mock_create_index:
        mock_create_index.side_effect = Exception('This should not be called twice')
        await lib.refresh_files()


@pytest.mark.asyncio
async def test_large_text_indexer(test_session, make_files_structure):
    """
    Large files have their indexes truncated.
    """
    large, = make_files_structure({
        'large_file.txt': 'foo ' * 1_000_000,
    })
    await lib._refresh_all_files()
    assert test_session.query(File).count() == 1

    assert large.is_file() and large.stat().st_size == 4_000_000

    large_file: File = test_session.query(File).one()
    assert len(large_file.d_text) < large.stat().st_size
    assert len(large_file.d_text) == 46_117


def test_glob_shared_stem(make_files_structure):
    mp4, png, j, name, video, something, vid2, vid2j = make_files_structure([
        'video.mp4',
        'video.png',
        'video.info.json',
        'video-name.txt',
        'video/',
        'something',
        'videos/video2 [name].mp4',
        'videos/video2 [name].info.json',
    ])

    def check(path, expected):
        assert sorted([i.name for i in lib.glob_shared_stem(path)]) == sorted(expected)

    check(mp4, ['video.mp4', 'video.png', 'video.info.json', 'video'])
    check(png, ['video.mp4', 'video.png', 'video.info.json', 'video'])
    check(j, ['video.mp4', 'video.png', 'video.info.json', 'video'])
    check(video, ['video.mp4', 'video.png', 'video.info.json', 'video'])

    check(something, ['something'])

    check(vid2, ['video2 [name].mp4', 'video2 [name].info.json'])
    check(vid2j, ['video2 [name].mp4', 'video2 [name].info.json'])
