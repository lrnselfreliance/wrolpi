from datetime import timedelta
from http import HTTPStatus
from json import dumps

import pytest

from modules.videos.models import Video
from modules.videos.video.lib import get_video_for_app
from wrolpi.dates import now
from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.root_api import api_app


def test_get_video_prev_next(test_session, channel_factory, video_factory):
    """
    Test that the previous and next videos will be retrieved when fetching a video.
    """
    channel1, channel2, channel3, channel4 = channel_factory(), channel_factory(), channel_factory(), channel_factory()

    now_ = now()
    second = timedelta(seconds=1)

    # The upload_date decides the order of the prev/next videos.
    video_factory(title='vid1', channel_id=channel1.id, upload_date=now_)
    video_factory(title='vid2', channel_id=channel1.id, upload_date=now_ + second)
    video_factory(title='vid3', channel_id=channel2.id, upload_date=now_ + (second * 4))
    video_factory(title='vid4', channel_id=channel1.id, upload_date=now_ + (second * 3))
    video_factory(title='vid5', channel_id=channel2.id, upload_date=now_ + (second * 2))
    video_factory(title='vid6', channel_id=channel2.id, upload_date=now_ + (second * 5))
    video_factory(title='vid7', channel_id=channel1.id)
    video_factory(title='vid8', channel_id=channel2.id, upload_date=now_ + (second * 7))
    video_factory(title='vid9', channel_id=channel3.id, upload_date=now_ + (second * 8))
    # Videos without an upload date can't be placed.
    video_factory(title='vid10', channel_id=channel4.id)
    video_factory(title='vid11', channel_id=channel4.id)

    test_session.commit()

    tests = [
        # Channel 1's videos were inserted in upload_date order.
        (1, (None, 'vid2')),
        (2, ('vid1', 'vid4')),
        (4, ('vid2', None)),  # 7 has no upload_date, so it doesn't come after 4.
        (7, (None, None)),  # 7 has no upload_date, so we don't know the order of it.
        # Channel 3 has only one video.
        (9, (None, None)),
        # Channel 2 was inserted out of order.
        (5, (None, 'vid3')),
        (3, ('vid5', 'vid6')),
        (8, ('vid6', None)),
        # Channel 4's videos have no upload date, so we don't know what is previous/next.
        (10, (None, None)),
    ]

    for id_, (prev_title, next_title) in tests:
        video = test_session.query(Video).filter_by(id=id_).one()
        prev_video, next_video = video.get_surrounding_videos()

        try:
            if prev_title is None:
                assert prev_video is None
            else:
                assert prev_video and prev_video.title == prev_title

            if next_title is None:
                assert next_video is None
            else:
                assert next_video and next_video.title == next_title
        except AssertionError as e:
            raise AssertionError(f'Assert failed for {id_=} {prev_title=} {next_title=}') from e


def test_get_video_for_app(test_session, simple_channel, simple_video):
    vid, prev, next_ = get_video_for_app(simple_video.id)
    assert vid['video']['id'] == simple_video.id


@pytest.mark.asyncio
def test_video_delete(test_client, test_session, test_directory, channel_factory, video_factory):
    """Video.delete() removes the video's files, but leave the DB record."""
    channel1, channel2 = channel_factory(), channel_factory()
    vid1 = video_factory(channel_id=channel1.id, with_video_file=True, with_caption_file=True)
    vid2 = video_factory(channel_id=channel2.id, with_video_file=True, with_info_json=True)
    test_session.commit()

    assert test_session.query(Video).count() == 2

    vid1_video_path, vid1_caption_path = vid1.video_path, vid1.caption_path
    vid2_video_path, vid2_info_json_path = vid2.video_path, vid2.info_json_path

    # No videos have been deleted yet.
    assert vid1_video_path.is_file() and vid1_caption_path.is_file()
    assert vid2_video_path.is_file() and vid2_info_json_path.is_file()
    assert channel1.skip_download_videos is None
    assert channel2.skip_download_videos is None

    request, response = test_client.delete(f'/api/videos/video/{vid1.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Video was added to skip list.
    assert len(channel1.skip_download_videos) == 1
    # Video was deleted.
    assert test_session.query(Video).count() == 1
    assert vid1_video_path.is_file() is False and vid1_caption_path.is_file() is False
    assert vid2_video_path.is_file() and vid2_info_json_path.is_file()

    request, response = test_client.delete(f'/api/videos/video/{vid2.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert test_session.query(Video).count() == 0
    assert vid1_video_path.is_file() is False and vid1_caption_path.is_file() is False
    assert vid2_video_path.is_file() is False and vid2_info_json_path.is_file() is False

    # 3 does not exist.
    request, response = test_client.delete(f'/api/videos/video/3')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Can't parse the ids.
    request, response = test_client.delete(f'/api/videos/video/3,')
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_wrol_mode(test_directory, simple_channel, simple_video, wrol_mode_fixture, test_download_manager):
    """Many methods are blocked when WROL Mode is enabled."""
    channel = dumps(dict(name=simple_channel.name, directory=str(simple_channel.directory)))
    favorite = dumps(dict(video_id=simple_video.id, favorite=True))

    wrol_mode_fixture(True)

    # Can't create, update, or delete a channel.
    _, resp = api_app.test_client.post('/api/videos/channels', content=channel)
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']
    _, resp = api_app.test_client.put(f'/api/videos/channels/{simple_channel.id}', content=channel)
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']
    _, resp = api_app.test_client.delete(f'/api/videos/channels/{simple_channel.id}')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']

    # Can't delete a video
    _, resp = api_app.test_client.delete(f'/api/videos/video/{simple_video.id}')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']

    # Can't refresh or download
    _, resp = api_app.test_client.post('/api/files/refresh')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']
    _, resp = api_app.test_client.post(f'/api/videos/download/{simple_channel.id}')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == API_ERRORS[WROLModeEnabled]['code']

    # THE REST OF THESE METHODS ARE ALLOWED
    _, resp = api_app.test_client.post('/api/videos/favorite', content=favorite)
    assert resp.status_code == HTTPStatus.OK

    assert test_download_manager.stopped.is_set()

    wrol_mode_fixture(False)
    assert not test_download_manager.stopped.is_set()
