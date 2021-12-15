from datetime import datetime
from unittest import mock

import pytest

from modules.videos.channel import lib
from modules.videos.models import Channel
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
