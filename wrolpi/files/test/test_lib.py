import asyncio
import json
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

from wrolpi.common import timer
from wrolpi.dates import now, from_timestamp
from wrolpi.errors import InvalidFile, UnknownDirectory
from wrolpi.files import lib, indexers
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile
from wrolpi.vars import PROJECT_DIR


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
        ('foo', ('foo', '')),
        ('foo.mp4', ('foo', '.mp4')),
        ('foo.info.json', ('foo', '.info.json')),
        ('foo.something.info.json', ('foo.something', '.info.json')),
        ('foo-something.info.json', ('foo-something', '.info.json')),
        ('/absolute/foo-something.info.json', ('foo-something', '.info.json')),
        ('/absolute/foo', ('foo', '')),
        ('/absolute/foo.bar', ('foo', '.bar')),
        ('foo.en.srt', ('foo', '.en.srt')),
        ('foo.pl.srt', ('foo', '.pl.srt')),
    ]
)
def test_split_path_stem_and_suffix(path, expected):
    assert lib.split_path_stem_and_suffix(Path(path)) == expected


@pytest.mark.asyncio
async def test_refresh_files(test_session, make_files_structure, assert_file_groups):
    """All files in the media directory should be found when calling `refresh_files`"""
    files = make_files_structure([
        'foo.txt',
        'bar.txt',
        'baz.txt',
    ])
    foo, bar, baz = files

    await lib.refresh_files()
    assert_file_groups([
        {'full_stem': 'foo', 'indexed': True},
        {'full_stem': 'bar', 'indexed': True},
        {'full_stem': 'baz', 'indexed': True}])

    baz.unlink()

    await lib.refresh_files()
    assert_file_groups([{'full_stem': 'foo', 'indexed': True}, {'full_stem': 'bar', 'indexed': True}])

    foo.unlink()

    await lib.refresh_files()
    assert_file_groups([{'full_stem': 'bar', 'indexed': True}])


@pytest.mark.asyncio
async def test_refresh_bogus_files(test_session, make_files_structure, test_directory, assert_file_groups,
                                   insert_file_group):
    """Bogus files are removed during a refresh."""
    make_files_structure(['does exist.txt'])
    await lib.refresh_files()
    insert_file_group([test_directory / 'does not exist.txt'])
    test_session.commit()

    # Bogus file was inserted.
    assert_file_groups([
        {'full_stem': 'does exist', 'indexed': True},
        {'full_stem': 'does not exist', 'indexed': True},
    ])

    await lib.refresh_files()

    assert test_session.query(FileGroup).count() == 1, 'Bogus file was not removed'
    assert_file_groups([{'full_stem': 'does exist', 'indexed': True}])


@pytest.mark.asyncio
async def test_refresh_empty_media_directory(test_session, test_directory):
    """refresh_paths will refuse to refresh with an empty media directory."""
    with pytest.raises(UnknownDirectory):
        await lib.refresh_files()


@pytest.mark.asyncio
async def test__upsert_files(test_session, make_files_structure, test_directory, assert_file_groups, video_file,
                             srt_file3):
    bar, baz = make_files_structure({
        'dir1/bar.txt': None,
        'baz.txt': 'baz file',
    })
    video_file = video_file.rename(test_directory / 'video.mp4')
    srt_file3 = srt_file3.rename(test_directory / 'video.en.srt')
    video_stem = str(test_directory / video_file.stem)
    foo_mtime = from_timestamp(srt_file3.stat().st_mtime)

    # All files are found because they are in this refresh request, or in the `dir1` directory.
    idempotency = now()
    lib._upsert_files([video_file, srt_file3, bar, baz], idempotency)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'modification_datetime': foo_mtime, 'indexed': False,
         'files': [
             {'path': srt_file3, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency,
         'files': [{'path': bar, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}]
         },
        {'primary_path': baz, 'idempotency': idempotency,
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
        [{'full_stem': video_stem, 'idempotency': idempotency, 'modification_datetime': foo_mtime, 'indexed': True}],
        assert_count=False)

    # Only modified files need to be re-indexed.
    lib._upsert_files([video_file, srt_file3, bar, baz], idempotency)
    assert_file_groups([
        {'primary_path': video_file, 'idempotency': idempotency, 'modification_datetime': foo_mtime, 'indexed': True,
         'files': [
             {'path': srt_file3, 'size': 951, 'suffix': '.en.srt', 'mimetype': 'text/srt'},
             {'path': video_file, 'size': 1056318, 'suffix': '.mp4', 'mimetype': 'video/mp4'},
         ]},
        {'primary_path': bar, 'idempotency': idempotency,
         'files': [{'path': bar, 'size': 0, 'suffix': '.txt', 'mimetype': 'inode/x-empty'}],
         },
        {'primary_path': baz, 'idempotency': idempotency,
         'files': [{'path': baz, 'size': 7, 'suffix': '.txt', 'mimetype': 'text/plain'}],
         },
    ])

    # Deleting SRT removes it from the video.
    srt_file3.unlink()
    lib._upsert_files([video_file, bar, baz], idempotency)
    video_file_group: FileGroup = test_session.query(FileGroup).filter_by(full_stem=str(test_directory / 'video')).one()
    assert len(video_file_group.files) == 1, 'SRT file was not removed from files'


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
async def test_refresh_discover_paths_groups(test_session, make_files_structure, test_directory):
    make_files_structure(['dir1/foo.mp4', 'dir1/foo.info.json', 'baz.txt'])
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
async def test_file_group_tag(test_session, make_files_structure, test_directory, tag_factory):
    """A FileGroup can be tagged."""
    make_files_structure(['foo.mp4'])
    await lib.refresh_discover_paths([test_directory, ], now())
    one = tag_factory()

    foo: FileGroup = test_session.query(FileGroup).one()
    foo.add_tag(one)
    test_session.commit()

    tag_file2: TagFile = test_session.query(TagFile).one()
    assert tag_file2 and tag_file2.file_group == foo


@pytest.mark.asyncio
async def test_refresh_a_text_no_indexer(test_session, make_files_structure):
    """File.a_text is filled even if the file does not match an Indexer."""
    make_files_structure(['foo', 'bar-bar'])

    await lib.refresh_files()

    files = {i.a_text for i in test_session.query(FileGroup)}
    assert files == {'bar bar bar-bar', 'foo'}


@pytest.mark.asyncio
async def test_refresh_many_files(test_session, make_files_structure):
    """Used to profile file refreshing"""
    count = 10_000
    make_files_structure([f'{uuid4()}.txt' for _ in range(count)])
    with timer('first refresh'):
        await lib.refresh_files()
    assert test_session.query(FileGroup).count() == count

    with timer('second refresh'):
        await lib.refresh_files()
    assert test_session.query(FileGroup).count() == count


@pytest.mark.asyncio
async def test_refresh_cancel(test_session, make_files_structure, test_directory):
    """Refresh tasks can be canceled."""
    # Creat a lot of files so the refresh will take too long.
    make_files_structure([f'{uuid4()}.txt' for _ in range(1_000)])

    async def assert_cancel(task_):
        # Time the time it takes to cancel.
        before = datetime.now()
        # Sleep so the refresh task has time to run.
        await asyncio.sleep(0.1)

        # Cancel the refresh (it will be sleeping soon).
        task_.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task_
        assert (datetime.now() - before).total_seconds() < 0.8, 'Task took too long.  Was the refresh canceled?'

    task = asyncio.create_task(lib.refresh_files())
    await assert_cancel(task)


@pytest.mark.asyncio
async def test_mime_type(test_session, make_files_structure, test_directory, assert_files):
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
async def test_files_indexer(test_session, make_files_structure, test_directory):
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
        = test_session.query(FileGroup).order_by(FileGroup.full_stem)

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
])
def test_split_file_name_words(name, expected):
    assert lib.split_file_name_words(name) == expected


@pytest.mark.asyncio
async def test_large_text_indexer(test_session, make_files_structure):
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

    check(mp4, ['video.mp4', 'video.png', 'video.info.json', 'video'])
    check(png, ['video.mp4', 'video.png', 'video.info.json', 'video'])
    check(j, ['video.mp4', 'video.png', 'video.info.json', 'video'])
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
    assert matches == [str(test_directory / 'foo')]

    # Get all directories starting with b, ignore case
    matches = lib.get_matching_directories(test_directory / 'b')
    assert matches == [str(test_directory / 'Bar'), str(test_directory / 'baz')]

    # baz matches, but it has no subdirectories
    matches = lib.get_matching_directories(test_directory / 'baz')
    assert matches == [str(test_directory / 'baz')]

    # foo is an exact match, return subdirectories
    matches = lib.get_matching_directories(test_directory / 'foo')
    assert matches == [str(test_directory / 'foo/qux')]


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
        'bar.txt',
        'baz.txt',
    ])

    files = list(test_directory.iterdir())
    assert list(lib.group_files_by_stem(files)) == [
        [test_directory / 'bar.txt'],
        [test_directory / 'baz.txt'],
        [test_directory / 'foo.info.json', test_directory / 'foo.mp4', test_directory / 'foo.txt'],
    ]


def test_get_primary_file(test_directory, video_file, srt_file3, example_epub, example_mobi, example_pdf,
                          singlefile_contents_factory):
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


@pytest.mark.parametrize(
    'tags,wheres,params,join', [
        (
                ['one'],
                '(t0.name = %(tag_name0)s)',
                dict(tag_name0='one'),
                'LEFT JOIN tag_file tf0 ON tf0.file_group_id = fg.id LEFT JOIN tag t0 ON t0.id = tf0.tag_id',
        ),
        (
                ['one', 'two'],
                '(t0.name = %(tag_name0)s AND t1.name = %(tag_name1)s)',
                dict(tag_name0='one', tag_name1='two'),
                'LEFT JOIN tag_file tf0 ON tf0.file_group_id = fg.id LEFT JOIN tag t0 ON t0.id = tf0.tag_id'
                '\nLEFT JOIN tag_file tf1 ON tf1.file_group_id = fg.id LEFT JOIN tag t1 ON t1.id = tf1.tag_id',
        ),
        (
                [],
                '',
                dict(),
                '',
        ),
    ]
)
def test_tag_names_to_clauses(tags, wheres, params, join):
    result = lib.tag_names_to_clauses(tags)
    assert result[0] == wheres
    assert result[1] == params
    assert result[2] == join


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
    assert 'total_files' in progress
    assert 'unindexed' in progress
