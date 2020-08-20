from datetime import timedelta
from unittest import mock
from unittest.mock import MagicMock

from api.common import today
from api.db import get_db_context
from api.test.common import wrap_test_db, create_db_structure
from api.vars import DEFAULT_DOWNLOAD_FREQUENCY
from api.videos.downloader import update_channels, update_channel


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
    with get_db_context(commit=True) as (db_conn, db):
        Channel = db['channel']
        channel1, channel2 = Channel.get_where().order_by('id')
        channel1['url'] = channel2['url'] = 'some url'
        channel1.flush()
        channel2.flush()

    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel1, channel2 = Channel.get_where().order_by('id')
        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            # update_channels() is a generator, call it and fetch all of it's results.
            assert list(update_channels()), 'update_channels() was empty'

            # Both channels would have been updated.
            assert update_channel.call_count == 2
            update_channel.assert_any_call(channel1)
            update_channel.assert_any_call(channel2)

    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel1, channel2 = Channel.get_where().order_by('id')
        channel1['next_download'] = today() + timedelta(days=1)
        channel1.flush()

        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            assert list(update_channels()), 'update_channels() was empty'

            # Channel1 is not ready for an update
            update_channel.assert_called_once()
            update_channel.assert_called_with(channel2)

        channel1['next_download'] = today() + timedelta(days=1)
        channel1.flush()
        channel2['next_download'] = today() + timedelta(days=1)
        channel2.flush()

        with mock.patch('api.videos.downloader.update_channel') as update_channel:
            update_channel: MagicMock
            assert list(update_channels()), 'update_channels() was empty'

            # No channels needed to be updated
            assert update_channel.call_count == 0


@wrap_test_db
@create_db_structure(
    {
        'channel1': ['vid1.mp4'],
    },
)
def test_update_channel(tempdir):
    with get_db_context(commit=True) as (db_conn, db):
        Channel = db['channel']
        channel = Channel.get_one()
        channel['download_frequency'] = DEFAULT_DOWNLOAD_FREQUENCY
        assert channel['next_download'] is None
        channel.flush()

    with mock.patch('api.videos.downloader.YDL') as YDL:
        YDL.extract_info.return_value = {
            'entries': [],
        }
        update_channel(channel)

        with get_db_context() as (db_conn, db):
            Channel = db['channel']
            channel = Channel.get_one()
            # After and update, the next_download should be incremented by the download_frequency.
            assert channel['next_download'] > today()
