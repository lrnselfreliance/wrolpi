from datetime import datetime
from unittest import mock

import pytest
import sqlalchemy

from modules.videos.channel import lib
from modules.videos.common import apply_info_json
from modules.videos.models import Channel, Video
from modules.videos.video.lib import video_search
from wrolpi.dates import local_timezone
from wrolpi.downloader import DownloadFrequency

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


def test_search_censored_videos(test_session, simple_channel):
    for i in map(str, range(50)):
        test_session.add(Video(source_id=i, channel=simple_channel, video_path='foo'))
    vid = Video(source_id='51', video_path='bar')  # this should never be modified because it has no channel
    test_session.add(vid)
    test_session.commit()

    def set_entries(entries):
        simple_channel.info_json = {
            'entries': [{'id': j, 'view_count': 0} for j in entries]} if entries else sqlalchemy.null()
        test_session.commit()
        apply_info_json(simple_channel.id)
        test_session.commit()

    # All source_ids are in the entries.
    set_entries(map(str, range(50)))
    videos, total = video_search(filters=['censored'], order_by='id')
    assert [i['source_id'] for i in videos] == []
    assert total == 0

    # First 5 are censored.
    set_entries(map(str, range(5, 50)))
    videos, total = video_search(filters=['censored'], order_by='id')
    assert [i['source_id'] for i in videos] == [str(i) for i in range(5)]
    assert total == 5

    # First 25 are censored.
    set_entries(map(str, range(25, 50)))
    videos, total = video_search(filters=['censored'], order_by='id')
    assert [i['source_id'] for i in videos] == [str(i) for i in range(20)]
    assert total == 25
