import json
from datetime import timedelta
from http import HTTPStatus
from json import dumps

import pytest

from modules.videos.models import Video
from wrolpi.dates import now


def test_get_video_prev_next(async_client, test_session, channel_factory, video_factory):
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
        (7, ('vid4', None)),  # 7 has no upload_date, so we get the video next to it's file.
        # Channel 3 has only one video.
        (9, (None, None)),
        # Channel 2 was inserted out of order.
        (5, (None, 'vid3')),
        (3, ('vid5', 'vid6')),
        (8, ('vid6', None)),
        # Channel 4's videos have no upload date, so we don't know what is previous/next.
        (10, (None, 'vid11')),
        (11, ('vid10', None)),
    ]

    for id_, (prev_title, next_title) in tests:
        video = test_session.query(Video).filter_by(id=id_).one()
        prev_video, next_video = video.get_surrounding_videos()

        try:
            if prev_title is None:
                assert prev_video is None
            else:
                assert prev_video and prev_video.file_group.title == prev_title

            if next_title is None:
                assert next_video is None
            else:
                assert next_video and next_video.file_group.title == next_title
        except AssertionError as e:
            raise AssertionError(f'Assert failed for {id_=} {prev_title=} {next_title=}') from e


def test_get_video_prev_next_no_upload_date(async_client, test_session, video_factory, channel_factory):
    """
    Previous and Next Videos should be those next to a Video file when videos do not have upload dates.
    """
    channel1, channel2 = channel_factory(), channel_factory()
    vid0, vid1, vid2, vid3, vid4, vid5 = video_factory(channel2.id, title='vid0'), \
        video_factory(channel1.id, title='vid1'), \
        video_factory(channel1.id, title='vid2'), \
        video_factory(channel1.id, title='vid3'), \
        video_factory(title='vid4'), \
        video_factory(title='vid5')
    test_session.commit()

    # Channel 2 has only 1 video.
    prev, next_ = vid0.get_surrounding_videos()
    assert prev is None
    assert next_ is None

    # Channel 1 has 3 videos, finally getting surrounding videos.
    prev, next_ = vid1.get_surrounding_videos()
    assert prev is None
    assert next_ == vid2
    prev, next_ = vid2.get_surrounding_videos()
    assert prev == vid1
    assert next_ == vid3
    prev, next_ = vid3.get_surrounding_videos()
    assert prev == vid2
    assert next_ is None

    # Videos without a channel
    prev, next_ = vid4.get_surrounding_videos()
    assert prev is None
    assert next_ is vid5
    prev, next_ = vid5.get_surrounding_videos()
    assert prev == vid4
    assert next_ is None


@pytest.mark.asyncio
async def test_delete_video_api(async_client, test_session, channel_factory, video_factory, test_download_manager):
    """Video.delete() removes the video's files, but leave the DB record."""
    channel1, channel2 = channel_factory(), channel_factory()
    vid1 = video_factory(channel_id=channel1.id, with_video_file=True, with_caption_file=True,
                         with_info_json={'url': '1'})
    vid2 = video_factory(channel_id=channel2.id, with_video_file=True, with_info_json={'url': '2'})
    test_session.commit()

    assert test_session.query(Video).count() == 2

    vid1_video_path, vid1_caption_path = vid1.video_path, vid1.caption_paths[0]
    vid2_video_path, vid2_info_json_path = vid2.video_path, vid2.info_json_path

    # No videos have been deleted yet.
    assert vid1_video_path.is_file() and vid1_caption_path.is_file()
    assert vid2_video_path.is_file() and vid2_info_json_path.is_file()

    request, response = await async_client.delete(f'/api/videos/video/{vid1.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Video was added to skip list.
    assert test_download_manager.is_skipped(vid1.file_group.url)
    # Video was deleted.
    assert test_session.query(Video).count() == 1
    assert vid1_video_path.is_file() is False and vid1_caption_path.is_file() is False
    assert vid2_video_path.is_file() and vid2_info_json_path.is_file()

    request, response = await async_client.delete(f'/api/videos/video/{vid2.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert test_download_manager.is_skipped(vid1.file_group.url, vid2.file_group.url)
    assert test_session.query(Video).count() == 0
    assert vid1_video_path.is_file() is False and vid1_caption_path.is_file() is False
    assert vid2_video_path.is_file() is False and vid2_info_json_path.is_file() is False

    # 3 does not exist.
    request, response = await async_client.delete(f'/api/videos/video/3')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_wrol_mode(async_client, simple_channel, simple_video, wrol_mode_fixture,
                         test_download_manager, tag_factory):
    """Many methods are blocked when WROL Mode is enabled."""
    channel = dumps(dict(name=simple_channel.name, directory=str(simple_channel.directory)))
    tag = await tag_factory()

    await wrol_mode_fixture(True)

    # Can't create, update, or delete a channel.
    _, resp = await async_client.post('/api/videos/channels', content=channel)
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == 'WROL_MODE_ENABLED'
    _, resp = await async_client.put(f'/api/videos/channels/{simple_channel.id}', content=channel)
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == 'WROL_MODE_ENABLED'
    _, resp = await async_client.delete(f'/api/videos/channels/{simple_channel.id}')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == 'WROL_MODE_ENABLED'

    # Can't delete a video
    _, resp = await async_client.delete(f'/api/videos/video/{simple_video.id}')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == 'WROL_MODE_ENABLED'

    # Can't refresh
    _, resp = await async_client.post('/api/files/refresh')
    assert resp.status_code == HTTPStatus.FORBIDDEN
    assert resp.json['code'] == 'WROL_MODE_ENABLED'

    # THE REST OF THESE METHODS ARE ALLOWED
    content = dict(file_group_id=simple_video.file_group_id, tag_name=tag.name)
    _, resp = await async_client.post('/api/files/tag', content=json.dumps(content))
    assert resp.status_code == HTTPStatus.CREATED

    assert test_download_manager.stopped.is_set()

    await wrol_mode_fixture(False)
    assert not test_download_manager.stopped.is_set()


@pytest.mark.asyncio
async def test_api_video_extras(async_client, simple_channel, video_factory):
    """Can fetch extra data about a video (comments/captions)."""
    info_json = {'duration': 5, 'epoch': 12345, 'comments': [{'some': 'comments'}]}
    video = video_factory(simple_channel.id, with_info_json=info_json, with_caption_file=True)

    request, response = await async_client.get(f'/api/videos/video/{video.id}/captions')
    assert response.status_code == HTTPStatus.OK
    assert response.json.get('captions')

    request, response = await async_client.get(f'/api/videos/video/{video.id}/comments')
    assert response.status_code == HTTPStatus.OK
    assert response.json.get('comments')

    request, response = await async_client.get('/api/videos/video/123/captions')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = await async_client.get('/api/videos/video/123/comments')
    assert response.status_code == HTTPStatus.NOT_FOUND
