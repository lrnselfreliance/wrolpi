import pathlib

import pytest
import sqlalchemy

from modules.videos.common import apply_info_json
from modules.videos.lib import parse_video_file_name, validate_video, get_statistics
from modules.videos.models import Video
from modules.videos.video.lib import video_search
from wrolpi.files import lib as files_lib
from wrolpi.files.models import File


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
    videos, total = video_search(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == []
    assert total == 0

    # First 5 are censored.
    set_entries(map(str, range(5, 50)))
    videos, total = video_search(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == [str(i) for i in range(5)]
    assert total == 5

    # First 25 are censored.
    set_entries(map(str, range(25, 50)))
    videos, total = video_search(filters=['censored'], order_by='id', limit=20)
    assert [i['video']['source_id'] for i in videos] == [str(i) for i in range(20)]
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
async def test_associated_files(test_session, test_directory, video_file, image_file, vtt_file1):
    """A Video file has files related to it.  They should be attached to the Video record."""
    caption_file = video_file.with_suffix('.en.vtt')
    vtt_file1.rename(caption_file)
    poster_file = video_file.with_suffix('.jpeg')
    image_file.rename(poster_file)

    await files_lib._refresh_all_files()
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

    await files_lib._refresh_all_files()
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

    await files_lib._refresh_all_files()
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
