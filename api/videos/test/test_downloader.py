from datetime import timedelta, date
from queue import Queue
from unittest import mock
from unittest.mock import MagicMock

from api.common import today, ProgressReporter
from api.db import get_db_context
from api.test.common import wrap_test_db, create_db_structure
from api.vars import DEFAULT_DOWNLOAD_FREQUENCY
from api.videos.downloader import update_channels, update_channel, distribute_download_days


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
            update_channels(reporter)

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
            update_channels(reporter)

            # Channel1 is not ready for an update
            update_channel.assert_called_once()
            update_channel.assert_called_with(channel2)

        channel1['next_download'] = today() + timedelta(days=1)
        channel1.flush()
        channel2['next_download'] = today() + timedelta(days=1)
        channel2.flush()

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


@wrap_test_db
@create_db_structure(
    {
        'channel1': [],
        'channel2': [],
        'channel3': [],
        'channel4': [],
        'channel5': [],
        'channel6': [],
        'channel7': [],
        'channel8': [],
        'channel9': [],
        'channel10': [],
    }
)
def test_distribute_download_days(tempdir):
    with get_db_context(commit=True) as (db_conn, db):
        Channel = db['channel']

        curs = db_conn.cursor()
        curs.execute('update channel set download_frequency = %s, next_download = %s', (
            # Weekly downloads.
            60 * 60 * 24 * 7,
            # This will be used as the start of the date range.
            date(2020, 9, 8)
        ))

        # Sometimes a channel hasn't been downloaded, or won't be downloaded.
        channel10 = Channel.get_one(name='channel10')
        channel10['next_download'] = None
        channel10.flush()

    distribute_download_days()

    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        # Next downloads are spread out (as evenly as possible) over the next week.
        next_downloads = sorted([i['next_download'] for i in Channel.get_where(Channel['next_download'].IsNotNull())])
        assert next_downloads == [
            date(2020, 9, 9),
            date(2020, 9, 9),
            date(2020, 9, 10),
            date(2020, 9, 11),
            date(2020, 9, 12),
            date(2020, 9, 12),
            date(2020, 9, 13),
            date(2020, 9, 14),
            date(2020, 9, 15),
        ]
