import asyncio
import json
import pathlib
import shutil
import zipfile
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import List
from uuid import uuid4

import mock
import pytest
from PIL import Image

import wrolpi.common
from modules.videos import Video
from wrolpi.common import timer
from wrolpi.conftest import await_switches
from wrolpi.dates import now
from wrolpi.errors import InvalidFile, UnknownDirectory, FileGroupIsTagged, NoPrimaryFile
from wrolpi.files import lib, indexers
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile
from wrolpi.test.common import only_macos
from wrolpi.vars import PROJECT_DIR, IS_MACOS


@pytest.mark.asyncio
async def test_delete_file(async_client, test_session, make_files_structure, test_directory):
    """
    File in the media directory can be deleted.
    """
    make_files_structure([
        'archives/foo.txt',
        'bar.txt',
        'baz/',
    ])

    await lib.delete('bar.txt')
    assert (test_directory / 'archives/foo.txt').is_file()
    assert not (test_directory / 'bar.txt').exists()
    assert (test_directory / 'baz').is_dir()

    await lib.delete('archives/foo.txt')
    assert not (test_directory / 'archives/foo.txt').exists()
    assert not (test_directory / 'bar.txt').exists()

    # Can also delete directories.
    await lib.delete('baz')
    assert not (test_directory / 'baz').exists()

    with pytest.raises(InvalidFile):
        await lib.delete('does not exist')

    # Cannot delete the media directory.
    with pytest.raises(InvalidFile):
        await lib.delete('.')


@pytest.mark.asyncio
async def test_delete_file_multiple(async_client, test_session, make_files_structure, test_directory):
    """Multiple files can be deleted at once."""
    foo, bar, baz = make_files_structure([
        'archives/foo.txt',
        'archives/bar.txt',
        'archives/baz.txt',
    ])
    assert foo.is_file()
    assert bar.is_file()
    assert baz.is_file()

    await lib.delete('archives/foo.txt', 'archives/bar.txt', 'archives/baz.txt')
    assert not foo.is_file()
    assert not bar.is_file()
    assert not baz.is_file()


@pytest.mark.asyncio
async def test_delete_file_names(async_client, test_session, make_files_structure, test_directory, tag_factory):
    """Will not refuse to delete a file that shares the name of a nearby file when they are in different FileGroups."""
    foo, foo1 = make_files_structure({
        'archives/foo': 'text',
        'archives/foo1': 'text',
    })
    foo_fg = FileGroup.from_paths(test_session, foo)
    foo1_fg = FileGroup.from_paths(test_session, foo1)
    tag = await tag_factory()
    foo1_fg.add_tag(tag.id)
    test_session.commit()
    assert foo.is_file()
    assert foo1.is_file()

    await lib.delete('archives/foo')
    assert not foo.is_file()
    assert foo1.is_file()


@pytest.mark.asyncio
async def test_delete_file_link(async_client, test_session, test_directory):
    """Links can be deleted."""
    foo, bar = test_directory / 'foo', test_directory / 'bar'
    foo.touch()
    bar.symlink_to(foo)

    await lib.delete(bar)


@pytest.mark.asyncio
async def test_delete_tagged(await_switches, test_session, make_files_structure, tag_factory, video_bytes):
    """Cannot delete a file that has been tagged."""
    tag = await tag_factory()
    make_files_structure({'foo/bar.txt': 'asdf', 'foo/bar.mp4': video_bytes})
    await lib.refresh_files()
    # Both files end up in a group.
    bar = test_session.query(FileGroup).one()
    bar.add_tag(tag.id)
    await await_switches()
    test_session.commit()

    # Neither file can be deleted.
    with pytest.raises(FileGroupIsTagged):
        await lib.delete('foo/bar.txt')
    with pytest.raises(FileGroupIsTagged):
        await lib.delete('foo/bar.mp4')
    with pytest.raises(FileGroupIsTagged):
        await lib.delete('foo')


@pytest.mark.asyncio
async def test_delete_nested(test_session, make_files_structure):
    """Refuse to delete nested files in case user mis-clicks."""
    make_files_structure(['foo/bar'])

    with pytest.raises(InvalidFile):
        await lib.delete('foo', 'foo/bar')


@pytest.mark.parametrize(
    'path,full,expected',
    [
        ('foo', False, ('foo', '')),
        ('foo.mp4', False, ('foo', '.mp4')),
        ('foo.info.json', False, ('foo', '.info.json')),
        ('foo.something.info.json', False, ('foo.something', '.info.json')),
        ('foo-something.info.json', False, ('foo-something', '.info.json')),
        ('/absolute/foo-something.info.json', False, ('foo-something', '.info.json')),
        ('/absolute/foo', False, ('foo', '')),
        ('/absolute/foo.bar', False, ('foo', '.bar')),
        ('foo.en.srt', False, ('foo', '.en.srt')),
        ('foo.pl.srt', False, ('foo', '.pl.srt')),
        ('foo.en-US.srt', False, ('foo', '.en-US.srt')),
        ('foo.en-US.vtt', False, ('foo', '.en-US.vtt')),
        ('foo.en-us.vtt', False, ('foo', '.en-us.vtt')),
        ('foo.en-AUTO.srt', False, ('foo', '.en-AUTO.srt')),
        ('foo.en-auto.vtt', False, ('foo', '.en-auto.vtt')),
        # Absolute path can be returned.
        ('/absolute//foo.bar', True, ('/absolute/foo', '.bar')),
        # Case is preserved.
        ('foo.EN.SRT', False, ('foo', '.EN.SRT')),
        ('foo.INFO.JSON', False, ('foo', '.INFO.JSON')),
        # Part files from yt-dlp.
        ('foo.webm.part', False, ('foo', '.webm.part')),
        ('foo.f248.webm.part', False, ('foo', '.f248.webm.part')),
        ('foo.info.json.part', False, ('foo', '.info.json.part')),
        ('/absolute/foo.webm.part', True, ('/absolute/foo', '.webm.part')),
    ])
def test_split_path_stem_and_suffix(path, full, expected):
    assert lib.split_path_stem_and_suffix(Path(path), full) == expected


@pytest.mark.asyncio
async def test_refresh_files(async_client, test_session, make_files_structure, assert_file_groups):
    """All files in the media directory should be found when calling `refresh_files`"""
    files = make_files_structure([
        'foo.txt',
        'bar.txt',
        'baz.txt',
    ])
    foo, bar, baz = files

    await lib.refresh_files()
    assert_file_groups([
        {'primary_path': 'foo.txt', 'indexed': True},
        {'primary_path': 'bar.txt', 'indexed': True},
        {'primary_path': 'baz.txt', 'indexed': True}])

    baz.unlink()

    await lib.refresh_files()
    assert_file_groups([{'primary_path': 'foo.txt', 'indexed': True}, {'primary_path': 'bar.txt', 'indexed': True}])

    foo.unlink()

    await lib.refresh_files()
    assert_file_groups([{'primary_path': 'bar.txt', 'indexed': True}])


@pytest.mark.asyncio
async def test_file_group_location(async_client, test_session, make_files_structure):
    """FileGroup can return the URL necessary to preview the FileGroup."""
    make_files_structure({
        'foo/one.txt': 'one',
        'two.txt': 'two',
    })
    await lib.refresh_files()

    one, two = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    assert one.location == '/files?folders=foo&preview=foo%2Fone.txt'
    assert two.location == '/files?preview=two.txt'


@pytest.mark.asyncio
async def test_refresh_bogus_files(async_client, test_session, make_files_structure, test_directory,
                                   assert_file_groups, insert_file_group):
    """Bogus files are removed during a refresh."""
    make_files_structure(['does exist.txt'])
    await lib.refresh_files()
    insert_file_group([test_directory / 'does not exist.txt'])
    test_session.commit()

    # Bogus file was inserted.
    assert_file_groups([
        {'primary_path': 'does exist.txt', 'indexed': True},
        {'primary_path': 'does not exist.txt', 'indexed': True},
    ])

    await lib.refresh_files()

    assert test_session.query(FileGroup).count() == 1, 'Bogus file was not removed'
    assert_file_groups([{'primary_path': 'does exist.txt', 'indexed': True}])


@pytest.mark.asyncio
async def test_refresh_empty_media_directory(async_client, test_session, test_directory):
    """refresh_paths will refuse to refresh with an empty media directory."""
    with pytest.raises(UnknownDirectory):
        await lib.refresh_files()


@pytest.mark.asyncio
async def test__upsert_files(test_session, make_files_structure, test_directory, assert_file_groups, video_file,
                             srt_file3):
    baz, bar = make_files_structure({
        'dir1/bar.txt': None,
        'baz.txt': 'baz file',
    })
    video_file = video_file.rename(test_directory / 'video.mp4')
    srt_file3 = srt_file3.rename(test_directory / 'video.en.srt')

    # All files are found because they are in this refresh request, or in the `dir1` directory.
    idempotency = now()
    lib._upsert_files([video_file, srt_file3, bar, baz], idempotency)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': False,
         'files': [
             {'path': srt_file3, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': bar, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}]
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': baz, 'size': 8, 'suffix': '.txt', 'mimetype': 'text/plain'}]
         },
    ])

    # Modified files should be re-indexed.
    bar.touch()
    baz.write_text('new baz')
    # Simulate that the video was indexed, it should not be re-indexed because it was not modified.
    test_session.query(FileGroup).filter_by(primary_path=video_file).one().indexed = True
    test_session.commit()
    assert_file_groups(
        [{'primary_path': str(video_file), 'idempotency': idempotency,
          'indexed': True}],
        assert_count=False)

    # Only modified files need to be re-indexed.
    lib._upsert_files([video_file, srt_file3, bar, baz], idempotency)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': True,
         'files': [
             {'path': srt_file3, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': bar, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}],
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': baz, 'size': 7, 'suffix': '.txt', 'mimetype': 'text/plain'}],
         },
    ])

    # Deleting SRT removes it from the video.
    srt_file3.unlink()
    lib._upsert_files([video_file, bar, baz], idempotency)
    video_file_group: FileGroup = test_session.query(FileGroup).filter_by(primary_path=str(video_file)).one()
    assert len(video_file_group.files) == 1, 'SRT file was not removed from files'
    assert_file_groups([
        # Video is no longer indexed because SRT was removed.
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': video_file, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'}]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': bar, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}],
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': False,
         'files': [{'path': baz, 'size': 7, 'suffix': '.txt', 'mimetype': 'text/plain'}],
         },
    ])


@pytest.mark.asyncio
async def test_refresh_discover_paths(test_session, make_files_structure, test_directory, assert_files,
                                      assert_file_groups):
    foo, bar, baz = make_files_structure(['dir1/foo.txt', 'dir1/bar.txt', 'baz.txt'])
    dir1 = foo.parent

    # `refresh_paths` only refreshes the file requested.
    await lib.refresh_discover_paths([foo, ])
    assert_files([
        {'path': 'dir1/foo.txt'},
    ])

    # `refresh_paths` refreshes recursively.
    await lib.refresh_discover_paths([foo.parent, ])
    assert_files([
        {'path': 'dir1/foo.txt'},
        {'path': 'dir1/bar.txt'},
    ])

    # `refresh_paths` finally discovers the file at the top of the media directory.
    await lib.refresh_discover_paths([test_directory, ])
    assert_files([
        {'path': 'dir1/foo.txt'},
        {'path': 'dir1/bar.txt'},
        {'path': 'baz.txt'},
    ])

    # Records for deleted files are deleted.  Request a refresh of `dir1` so we indirectly refresh `foo`.
    foo.unlink()
    await lib.refresh_discover_paths([dir1, ])
    assert_files([
        {'path': 'dir1/bar.txt'},
        {'path': 'baz.txt'},
    ])

    # Records for all children of a directory are deleted.
    bar.unlink()
    dir1.rmdir()
    await lib.refresh_discover_paths([dir1, ])
    assert_files([
        {'path': 'baz.txt'},
    ])


@pytest.mark.asyncio
async def test_refresh_discover_paths_groups(test_session, make_files_structure, test_directory, video_bytes):
    make_files_structure({'dir1/foo.mp4': video_bytes, 'dir1/foo.info.json': 'hello', 'baz.txt': 'hello'})
    await lib.refresh_discover_paths([test_directory, ], now())

    # Two "foo" files, one "baz" file.
    assert test_session.query(FileGroup).count() == 2

    baz, foo = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    # "foo" files are related to the "foo" group.
    assert sorted([str(i['path'].relative_to(test_directory)) for i in foo.my_files()]) == [
        'dir1/foo.info.json', 'dir1/foo.mp4',
    ]
    # "bar" file is the only file related to the "bar" group.
    assert len(baz.my_files()) == 1
    assert str(baz.my_files()[0]['path'].relative_to(test_directory)) == 'baz.txt'
    assert baz.indexed is False


@pytest.mark.asyncio
async def test_file_group_tag(test_session, make_files_structure, test_directory, tag_factory, await_switches):
    """A FileGroup can be tagged."""
    make_files_structure(['foo.mp4'])
    await lib.refresh_discover_paths([test_directory, ], now())
    one = await tag_factory()

    foo: FileGroup = test_session.query(FileGroup).one()
    foo.add_tag(one.id)
    test_session.commit()

    tag_file2: TagFile = test_session.query(TagFile).one()
    assert tag_file2 and tag_file2.file_group == foo


@pytest.mark.asyncio
async def test_refresh_a_text_no_indexer(async_client, test_session, make_files_structure):
    """File.a_text is filled even if the file does not match an Indexer."""
    make_files_structure(['foo', 'bar-bar'])

    await lib.refresh_files()

    files = {i.a_text for i in test_session.query(FileGroup)}
    assert files == {'bar bar bar-bar', 'foo'}


@pytest.mark.asyncio
async def test_refresh_many_files(async_client, test_session, make_files_structure):
    """Used to profile file refreshing"""
    file_count = 10_000
    make_files_structure([f'{uuid4()}.txt' for _ in range(file_count)])
    with timer('first refresh'):
        await lib.refresh_files()
    assert test_session.query(FileGroup).count() == file_count

    with timer('second refresh'):
        await lib.refresh_files()
    assert test_session.query(FileGroup).count() == file_count


@pytest.mark.asyncio
async def test_refresh_cancel(async_client, test_session, make_files_structure, test_directory):
    """Refresh tasks can be canceled."""
    # Creat a lot of files so the refresh will take too long.
    make_files_structure([f'{uuid4()}.txt' for _ in range(1_000)])

    async def assert_cancel(task_):
        # Time the time it takes to cancel.
        before = datetime.now()
        # Sleep so the refresh task has time to run.
        await asyncio.sleep(0)

        # Cancel the refresh (it will be sleeping soon).
        task_.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task_
        assert (datetime.now() - before).total_seconds() < 1.2, 'Task took too long.  Was the refresh canceled?'

    task = asyncio.create_task(lib.refresh_files())
    await assert_cancel(task)


@pytest.mark.asyncio
async def test_mime_type(async_client, test_session, make_files_structure, test_directory, assert_files):
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
    assert_files([
        {'path': 'dir/foo text.txt'},
        {'path': 'dir/bar.jpeg'},
        {'path': 'dir/baz.mp4'},
        {'path': 'dir/empty'},
    ])

    foo = test_session.query(FileGroup).filter_by(primary_path=f'{test_directory}/dir/foo text.txt').one()
    bar = test_session.query(FileGroup).filter_by(primary_path=f'{test_directory}/dir/bar.jpeg').one()
    baz = test_session.query(FileGroup).filter_by(primary_path=f'{test_directory}/dir/baz.mp4').one()
    empty = test_session.query(FileGroup).filter_by(primary_path=f'{test_directory}/dir/empty').one()

    assert foo.mimetype == 'text/plain'
    assert bar.mimetype == 'image/jpeg'
    assert baz.mimetype == 'video/mp4'
    assert empty.mimetype == 'inode/x-empty'


@pytest.mark.asyncio
async def test_files_indexer(async_client, test_session, make_files_structure, test_directory):
    """An Indexer is provided for each file based on it's mimetype or contents."""
    source_files: List[str] = [
        'a text file.txt',
        'a zip file.zip',
        'images/an image file.jpeg',
        'unknown file',
        'videos/a video file.info.json',  # This is "associated" and will be hidden.
        'videos/a video file.mp4',
    ]
    text_path, zip_path, image_path, unknown_path, info_json_path, video_path \
        = make_files_structure(source_files)
    text_path.write_text('text file contents')
    Image.new('RGB', (25, 25), color='grey').save(image_path)
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        zip_file.write(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4')
    info_json_path.write_text(json.dumps({'description': 'the video description'}))

    # Enable slow feature for testing.
    # TODO can this be sped up to always be included?
    with mock.patch('modules.videos.lib.EXTRACT_SUBTITLES', True):
        await lib.refresh_files()

    text_file, zip_file, image_file, unknown_file, video_file \
        = test_session.query(FileGroup).order_by(FileGroup.primary_path)

    # Indexers are detected correctly.
    assert text_file.mimetype == 'text/plain' and text_file.indexer == indexers.TextIndexer
    assert zip_file.mimetype == 'application/zip' and zip_file.indexer == indexers.ZipIndexer
    assert image_file.mimetype == 'image/jpeg' and image_file.indexer == indexers.DefaultIndexer
    assert unknown_file.mimetype == 'inode/x-empty' and unknown_file.indexer == indexers.DefaultIndexer
    # Video are indexed by the modeler, not by an indexer.
    assert video_file.mimetype == 'video/mp4' and video_file.indexer == indexers.DefaultIndexer

    # File are indexed by their titles and contents.
    files, total = lib.search_files('file', 10, 0)
    assert total == 5, 'All files contain "file" in their file name.  The associated video file is hidden.'
    files, total = lib.search_files('image', 10, 0)
    assert total == 1 and files[0]['title'] == 'an image file.jpeg', 'The image file title contains "image".'
    files, total = lib.search_files('contents', 10, 0)
    assert total == 1 and files[0]['title'] == 'a text file.txt', 'The text file contains "contents".'
    files, total = lib.search_files('video', 10, 0)
    assert total == 1 and {i['title'] for i in files} == {'a video file'}, 'The video file contains "video".'
    files, total = lib.search_files('yawn', 10, 0)
    assert total == 1 and files[0]['title'] == 'a video file', 'The video file captions contain "yawn".'
    files, total = lib.search_files('bunny', 10, 0)
    assert total == 1 and {i['title'] for i in files} == {'a zip file.zip'}, \
        'The zip file contains a file with "bunny" in the title.'

    with mock.patch('modules.videos.models.Video.validate') as mock_validate:
        mock_validate.side_effect = Exception('This should not be called twice')
        await lib.refresh_files()

    # Change the contents, the file should be re-indexed.
    text_path.write_text('new text contents')
    await lib.refresh_files()
    files, total = lib.search_files('new', 10, 0)
    assert total == 1


@pytest.mark.parametrize('name,expected', [
    ('this.txt', 'this txt'),
    ('name', 'name'),
    ('name two', 'name two'),
    ('this self-reliance_split.txt', 'this self reliance self-reliance split txt'),
    ('-be_split!.txt', '-be split! txt'),
    ('WROLPi-v0.10-aarch64-desktop.img.xz', 'WROLPi v0.10 aarch64 desktop.img WROLPi-v0.10-aarch64-desktop.img xz'),
    ('some words [but words in braces].txt', 'some words but words in braces txt'),
    ('some words (but words in parentheses).txt', 'some words but words in parentheses txt'),
])
def test_split_file_name_words(name, expected):
    assert lib.split_file_name_words(name) == expected


@pytest.mark.asyncio
async def test_large_text_indexer(async_client, test_session, make_files_structure):
    """
    Large files have their indexes truncated.
    """
    large, = make_files_structure({
        'large_file.txt': 'foo ' * 1_000_000,
    })
    await lib.refresh_files()
    assert test_session.query(FileGroup).count() == 1

    assert large.is_file() and large.stat().st_size == 4_000_000

    large_file: FileGroup = test_session.query(FileGroup).one()
    assert len(large_file.d_text) < large.stat().st_size
    assert len(large_file.d_text) == 90_072


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

    check(mp4, ['video.mp4', 'video.png', 'video.info.json'])
    check(png, ['video.mp4', 'video.png', 'video.info.json'])
    check(j, ['video.mp4', 'video.png', 'video.info.json'])
    check(video, ['video.mp4', 'video.png', 'video.info.json', 'video'])

    check(something, ['something'])

    check(vid2, ['video2 [name].mp4', 'video2 [name].info.json'])
    check(vid2j, ['video2 [name].mp4', 'video2 [name].info.json'])


def test_matching_directories(make_files_structure, test_directory):
    make_files_structure([
        'foo/qux/',
        'Bar/',
        'baz/baz'
        'barr',
        'bazz',
    ])

    # No directories have c
    matches = lib.get_matching_directories(test_directory / 'c')
    assert matches == []

    # Get all directories starting with f
    matches = lib.get_matching_directories(test_directory / 'f')
    assert matches == [test_directory / 'foo']

    # Get all directories starting with b, ignore case
    matches = lib.get_matching_directories(test_directory / 'b')
    assert matches == [test_directory / 'Bar', test_directory / 'baz']

    # baz matches, but it has no subdirectories
    matches = lib.get_matching_directories(test_directory / 'baz')
    assert matches == [test_directory / 'baz']

    # foo is an exact match, return subdirectories
    matches = lib.get_matching_directories(test_directory / 'foo')
    assert matches == [test_directory / 'foo/qux']


def test_get_mimetype(example_epub, example_mobi, example_pdf, image_file, video_file):
    assert lib.get_mimetype(example_epub) == 'application/epub+zip'
    assert lib.get_mimetype(example_mobi) == 'application/x-mobipocket-ebook'
    assert lib.get_mimetype(example_pdf) == 'application/pdf'
    assert lib.get_mimetype(image_file) == 'image/jpeg'
    assert lib.get_mimetype(video_file) == 'video/mp4'


def test_group_files_by_stem(make_files_structure, test_directory):
    make_files_structure([
        'foo.mp4',
        'foo.txt',
        'foo.info.json',
        'foo.live_chat.json',
        'bar.txt',
        'baz.txt',
    ])

    files = list(test_directory.iterdir())
    assert list(lib.group_files_by_stem(files)) == [
        [test_directory / 'bar.txt'],
        [test_directory / 'baz.txt'],
        [test_directory / 'foo.info.json', test_directory / 'foo.live_chat.json', test_directory / 'foo.mp4',
         test_directory / 'foo.txt'],
    ]


def test_get_primary_file(test_directory, video_file, srt_file3, example_epub, example_mobi, example_pdf,
                          singlefile_contents_factory, make_files_structure):
    """Test that the most important file is returned from a list of files."""
    srt_file3 = srt_file3.rename(test_directory / f'{video_file.stem}.srt')
    # Same primary_file no matter the order.
    assert lib.get_primary_file([video_file, srt_file3]) == video_file
    assert lib.get_primary_file([srt_file3, video_file]) == video_file

    singlefile = test_directory / 'singlefile.html'
    singlefile.write_text(singlefile_contents_factory())
    singlefile_text = test_directory / 'singlefile.txt'
    singlefile_text.write_text('the contents')

    assert lib.get_primary_file([singlefile, singlefile_text]) == singlefile

    assert lib.get_primary_file([example_epub, example_mobi]) == example_epub
    assert lib.get_primary_file([example_mobi, example_epub]) == example_epub

    assert lib.get_primary_file([example_pdf, example_mobi]) == example_pdf
    assert lib.get_primary_file([example_pdf, example_mobi, example_epub]) == example_epub

    # No primary file in this group.
    foo, bar = make_files_structure({'foo': 'text', 'bar': None})
    with pytest.raises(NoPrimaryFile):
        assert lib.get_primary_file([foo, bar])


def test_get_refresh_progress(test_client, test_session):
    request, response = test_client.get('/api/files/refresh_progress')
    assert response.status_code == HTTPStatus.OK
    assert 'progress' in response.json
    progress = response.json['progress']
    assert 'cleanup' in progress
    assert 'discovery' in progress
    assert 'indexed' in progress
    assert 'indexing' in progress
    assert 'modeled' in progress
    assert 'modeling' in progress
    assert 'refreshing' in progress
    assert 'counted_files' in progress
    assert 'total_file_groups' in progress
    assert 'unindexed' in progress


@pytest.mark.asyncio
async def test_refresh_files_no_groups(test_session, test_directory, make_files_structure, zip_file_factory):
    """Files that share a name, but cannot be grouped into a FileGroup have their own FileGroups."""
    foo_txt, foo_zip = make_files_structure({
        'foo.txt': 'text',
        'foo.zip': zip_file_factory(),
    })
    assert foo_txt.stat().st_size and foo_zip.stat().st_size

    await lib.refresh_files()

    # Two distinct FileGroups.
    assert test_session.query(FileGroup).count() == 2
    txt, zip_ = test_session.query(FileGroup)
    assert txt.primary_path == foo_txt and txt.size == foo_txt.stat().st_size
    assert zip_.primary_path == foo_zip and zip_.size == foo_zip.stat().st_size


@pytest.mark.asyncio
async def test_refresh_directories(test_session, test_directory, assert_directories):
    """
    Directories are stored when they are discovered.  They are removed when they can no longer be found.
    """
    foo = test_directory / 'foo'
    bar = test_directory / 'bar'
    baz = test_directory / 'baz'
    foo.mkdir()
    bar.mkdir()
    baz.mkdir()

    await lib.refresh_files()
    assert_directories({'foo', 'bar', 'baz'})

    # Deleted directory is removed.
    foo.rmdir()
    await lib.refresh_files()
    assert_directories({'bar', 'baz'})

    bar.rmdir()
    await lib.refresh_files([bar])
    assert_directories({'baz', })

    # A new directory can be refreshed directly.
    foo.mkdir()
    await lib.refresh_files([foo])
    assert_directories({'foo', 'baz'})


@pytest.mark.asyncio
async def test_file_group_merge(async_client, test_session, test_directory, make_files_structure, tag_factory,
                                video_bytes, srt_file3):
    """A FileGroup can be created from multiple existing FileGroups.  Any Tags applied to the existing groups will be
    migrated."""
    vid, srt = make_files_structure({
        'vid.mp4': video_bytes,
        'vid.srt': (PROJECT_DIR / 'test/example3.en.srt').read_text(),
    })
    one, two = await tag_factory(), await tag_factory()
    vid_group = FileGroup.from_paths(test_session, vid)
    srt_group = FileGroup.from_paths(test_session, srt)
    test_session.add_all([vid_group, srt_group])
    test_session.flush([vid_group, srt_group])
    vid_tag_file = vid_group.add_tag(one.name, test_session)
    srt_tag_file = srt_group.add_tag(two.name, test_session)
    test_session.flush([vid_tag_file, srt_tag_file])
    tag_file_created_at = vid_tag_file.created_at
    srt_file_created_at = srt_tag_file.created_at
    test_session.commit()

    assert vid_group.mimetype == 'video/mp4'
    assert srt_group.mimetype == 'text/srt'

    # Both FileGroups are merged.
    vid = FileGroup.from_paths(test_session, vid, srt)
    test_session.commit()
    assert {i['path'].name for i in vid.files} == {'vid.mp4', 'vid.srt'}

    assert test_session.query(FileGroup).count() == 1
    assert set(vid.tag_names) == {'one', 'two'}
    assert {i['path'].name for i in vid.files} == {'vid.mp4', 'vid.srt'}
    # TagFile.created_at is preserved.
    assert [i for i in vid.tag_files if i.tag.name == 'one'][0].created_at == tag_file_created_at
    assert [i for i in vid.tag_files if i.tag.name == 'two'][0].created_at == srt_file_created_at
    # Size is combined
    assert vid.size > len(video_bytes)
    assert vid.mimetype == 'video/mp4'


@pytest.mark.asyncio
async def test_move(async_client, test_session, test_directory, make_files_structure, video_bytes,
                    singlefile_contents_factory):
    """files.lib.move behaves likes posix mv"""
    make_files_structure({
        'foo/bar/video.mp4': video_bytes,
        'foo/bar/baz/archive.html': (singlefile_text := singlefile_contents_factory()),
        'foo/bytes.txt': b'text',
        'foo/text.txt': 'text',
    })
    foo = test_directory / 'foo'
    qux = test_directory / 'qux'
    await lib.refresh_files()

    # mv foo qux
    plan = await lib.move(qux, foo, session=test_session)
    plan = [(str(i.relative_to(test_directory)), str(j.relative_to(test_directory))) for i, j in plan.items()]
    # The deepest files are moved first.
    assert plan == [('foo/bar/baz/archive.html', 'qux/foo/bar/baz/archive.html'),
                    ('foo/bar/video.mp4', 'qux/foo/bar/video.mp4'),
                    ('foo/bar/baz', 'qux/foo/bar/baz'),
                    ('foo/text.txt', 'qux/foo/text.txt'),
                    ('foo/bytes.txt', 'qux/foo/bytes.txt'),
                    ('foo/bar', 'qux/foo/bar'),
                    ]
    # Files were moved.
    assert (qux / 'foo/bar/video.mp4').is_file() and (qux / 'foo/bar/video.mp4').read_bytes() == video_bytes
    assert (qux / 'foo/bar/baz/archive.html').is_file() \
           and (qux / 'foo/bar/baz/archive.html').read_text() == singlefile_text
    assert (qux / 'foo/bytes.txt').is_file() and (qux / 'foo/bytes.txt').read_bytes() == b'text'
    assert (qux / 'foo/text.txt').is_file() and (qux / 'foo/text.txt').read_text() == 'text'
    # Directories were moved.
    assert not foo.exists()


@pytest.mark.asyncio
async def test_move_files(async_client, test_session, test_directory, make_files_structure):
    """Files can be moved using files.lib.move."""
    one, two = make_files_structure({
        'foo/one.txt': 'one',
        'two.txt': 'two',
    })
    dest = test_directory / 'dest'

    plan = await lib.move(dest, one, two, session=test_session)
    assert list(plan.items()) == [
        (test_directory / 'foo/one.txt', test_directory / 'dest/one.txt'),
        (test_directory / 'two.txt', test_directory / 'dest/two.txt'),
    ]
    # one.txt is moved out of foo.
    assert not (test_directory / 'foo/one.txt').exists(), 'one.txt is lingering in source'
    assert not (test_directory / 'two.txt').exists(), 'two.txt is lingering in source'
    assert (dest / 'one.txt').read_text() == 'one', 'one.txt was not moved to destination'
    assert (dest / 'two.txt').read_text() == 'two', 'two.txt was not moved to destination'


@pytest.mark.asyncio
async def test_move_deep_directory(async_client, test_session, test_directory, make_files_structure):
    """Moving files/directories from one deep directory to another is supported."""
    baz, foo, quuz_mp4, quuz_txt, quux = make_files_structure({
        'foo/foo.txt': 'foo',
        'foo/bar/baz.txt': 'baz',
        'foo/qux/quux.txt': 'quux',
        'foo/quuz.txt': 'quuz text',  # this text file will be moved when it's MP4 is moved.
        'foo/quuz.mp4': 'quuz mp4',
    })
    assert foo.name == 'foo.txt' \
           and baz.name == 'baz.txt' \
           and quux.name == 'quux.txt' \
           and quuz_mp4.name == 'quuz.mp4' \
           and quuz_txt.name == 'quuz.txt', \
        'Test directory was not initiated correctly.'
    bar, qux = baz.parent, quux.parent
    dest = test_directory / 'deep/dest'

    # mv foo/bar foo/qux foo/quuz.mp4 foo/quuz.txt deep/dest
    plan = await lib.move(dest, bar, qux, quuz_mp4, quuz_txt, session=test_session)
    assert list(plan.items()) == [
        (test_directory / 'foo/qux/quux.txt', test_directory / 'deep/dest/qux/quux.txt'),
        (test_directory / 'foo/bar/baz.txt', test_directory / 'deep/dest/bar/baz.txt'),
        (test_directory / 'foo/quuz.txt', test_directory / 'deep/dest/quuz.txt'),
        (test_directory / 'foo/quuz.mp4', test_directory / 'deep/dest/quuz.mp4'),
    ]

    # Unrelated files and directories are untouched.
    assert not (test_directory / 'deep/dest/foo').is_dir(), 'foo/ should not have been moved.'
    assert (test_directory / 'foo').is_dir(), 'foo/ should not be deleted.'
    assert (test_directory / 'foo/foo.txt').read_text() == 'foo', 'foo.txt should not be moved.'

    # Files are moved, preserving the name of their directory.
    assert (test_directory / 'deep/dest/bar').is_dir(), 'foo/bar/ was not moved'
    assert (test_directory / 'deep/dest/bar/baz.txt').is_file(), 'foo/bar/baz.txt was not moved'
    assert (test_directory / 'deep/dest/bar/baz.txt').read_text() == 'baz', 'foo/bar/baz.txt has wrong contents.'
    assert (test_directory / 'deep/dest/qux/quux.txt').read_text() == 'quux', 'quux.txt has the wrong contents'
    assert (test_directory / 'deep/dest/quuz.txt').read_text() == 'quuz text', 'quuz.txt has the wrong contents'
    assert (test_directory / 'deep/dest/quuz.mp4').read_text() == 'quuz mp4', 'quuz.mp4 has the wrong contents'

    # Old directory was removed.
    assert not (test_directory / 'foo/bar').is_dir(), 'bar directory was not moved'


@pytest.mark.asyncio
async def test_move_directory(async_client, test_session, test_directory, make_files_structure,
                              assert_directories):
    """A Directory record is deleted when it's directory is deleted."""
    make_files_structure({
        'foo/one.txt': 'one',
    })
    await lib.refresh_files()
    assert_directories({'foo'})

    bar = test_directory / 'bar'
    await lib.rename(test_directory / 'foo', 'bar', session=test_session)
    assert (bar / 'one.txt').read_text() == 'one'
    assert_directories({'bar'})


count = 0


@pytest.mark.asyncio
async def test_move_error(test_session, test_directory, make_files_structure, video_bytes, singlefile_contents_factory):
    """Files are restored when a move fails."""
    make_files_structure({
        'foo/bar/video.mp4': video_bytes,
        'foo/bar/baz/archive.html': (singlefile_text := singlefile_contents_factory()),
        'foo/bytes.txt': b'text',
        'foo/text.txt': 'text',
    })
    foo = test_directory / 'foo'
    qux = test_directory / 'qux'

    def mock_shutil_move(*args, **kwargs):
        # Mock the `shutil.move` with this function which will unexpectedly fail on the 3rd call.
        global count
        count += 1
        if count == 3:
            raise FileNotFoundError('fake file move failure')
        return shutil.move(*args, **kwargs)

    with mock.patch('wrolpi.files.lib.shutil.move', mock_shutil_move), pytest.raises(FileNotFoundError):
        await lib.move(qux, foo, session=test_session)
    # The move failed, the files should be moved back.
    # foo was not deleted.
    assert foo.is_dir()
    assert (foo / 'bar/baz/archive.html').is_file() and (foo / 'bar/baz/archive.html').read_text() == singlefile_text
    assert (foo / 'bar/video.mp4').is_file() and (foo / 'bar/video.mp4').read_bytes() == video_bytes
    assert (foo / 'bytes.txt').is_file() and (foo / 'bytes.txt').read_bytes() == b'text'
    assert (foo / 'text.txt').is_file() and (foo / 'text.txt').read_text() == 'text'
    # Destination did not exist on move, so it was deleted.
    assert not qux.exists()


@pytest.mark.asyncio
async def test_file_group_move(async_client, test_session, make_files_structure, test_directory, video_bytes,
                               srt_text):
    """Test FileGroup's move method"""
    video, srt = make_files_structure({
        'video.mp4': video_bytes,
        'video.srt': srt_text,
    })
    await lib.refresh_files()
    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.indexed is True

    (test_directory / 'foo').mkdir()
    new_path = test_directory / 'foo/video.mp4'
    file_group.move(new_path)

    new_srt = new_path.with_suffix('.srt')
    assert new_path.read_bytes() == video_bytes
    assert new_srt.read_text() == srt_text
    assert not video.is_file()
    assert not srt.is_file()


@pytest.mark.asyncio
async def test_move_tagged(async_client, test_session, test_directory, make_files_structure, tag_factory):
    """A FileGroup's tag is preserved when moved or renamed."""
    tag = await tag_factory()
    foo, bar, = make_files_structure({
        'foo/foo.txt': 'foo',
        'foo/bar.txt': 'bar',
    })
    await lib.refresh_files()
    bar_file_group, foo_file_group = test_session.query(FileGroup).order_by(FileGroup.primary_path)
    bar_file_group.title = 'custom title'  # Should not be overwritten.
    bar_file_group.add_tag(tag.id)
    test_session.commit()

    qux = test_directory / 'qux'
    qux.mkdir()

    # Move both files into qux.  The Tag should also be moved.
    await lib.move(qux, bar, foo, session=test_session)
    new_foo = qux / 'foo.txt'
    new_bar = qux / 'bar.txt'
    # Files were moved.
    assert new_foo.read_text() == 'foo'
    assert new_bar.read_text() == 'bar'
    assert (test_directory / 'foo').is_dir()
    assert not (test_directory / 'foo/foo.txt').exists()
    assert not (test_directory / 'foo/bar.txt').exists()
    # Tag was moved.
    bar_file_group, foo_file_group = test_session.query(FileGroup).order_by(FileGroup.primary_path)
    assert bar_file_group.primary_path == new_bar == bar_file_group.files[0]['path']
    assert bar_file_group.primary_path.is_file()
    assert bar_file_group.tag_files
    # foo.txt was not tagged, but was moved.
    assert not foo_file_group.tag_files
    assert foo_file_group.primary_path.is_file()
    assert foo_file_group.primary_path == new_foo == foo_file_group.files[0]['path']
    assert bar_file_group.title == 'custom title', 'Custom title should not have been overwritten.'

    # Rename "bar.txt" to "baz.txt"
    await lib.rename(new_bar, 'baz.txt', session=test_session)
    baz = new_bar.with_name('baz.txt')
    assert baz.read_text() == 'bar'


@pytest.mark.asyncio
async def test_html_index(async_client, test_session, test_directory, make_files_structure):
    make_files_structure({
        'archive.html': '''<html>
        <title>The Title</title>

        <style>
        body {
            color: red;
        }
        </style>

        <script class="sf-hidden" type="application/ld+json">
         {"@context":"http://schema.org", "@type":"NewsArticle",
          "datePublished":"2022-09-27T00:40:19.000Z", "dateModified":"2022-09-27T13:43:47.971Z",
          "author":{"@type":"Person", "name":"BOBBY", "jobTitle":""},
          "creator":{"@type":"Person", "name":"OTHER BOBBY", "jobTitle":""},
          "description": "The article description"}
        </script>

        <body>
        <h1>Some Header</h1>
        <p>Some Text</p>

        <span>Span Text</span>

        Outside element.
        </body>

        </html>
        '''
    })

    await lib.refresh_files()

    assert test_session.query(FileGroup).count() == 1, 'Too many files were refreshed.'
    archive_file: FileGroup = test_session.query(FileGroup).one()
    assert archive_file.a_text == 'The Title'
    assert archive_file.b_text == 'archive html'
    assert archive_file.c_text == 'The article description'
    assert archive_file.d_text == '''Some Header
Some Text
Span Text
Outside element.'''


@pytest.mark.asyncio
async def test_doc_indexer(async_client, test_session, example_doc):
    """The contents of a Microsoft doc files can be indexed."""
    await lib.refresh_files()
    assert test_session.query(FileGroup).count() == 1
    doc = test_session.query(FileGroup).one()
    assert doc.title == 'example word.doc'
    assert doc.a_text == 'example word doc'
    if IS_MACOS:
        assert doc.d_text == 'Example Word Document\nSecond page'
    else:
        assert doc.d_text == 'Example Word Document\n\nSecond page\n'


@pytest.mark.asyncio
async def test_docx_indexer(async_client, test_session, example_docx):
    """The contents of a Microsoft docx files can be indexed."""
    await lib.refresh_files()
    assert test_session.query(FileGroup).count() == 1
    doc = test_session.query(FileGroup).one()
    assert doc.title == 'example word.docx'
    assert doc.a_text == 'example word docx'
    assert doc.d_text == 'Example Word Document Second page'


@pytest.mark.asyncio
async def test_file_search_date_range(async_client, test_session, example_pdf, example_doc):
    """Test searching FileGroups by their published datetime."""
    await lib.refresh_files()
    doc, pdf = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()

    files, total = lib.search_files('', 10, 0)
    assert total == 2, 'Should only be 2 files.'

    # PDF was published in December.
    files, total = lib.search_files('', 10, 0, months=[12, ])
    assert total == 1, 'Only PDF should be from December 2022'
    assert files[0]['id'] == pdf.id

    # PDF was published in 2022.
    files, total = lib.search_files('', 10, 0, from_year=2022, to_year=2022)
    assert total == 1, 'Only PDF should be from December 2022'
    assert files[0]['id'] == pdf.id

    # PDF was NOT published in 2023.
    files, total = lib.search_files('', 10, 0, from_year=2023)
    assert total == 0, 'No example files are published in 2023'

    files, total = lib.search_files('', 10, 0, to_year=2022)
    assert total == 1
    assert files[0]['id'] == pdf.id


def test_replace_file(test_directory):
    file = test_directory / 'foo.txt'
    file.write_text('old contents')
    assert file.read_text() == 'old contents'

    wrolpi.common.replace_file(file, 'new contents')
    assert file.read_text() == 'new contents'
    assert not (test_directory / 'foo.txt.tmp').exists()

    wrolpi.common.replace_file(file, b'new bytes')
    assert file.read_bytes() == b'new bytes'
    assert not (test_directory / 'foo.txt.tmp').exists()

    # Default behavior is to refuse to replace a non-existent file.
    with pytest.raises(FileNotFoundError):
        wrolpi.common.replace_file('does not exist', 'foo')

    # Non-existent file can be created.
    wrolpi.common.replace_file(test_directory / 'will now exist', 'foo', missing_ok=True)


@pytest.mark.asyncio
async def test_upsert_file_video_with_channel(async_client, test_session, test_directory, video_bytes,
                                              channel_factory, video_factory):
    """A video file that is uploaded should be assigned to a Channel if it is in the Channel's directory."""
    channel = channel_factory()
    # Put the video file in the Channel's directory.
    video_file: pathlib.Path = channel.directory / 'video.mp4'
    video_file.write_bytes(video_bytes)
    # Put an info json file next to the video file.
    info_json_file = video_file.with_suffix('.info.json')
    info_json_file.write_text(json.dumps({'duration': 5}))

    # Upsert the file, it should be modeled.
    fg: FileGroup = await lib.upsert_file(video_file)
    assert fg.model == 'video', 'Upserted file should have been modeled.'
    assert fg.my_video_files(), 'Video file was upserted.'
    assert fg.my_json_files(), 'Info json file should have been found near video file.'

    # The video is in the correct Channel and has its files.
    video: Video = test_session.query(Video).one()
    assert video.channel_id == channel.id, "Videos should be assigned to the Channel their files are in"
    assert video.video_path, 'Video file was upserted'
    assert video.info_json_path, 'Info json file not found near video file.'


@pytest.mark.asyncio
async def test_move_many_files(async_client, test_session, test_directory, make_files_structure):
    make_files_structure([f'foo/{i}.txt' for i in range(10_000)])
    await lib.refresh_files()

    foo = test_directory / 'foo'
    bar = test_directory / 'bar'

    with timer('test_move_many_files'):
        # mv foo bar
        await lib.move(bar, foo, session=test_session)

    assert not foo.is_dir()
    assert bar.is_dir()
    assert (bar / 'foo').is_dir()
    assert (bar / 'foo/0.txt').is_file()


@only_macos
def test_get_real_path_name(test_directory):
    (test_directory / 'foo.txt').touch()
    assert (test_directory / 'foo.txt').exists()
    assert lib.get_real_path_name(test_directory / 'foo.txt') == test_directory / 'foo.txt'

    assert (test_directory / 'FOO.TXT').exists()
    assert lib.get_real_path_name(test_directory / 'FOO.txt') == test_directory / 'foo.txt'
