import time
from datetime import timedelta
from queue import Queue
from unittest import mock
from unittest.mock import MagicMock

import pytest

from api.common import today, ProgressReporter
from api.db import get_db_context
from api.test.common import wrap_test_db, create_db_structure, TestAPI
from api.videos.common import load_channels_config
from api.videos.downloader import update_channels, find_all_missing_videos, download_all_missing_videos, \
    download_video
from api.videos.lib import save_channels_config
from api.videos.models import Channel, Video


class FakeYDL:

    @staticmethod
    def extract_info(*a, **kw):
        return {
            'entries': [
                {'id': 1},
            ],
        }


@wrap_test_db
@create_db_structure(
    {
        'channel1': ['vid1.mp4'],
        'channel2': ['vid2.mp4']
    },
)
def test_update_channels(tempdir):
    """
    Channels are only updated if their "next_download" has expired, or if they have never been updated.
    """
    q = Queue()
    reporter = ProgressReporter(q, 2)

    with get_db_context(commit=True) as (engine, session):
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        channel1.url = channel2.url = 'some url'

    with get_db_context() as (engine, session):
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # Both channels would have been updated.
            assert update_channel.call_count == 2
            update_channel.assert_any_call(channel1)
            update_channel.assert_any_call(channel2)

    with get_db_context() as (engine, session):
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        channel1.next_download = today() + timedelta(days=1)
        session.commit()

        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # Channel1 is not ready for an update
            update_channel.assert_called_once()
            update_channel.assert_called_with(channel2)

        channel1.next_download = today() + timedelta(days=1)
        channel2.next_download = today() + timedelta(days=1)
        session.commit()

        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # No channels needed to be updated
            assert update_channel.call_count == 0


class TestDownloader(TestAPI):
    @wrap_test_db
    @create_db_structure(
        {
            'channel1': ['vid1.mp4'],
            'channel2': ['vid2.mp4']
        },
    )
    def test_find_all_missing_videos(self, tempdir):
        with get_db_context(commit=True) as (engine, session):
            channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
            channel1.url = channel2.url = 'some url'
            channel1.info_json = {'entries': [{'id': 'foo'}]}

        # No missing videos
        self.assertEqual([], list(find_all_missing_videos()))

        # Create a video that has no video file.
        with get_db_context(commit=True) as (engine, session):
            video = Video(title='needs to be downloaded', channel_id=channel1.id, source_id='foo')
            session.add(video)

        missing = list(find_all_missing_videos())
        self.assertEqual(len(missing), 1)

        # The video returned is the one we faked.
        channel, id_, entry = missing[0]
        self.assertEqual(channel, channel1)
        # Two videos were created for this test already.
        self.assertEqual(id_, 3)
        # The fake entry we added is regurgitated back.
        self.assertEqual(entry, channel1.info_json['entries'][0])

    @wrap_test_db
    def test_skip_committed(self):
        q = Queue()
        r = ProgressReporter(q, 2)

        with get_db_context(commit=True) as (engine, session):
            channel = Channel(link='channel')
            video = dict(title='foo', id=1)
            session.add(channel)

        # Save the config without the skipped video
        save_channels_config()
        config = load_channels_config()
        self.assertEqual(config['channel']['skip_download_videos'], [])

        def _find_all_missing_videos(*a, **kw):
            return [(channel, video['id'], video)]

        def _download_video(*a, **kw):
            raise Exception('Force the video to be skipped with unrecoverable error: 404: Not Found')

        with mock.patch('api.videos.downloader.find_all_missing_videos', _find_all_missing_videos), \
                mock.patch('api.videos.downloader.download_video', _download_video):
            download_all_missing_videos(r)

        with get_db_context() as (engine, session):
            channel = session.query(Channel).one()
            self.assertIn('1', channel.skip_download_videos)

            config = load_channels_config()
            self.assertEqual(config['channel']['skip_download_videos'], ['1'])

    @pytest.mark.skip
    def test_download_timeout(self):
        class FakeYoutubeDL:
            def __init__(self, *a, **kw):
                pass

            def add_default_info_extractors(self):
                pass

            def extract_info(self, *a, **kw):
                # Sleep longer than the 1 second timeout.
                for i in range(10):
                    time.sleep(1)

        with mock.patch('api.timeout.TEST_TIMEOUT', 1), \
                mock.patch('api.videos.downloader.YoutubeDL', FakeYoutubeDL), \
                mock.patch('api.videos.downloader.get_absolute_media_path'):
            channel = Channel()
            self.assertRaises(TimeoutError, download_video, channel, {'id': 1})

    # {key: 'daily', text: 'Daily', value: 86400},
    # {key: 'weekly', text: 'Weekly', value: 604800},
    # {key: 'biweekly', text: 'Biweekly', value: 1209600},
    # {key: '30days', text: '30 Days', value: 2592000},
    # {key: '90days', text: '90 Days', value: 7776000},

    @wrap_test_db
    @create_db_structure(
        {
            'channel1': ['vid1.mp4'],
            'channel2': ['vid2.mp4'],
            'channel3': ['vid3.mp4'],
            'channel4': ['vid4.mp4'],
            'channel5': ['vid5.mp4'],
        },
    )
    @mock.patch('api.videos.downloader.YDL', FakeYDL())
    def test_update_channel_order(self, tempdir):
        q = Queue()
        reporter = ProgressReporter(q, 2)

        # All channels are downloaded weekly.
        with get_db_context(commit=True) as (engine, session):
            channels = list(session.query(Channel).order_by(Channel.link).all())
            for channel in channels:
                channel.download_frequency = 604800  # one week
                channel.url = 'some url'
                self.assertEqual(channel.next_download, None)

        # Channels will download on different days the next week.
        update_channels(reporter)
        days = [8, 9, 11, 12, 14]
        for days_, channel in zip(days, channels):
            self.assertEqual(channel.next_download, today() + timedelta(days=days_))

        # Even though all channels aren't updated, their order is the same.
        with get_db_context(commit=True):
            channels[0].next_download = None
            channels[1].next_download = None
            channels[4].next_download = None
        update_channels(reporter)
        for days_, channel in zip(days, channels):
            self.assertEqual(channel.next_download, today() + timedelta(days=days_))

        # Multiple frequencies are supported.
        with get_db_context(commit=True) as (engine, session):
            frequency_map = {
                'channel1': 604800,  # weekly
                'channel2': 604800,
                'channel3': 1209600,  # bi-weekly
                'channel4': 1209600,
                'channel5': 2592000,  # 30 days
            }
            for channel in channels:
                channel.download_frequency = frequency_map[channel.link]
                channel.next_download = None
        update_channels(reporter)
        days = [10, 14, 21, 28, 60]
        for days_, channel in zip(days, channels):
            self.assertEqual(channel.next_download, today() + timedelta(days=days_))
