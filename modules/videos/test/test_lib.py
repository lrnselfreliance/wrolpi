import pathlib
import shutil
from http import HTTPStatus

import pytest

from modules.videos import lib
from modules.videos.downloader import ChannelDownloader, VideoDownloader
from modules.videos.lib import parse_video_file_name, validate_video, get_statistics, format_videos_destination
from modules.videos.models import Video, Channel
from wrolpi.common import get_wrolpi_config
from wrolpi.downloader import Download, RSSDownloader
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR


@pytest.mark.parametrize('file_name,expected', [
    ('channel_20000101_12345678910_ some title.mp4', ('channel', '20000101', '12345678910', 'some title')),
    ('channel name_NA_12345678910_ some title.mp4', ('channel name', None, '12345678910', 'some title')),
    ('channel name_NA_12345678910_ some title.MP4', ('channel name', None, '12345678910', 'some title')),
    ('20000101 foo.mp4', (None, None, None, '20000101 foo')),
    ('20000101foo.mp4', (None, None, None, '20000101foo')),
    ('something 20000101 foo.mp4', (None, None, None, 'something 20000101 foo')),
    ('something_20000101_foo.mp4', ('something', '20000101', None, 'foo')),
    ('foo .mp4', (None, None, None, 'foo')),  # Has trailing whitespace.
    ('NA_20000303_vp91w5_Bob&apos;s Pancakes.mp4', (None, '20000303', 'vp91w5', 'Bob&apos;s Pancakes')),
    ('NA_20000303_Bob&apos;s Pancakes.mp4', (None, '20000303', None, 'Bob&apos;s Pancakes')),
    ('20000303_Bob&apos;s Pancakes.mp4', (None, '20000303', None, 'Bob&apos;s Pancakes')),
    ('NA_NA_vp91w5_Bob&apos;s Pancakes.mp4', (None, None, 'vp91w5', 'Bob&apos;s Pancakes')),
    ('Learning Self-Reliance_20170529_p_MzsCFkUPU_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', 'p_MzsCFkUPU', 'Beekeeping 2017 Part 6 - Merging Hives')),
    ('Learning Self-Reliance_20170529_p_Mzs_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', 'p_Mzs', 'Beekeeping 2017 Part 6 - Merging Hives')),
    ('Learning Self-Reliance_20170529_p_Beekeeping 2017 Part 6 - Merging Hives.mp4',
     ('Learning Self-Reliance', '20170529', None, 'p_Beekeeping 2017 Part 6 - Merging Hives')),
    ('Learning Self-Reliance_20240722_clyx8ark92qk70860vtl997n5_Long Source Id File with _.mp4',
     ('Learning Self-Reliance', '20240722', 'clyx8ark92qk70860vtl997n5', 'Long Source Id File with _'))
])
def test_parse_video_file_name(file_name, expected):
    """
    A Video's title can be parsed from the video file.
    """
    video_path = pathlib.Path(file_name)
    assert parse_video_file_name(video_path) == expected, f'{file_name} != {expected}'


@pytest.mark.asyncio
async def test_video_factory(test_session, video_factory, channel_factory):
    """
    The `video_factory` pytest fixture is used in many video tests.  Test all it's functionality.
    """
    channel = channel_factory()
    video = video_factory(
        channel_id=channel.id,
        with_video_file=True,
        with_info_json={'description': 'hello'},
        with_caption_file=True,
        with_poster_ext='png',
        source_id='some id',
    )
    test_session.commit()

    assert video.video_path and video.video_path.is_file()
    assert video.caption_paths and all(i.is_file() for i in video.caption_paths)
    assert video.poster_path and video.poster_path.is_file()
    assert video.info_json_path and video.info_json_path.is_file()

    assert video.file_group.a_text  # title
    assert video.file_group.b_text is None
    assert video.file_group.c_text
    assert video.file_group.d_text  # captions
    assert video.source_id == 'some id'


def test_validate_video(test_directory, video_factory, image_bytes_factory, video_file):
    """A video poster will be generated only if the channel permits."""
    video_file = video_file.rename(test_directory / 'Channel Name_20050607_1234567890_The Title.mp4')
    vid1 = video_factory(with_video_file=video_file, with_info_json=True)
    # Clear source_id so source_id in the file will be extracted.
    vid1.source_id = None
    assert not vid1.poster_path

    validate_video(vid1, True)
    assert vid1.video_path == video_file
    assert vid1.poster_path, 'Poster was not created'
    assert vid1.poster_path.is_file(), 'Poster path does not exist'
    assert vid1.video_path.stem == vid1.poster_path.stem
    assert vid1.poster_path.suffix == '.jpg'
    # File name date is assumed to be local timezone.
    assert vid1.file_group.published_datetime and vid1.file_group.published_datetime.year == 2005
    assert vid1.file_group.download_datetime
    assert vid1.source_id == '1234567890'
    assert vid1.file_group.title == 'The Title'

    # Replace info json, FileGroup attributes should be replaced.
    info_json = {
        'channel_id': 'channel id',
        'channel_url': 'https://example.com/example_video_json_channel',
        'duration': 635,
        'epoch': 123456789,
        'fulltitle': 'The full title',
        'id': 'some long id',
        'title': 'The title',
        'upload_date': '20240917',
        'uploader_id': 'uploader id',
        'uploader_url': 'https://example.com/example_video_json_uploader',
        'view_count': 406
    }
    vid1.replace_info_json(info_json)
    validate_video(vid1, False)
    assert vid1.file_group.published_datetime and vid1.file_group.published_datetime.year == 2024
    assert vid1.file_group.title == 'The full title'

    # A PNG is converted, but not deleted.
    vid2 = video_factory(with_video_file=True, with_poster_ext='.png')
    assert vid2.poster_path and vid2.poster_path.suffix == '.png', 'Poster was not initialized'
    assert {i.suffix for i in vid2.file_group.my_paths()} == {'.png', '.mp4'}
    validate_video(vid2, True)
    assert vid2.poster_path.is_file(), 'New poster was not generated'
    assert vid2.poster_path.suffix == '.jpg' and vid2.poster_path.stat().st_size > 0
    assert {i.suffix for i in vid2.file_group.my_paths()} == {'.jpg', '.png', '.mp4'}


@pytest.mark.asyncio
async def test_get_statistics(test_session, video_factory, channel_factory):
    # Can get statistics in empty DB.
    await get_statistics()

    channel1 = channel_factory()
    channel2 = channel_factory()
    video_factory(channel_id=channel1.id)
    video_factory(channel_id=channel1.id)
    video_factory(channel_id=channel2.id)
    video_factory()

    result = await get_statistics()
    assert 'statistics' in result
    assert 'videos' in result['statistics']
    assert 'channels' in result['statistics']
    assert 'historical' in result['statistics']


@pytest.mark.asyncio
async def test_orphaned_files(async_client, test_session, make_files_structure, test_directory, video_factory):
    # A Video without associated files is not orphaned.
    vid1 = video_factory(title='vid1', with_video_file=True)
    # The video files will be removed...
    vid2 = video_factory(title='vid2', with_video_file=True, with_caption_file=True, with_poster_ext='jpeg',
                         with_info_json=True)
    vid3 = video_factory(title='vid3', with_video_file=True, with_poster_ext='jpg')
    # This will be ignored because it is not in the "videos" subdirectory.
    shutil.copy(PROJECT_DIR / 'test/example1.en.vtt', test_directory / 'vid4.en.vtt')
    test_session.commit()

    # Remove vid2 video. Caption, poster, info_json are now orphaned.
    vid2.video_path.unlink()
    vid2_caption_paths, vid2_poster_path, vid2_info_json_path = vid2.caption_paths, vid2.poster_path, vid2.info_json_path
    # Remove vid3 video.  Poster is now orphaned.
    vid3.video_path.unlink()
    vid3_poster_path = vid3.poster_path
    await files_lib.refresh_files()
    test_session.commit()

    # 6 files when two video files are deleted.
    # (vid1, vid2[caption,poster,json], vid3 poster, vid4)
    assert test_session.query(FileGroup).count() == 4
    assert test_session.query(Video).count() == 1

    videos_directory = test_directory / 'videos'
    results = lib.find_orphaned_video_files(videos_directory)

    assert sorted(list(results)) == sorted([
        vid2_caption_paths[0],
        vid2_info_json_path,
        vid2_poster_path,
        vid3_poster_path,
    ])


def test_link_channel_and_downloads(test_session, channel_factory, test_download_manager):
    channel = channel_factory(
        url='https://www.youtube.com/c/LearningSelfReliance/videos',
        source_id='UCng5u6ASda3LNRXJN0JCQJA',
    )
    download1 = Download(url=channel.get_rss_url(), downloader=RSSDownloader.name)
    download2 = Download(url='https://example.com/videos', downloader=ChannelDownloader.name, frequency=99,
                         settings=dict(destination=str(channel.directory)))
    download3 = Download(url='https://example.com/video/1', downloader=RSSDownloader.name,
                         settings=dict(destination=str(channel.directory)))
    test_session.add_all([download1, download2, download3])
    test_session.commit()
    assert test_session.query(Download).count() == 3
    assert not any(i.channel_id for i in test_download_manager.get_downloads(test_session))

    # `link_channel_and_downloads` creates missing Downloads.
    lib.link_channel_and_downloads(session=test_session)
    assert test_session.query(Download).count() == 3
    assert all(i.channel_id for i in test_download_manager.get_recurring_downloads(test_session))
    assert not any(i.channel_id for i in test_download_manager.get_once_downloads(test_session))


@pytest.mark.asyncio
def test_link_channel_and_downloads_migration(async_client, test_session, channel_factory, test_download_manager):
    """Test the 8d0d81bc9c34_channel_channel_downloads.py migration."""
    # A simple Channel which has a download for its URL.
    channel1 = channel_factory(url='https://example.com/channel1')
    download1 = Download(url='https://example.com/channel1', downloader=ChannelDownloader.name, frequency=1)
    # A Channel which has two Downloads.  One for it's URL, another which is an RSS feed in its directory.
    channel2 = channel_factory(url='https://example.com/channel2')
    download2a = Download(url='https://example.com/channel2/rss', downloader=RSSDownloader.name, frequency=1,
                          settings=dict(destination=str(channel2.directory)))
    download2b = Download(url='https://example.com/channel2', downloader=ChannelDownloader.name, frequency=1,
                          settings=dict(destination=str(channel2.directory)))
    # Download does not have a frequency, so it cannot be a channel download.
    download2c = Download(url='https://example.com/channel2/video/1', downloader=VideoDownloader.name)
    # A Channel which has a URL, but no Downloads.
    channel3 = channel_factory()
    test_session.add_all([download1, download2a, download2b, download2c])
    test_session.commit()

    assert not channel1.downloads
    assert channel2.directory and not channel2.downloads
    assert not channel3.downloads

    lib.link_channel_and_downloads(test_session)

    assert channel1.downloads
    assert channel2.downloads
    assert not channel3.downloads

    assert test_session.query(Channel).count() == 3
    assert test_session.query(Download).count() == 4
    d1, d2a, d2b, d2c = test_session.query(Download).order_by(Download.url).all()
    assert d1.url == channel1.url == 'https://example.com/channel1' and d1.frequency == 1
    assert d1.channel_id
    assert d2a.url == 'https://example.com/channel2' and d2a.frequency == 1
    assert d2a.channel_id
    assert d2b.url == 'https://example.com/channel2/rss' and d2b.frequency == 1
    assert d2b.channel_id
    assert d2c.url == 'https://example.com/channel2/video/1' and d2c.frequency is None
    assert not d2c.channel_id


@pytest.mark.asyncio
async def test_format_videos_destination(async_client, test_directory):
    """Videos destination is formatted according to the WROLPiConfig."""
    wrolpi_config = get_wrolpi_config()

    # Channel directory without a tag.
    wrolpi_config.videos_destination = 'videos/%(channel_tag)s/%(channel_name)s'
    assert format_videos_destination('Simple Channel', None, None) \
           == test_directory / 'videos/Simple Channel'

    # One tag can be applied to a Channel.
    assert format_videos_destination('Simple Channel', 'one', None) \
           == test_directory / 'videos/one/Simple Channel'

    # Channel Domain is also supported.
    wrolpi_config.videos_destination = 'videos/%(channel_tag)s/%(channel_domain)s/%(channel_name)s'
    assert format_videos_destination('Simple Channel', 'one', 'https://example.com') \
           == test_directory / 'videos/one/example.com/Simple Channel'

    # Channel name is not required.
    wrolpi_config.videos_destination = '%(channel_tag)s/%(channel_domain)s'
    assert format_videos_destination('Simple Channel', 'one', 'https://example.com') \
           == test_directory / 'one/example.com'

    # Invalid `videos_destination` raises an error.
    wrolpi_config.videos_destination = '%(channel_tag)s/%(channel)s'
    with pytest.raises(FileNotFoundError):
        assert format_videos_destination()


@pytest.mark.asyncio
async def test_videos_downloader_config_api(async_client, test_directory, test_videos_downloader_config):
    # The WROLPi default resolutions.
    config = lib.get_videos_downloader_config()
    assert config.video_resolutions == ['1080p', '720p', '480p', 'maximum']

    request, response = await async_client.get('/api/config?file_name=videos_downloader.yaml')
    assert response.status == HTTPStatus.OK
    config = response.json['config']

    # Change the `video_resolutions`
    config['video_resolutions'] = ['720p', 'maximum']
    body = dict(config=config)
    request, response = await async_client.post('/api/config?file_name=videos_downloader.yaml', json=body)
    assert response.status == HTTPStatus.NO_CONTENT
    # Config file was actually changed.
    config = lib.get_videos_downloader_config()
    assert config.video_resolutions == ['720p', 'maximum']
    assert (test_directory / 'config/videos_downloader.yaml').is_file()
    assert config.is_valid()
    contents = config.read_config_file()
    assert contents['video_resolutions'] == ['720p', 'maximum']
    assert '1080p' not in config.get_file().read_text()

    # Cannot set invalid `file_name_format`.
    config = lib.get_videos_downloader_config().dict()
    config['yt_dlp_options']['file_name_format'] = 'invalid format'
    body = dict(config=config)
    request, response = await async_client.post('/api/config?file_name=videos_downloader.yaml', json=body)
    assert response.status == HTTPStatus.BAD_REQUEST
    assert 'Invalid config' in response.json.get('error')


@pytest.mark.parametrize('file_name,expected', [
    ('/home/wrolpi/.config/chromium/Default', 'chromium:Default'),
    ('/home/wrolpi/.mozilla/firefox/29el0wk0.default-release', 'firefox:29el0wk0.default-release'),
])
def test_browser_profile_to_yt_dlp_arg(file_name, expected):
    """
    Test the conversion of a browser profile to yt-dlp arguments.
    """
    file_name = pathlib.Path(file_name)
    assert lib.browser_profile_to_yt_dlp_arg(file_name) == expected


def test_video_location(test_session, video_factory, channel_factory):
    # Video location without a channel, it opens the preview.
    video1 = video_factory(title='vid1')
    assert video1.location == '/videos/video/1'

    # Video location with a channel.
    channel = channel_factory(name='ChannelName')
    video2 = video_factory(title='vid2', channel_id=channel.id)
    assert video2.location == '/videos/channel/1/video/2'
