import pathlib
from datetime import timedelta
from http import HTTPStatus
from json import dumps
from unittest import mock
from unittest.mock import MagicMock
from uuid import uuid4

from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from modules.videos.video.lib import get_video_for_app
from wrolpi.common import now
from wrolpi.db import get_db_session
from wrolpi.errors import API_ERRORS, WROLModeEnabled
from wrolpi.root_api import api_app
from wrolpi.test.common import wrap_test_db, TestAPI


class TestVideoFunctions(TestAPI):

    @wrap_test_db
    def test_get_video_prev_next(self):
        """
        Test that the previous and next videos will be retrieved when fetching a video.
        """

        with get_db_session(commit=True) as session:
            for _ in range(4):
                session.add(Channel(link=str(uuid4())))
            channel1, channel2, channel3, channel4 = session.query(Channel).all()

            now_ = now()
            second = timedelta(seconds=1)

            # The upload_date decides the order of the prev/next videos.
            session.add(Video(title=f'vid1', channel_id=channel1.id, upload_date=now_))
            session.add(Video(title=f'vid2', channel_id=channel1.id, upload_date=now_ + second))
            session.add(Video(title=f'vid3', channel_id=channel2.id, upload_date=now_ + (second * 4)))
            session.add(Video(title=f'vid4', channel_id=channel1.id, upload_date=now_ + (second * 3)))
            session.add(Video(title=f'vid5', channel_id=channel2.id, upload_date=now_ + (second * 2)))
            session.add(Video(title=f'vid6', channel_id=channel2.id, upload_date=now_ + (second * 5)))
            session.add(Video(title=f'vid7', channel_id=channel1.id))
            session.add(Video(title=f'vid8', channel_id=channel2.id, upload_date=now_ + (second * 7)))
            session.add(Video(title=f'vid9', channel_id=channel3.id, upload_date=now_ + (second * 8)))
            session.add(Video(title=f'vid10', channel_id=channel4.id))
            session.add(Video(title=f'vid11', channel_id=channel4.id))

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
            video = session.query(Video).filter_by(id=id_).one()
            prev_video, next_video = video.get_surrounding_videos()

            if prev_title is None:
                self.assertIsNone(prev_video)
            else:
                self.assertDictContains(prev_video, {'title': prev_title})

            if next_title is None:
                self.assertIsNone(next_video)
            else:
                self.assertDictContains(next_video, {'title': next_title})

    @wrap_test_db
    @create_channel_structure({
        'channel1': ['vid1.mp4']
    })
    def test_wrol_mode(self, tempdir):
        """
        Many methods are blocked when WROL Mode is enabled.
        """
        channel = dumps(dict(name='foo', directory='foo'))
        favorite = dumps(dict(video_id=1, favorite=True))

        with mock.patch('wrolpi.common.wrol_mode_enabled', lambda: True):
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
    @create_channel_structure({
        'channel1': [
            'vid1.mp4',
            'vid1.en.vtt',
        ],
    })
    def test_get_video_for_app(self, tempdir):
        with get_db_session(commit=True) as session:
            vid1 = session.query(Video).one()

        vid, prev, next_ = get_video_for_app(vid1.id)
        self.assertEqual(vid['id'], vid1.id)

    @wrap_test_db
    @create_channel_structure({
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
        with get_db_session(commit=True) as session:
            channel1 = session.query(Channel).filter_by(name='channel1').one()
            channel2 = session.query(Channel).filter_by(name='channel2').one()
            vid1, vid2 = session.query(Video).order_by(Video.video_path).all()
            vid1.source_id = 'foo'
            vid2.source_id = 'bar'

            # No videos have been deleted yet.
            self.assertIsNone(channel1.skip_download_videos)
            self.assertIsNone(channel2.skip_download_videos)
            self.assertTrue((tempdir / 'channel1/vid1.mp4').is_file())

            vid1.delete()

            channel1 = session.query(Channel).filter_by(name='channel1').one()
            # Video was added to skip list.
            self.assertEqual(len(channel1.skip_download_videos), 1)
            # Deleting a video leaves it's entry in the DB, but its files are deleted.
            self.assertEqual(session.query(Video).count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertTrue((tempdir / 'channel2/vid2.mp4').is_file())

            vid2.delete()

            self.assertEqual(session.query(Video).count(), 2)
            self.assertFalse((tempdir / 'channel1/vid1.mp4').is_file())
            self.assertFalse((tempdir / 'channel2/vid2.mp4').is_file())

    def test_events(self):
        request, response = api_app.test_client.get('/api/events')
        self.assertOK(response)
        self.assertGreater(len(response.json['events']), 1)
        self.assertFalse(any(i['is_set'] for i in response.json['events']))

        calls = []

        async def fake_refresh_videos(*a, **kw):
            calls.append((a, kw))

        with mock.patch('modules.videos.api.refresh_videos', fake_refresh_videos), \
                mock.patch('modules.videos.api.refresh_event') as refresh_event:
            refresh_event: MagicMock

            # Cannot start a second refresh while one is running.
            refresh_event.is_set.return_value = True
            request, response = api_app.test_client.post('/api/videos:refresh')
            self.assertCONFLICT(response)

            # Refresh is started, a stream is created
            refresh_event.is_set.return_value = False
            request, response = api_app.test_client.post('/api/videos:refresh')
            self.assertOK(response)
            self.assertEqual(response.json['code'], 'stream-started')
            stream_url: str = response.json['stream_url']
            assert stream_url.startswith('ws://')
            assert calls == [((None,), {})]
            refresh_event.set.assert_called()
