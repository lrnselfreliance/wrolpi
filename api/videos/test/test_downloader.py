import unittest
from datetime import timedelta
from queue import Queue
from unittest import mock
from unittest.mock import MagicMock

from api.common import today, ProgressReporter
from api.db import get_db_context
from api.test.common import wrap_test_db, create_db_structure
from api.vars import DEFAULT_DOWNLOAD_FREQUENCY
from api.videos.downloader import update_channels, update_channel, find_all_missing_videos
from api.videos.models import Channel, Video


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


@wrap_test_db
@create_db_structure(
    {
        'channel1': ['vid1.mp4'],
    },
)
def test_update_channel(tempdir):
    with get_db_context(commit=True) as (engine, session):
        channel = session.query(Channel).one()
        channel.download_frequency = DEFAULT_DOWNLOAD_FREQUENCY
        assert channel.next_download is None

    with mock.patch('api.videos.downloader.YDL') as YDL:
        YDL.extract_info.return_value = {
            'entries': [],
        }
        update_channel(channel)

        with get_db_context() as (engine, session):
            channel = session.query(Channel).one()
            # After and update, the next_download should be incremented by the download_frequency.
            assert channel.next_download > today()


class TestDownloader(unittest.TestCase):
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
