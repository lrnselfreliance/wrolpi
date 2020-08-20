import pathlib
from datetime import datetime, timedelta
from http import HTTPStatus
from json import dumps
from unittest import mock

from api.api import api_app
from api.db import get_db_context
from api.errors import API_ERRORS, WROLModeEnabled
from api.test.common import wrap_test_db, TestAPI, create_db_structure
from api.videos.video.lib import get_surrounding_videos, delete_video


class TestVideoFunctions(TestAPI):

    @wrap_test_db
    def test_get_video_prev_next(self):
        """
        Test that the previous and next videos will be retrieved when fetching a video.
        """

        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']

            channel1 = Channel().flush()
            channel2 = Channel().flush()
            channel3 = Channel().flush()
            channel4 = Channel().flush()

            now = datetime.utcnow()
            second = timedelta(seconds=1)

            # The upload_date decides the order of the prev/next videos.
            Video(title=f'vid1', channel_id=channel1['id'], upload_date=now).flush()
            Video(title=f'vid2', channel_id=channel1['id'], upload_date=now + second).flush()
            Video(title=f'vid3', channel_id=channel2['id'], upload_date=now + (second * 4)).flush()
            Video(title=f'vid4', channel_id=channel1['id'], upload_date=now + (second * 3)).flush()
            Video(title=f'vid5', channel_id=channel2['id'], upload_date=now + (second * 2)).flush()
            Video(title=f'vid6', channel_id=channel2['id'], upload_date=now + (second * 5)).flush()
            Video(title=f'vid7', channel_id=channel1['id']).flush()
            Video(title=f'vid8', channel_id=channel2['id'], upload_date=now + (second * 7)).flush()
            Video(title=f'vid9', channel_id=channel3['id'], upload_date=now + (second * 8)).flush()
            Video(title=f'vid10', channel_id=channel4['id']).flush()
            Video(title=f'vid11', channel_id=channel4['id']).flush()

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
                video = Video.get_one(id=id_)
                prev_video, next_video = get_surrounding_videos(db, id_, video['channel_id'])

                if prev_title is None:
                    self.assertIsNone(prev_video)
                else:
                    self.assertDictContains(prev_video, {'title': prev_title})

                if next_title is None:
                    self.assertIsNone(next_video)
                else:
                    self.assertDictContains(next_video, {'title': next_title})

    @wrap_test_db
    @create_db_structure({
        'channel1': ['vid1.mp4']
    })
    def test_wrol_mode(self, tempdir):
        """
        Many methods are blocked when WROL Mode is enabled.
        """
        channel = dumps(dict(name='foo', directory='foo'))
        favorite = dumps(dict(video_id=1, favorite=True))

        with mock.patch('api.common.wrol_mode_enabled', lambda: True):
            # Can't create, update, or delete a channel.
            _, resp = api_app.test_client.post('/api/videos/channels', data=channel)
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])
            _, resp = api_app.test_client.put('/api/videos/channels/channel1', data=channel)
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])
            _, resp = api_app.test_client.patch('/api/videos/channels/channel1', data=channel)
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])
            _, resp = api_app.test_client.delete('/api/videos/channels/channel1')
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])

            # Can't delete a video
            _, resp = api_app.test_client.delete('/api/videos/video/1')
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])

            # Can't refresh or download
            _, resp = api_app.test_client.post('/api/videos:refresh')
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])
            _, resp = api_app.test_client.post('/api/videos:download')
            self.assertError(resp, HTTPStatus.FORBIDDEN, API_ERRORS[WROLModeEnabled]['code'])

            # THE REST OF THESE METHODS ARE ALLOWED
            _, resp = api_app.test_client.post('/api/videos:favorite', data=favorite)
            self.assertEqual(resp.status_code, HTTPStatus.OK)

    @wrap_test_db
    @create_db_structure({
        'channel1': [
            'vid1.mp4',
            'vid1.en.vtt',
        ],
        'channel2': [
            'vid2.mp4',
            'vid2.info.json',
        ],
    })
    def test_delete_video(self, tempdir: pathlib.Path):
        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']

            channel1 = Channel.get_one(name='channel1')
            channel2 = Channel.get_one(name='channel2')
            vid1, vid2 = Video.get_where().order_by('video_path ASC')

            # No videos have been deleted yet.
            self.assertIsNone(channel1['skip_download_videos'])
            self.assertIsNone(channel2['skip_download_videos'])
            self.assertTrue((tempdir / 'channel1/vid1.mp4').is_file())

            delete_video(vid1)

            channel1 = Channel.get_one(name='channel1')
            # Video was added to skip list.
            self.assertEqual(len(channel1['skip_download_videos']), 1)
            # Deleting a video leaves it's entry in the DB, but its files are deleted.
            self.assertEqual(Video.count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertTrue((tempdir / 'channel2/vid2.mp4').is_file())

            delete_video(vid2)

            self.assertEqual(Video.count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertFalse((tempdir / 'channel2/vid2.mp4').is_file())

            # A video can be deleted again.  This is because its only marked as deleted.
            delete_video(vid2)
