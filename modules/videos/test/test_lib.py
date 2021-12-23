from datetime import datetime
from unittest import mock

import pytest
import sqlalchemy

from modules.videos.channel import lib
from modules.videos.models import Channel, Video
from modules.videos.video.lib import _censored_source_ids, video_search
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
    assert _censored_source_ids(channel1.link) == set()

    # "foo" is censored.
    set_entries(['bar'], ['qux', 'quux', 'quuz'])
    assert _censored_source_ids(channel1.link) == {'foo'}
    assert _censored_source_ids() == {'foo'}

    # channel1 has no info_json.
    set_entries(None, ['qux', 'quux', 'quuz'])
    assert _censored_source_ids(channel1.link) == set()

    # Censor channel2 and channel1.
    set_entries(['bar'], ['quuz'])
    assert _censored_source_ids() == {'foo', 'qux', 'quux'}
    assert _censored_source_ids(channel1.link) == {'foo', }
    assert _censored_source_ids(channel2.link) == {'qux', 'quux'}

    # channel 1 has no info_json
    set_entries(None, ['quuz'])
    assert _censored_source_ids() == {'qux', 'quux'}
    assert _censored_source_ids(channel1.link) == set()
    assert _censored_source_ids(channel2.link) == {'qux', 'quux'}

    # channel 2 has no entries
    set_entries(None, [])
    assert _censored_source_ids() == set()
    assert _censored_source_ids(channel2.link) == set()


def test_search_censored_videos(test_session, simple_channel):
    for i in map(str, range(50)):
        test_session.add(Video(source_id=i, channel=simple_channel, video_path='foo'))
    test_session.commit()

    def set_entries(entries):
        simple_channel.info_json = {'entries': [{'id': j} for j in entries]} if entries else sqlalchemy.null()
        test_session.commit()

    # All source_ids are in the entries.
    set_entries(map(str, range(50)))
    videos, total = video_search(filters=['censored'])
    assert [i['source_id'] for i in videos] == []
    assert total == 0

    # First 5 are censored.
    set_entries(map(str, range(5, 50)))
    videos, total = video_search(filters=['censored'])
    assert [i['source_id'] for i in videos] == [str(i) for i in range(5)]
    assert total == 5

    # First 25 are censored.
    set_entries(map(str, range(25, 50)))
    videos, total = video_search(filters=['censored'])
    assert [i['source_id'] for i in videos] == [str(i) for i in range(20)]
    assert total == 25


def test_censored_videos_no_channel(test_session):
    with pytest.raises(UnknownChannel):
        _censored_source_ids('foo')
