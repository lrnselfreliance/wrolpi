import json
import shutil
from http import HTTPStatus
from pathlib import Path

import pytest

from modules.videos.models import Video, Channel
from modules.videos.video import lib as video_lib
from wrolpi.downloader import DownloadFrequency
from wrolpi.files.lib import refresh_files
from wrolpi.files.models import File
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_refresh_videos_index(test_session, test_directory, video_factory):
    """A video discovered during refresh has files associated with it.  Only the video file is indexed."""
    video_factory(with_video_file=True, with_caption_file=True, with_poster_ext='jpg', with_info_json=True)
    test_session.commit()

    test_session.query(Video).delete()
    test_session.query(File).delete()
    test_session.commit()

    for _ in range(1):
        # Refreshing twice does not change the results.
        await refresh_files()

        assert test_session.query(File).count() == 4
        video: Video = test_session.query(Video).one()
        assert video.video_file.indexed is True, 'Video was not indexed'
        assert video.video_file.a_text, 'Video title was not indexed'
        assert video.video_file.d_text, 'Video captions were not indexed'

        assert not video.poster_file.indexed
        assert not video.caption_file.indexed
        assert not video.info_json_file.indexed


def test_refresh_videos(test_client, test_session, test_directory, simple_channel, video_factory):
    subdir = test_directory / 'subdir'
    subdir.mkdir()

    # video1 is in a subdirectory, move its files into the subdirectory.
    video1 = video_factory(channel_id=simple_channel.id, with_video_file=subdir / 'video1.mp4',
                           with_info_json=True,
                           with_poster_ext='jpg')
    test_session.commit()
    test_session.delete(video1.poster_file)
    video1.poster_path = None
    # video2 is in the test directory.
    video2 = video_factory(channel_id=simple_channel.id, with_video_file=True, with_info_json=True,
                           with_poster_ext='jpg')
    video2.poster_path = video2.poster_file = video1.poster_path = None
    test_session.commit()

    assert not video1.size, 'video1 should not have size during creation'

    # Create a video not in the DB.
    vid3 = test_directory / 'vid3.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', vid3)

    # Orphan poster should be ignored.
    orphan_poster = Path(test_directory / 'channel name_20000104_defghijklmn_title.jpg')
    orphan_poster.touch()

    # Create a bogus video in the channel.
    video_file = File(path=test_directory / 'foo')
    video_file.idempotency = None  # File was not added in the current refresh.
    bogus = Video(video_file=video_file, channel_id=simple_channel.id)
    test_session.add(bogus)
    test_session.commit()

    test_client.post('/api/files/refresh')

    # Posters were found during refresh.
    assert video1.poster_path
    assert 'subdir' in str(video1.poster_path)
    assert video2.poster_path
    # Missing video3 was found
    video3: Video = test_session.query(Video).filter_by(id=4).one()
    assert video3.video_path == vid3
    assert len(set(test_session.query(Video.video_path))) == 3, 'Should have 3 distinct video files'
    # Bogus video was removed.
    assert not any('foo' in str(i.video_path) for i in test_session.query(Video).all())
    # Orphan file was not deleted.
    assert orphan_poster.is_file(), 'Orphan poster was removed!'

    assert video1.size, 'video1 size was not found'

    # Remove video1's poster, video1 should be updated.
    video1_video_path = str(video1.video_path)
    video1.poster_path.unlink()
    test_client.post('/api/files/refresh')
    video1 = test_session.query(Video).filter_by(video_path=video1_video_path).one()
    assert not video1.poster_path


def test_channels_with_videos(test_session, test_client, test_directory, channel_factory, video_factory):
    channel1 = channel_factory('channel1', name='channel1')
    channel2 = channel_factory('channel2', name='channel2')
    vid1 = video_factory(channel_id=channel1.id, with_video_file=True)
    vid2 = video_factory(channel_id=channel2.id, with_video_file=True)
    vid3 = video_factory(with_video_file=True)
    test_session.commit()

    vid1_path = vid1.video_path
    vid2_path = vid2.video_path
    vid3_path = vid3.video_path

    test_session.delete(vid1)
    test_session.delete(vid2)
    test_session.delete(vid3)
    test_session.commit()

    assert test_session.query(Video).count() == 0, 'Videos were not deleted'
    assert test_session.query(Channel).count() == 2, 'Channels were deleted!'
    assert vid1_path.is_file(), 'Video file was deleted'
    assert vid2_path.is_file(), 'Video file was deleted'
    assert vid3_path.is_file(), 'Video file was deleted'

    test_client.post('/api/files/refresh')

    assert test_session.query(Video).count() == 3, 'Did not find correct amount of video files.'
    assert {i[0] for i in test_session.query(Channel.name)} == {'channel1', 'channel2'}, 'Channels were changed.'

    vid1: Video = test_session.query(Video).filter_by(video_path=vid1_path).one()
    vid2: Video = test_session.query(Video).filter_by(video_path=vid2_path).one()
    vid3: Video = test_session.query(Video).filter_by(video_path=vid3_path).one()

    assert vid1.channel == channel1
    assert vid2.channel == channel2
    assert vid3.channel is None


def test_api_download_channel(test_session, test_client, simple_channel):
    """A Channel download (a catalog update) can be triggered via the API."""
    # simple_channel does not have a download record.
    request, response = test_client.post(f'/api/videos/download/{simple_channel.id}')
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.json
    assert 'not have a download' in response.json['message']

    # Add a download frequency to the channel, this should also create a download.
    simple_channel.update(dict(download_frequency=DownloadFrequency.daily))
    test_session.commit()
    request, response = test_client.post(f'/api/videos/download/{simple_channel.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_search_videos_file(test_client, test_session, test_directory, video_with_search_factory):
    """Test that videos can be searched and that their order is by their textsearch rank."""
    # These captions have repeated letters, so they will be higher in the ranking.
    videos = [
        ('1', 'b b b b e d d'),
        ('2', '2 b b b d'),
        ('3', 'b b'),
        ('4', 'b e e'),
        ('5', ''),
    ]
    for title, caption in videos:
        video_with_search_factory(title=title, d_text=caption)
    test_session.commit()

    def assert_search(search_str, expected, limit=20, total=None):
        d = json.dumps({'search_str': search_str, 'limit': limit})
        _, resp = test_client.post('/api/videos/search', content=d)
        assert resp.status_code == HTTPStatus.OK
        response_ids = [i['video']['id'] for i in resp.json['files']]
        assert response_ids == expected
        assert resp.json['totals']['files'] == (total or len(expected))

    # Repeated runs should return the same result
    for _ in range(2):
        # Only videos with a b are returned, ordered by the amount of b's
        assert_search('b', [1, 2, 3, 4])

    # Only two captions have e
    assert_search('e', [4, 1])

    # Only two captions have d
    assert_search('d', [1, 2])

    # 5 can be gotten by it's title
    assert_search('5', [5])

    # only video 1 has e and d
    assert_search('e d', [1])

    # video 1 and 4 have b and e, but 1 has more
    assert_search('b e', [1, 4])

    # Check totals are correct even with a limit
    assert_search('b', [1, 2], limit=2, total=4)


def test_search_videos(test_client, test_session, video_factory, assert_video_search, simple_channel):
    """Search the Video table.  This does not need to use a join with the File table."""
    vid1 = video_factory(upload_date='2022-09-16', with_video_file=True)
    vid2 = video_factory(upload_date='2022-09-17', with_video_file=True, channel_id=simple_channel.id)
    vid3 = video_factory(upload_date='2022-09-18', with_video_file=True)
    vid1.set_favorite(True)
    test_session.commit()
    assert test_session.query(Video).count() == 3
    assert test_session.query(File).count() == 3

    assert_video_search(assert_total=3, assert_ids=[vid1.id, vid2.id, vid3.id], order_by='upload_date')
    assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id, vid1.id], order_by='-upload_date')
    assert_video_search(assert_total=3, assert_ids=[vid3.id, vid2.id], order_by='-upload_date', limit=2)
    assert_video_search(assert_total=3, assert_ids=[vid2.id, vid1.id], order_by='-upload_date', limit=2, offset=1)
    assert_video_search(assert_total=1, assert_ids=[vid2.id], order_by='-upload_date', channel_id=simple_channel.id)
    assert_video_search(assert_total=1, assert_ids=[vid1.id], filters=['favorite'])
    assert_video_search(assert_total=1, assert_ids=[vid1.id], filters=['favorite'], limit=1)

    # No results, no total is returned from the DB.
    assert_video_search(assert_total=0, assert_ids=[], filters=['favorite'], offset=1)

    # Check all order_by.
    for order_by in video_lib.VIDEO_ORDERS:
        assert_video_search(order_by=order_by)
