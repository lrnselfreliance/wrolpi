from datetime import datetime, timedelta
from unittest import mock

import pytest
import sqlalchemy

from modules.videos.channel import lib
from modules.videos.models import Channel, Video
from modules.videos.video.lib import censored_videos
from wrolpi.dates import local_timezone
from wrolpi.downloader import DownloadFrequency
from wrolpi.errors import UnknownChannel

daily, weekly, days30 = DownloadFrequency.daily, DownloadFrequency.weekly, DownloadFrequency.days30


@pytest.mark.parametrize(
    'channels,expected',
    [
        ([Channel(download_frequency=daily, url='https://example.com/1')],
         [('https://example.com/1', daily, '2000-01-02 00:00:00-07:00')]
         ),
        # Several different download frequencies.
        ([
             Channel(download_frequency=daily, url='https://example.com/1'),
             Channel(download_frequency=daily, url='https://example.com/2'),
             Channel(download_frequency=daily, url='https://example.com/3'),
             Channel(download_frequency=weekly, url='https://example.com/4'),
             Channel(download_frequency=weekly, url='https://example.com/5'),
             Channel(download_frequency=days30, url='https://example.com/6'),
         ],
         [
             ('https://example.com/1', daily, '2000-01-02 00:00:00-07:00'),
             ('https://example.com/2', daily, '2000-01-02 08:00:00-07:00'),
             ('https://example.com/3', daily, '2000-01-02 16:00:00-07:00'),
             ('https://example.com/4', weekly, '2000-01-08 00:00:00-07:00'),
             ('https://example.com/5', weekly, '2000-01-11 12:00:00-07:00'),
             ('https://example.com/6', days30, '2000-01-31 00:00:00-07:00'),
         ]
        ),
        # Multiple downloads in a day.
        ([Channel(download_frequency=daily, url=f'https://example.com/{i}') for i in range(1, 3)],
         [
             ('https://example.com/1', daily, '2000-01-02 00:00:00-07:00'),
             ('https://example.com/2', daily, '2000-01-02 12:00:00-07:00'),
         ]
         ),
        # More downloads in a week than days in a week.
        ([Channel(download_frequency=weekly, url=f'https://example.com/{i}') for i in range(1, 9)],
         [
             ('https://example.com/1', weekly, '2000-01-08 00:00:00-07:00'),
             ('https://example.com/2', weekly, '2000-01-08 21:00:00-07:00'),
             ('https://example.com/3', weekly, '2000-01-09 18:00:00-07:00'),
             ('https://example.com/4', weekly, '2000-01-10 15:00:00-07:00'),
             ('https://example.com/5', weekly, '2000-01-11 12:00:00-07:00'),
             ('https://example.com/6', weekly, '2000-01-12 09:00:00-07:00'),
             ('https://example.com/7', weekly, '2000-01-13 06:00:00-07:00'),
             ('https://example.com/8', weekly, '2000-01-14 03:00:00-07:00'),
         ]
         ),
        # Any Channel without a URL AND frequency is ignored.
        ([
             Channel(download_frequency=daily, url='https://example.com/1'),
             Channel(download_frequency=daily),
             Channel(url='this should be ignored'),
         ],
         [('https://example.com/1', daily, '2000-01-02 00:00:00-07:00')]
        ),
    ]
)
@mock.patch('modules.videos.channel.lib.today', lambda: local_timezone(datetime(2000, 1, 1, 0, 0, 0)))
def test_spread_by_frequency(channels, expected):
    result = lib._spread_by_frequency(channels)
    for result, (expected_url, expected_frequency, expected_dt) in zip(result, expected):
        assert result['url'] == expected_url
        assert result['frequency'] == expected_frequency
        assert str(result['next_download']) == expected_dt


def test_censored_videos(test_session, channel_factory):
    """
    Censored videos can be found by comparing the videos we have versus what is listed in the Channel's catalog.
    """
    channel1 = channel_factory()
    channel2 = channel_factory()

    channel1.info_json = {'entries': [
        {'id': 'foo'},
        {'id': 'bar'},
    ]}
    channel2.info_json = {'entries': [
        {'id': 'qux'},
        {'id': 'quux'},
        {'id': 'quuz'},
    ]}
    vid1 = Video(source_id='foo', channel=channel1)
    vid2 = Video(source_id='bar', channel=channel1)
    vid3 = Video(source_id='baz')  # Without a channel, this will never be returned.
    vid4 = Video(source_id='qux', channel=channel2)
    vid5 = Video(source_id='quux', channel=channel2)
    vid6 = Video(source_id='quuz', channel=channel2)
    test_session.add_all([vid1, vid2, vid3, vid4, vid5, vid6])
    test_session.commit()

    def set_entries(channel1_entries, channel2_entries):
        channel1.info_json = {'entries': [{'id': i} for i in channel1_entries]} if channel1_entries else \
            sqlalchemy.null()
        channel2.info_json = {'entries': [{'id': i} for i in channel2_entries]} if channel2_entries else \
            sqlalchemy.null()
        test_session.commit()

    # All source_id's are in "entries".
    set_entries(['foo', 'bar'], ['qux', 'quux', 'quuz'])
    assert censored_videos(channel1.link) == []

    # One video was removed from the catalog.
    set_entries(['bar'], ['qux', 'quux', 'quuz'])
    assert censored_videos(channel1.link) == [vid1, ]
    assert censored_videos() == [vid1, ]
    assert censored_videos(channel2.link) == []

    # channel1 has no info_json.
    set_entries(None, ['qux', 'quux', 'quuz'])
    assert censored_videos(channel1.link) == []

    # Censor channel2 and channel1.
    set_entries(['bar'], ['quuz'])
    assert censored_videos() == [vid1, vid4, vid5]
    assert censored_videos(channel1.link) == [vid1, ]
    assert censored_videos(channel2.link) == [vid4, vid5]

    # channel 1 has no info_json
    set_entries(None, ['quuz'])
    assert censored_videos() == [vid4, vid5]
    assert censored_videos(channel1.link) == []
    assert censored_videos(channel2.link) == [vid4, vid5]

    # channel 2 has no entries
    set_entries(None, [])
    assert censored_videos() == []
    assert censored_videos(channel2.link) == []


def test_censored_videos_limit(test_session, channel_factory):
    channel1 = channel_factory()
    source_ids = []
    for i in range(50):
        source_ids.append(str(i))
        upload_date = local_timezone(datetime(2000, 1, 1, 0, 0, 0) + timedelta(days=i))
        test_session.add(Video(source_id=str(i), channel=channel1, upload_date=upload_date))
    # All videos are censored.
    channel1.info_json = {'entries': []}
    test_session.commit()

    assert len(censored_videos()) == 20
    assert [i.source_id for i in censored_videos()] == list(map(str, range(20)))

    assert [i.source_id for i in censored_videos(offset=20)] == list(map(str, range(20, 40)))


def test_censored_videos_no_channel(test_session):
    with pytest.raises(UnknownChannel):
        censored_videos('foo')
