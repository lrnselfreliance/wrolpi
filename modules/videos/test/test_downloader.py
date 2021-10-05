import time
from datetime import timedelta
from queue import Queue
from unittest import mock
from unittest.mock import MagicMock

import pytest

from modules.videos.downloader import update_channels, find_all_missing_videos, download_video
from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from wrolpi.common import today, ProgressReporter
from wrolpi.db import get_db_session
from wrolpi.test.common import wrap_test_db, TestAPI


class FakeYDL:

    @staticmethod
    def extract_info(*a, **kw):
        return {
            'entries': [
                {'id': 1},
            ],
        }


@wrap_test_db
@create_channel_structure(
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

    with get_db_session(commit=True) as session:
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        channel1.url = channel2.url = 'some url'

    with get_db_session() as session:
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        with mock.patch('modules.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # Both channels would have been updated.
            assert update_channel.call_count == 2
            update_channel.assert_any_call(channel1)
            update_channel.assert_any_call(channel2)

    with get_db_session() as session:
        channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
        channel1.next_download = today() + timedelta(days=1)
        session.commit()

        with mock.patch('modules.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # Channel1 is not ready for an update
            update_channel.assert_called_once()
            update_channel.assert_called_with(channel2)

        channel1.next_download = today() + timedelta(days=1)
        channel2.next_download = today() + timedelta(days=1)
        session.commit()

        with mock.patch('modules.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            update_channels(reporter)

            # No channels needed to be updated
            assert update_channel.call_count == 0


class TestDownloader(TestAPI):
    @wrap_test_db
    @create_channel_structure(
        {
            'channel1': ['vid1.mp4'],
            'channel2': ['vid2.mp4']
        },
    )
    def test_find_all_missing_videos(self, tempdir):
        with get_db_session(commit=True) as session:
            channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
            channel1.url = channel2.url = 'some url'
            channel1.info_json = {'entries': [{'id': 'foo'}]}

        # No missing videos
        self.assertEqual([], list(find_all_missing_videos()))

        # Create a video that has no video file.
        with get_db_session(commit=True) as session:
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
                mock.patch('modules.videos.downloader.YoutubeDL', FakeYoutubeDL), \
                mock.patch('modules.videos.downloader.get_absolute_media_path'):
            channel = Channel()
            self.assertRaises(TimeoutError, download_video, channel, {'id': 1})

    # {key: 'daily', text: 'Daily', value: 86400},
    # {key: 'weekly', text: 'Weekly', value: 604800},
    # {key: 'biweekly', text: 'Biweekly', value: 1209600},
    # {key: '30days', text: '30 Days', value: 2592000},
    # {key: '90days', text: '90 Days', value: 7776000},

    @wrap_test_db
    @create_channel_structure(
        {
            'channel1': [],  # More channels than days in a week.
            'channel2': [],
            'channel3': [],
            'channel4': [],
            'channel5': [],
            'channel6': [],
            'channel7': [],
            'channel8': [],
            'channel9': [],
        },
    )
    @mock.patch('modules.videos.downloader.YDL', FakeYDL())
    def test_update_channel_order(self, tempdir):
        q = Queue()
        reporter = ProgressReporter(q, 2)

        # All channels are downloaded weekly.
        with get_db_session(commit=True) as session:
            channels = list(session.query(Channel).order_by(Channel.link).all())
            for channel in channels:
                channel.download_frequency = 604800  # one week
                channel.url = 'some url'
                self.assertEqual(channel.next_download, None)

        # Channels will download on different days the next week.  Except where there are not enough days.
        update_channels(reporter)
        days = [7, 8, 9, 10, 10, 11, 12, 13, 14]
        for days_, channel in zip(days, channels):
            nd, expected = channel.next_download, today() + timedelta(days=days_)
            self.assertEqual(nd, expected, f'Expected {(nd - expected).days} days for {channel}')

        # Even though all channels aren't updated, their order is the same.
        with get_db_session(commit=True):
            channels[0].next_download = None
            channels[1].next_download = None
            channels[4].next_download = None
            channels[8].next_download = None
        update_channels(reporter)
        for days_, channel in zip(days, channels):
            self.assertEqual(channel.next_download, today() + timedelta(days=days_))

        # Multiple frequencies are supported.
        with get_db_session(commit=True) as session:
            frequency_map = {
                'channel1': 604800,  # weekly
                'channel2': 604800,
                'channel3': 1209600,  # bi-weekly
                'channel4': 1209600,
                'channel5': 2592000,  # 30 days
                'channel6': 2592000,
                'channel7': 2592000,
                'channel8': 2592000,
                'channel9': 2592000,
            }
            for channel in channels:
                channel.download_frequency = frequency_map[channel.link]
                channel.next_download = None
        update_channels(reporter)
        days = [10, 14, 21, 28,
                36, 42, 48, 54, 60  # 6 days apart = 30 days / 5
                ]
        for days_, channel in zip(days, channels):
            nd, expected = channel.next_download, today() + timedelta(days=days_)
            self.assertEqual(nd, expected, f'Expected {(nd - expected).days} days for {channel}')
