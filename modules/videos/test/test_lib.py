import json
import pathlib
import shutil

import pytest
import sqlalchemy

from modules.videos import lib
from modules.videos.common import apply_info_json
from modules.videos.lib import parse_video_file_name, validate_video, get_statistics
from modules.videos.models import Video
from modules.videos.video.lib import search_videos
from wrolpi.dates import strptime
from wrolpi.files import lib as files_lib
from wrolpi.files.lib import refresh_files
from wrolpi.files.models import File
from wrolpi.test.common import skip_circleci
from wrolpi.vars import PROJECT_DIR


def test_search_censored_videos(test_session, simple_channel, video_factory):
    for i in map(str, range(50)):
        video_factory(channel_id=simple_channel.id, source_id=i)
    vid = video_factory(source_id=51)  # this should never be modified because it has no channel
    test_session.add(vid)
    test_session.commit()

    def set_entries(entries):
        simple_channel.info_json = {
            'entries': [{'id': j, 'view_count': 0} for j in entries]} if entries else sqlalchemy.null()
        test_session.commit()
        apply_info_json(simple_channel.id)
        test_session.commit()

    # All source_ids are in the entries.
    set_entries(map(str, range(50)))
    videos, total = search_videos(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == []
    assert total == 0

    # First 5 are censored.
    set_entries(map(str, range(5, 50)))
    videos, total = search_videos(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == [str(i) for i in range(5)]
    assert all(i['video']['censored'] for i in videos)
    assert total == 5

    # First 25 are censored.
    set_entries(map(str, range(25, 50)))
    videos, total = search_videos(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == [str(i) for i in range(20)]
    assert all(i['video']['censored'] for i in videos)
    assert total == 25


@pytest.mark.parametrize('file_name,expected', [
    ('channel_20000101_12345678910_ some title.mp4', ('channel', '20000101', '12345678910', 'some title')),
    ('channel name_NA_12345678910_ some title.mp4', ('channel name', None, '12345678910', 'some title')),
    ('20000101 foo.mp4', (None, None, None, '20000101 foo')),
    ('20000101foo.mp4', (None, None, None, '20000101foo')),
    ('something 20000101 foo.mp4', (None, None, None, 'something 20000101 foo')),
    ('something_20000101_foo.mp4', ('something', '20000101', None, 'foo')),
    ('foo .mp4', (None, None, None, 'foo')),
    ('NA_20000303_vp91w5_Bob&apos;s Pancakes.mp4', (None, '20000303', 'vp91w5', 'Bob&apos;s Pancakes')),
    ('NA_NA_vp91w5_Bob&apos;s Pancakes.mp4', (None, None, 'vp91w5', 'Bob&apos;s Pancakes')),
    ('Learning Self-Reliance_20170529_p_MzsCFkUPU_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', 'p_MzsCFkUPU', 'Beekeeping 2017 Part 6 - Merging Hives')),
    ('Learning Self-Reliance_20170529_p_Mzs_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', 'p_Mzs', 'Beekeeping 2017 Part 6 - Merging Hives')),
    ('Learning Self-Reliance_20170529_p_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', None, 'p_Beekeeping 2017 Part 6 - Merging Hives')),
])
def test_parse_video_file_name(file_name, expected):
    """
    A Video's title can be parsed from the video file.
    """
    video_path = pathlib.Path(file_name)
    assert parse_video_file_name(video_path) == expected, f'{file_name} != {expected}'


@pytest.mark.asyncio
async def test_associated_video_files(test_session, test_directory, video_file, image_file, vtt_file1):
    """A Video file has files related to it.  They should be attached to the Video record."""
    caption_file = video_file.with_suffix('.en.vtt')
    vtt_file1.rename(caption_file)
    poster_file = video_file.with_suffix('.jpeg')
    image_file.rename(poster_file)

    await files_lib.refresh_files()
    test_session.commit()

    # All files were found.
    file_paths = {i.path for i in test_session.query(File)}
    assert len(file_paths) == 3

    video: Video = test_session.query(Video).one()
    video_id = video.id
    assert video.video_file == video_file
    assert video.poster_file == poster_file
    assert video.caption_file == caption_file
    assert video.video_file.modification_datetime
    assert video.video_file.size
    assert video.video_file.indexed

    await files_lib.refresh_files()
    test_session.commit()

    # No new files were added.
    assert {i.path for i in test_session.query(File)} == file_paths
    # Same video exists.
    video: Video = test_session.query(Video).one()
    assert video.id == video_id, 'Video id changed.  Was the video recreated?'


@pytest.mark.asyncio
async def test_unassociated_video(test_session, test_directory, video_file):
    """A Video file without associated files is still a Video."""
    # Move the video file into a new subdirectory.  The video file should still be found.
    sub_dir = test_directory / 'subdir'
    sub_dir.mkdir()
    new_video_file_path = sub_dir / video_file.name
    video_file.rename(new_video_file_path)
    video_file = new_video_file_path

    await files_lib.refresh_files()
    test_session.commit()

    video: Video = test_session.query(Video).one()
    assert video.video_file == video_file


@pytest.mark.asyncio
async def test_video_factory(test_session, video_factory, channel_factory):
    """
    The `video_factory` pytest fixture is used in many video tests.  Test all it's functionality.
    """
    channel = channel_factory()
    video = video_factory(
        channel_id=channel.id,
        with_video_file=True,
        with_info_json={'description': 'hello'},
        with_caption_file=True,
        with_poster_ext='png',
        source_id='some id',
    )
    test_session.commit()

    assert video.video_path and video.video_file and video.video_path.is_file()
    assert video.caption_path and video.caption_file and video.caption_path.is_file()
    assert video.poster_path and video.poster_file and video.poster_path.is_file()
    assert video.info_json_path and video.info_json_file and video.info_json_path.is_file()

    assert video.video_file.a_text  # title
    assert video.video_file.b_text is None
    assert video.video_file.c_text and 'hello' in video.video_file.c_text  # description
    assert video.video_file.d_text  # captions
    assert video.source_id == 'some id'


def test_validate_video(test_session, test_directory, video_factory):
    """A video poster will be generated only if the channel permits."""
    vid1 = video_factory(with_video_file=True)
    assert not vid1.poster_path

    validate_video(vid1, True, test_session)
    assert vid1.poster_path, 'Poster was not created'
    assert vid1.poster_path.is_file(), 'Poster path does not exist'
    assert vid1.video_path.stem == vid1.poster_path.stem
    assert vid1.poster_path.suffix == '.jpg'

    # A PNG is replaced.
    vid2 = video_factory(with_video_file=True, with_poster_ext='.png')
    vid2.poster_path.with_suffix('.jpg').touch()  # New poster exists, replace it.
    assert vid2.poster_path and vid2.poster_path.is_file() and vid2.poster_path.suffix == '.png', \
        'Poster was not initialized'
    validate_video(vid2, True, test_session)
    assert vid2.poster_path.is_file(), 'New poster was not generated'
    assert vid2.poster_path.suffix == '.jpg'


@pytest.mark.asyncio
async def test_get_statistics(test_session, video_factory, channel_factory):
    # Can get statistics in empty DB.
    await get_statistics()

    channel1 = channel_factory()
    channel2 = channel_factory()
    video_factory(channel_id=channel1.id)
    video_factory(channel_id=channel1.id)
    video_factory(channel_id=channel2.id)
    video_factory()

    result = await get_statistics()
    assert 'statistics' in result
    assert 'videos' in result['statistics']
    assert 'channels' in result['statistics']
    assert 'historical' in result['statistics']


@skip_circleci
@pytest.mark.asyncio
async def test_video_epoch(test_session, test_directory, video_file):
    """The epoch in a Video's info_json is more precise and should be used when available.

    Fallback to the upload_date in the Video file's name.
    """
    # The date from a video file's name is assumed to be midnight in UTC.
    upload_date = '20221206'

    destination = test_directory / f'test channel_{upload_date}_the title.mp4'
    video_file.rename(destination)
    video_file = destination

    await refresh_files()
    assert test_session.query(File).count() == 1
    assert test_session.query(Video).count() == 1

    video: Video = test_session.query(Video).one()
    # Upload date is converted to local time.
    assert video.title == 'the title'
    assert video.upload_date == strptime('2022-12-05 17:00:00'), \
        'Video upload_date should be the date from the file name.'
    assert not video.info_json_file, 'Video should not have info json file'

    # Write info_json with more precise epoch.
    info_json_path = video_file.with_suffix('.info.json')
    info_json = {'epoch': 1656783193}
    info_json_path.write_text(json.dumps(info_json))
    # Invalidate video so the JSON will be processed again.
    video.validated = False
    test_session.commit()

    # Epoch should replace file upload_date.
    await refresh_files()
    assert test_session.query(File).count() == 2
    assert video.info_json_file, 'Video info json was not discovered.'
    assert video.upload_date == strptime('2022-07-02 11:33:13'), 'Epoch from info_json did not replace file upload_date'
    assert video_file.is_file() and info_json_path.is_file(), 'Files should contain the old date.'


@pytest.mark.asyncio
async def test_orphaned_files(test_session, make_files_structure, test_directory, video_factory):
    # A Video without associated files is not orphaned.
    vid1 = video_factory(with_video_file=True)
    # The video files will be removed...
    vid2 = video_factory(with_video_file=True, with_caption_file=True, with_poster_ext='jpeg', with_info_json=True)
    vid3 = video_factory(with_video_file=True, with_poster_ext='jpg')
    # This will be ignored because it is not in the "videos" subdirectory.
    shutil.copy(PROJECT_DIR / 'test/example1.en.vtt', test_directory / 'video4.en.vtt')
    test_session.commit()

    # Remove vid2 video. Caption, poster, info_json are now orphaned.
    vid2.video_path.unlink()
    vid2_caption_path, vid2_poster_path, vid2_info_json_path = vid2.caption_path, vid2.poster_path, vid2.info_json_path
    # Remove vid3 video.  Poster is now orphaned.
    vid3.video_path.unlink()
    vid3_poster_path = vid3.poster_path
    await refresh_files()
    test_session.commit()

    # 6 files when two video files are deleted.
    # (vid1, vid2[caption,poster,json], vid3 poster, vid4)
    assert test_session.query(File).count() == 6
    assert test_session.query(Video).count() == 1

    videos_directory = test_directory / 'videos'
    results = lib.find_orphaned_video_files(videos_directory)

    assert sorted(list(results)) == sorted([
        vid2_caption_path,
        vid2_info_json_path,
        vid2_poster_path,
        vid3_poster_path,
    ])
