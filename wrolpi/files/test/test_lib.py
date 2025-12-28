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
from wrolpi.files.worker import file_worker
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
    foo1_fg.add_tag(test_session, tag.id)
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
    await file_worker.run_queue_to_completion()
    # Both files end up in a group.
    bar = test_session.query(FileGroup).one()
    bar.add_tag(test_session, tag.id)
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

    await file_worker.run_queue_to_completion()
    assert_file_groups([
        {'primary_path': 'foo.txt', 'indexed': True},
        {'primary_path': 'bar.txt', 'indexed': True},
        {'primary_path': 'baz.txt', 'indexed': True}])

    baz.unlink()

    await file_worker.run_queue_to_completion()
    assert_file_groups([{'primary_path': 'foo.txt', 'indexed': True}, {'primary_path': 'bar.txt', 'indexed': True}])

    foo.unlink()

    await file_worker.run_queue_to_completion()
    assert_file_groups([{'primary_path': 'bar.txt', 'indexed': True}])


@pytest.mark.asyncio
async def test_file_group_location(async_client, test_session, make_files_structure):
    """FileGroup can return the URL necessary to preview the FileGroup."""
    make_files_structure({
        'foo/one.txt': 'one',
        'two.txt': 'two',
    })
    await file_worker.run_queue_to_completion()

    one, two = test_session.query(FileGroup).order_by(FileGroup.primary_path).all()
    assert one.location == '/files?folders=foo&preview=foo%2Fone.txt'
    assert two.location == '/files?preview=two.txt'


@pytest.mark.asyncio
async def test_refresh_bogus_files(async_client, test_session, make_files_structure, test_directory,
                                   assert_file_groups, insert_file_group):
    """Bogus files are removed during a refresh."""
    make_files_structure(['does exist.txt'])
    await file_worker.run_queue_to_completion()
    insert_file_group([test_directory / 'does not exist.txt'])
    test_session.commit()

    # Bogus file was inserted.
    assert_file_groups([
        {'primary_path': 'does exist.txt', 'indexed': True},
        {'primary_path': 'does not exist.txt', 'indexed': True},
    ])

    await file_worker.run_queue_to_completion()

    assert test_session.query(FileGroup).count() == 1, 'Bogus file was not removed'
    assert_file_groups([{'primary_path': 'does exist.txt', 'indexed': True}])


@pytest.mark.asyncio
async def test_refresh_empty_media_directory(async_client, test_session, test_directory):
    """refresh_paths will refuse to refresh with an empty media directory."""
    with pytest.raises(UnknownDirectory):
        await file_worker.run_queue_to_completion()


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
    # Note: files now store relative filenames only (not absolute paths)
    # Two-phase indexing: indexed=True (surface), deep_indexed=False (needs modeler)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [
             {'path': srt_file3.name, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file.name, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': bar.name, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}]
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': baz.name, 'size': 8, 'suffix': '.txt', 'mimetype': 'text/plain'}]
         },
    ])

    # Modified files should be re-indexed (deep_indexed reset to False).
    bar.touch()
    baz.write_text('new baz')
    # Simulate that the video was deep indexed, it should not be re-indexed because it was not modified.
    video_fg = test_session.query(FileGroup).filter_by(primary_path=video_file).one()
    video_fg.deep_indexed = True
    test_session.commit()
    assert_file_groups(
        [{'primary_path': str(video_file), 'idempotency': idempotency,
          'indexed': True, 'deep_indexed': True}],
        assert_count=False)

    # Only modified files need to be re-indexed (deep_indexed reset).
    lib._upsert_files([video_file, srt_file3, bar, baz], idempotency)
    # Note: files now store relative filenames only (not absolute paths)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': True,
         'files': [
             {'path': srt_file3.name, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file.name, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': bar.name, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}],
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': baz.name, 'size': 7, 'suffix': '.txt', 'mimetype': 'text/plain'}],
         },
    ])

    # Deleting SRT removes it from the video.
    srt_file3.unlink()
    lib._upsert_files([video_file, bar, baz], idempotency)
    # Expire session cache to get fresh data after raw SQL update.
    test_session.expire_all()
    video_file_group: FileGroup = test_session.query(FileGroup).filter_by(primary_path=str(video_file)).one()
    assert len(video_file_group.files) == 1, 'SRT file was not removed from files'
    # Note: files now store relative filenames only (not absolute paths)
    assert_file_groups([
        # Video deep_indexed is reset because SRT was removed (files changed).
        {'primary_path': video_file, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': video_file.name, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'}]},
        {'primary_path': bar, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': bar.name, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}],
         },
        {'primary_path': baz, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False,
         'files': [{'path': baz.name, 'size': 7, 'suffix': '.txt', 'mimetype': 'text/plain'}],
         },
    ])


def test_same_stem_files_in_separate_batches_creates_orphans(test_session, test_directory, video_bytes):
    """
    BUG DEMONSTRATION: When files with the same stem are processed in
    separate calls to _upsert_files, they create separate FileGroups
    instead of being grouped together.

    This replicates the real-world issue where video thumbnails (.webp)
    are not associated with their video (.mp4) FileGroups.
    """
    # Create files with the same stem
    video_path = test_directory / 'my_video.mp4'
    poster_path = test_directory / 'my_video.webp'

    video_path.write_bytes(video_bytes)
    poster_path.write_bytes(b'RIFF\x00\x00\x00\x00WEBP')  # Minimal webp

    idempotency = now()

    # Simulate batch 1: only video file
    lib._upsert_files([video_path], idempotency)

    # Simulate batch 2: only poster file (processed separately, simulating batch split)
    lib._upsert_files([poster_path], idempotency)

    # BUG: This creates 2 FileGroups instead of 1
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).filter(
        FileGroup.directory == str(test_directory)
    ).all()

    # This assertion demonstrates the bug - we expect 1 but get 2
    assert len(file_groups) == 2, \
        f"BUG DEMO: Expected 2 orphaned FileGroups (the bug), got {len(file_groups)}"

    # The video FileGroup only has the video, not the poster
    video_fg = next(fg for fg in file_groups if fg.mimetype == 'video/mp4')
    assert len(video_fg.files) == 1, "Video FileGroup should only have 1 file (the bug)"
    assert video_fg.files[0]['mimetype'] == 'video/mp4'

    # The poster is in its own FileGroup (orphaned)
    poster_fg = next(fg for fg in file_groups if fg.mimetype == 'image/webp')
    assert len(poster_fg.files) == 1, "Poster FileGroup should only have 1 file"


@pytest.mark.asyncio
async def test_subsequent_refresh_merges_orphaned_file_groups(async_client, test_session, test_directory, video_bytes):
    """
    Demonstrates that a global refresh will correctly merge orphaned FileGroups
    that share the same stem.

    This simulates the real-world scenario where orphaned FileGroups were
    created (e.g., due to files being processed in separate batches before
    the batch expansion fix), and shows that a global refresh fixes the issue.
    """
    # Create files with the same stem
    video_path = test_directory / 'my_video.mp4'
    poster_path = test_directory / 'my_video.webp'

    video_path.write_bytes(video_bytes)
    poster_path.write_bytes(b'RIFF\x00\x00\x00\x00WEBP')

    idempotency1 = now()

    # Simulate orphaned state: files processed in separate batches (the bug scenario)
    # This represents data from before the batch expansion fix was applied
    lib._upsert_files([video_path], idempotency1)
    lib._upsert_files([poster_path], idempotency1)

    # Verify orphan state: 2 separate FileGroups
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).filter(
        FileGroup.directory == str(test_directory)
    ).all()
    assert len(file_groups) == 2, "Setup: Should have 2 orphaned FileGroups"

    # Global refresh should merge the orphaned FileGroups
    await file_worker.run_queue_to_completion()

    # After global refresh, should be merged into 1 FileGroup
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).filter(
        FileGroup.directory == str(test_directory)
    ).all()

    assert len(file_groups) == 1, \
        f"After global refresh, expected 1 FileGroup, got {len(file_groups)}"

    fg = file_groups[0]
    assert fg.mimetype == 'video/mp4', "Primary should be video"
    assert len(fg.files) == 2, f"Should have 2 files, got {len(fg.files)}"


@pytest.mark.asyncio
async def test_upsert_mtime_resets_deep_indexed(test_session, make_files_structure, test_directory, assert_file_groups):
    """Test that touching a file (mtime change only) resets deep_indexed."""
    import time
    foo, = make_files_structure(['foo.txt'])

    # Initial upsert - file is surface indexed, not deep indexed.
    idempotency = now()
    lib._upsert_files([foo], idempotency)
    assert_file_groups([
        {'primary_path': foo, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False},
    ])

    # Simulate that the file was deep indexed.
    foo_fg = test_session.query(FileGroup).filter_by(primary_path=foo).one()
    foo_fg.deep_indexed = True
    test_session.commit()
    assert_file_groups([
        {'primary_path': foo, 'indexed': True, 'deep_indexed': True},
    ], assert_count=False)

    # Touch the file to change mtime only (size stays the same).
    time.sleep(0.01)  # Ensure mtime changes
    foo.touch()

    # Re-upsert - deep_indexed should be reset because mtime changed.
    lib._upsert_files([foo], idempotency)
    test_session.expire_all()
    assert_file_groups([
        {'primary_path': foo, 'idempotency': idempotency, 'indexed': True, 'deep_indexed': False},
    ])


@pytest.mark.asyncio
async def test_refresh_paths(async_client, test_session, make_files_structure, test_directory, assert_files,
                             assert_file_groups):
    """Test that refresh_files() handles specific paths correctly."""
    foo, bar, baz = make_files_structure(['dir1/foo.txt', 'dir1/bar.txt', 'baz.txt'])
    dir1 = foo.parent

    # `refresh_files` refreshes recursively from a directory.
    await file_worker.run_queue_to_completion([foo.parent, ])
    assert_files([
        {'path': 'dir1/foo.txt'},
        {'path': 'dir1/bar.txt'},
    ])

    # `refresh_files` discovers files at the top of the media directory.
    await file_worker.run_queue_to_completion([test_directory, ])
    assert_files([
        {'path': 'dir1/foo.txt'},
        {'path': 'dir1/bar.txt'},
        {'path': 'baz.txt'},
    ])

    # Records for deleted files are deleted.  Request a refresh of `dir1` so we indirectly refresh `foo`.
    foo.unlink()
    await file_worker.run_queue_to_completion([dir1, ])
    assert_files([
        {'path': 'dir1/bar.txt'},
        {'path': 'baz.txt'},
    ])

    # Records for all children of a directory are deleted.
    bar.unlink()
    dir1.rmdir()
    await file_worker.run_queue_to_completion([dir1, ])
    assert_files([
        {'path': 'baz.txt'},
    ])


@pytest.mark.asyncio
async def test_refresh_files_groups(async_client, test_session, make_files_structure, test_directory, video_bytes):
    """Test that files with shared stems are grouped into FileGroups."""
    make_files_structure({'dir1/foo.mp4': video_bytes, 'dir1/foo.info.json': 'hello', 'baz.txt': 'hello'})
    await file_worker.run_queue_to_completion([test_directory, ])

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
    # Full pipeline: both surface and deep indexed
    assert baz.indexed is True
    assert baz.deep_indexed is True


@pytest.mark.asyncio
async def test_file_group_tag(test_session, make_files_structure, test_directory, tag_factory, await_switches):
    """A FileGroup can be tagged."""
    make_files_structure(['foo.mp4'])
    await file_worker.run_queue_to_completion([test_directory, ])
    one = await tag_factory()

    foo: FileGroup = test_session.query(FileGroup).one()
    foo.add_tag(test_session, one.id)
    test_session.commit()

    tag_file2: TagFile = test_session.query(TagFile).one()
    assert tag_file2 and tag_file2.file_group == foo


@pytest.mark.asyncio
async def test_refresh_a_text_no_indexer(async_client, test_session, make_files_structure):
    """File.a_text is filled even if the file does not match an Indexer."""
    make_files_structure(['foo', 'bar-bar'])

    await file_worker.run_queue_to_completion()

    files = {i.a_text for i in test_session.query(FileGroup)}
    assert files == {'bar bar bar-bar', 'foo'}


@pytest.mark.asyncio
async def test_refresh_many_files(async_client, test_session, make_files_structure):
    """Used to profile file refreshing"""
    file_count = 10_000
    make_files_structure([f'{uuid4()}.txt' for _ in range(file_count)])
    with timer('first refresh'):
        await file_worker.run_queue_to_completion()
    assert test_session.query(FileGroup).count() == file_count

    with timer('second refresh'):
        await file_worker.run_queue_to_completion()
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

    task = asyncio.create_task(file_worker.run_queue_to_completion())
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

    await file_worker.run_queue_to_completion()
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
        await file_worker.run_queue_to_completion()

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
        await file_worker.run_queue_to_completion()

    # Change the contents, the file should be re-indexed.
    text_path.write_text('new text contents')
    await file_worker.run_queue_to_completion()
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
    await file_worker.run_queue_to_completion()
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


@pytest.mark.asyncio
async def test_get_refresh_progress(async_client, test_session):
    request, response = await async_client.get('/api/files/refresh_progress')
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
async def test_refresh_files_no_groups(async_client, test_session, test_directory, make_files_structure, zip_file_factory):
    """Files that share a name, but cannot be grouped into a FileGroup have their own FileGroups."""
    foo_txt, foo_zip = make_files_structure({
        'foo.txt': 'text',
        'foo.zip': zip_file_factory(),
    })
    assert foo_txt.stat().st_size and foo_zip.stat().st_size

    await file_worker.run_queue_to_completion()

    # Two distinct FileGroups.
    assert test_session.query(FileGroup).count() == 2
    txt, zip_ = test_session.query(FileGroup)
    assert txt.primary_path == foo_txt and txt.size == foo_txt.stat().st_size
    assert zip_.primary_path == foo_zip and zip_.size == foo_zip.stat().st_size


@pytest.mark.asyncio
async def test_refresh_directories(test_session, test_directory, assert_directories, await_switches):
    """
    Directories are stored when they are discovered.  They are removed when they can no longer be found.
    """
    foo = test_directory / 'foo'
    bar = test_directory / 'bar'
    baz = test_directory / 'baz'
    foo.mkdir()
    bar.mkdir()
    baz.mkdir()

    await file_worker.run_queue_to_completion()
    assert_directories({'foo', 'bar', 'baz'})

    # Deleted directory is removed.
    foo.rmdir()
    await file_worker.run_queue_to_completion()
    assert_directories({'bar', 'baz'})

    bar.rmdir()
    await file_worker.run_queue_to_completion([bar])
    assert_directories({'baz', })

    # A new directory can be refreshed directly.
    foo.mkdir()
    await file_worker.run_queue_to_completion([foo])
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
    vid_tag_file = vid_group.add_tag(test_session, one.name)
    srt_tag_file = srt_group.add_tag(test_session, two.name)
    test_session.flush([vid_tag_file, srt_tag_file])
    tag_file_created_at = vid_tag_file.created_at
    srt_file_created_at = srt_tag_file.created_at
    test_session.commit()

    assert vid_group.mimetype == 'video/mp4'
    assert srt_group.mimetype == 'text/srt'

    # Both FileGroups are merged.
    vid = FileGroup.from_paths(test_session, vid, srt)
    test_session.commit()
    # files now stores relative filenames as strings, use my_files() to get resolved Paths
    assert {i['path'].name for i in vid.my_files()} == {'vid.mp4', 'vid.srt'}

    assert test_session.query(FileGroup).count() == 1
    assert set(vid.tag_names) == {'one', 'two'}
    assert {i['path'].name for i in vid.my_files()} == {'vid.mp4', 'vid.srt'}
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
    await file_worker.run_queue_to_completion()

    # mv foo qux
    plan = await lib.move(test_session, qux, foo)
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

    plan = await lib.move(test_session, dest, one, two)
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
    plan = await lib.move(test_session, dest, bar, qux, quuz_mp4, quuz_txt)
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
    await file_worker.run_queue_to_completion()
    assert_directories({'foo'})

    bar = test_directory / 'bar'
    await lib.rename(test_session, test_directory / 'foo', 'bar')
    assert (bar / 'one.txt').read_text() == 'one'
    assert_directories({'bar'})


count = 0


@pytest.mark.asyncio
async def test_move_error(async_client, test_session, test_directory, make_files_structure, video_bytes,
                          singlefile_contents_factory):
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
        await lib.move(test_session, qux, foo)
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
async def test_physically_moved_file_creates_duplicate_filegroup(async_client, test_session, test_directory,
                                                                  make_files_structure):
    """
    BUG: When files are physically moved (outside WROLPi) but the DB isn't updated,
    subsequent operations create duplicate FileGroups instead of updating existing ones.

    This happens because FileGroup.from_paths queries by exact primary_path, not by filename.
    """
    # Create a file and its FileGroup at location A
    make_files_structure({'dir_a/video.mp4': b'video content'})
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    await file_worker.run_queue_to_completion()

    # Verify one FileGroup exists at dir_a
    file_groups_before = test_session.query(FileGroup).all()
    assert len(file_groups_before) == 1
    original_fg = file_groups_before[0]
    original_fg_id = original_fg.id
    assert original_fg.directory == dir_a
    assert original_fg.primary_path == dir_a / 'video.mp4'

    # Physically move the file to dir_b (simulating failed move or manual move)
    shutil.move(dir_a / 'video.mp4', dir_b / 'video.mp4')
    assert not (dir_a / 'video.mp4').exists()
    assert (dir_b / 'video.mp4').exists()

    # Now call from_paths on the new location - this simulates what happens during refresh
    # BUG: This creates a NEW FileGroup instead of updating the existing one
    new_fg = FileGroup.from_paths(test_session, dir_b / 'video.mp4')
    test_session.flush()

    # Check the result
    all_file_groups = test_session.query(FileGroup).all()

    # BUG DEMONSTRATION: We now have 2 FileGroups for the same logical file!
    # The original one still points to dir_a (orphaned - no physical file)
    # The new one points to dir_b (where the file actually is)
    assert len(all_file_groups) == 2, \
        f"Expected 2 FileGroups (bug: duplicate created), got {len(all_file_groups)}"

    # Verify we have one at each location
    dirs = {fg.directory for fg in all_file_groups}
    assert dirs == {dir_a, dir_b}, f"Expected FileGroups at both dirs, got {dirs}"

    # The original FileGroup is now orphaned (points to non-existent file)
    original_fg = test_session.query(FileGroup).filter(FileGroup.id == original_fg_id).one()
    assert not original_fg.primary_path.exists(), "Original FileGroup should point to non-existent file"

    # EXPECTED BEHAVIOR (when bug is fixed):
    # - Only 1 FileGroup should exist
    # - It should be updated to point to the new location (dir_b)
    # - The test assertions above will fail once the bug is fixed


@pytest.mark.asyncio
async def test_move_handles_orphaned_filegroup_conflict(async_client, test_session, test_directory,
                                                         make_files_structure):
    """
    When moving files to a location that has orphaned FileGroups, the move should succeed
    by proactively deleting unindexed orphans before the DB update.

    Orphaned FileGroups have indexed=False because they point to non-existent files.
    The move operation detects these conflicts and deletes them before updating paths.
    """
    # Create a file and its FileGroup at location A
    make_files_structure({'dir_a/video.mp4': b'video content'})
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    await file_worker.run_queue_to_completion()

    # Verify one FileGroup exists at dir_a
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 1
    original_fg = file_groups[0]
    assert original_fg.directory == dir_a

    # Create an orphaned FileGroup at dir_b (simulating a previous failed move)
    # This orphan has no physical file, no linked model, and is not indexed
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dir_b / 'video.mp4'
    orphan_fg.directory = dir_b
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = False  # Orphans are unindexed (can't index non-existent files)
    test_session.add(orphan_fg)
    test_session.commit()

    # Now we have 2 FileGroups: one real at dir_a, one orphan at dir_b
    assert test_session.query(FileGroup).count() == 2
    orphan_id = orphan_fg.id

    # Try to move from dir_a to dir_b - this would fail with UniqueViolation without the fix
    await lib.move(test_session, dir_b, dir_a / 'video.mp4')

    # Verify the move succeeded
    assert not (dir_a / 'video.mp4').exists(), "File should be moved from dir_a"
    assert (dir_b / 'video.mp4').exists(), "File should be at dir_b"

    # Verify we still have only 1 FileGroup (orphan was deleted, original was updated)
    remaining = test_session.query(FileGroup).all()
    assert len(remaining) == 1, f"Expected 1 FileGroup after move, got {len(remaining)}"

    # The remaining FileGroup should be the original one, now at dir_b
    assert remaining[0].id == original_fg.id
    assert remaining[0].directory == dir_b
    assert remaining[0].primary_path == dir_b / 'video.mp4'

    # The orphan should be deleted
    orphan = test_session.query(FileGroup).filter(FileGroup.id == orphan_id).one_or_none()
    assert orphan is None, "Orphaned FileGroup should have been deleted"


@pytest.mark.asyncio
async def test_move_handles_indexed_orphan_at_target(async_client, test_session, test_directory,
                                                      make_files_structure):
    """
    When target has an indexed FileGroup that is NOT linked to any model (orphan),
    it should be deleted and the move should proceed.
    """
    make_files_structure({'dir_a/video.mp4': b'video content'})
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    await file_worker.run_queue_to_completion()

    original_fg = test_session.query(FileGroup).one()
    assert original_fg.directory == dir_a

    # Create an indexed but orphan FileGroup at target (not linked to Video)
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dir_b / 'video.mp4'
    orphan_fg.directory = dir_b
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = True  # Indexed but not linked to any model
    test_session.add(orphan_fg)
    test_session.commit()

    orphan_id = orphan_fg.id
    assert test_session.query(FileGroup).count() == 2

    # Move should succeed - indexed orphan at target gets deleted
    await lib.move(test_session, dir_b, dir_a / 'video.mp4')

    assert (dir_b / 'video.mp4').exists()
    remaining = test_session.query(FileGroup).all()
    assert len(remaining) == 1
    assert remaining[0].id == original_fg.id
    assert test_session.query(FileGroup).filter(FileGroup.id == orphan_id).one_or_none() is None


@pytest.mark.asyncio
async def test_move_target_linked_source_orphan(async_client, test_session, test_directory,
                                                 make_files_structure):
    """
    When target FileGroup is linked to a Video and source FileGroup is orphan,
    the source orphan should be deleted and DB update skipped (target already correct).
    """
    make_files_structure({'dir_a/video.mp4': b'video content'})
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    await file_worker.run_queue_to_completion()

    source_fg = test_session.query(FileGroup).one()
    source_fg_id = source_fg.id

    # Create target FileGroup at dir_b and link it to a Video
    target_fg = FileGroup()
    target_fg.primary_path = dir_b / 'video.mp4'
    target_fg.directory = dir_b
    target_fg.mimetype = 'video/mp4'
    target_fg.indexed = True
    test_session.add(target_fg)
    test_session.flush()

    video = Video(file_group_id=target_fg.id)
    test_session.add(video)
    test_session.commit()

    target_fg_id = target_fg.id
    assert test_session.query(FileGroup).count() == 2

    # Move files - source orphan deleted, target kept
    await lib.move(test_session, dir_b, dir_a / 'video.mp4')

    # File was moved
    assert (dir_b / 'video.mp4').exists()

    # Source FileGroup (orphan) was deleted
    assert test_session.query(FileGroup).filter(FileGroup.id == source_fg_id).one_or_none() is None

    # Target FileGroup (linked) was kept
    remaining = test_session.query(FileGroup).filter(FileGroup.id == target_fg_id).one_or_none()
    assert remaining is not None, "Linked target FileGroup should be kept"
    assert remaining.primary_path == dir_b / 'video.mp4'


@pytest.mark.asyncio
async def test_move_both_linked_raises_error(async_client, test_session, test_directory,
                                              make_files_structure):
    """
    When both source and target FileGroups are linked to models,
    the move should raise an error (needs manual resolution).
    """
    make_files_structure({'dir_a/video.mp4': b'video content'})
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    await file_worker.run_queue_to_completion()

    source_fg = test_session.query(FileGroup).one()

    # Link source to a Video
    video1 = Video(file_group_id=source_fg.id)
    test_session.add(video1)
    test_session.flush()

    # Create target FileGroup at dir_b and link it to another Video
    target_fg = FileGroup()
    target_fg.primary_path = dir_b / 'video.mp4'
    target_fg.directory = dir_b
    target_fg.mimetype = 'video/mp4'
    target_fg.indexed = True
    test_session.add(target_fg)
    test_session.flush()

    video2 = Video(file_group_id=target_fg.id)
    test_session.add(video2)
    test_session.commit()

    # Move should fail - both FileGroups are linked
    with pytest.raises(ValueError, match="Cannot resolve conflict"):
        await lib.move(test_session, dir_b, dir_a / 'video.mp4')


@pytest.mark.asyncio
async def test_file_group_move(async_client, test_session, make_files_structure, test_directory, video_bytes,
                               srt_text):
    """Test FileGroup's move method"""
    video, srt = make_files_structure({
        'video.mp4': video_bytes,
        'video.srt': srt_text,
    })
    await file_worker.run_queue_to_completion()
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
    await file_worker.run_queue_to_completion()
    bar_file_group, foo_file_group = test_session.query(FileGroup).order_by(FileGroup.primary_path)
    bar_file_group.title = 'custom title'  # Should not be overwritten.
    bar_file_group.add_tag(test_session, tag.id)
    test_session.commit()

    qux = test_directory / 'qux'
    qux.mkdir()

    # Move both files into qux.  The Tag should also be moved.
    await lib.move(test_session, qux, bar, foo)
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
    assert bar_file_group.primary_path == new_bar
    # files now stores relative filenames; use my_files() to get resolved absolute paths
    assert bar_file_group.my_files()[0]['path'] == new_bar
    assert bar_file_group.primary_path.is_file()
    assert bar_file_group.tag_files
    # foo.txt was not tagged, but was moved.
    assert not foo_file_group.tag_files
    assert foo_file_group.primary_path.is_file()
    assert foo_file_group.primary_path == new_foo
    assert foo_file_group.my_files()[0]['path'] == new_foo
    assert bar_file_group.title == 'custom title', 'Custom title should not have been overwritten.'

    # Rename "bar.txt" to "baz.txt"
    await lib.rename(test_session, new_bar, 'baz.txt')
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

    await file_worker.run_queue_to_completion()

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
    await file_worker.run_queue_to_completion()
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
    await file_worker.run_queue_to_completion()
    assert test_session.query(FileGroup).count() == 1
    doc = test_session.query(FileGroup).one()
    assert doc.title == 'example word.docx'
    assert doc.a_text == 'example word docx'
    assert doc.d_text == 'Example Word Document Second page'


@pytest.mark.asyncio
async def test_file_search_date_range(async_client, test_session, example_pdf, example_doc):
    """Test searching FileGroups by their published datetime."""
    await file_worker.run_queue_to_completion()
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
    from wrolpi.db import get_db_curs

    make_files_structure([f'foo/{i}.txt' for i in range(10_000)])
    await file_worker.run_queue_to_completion()

    foo = test_directory / 'foo'
    bar = test_directory / 'bar'

    # Track get_db_curs calls to verify commit=True is passed for bulk updates.
    # Without commit=True, raw SQL is rolled back in production.
    get_db_curs_calls = []
    original_get_db_curs = get_db_curs

    def tracking_get_db_curs(*args, **kwargs):
        get_db_curs_calls.append(kwargs)
        return original_get_db_curs(*args, **kwargs)

    with timer('test_move_many_files'), mock.patch('wrolpi.files.lib.get_db_curs', tracking_get_db_curs):
        # mv foo bar
        await lib.move(test_session, bar, foo)

    assert not foo.is_dir()
    assert bar.is_dir()
    assert (bar / 'foo').is_dir()
    assert (bar / 'foo/0.txt').is_file()

    # Verify bulk update used commit=True (required for raw SQL to persist in production)
    assert get_db_curs_calls, 'get_db_curs should have been called for bulk update'
    assert all(call.get('commit') is True for call in get_db_curs_calls), \
        'get_db_curs must be called with commit=True to persist raw SQL in production'


@only_macos
def test_get_real_path_name(test_directory):
    (test_directory / 'foo.txt').touch()
    assert (test_directory / 'foo.txt').exists()
    assert lib.get_real_path_name(test_directory / 'foo.txt') == test_directory / 'foo.txt'

    assert (test_directory / 'FOO.TXT').exists()
    assert lib.get_real_path_name(test_directory / 'FOO.txt') == test_directory / 'foo.txt'


# --- Bulk Tagging Tests ---


@pytest.mark.asyncio
async def test_get_bulk_tag_preview_files(async_client, test_session, make_files_structure, tag_factory):
    """get_bulk_tag_preview returns correct file count and shared tags for files."""
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
    tag1 = await tag_factory('shared')
    tag2 = await tag_factory('only_foo')
    fg_foo.add_tag(test_session, tag1.id)
    fg_foo.add_tag(test_session, tag2.id)
    fg_bar.add_tag(test_session, tag1.id)
    fg_baz.add_tag(test_session, tag1.id)
    test_session.commit()

    # Preview for all three files
    preview = lib.get_bulk_tag_preview(['foo.txt', 'bar.txt', 'baz.txt'])
    assert preview.file_count == 3
    assert 'shared' in preview.shared_tag_names
    assert 'only_foo' not in preview.shared_tag_names  # Not shared by all


@pytest.mark.asyncio
async def test_get_bulk_tag_preview_directory(test_session, make_files_structure, test_directory, tag_factory):
    """get_bulk_tag_preview recursively finds files in directories."""
    make_files_structure({
        'mydir/foo.txt': 'foo',
        'mydir/bar.txt': 'bar',
        'mydir/subdir/baz.txt': 'baz',
    })

    # Preview for the directory - should find all files recursively
    preview = lib.get_bulk_tag_preview(['mydir/'])
    assert preview.file_count == 3


@pytest.mark.asyncio
async def test_get_bulk_tag_preview_multi_file_filegroup(async_client, test_session, make_files_structure,
                                                         test_directory, tag_factory):
    """get_bulk_tag_preview finds shared tags for multi-file FileGroups.

    This tests a bug where `get_unique_files_by_stem` may return a non-primary file (e.g. .readability.json)
    but the FileGroup query looks for exact primary_path match (e.g. .html), causing no FileGroup to be found.
    """
    # Create a multi-file FileGroup like an Archive (primary is .html, but has .readability.json, etc.)
    # SingleFile archives are named with the pattern: %Y-%m-%d-%H-%M-%S_title.html
    html_file, json_file, txt_file = make_files_structure({
        'archive/2025-01-01-12-00-00_Page Title.html': '<html>content</html>',
        'archive/2025-01-01-12-00-00_Page Title.readability.json': '{"title": "Page"}',
        'archive/2025-01-01-12-00-00_Page Title.readability.txt': 'Page content',
    })

    # Create the FileGroup with .html as the primary path
    fg = FileGroup.from_paths(test_session, html_file, json_file, txt_file)
    test_session.commit()

    # Verify the primary_path is the .html file
    assert fg.primary_path.suffix == '.html', f'Expected primary_path to be .html, got {fg.primary_path}'

    # Add a tag to this FileGroup
    tag = await tag_factory('my_tag')
    fg.add_tag(test_session, tag.id)
    test_session.commit()

    # Preview for the directory should find the FileGroup and its tag
    preview = lib.get_bulk_tag_preview(['archive/'])
    assert preview.file_count == 1, f'Expected 1 FileGroup, got {preview.file_count}'
    assert 'my_tag' in preview.shared_tag_names, f'Expected my_tag in shared tags, got {preview.shared_tag_names}'


def test_get_bulk_tag_preview_empty(test_session, test_directory):
    """get_bulk_tag_preview returns 0 for empty or non-existent paths."""
    preview = lib.get_bulk_tag_preview([])
    assert preview.file_count == 0
    assert preview.shared_tag_names == []


@pytest.mark.asyncio
@pytest.mark.parametrize('test_case,expected_fg_count', [
    ('existing_filegroups', 2),
    ('creates_filegroups', 2),
    ('recursive_directory', 2),
    ('multi_file_filegroup', 1),
])
async def test_process_bulk_tag_job_add_tags(test_case, expected_fg_count, async_client, test_session,
                                             make_files_structure, tag_factory, video_bytes, srt_text):
    """_process_bulk_tag_job adds tags to files in various scenarios."""
    if test_case == 'existing_filegroups':
        foo, bar = make_files_structure({'foo.txt': 'foo', 'bar.txt': 'bar'})
        FileGroup.from_paths(test_session, foo)
        FileGroup.from_paths(test_session, bar)
        test_session.commit()
        job_paths = ['foo.txt', 'bar.txt']
    elif test_case == 'creates_filegroups':
        make_files_structure({'foo.txt': 'foo', 'bar.txt': 'bar'})
        job_paths = ['foo.txt', 'bar.txt']
    elif test_case == 'recursive_directory':
        make_files_structure({'mydir/foo.txt': 'foo', 'mydir/subdir/bar.txt': 'bar'})
        job_paths = ['mydir/']
    elif test_case == 'multi_file_filegroup':
        make_files_structure({
            'video.mp4': video_bytes,
            'video.srt': srt_text,
            'video.info.json': '{"title": "Test Video"}',
        })
        job_paths = ['video.mp4']

    tag = await tag_factory('new_tag')
    test_session.commit()

    job = {'paths': job_paths, 'add_tag_names': ['new_tag'], 'remove_tag_names': []}
    await lib._process_bulk_tag_job(job)

    test_session.expire_all()
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == expected_fg_count
    for fg in fgs:
        assert 'new_tag' in fg.tag_names

    # Additional assertion for multi-file FileGroup
    if test_case == 'multi_file_filegroup':
        # files now stores relative filenames as strings; use my_files() to get resolved Paths
        file_paths = {f['path'].name for f in fgs[0].my_files()}
        assert file_paths == {'video.mp4', 'video.srt', 'video.info.json'}


@pytest.mark.asyncio
async def test_process_bulk_tag_job_remove_tags(async_client, test_session, make_files_structure, tag_factory):
    """_process_bulk_tag_job removes tags from files."""
    foo, bar = make_files_structure({
        'foo.txt': 'foo',
        'bar.txt': 'bar',
    })

    # Create FileGroups with a tag
    fg_foo = FileGroup.from_paths(test_session, foo)
    fg_bar = FileGroup.from_paths(test_session, bar)
    test_session.commit()

    tag = await tag_factory('to_remove')
    fg_foo.add_tag(test_session, tag.id)
    fg_bar.add_tag(test_session, tag.id)
    test_session.commit()

    job = {
        'paths': ['foo.txt', 'bar.txt'],
        'add_tag_names': [],
        'remove_tag_names': ['to_remove'],
    }

    await lib._process_bulk_tag_job(job)

    # Verify tags were removed
    test_session.expire_all()
    fgs = test_session.query(FileGroup).all()
    for fg in fgs:
        assert 'to_remove' not in fg.tag_names


def test_sanitize_filename_surrogates_valid_path(test_directory, make_files_structure):
    """sanitize_filename_surrogates() returns the same path for valid UTF-8 filenames."""
    foo, = make_files_structure({'foo.txt': 'content'})

    result = lib.sanitize_filename_surrogates(foo)

    assert result == foo
    assert foo.exists()


def test_sanitize_filename_surrogates_with_emoji(test_directory, make_files_structure):
    """sanitize_filename_surrogates() handles valid emoji filenames correctly."""
    # Valid emoji filename (this should work on most filesystems)
    files = make_files_structure({'test_emoji_🎉.txt': 'content'})
    emoji_file = files[0]

    result = lib.sanitize_filename_surrogates(emoji_file)

    assert result == emoji_file
    assert emoji_file.exists()


def test_sanitize_filename_surrogates_nonexistent_path(test_directory):
    """sanitize_filename_surrogates() returns the path unchanged if file doesn't exist."""
    nonexistent = test_directory / 'does_not_exist.txt'

    result = lib.sanitize_filename_surrogates(nonexistent)

    # Path doesn't exist, so it's returned unchanged (no rename attempted)
    assert result == nonexistent


@pytest.mark.skipif(IS_MACOS, reason="macOS filesystem enforces UTF-8, can't create files with invalid surrogates")
def test_sanitize_filename_surrogates_renames_file(test_directory):
    """sanitize_filename_surrogates() renames files when it detects invalid UTF-8.

    This test only runs on Linux where filesystems allow invalid UTF-8 filenames.
    """
    import os

    # Create a file with invalid UTF-8 bytes in the filename using raw bytes
    # \xed\xa0\xbc is an invalid UTF-8 sequence (unpaired surrogate)
    bad_filename_bytes = b'bad_\xed\xa0\xbc_file.txt'
    bad_file_path_bytes = os.fsencode(test_directory) + b'/' + bad_filename_bytes

    # Write content to the file using raw bytes path
    with open(bad_file_path_bytes, 'wb') as f:
        f.write(b'test content')

    # Get the path as Python sees it (with surrogates)
    bad_path = test_directory / os.fsdecode(bad_filename_bytes)
    assert bad_path.exists()

    # Verify the path string contains surrogates (can't be encoded to UTF-8)
    with pytest.raises(UnicodeEncodeError):
        str(bad_path).encode('utf-8')

    # Call the sanitize function
    result = lib.sanitize_filename_surrogates(bad_path)

    # The file should have been renamed
    assert result != bad_path
    assert result.exists()
    assert not bad_path.exists()
    # Surrogates should be replaced with underscores - the result should be valid UTF-8
    try:
        str(result).encode('utf-8')
    except UnicodeEncodeError:
        pytest.fail("Result path still contains invalid UTF-8 surrogates")
    # Content should be preserved
    assert result.read_text() == 'test content'


@pytest.mark.asyncio
async def test_rename_file_with_associated_files_twice(async_client, test_session, test_directory, make_files_structure,
                                                        video_bytes, srt_text):
    """
    Renaming a FileGroup twice should rename all associated files both times.

    Regression test for: When renaming "example.mp4" to "example 2.mp4" and then back to "example.mp4",
    the associated file "example.srt" should be renamed along with the primary file both times.
    """
    # Create a FileGroup with primary file and associated file
    video, srt = make_files_structure({
        'example.mp4': video_bytes,
        'example.srt': srt_text,
    })
    await file_worker.run_queue_to_completion()

    # Verify initial state
    file_group = test_session.query(FileGroup).one()
    assert file_group.primary_path == video
    assert len(file_group.files) == 2
    assert video.is_file()
    assert srt.is_file()

    # First rename: "example.mp4" -> "example 2.mp4"
    new_path_1 = await lib.rename_file(video, 'example 2.mp4')
    test_session.expire_all()

    # Verify first rename - both files should be renamed
    new_video_1 = test_directory / 'example 2.mp4'
    new_srt_1 = test_directory / 'example 2.srt'
    assert new_path_1 == new_video_1
    assert new_video_1.is_file(), "Video should be renamed to 'example 2.mp4'"
    assert new_srt_1.is_file(), "SRT should be renamed to 'example 2.srt'"
    assert not video.exists(), "Old video should not exist"
    assert not srt.exists(), "Old SRT should not exist"

    # Verify FileGroup is updated
    file_group = test_session.query(FileGroup).one()
    assert file_group.primary_path == new_video_1
    file_names = [f['path'] for f in file_group.files]
    assert 'example 2.mp4' in file_names
    assert 'example 2.srt' in file_names
    assert len(file_group.files) == 2

    # Second rename: "example 2.mp4" -> "example.mp4"
    new_path_2 = await lib.rename_file(new_video_1, 'example.mp4')
    test_session.expire_all()

    # Verify second rename - BOTH files should be renamed back
    final_video = test_directory / 'example.mp4'
    final_srt = test_directory / 'example.srt'
    assert new_path_2 == final_video
    assert final_video.is_file(), "Video should be renamed back to 'example.mp4'"
    assert final_srt.is_file(), "SRT should be renamed back to 'example.srt'"
    assert not new_video_1.exists(), "'example 2.mp4' should not exist"
    assert not new_srt_1.exists(), "'example 2.srt' should not exist"

    # Verify FileGroup is updated
    file_group = test_session.query(FileGroup).one()
    assert file_group.primary_path == final_video
    file_names = [f['path'] for f in file_group.files]
    assert 'example.mp4' in file_names
    assert 'example.srt' in file_names
    assert len(file_group.files) == 2


@pytest.mark.asyncio
async def test_rename_non_primary_file_renames_filegroup(async_client, test_session, test_directory,
                                                          make_files_structure, video_bytes, srt_text):
    """
    Renaming a non-primary file (like a subtitle) should rename the entire FileGroup.

    If a user renames "example.srt" to "renamed.srt", the primary "example.mp4"
    should also be renamed to "renamed.mp4".
    """
    # Create a FileGroup with primary file and associated file
    video, srt = make_files_structure({
        'example.mp4': video_bytes,
        'example.srt': srt_text,
    })
    await file_worker.run_queue_to_completion()

    # Verify initial state
    file_group = test_session.query(FileGroup).one()
    assert file_group.primary_path == video
    assert len(file_group.files) == 2

    # Rename the non-primary file (the SRT)
    new_path = await lib.rename_file(srt, 'renamed.srt')
    test_session.expire_all()

    # Verify all files in the FileGroup were renamed
    new_video = test_directory / 'renamed.mp4'
    new_srt = test_directory / 'renamed.srt'
    assert new_path == new_srt
    assert new_video.is_file(), "Primary video should be renamed to 'renamed.mp4'"
    assert new_srt.is_file(), "SRT should be renamed to 'renamed.srt'"
    assert not video.exists(), "Old video should not exist"
    assert not srt.exists(), "Old SRT should not exist"

    # Verify FileGroup is updated correctly
    file_group = test_session.query(FileGroup).one()
    assert file_group.primary_path == new_video
    file_names = [f['path'] for f in file_group.files]
    assert 'renamed.mp4' in file_names
    assert 'renamed.srt' in file_names
    assert len(file_group.files) == 2
