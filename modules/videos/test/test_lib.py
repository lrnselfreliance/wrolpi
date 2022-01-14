import json
import pathlib
import shutil
from datetime import datetime
from unittest import mock

import pytest
import sqlalchemy

from modules.videos.channel import lib
from modules.videos.common import apply_info_json
from modules.videos.lib import validate_videos, parse_video_file_name
from modules.videos.models import Channel, Video
from modules.videos.video.lib import video_search
from wrolpi.dates import local_timezone
from wrolpi.downloader import DownloadFrequency
from wrolpi.vars import PROJECT_DIR

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


def test_validate_videos(test_session, simple_channel, video_factory):
    """
    Videos that aren't validated should have their data filled in while being validated.
    """
    simple_channel.generate_posters = True

    vid1_json = {'title': 'info&apos;s title'}
    vid3_json = {'duration': 100}
    vid5_json = {'view_count': 42}
    vid6_json = {'webpage_url': 'https://example.com/webpage', 'url': 'https://example.com/url'}

    vid1 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=vid1_json)
    vid2 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=True)
    vid3 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=vid3_json)
    vid4 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=True)
    vid5 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=vid5_json)
    vid6 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg', with_info_json=vid6_json)
    vid7 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='jpg')
    vid8 = video_factory(simple_channel.id, with_video_file=True, with_poster_ext='webp')
    vid9 = video_factory(simple_channel.id, with_video_file=True)

    # These videos are missing this data, and a refresh should fill them in.
    vid1.title = None
    vid2.caption = None
    vid2.title = None
    vid3.duration = None
    vid4.size = None
    vid5.view_count = None
    vid6.url = None
    vid7.poster_path = None
    test_session.commit()

    # Write the associated files.  This data should be processed.
    vid2.caption_path = vid2.video_path.path.with_suffix('.en.vtt')
    shutil.copy(PROJECT_DIR / 'test/example1.en.vtt', vid2.caption_path)
    test_session.commit()

    # All Videos are validated, all data is filled out.  The info json data is trusted first.
    validate_videos()
    assert all([i.validated for i in test_session.query(Video)])
    assert vid1.title == "info's title"
    assert vid2.caption.startswith('okay welcome')
    assert 'mp4' not in vid2.title
    assert vid3.duration == 100
    assert vid4.size == 1055736
    assert vid5.view_count == 42
    assert vid6.url == 'https://example.com/webpage'
    assert str(vid7.poster_path).endswith('.jpg')
    assert str(vid8.poster_path).endswith('.jpg')
    assert str(vid9.poster_path).endswith('.jpg')  # this was generated from the video file.

    vid1.title = None
    vid3.duration = None
    vid5.view_count = None
    vid6.url = None
    vid9.poster_path = None
    test_session.commit()

    # Validation does not happen because all are still validated.
    validate_videos()

    # All videos need to be validated again.
    for i in test_session.query(Video):
        i.validated = False
    # Use backup methods to fetch data.
    vid1.info_json_path = None
    vid3.info_json_path = None
    vid5.info_json_path = None
    vid6.info_json_path.path.write_text(json.dumps({'url': 'https://example.com/url'}))
    test_session.commit()

    validate_videos()
    assert all([i.validated for i in test_session.query(Video)])
    assert vid1.title != "info's title"  # file name is used.
    assert vid3.duration == 5  # video file duration is used.
    assert vid5.view_count is None
    assert vid6.url == 'https://example.com/url'  # url is used as backup url.
    # Posters are both JPEG format.  Webp file is removed.
    assert vid7.poster_path.path.is_file()
    assert vid8.poster_path.path.is_file()
    assert not vid8.poster_path.path.with_suffix('.webp').is_file()
    assert str(vid9.poster_path).endswith('.jpg')  # the generated file was rediscovered.


def test_validate_video_exception(test_session, simple_channel, video_factory):
    """
    Test that even if a Video cannot be validated, the other Videos will still be validated.
    """
    vid1 = video_factory(simple_channel.id, with_video_file=True)
    vid2 = video_factory(simple_channel.id, with_video_file=True)
    # The validator should not even check this Video because it does not have a video file.
    vid3 = video_factory(simple_channel.id)
    vid3.video_path = None
    assert not all([i.validated for i in test_session.query(Video)])
    test_session.commit()

    with mock.patch('modules.videos.lib.process_video_info_json') as mock_process_video_info_json:
        mock_process_video_info_json.side_effect = [
            Exception('skip this video'),
            (None, None, None, None),
            ('should not be set to video 3', None, None, None),  # This should not be called!
        ]
        validate_videos()
        # Only first two videos are validated.
        assert mock_process_video_info_json.call_count == 2, mock_process_video_info_json.call_count
    test_session.commit()

    assert not vid1.validated
    assert vid2.validated
    assert not vid3.validated


@pytest.mark.parametrize('file_name,expected', [
    ('channel_20000101_12345678910_ some title.mp4', ('channel', '20000101', '12345678910', 'some title')),
    ('channel name_NA_12345678910_ some title.mp4', ('channel name', None, '12345678910', 'some title')),
    ('20000101 foo.mp4', (None, None, None, '20000101 foo')),
    ('20000101foo.mp4', (None, None, None, '20000101foo')),
    ('something 20000101 foo.mp4', (None, None, None, 'something 20000101 foo')),
    ('something_20000101_foo.mp4', ('something', '20000101', None, 'foo')),
    ('foo .mp4', (None, None, None, 'foo')),
    ('NA_20000303_vp91w5_Bob&apos;s Pancakes.mp4', (None, '20000303', 'vp91w5', 'Bob&apos;s Pancakes')),
    ('NA_NA_vp91w5_Bob&apos;s Pancakes.mp4', (None, None, 'vp91w5', 'Bob&apos;s Pancakes')),
])
def test_parse_video_file_name(file_name, expected):
    """
    A Video's title can be parsed from the video file.
    """
    video_path = pathlib.Path(file_name)
    assert parse_video_file_name(video_path) == expected, f'{file_name} != {expected}'


def test_validate_does_not_generate_when_disabled(test_session, channel_factory, video_factory):
    """
    A poster should not be generated if the Video's Channel forbids it.
    """
    channel1 = channel_factory()  # posters should not be generated by default.
    channel2 = channel_factory()
    channel2.generate_posters = True
    vid1 = video_factory(channel1.id, with_video_file=True)
    vid2 = video_factory(channel2.id, with_video_file=True)
    # webp will not be converted unless generate_posters is enabled.
    vid3 = video_factory(channel1.id, with_video_file=True, with_poster_ext='webp')
    test_session.commit()
    assert not vid1.poster_path
    assert not vid2.poster_path
    assert str(vid3.poster_path).endswith('webp')

    validate_videos()

    assert not vid1.poster_path
    assert vid2.poster_path
    assert str(vid3.poster_path).endswith('webp')
