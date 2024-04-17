import asyncio
import shutil
from copy import copy
from unittest import mock

import pytest

from modules.videos.channel.lib import download_channel
from modules.videos.downloader import VideoDownloader, \
    get_or_create_channel, channel_downloader, video_downloader
from modules.videos.models import Channel, Video
from wrolpi.downloader import Download, DownloadResult
from wrolpi.errors import InvalidDownload
from wrolpi.test.common import skip_circleci
from wrolpi.vars import PROJECT_DIR

example_video_json = {
    'age_limit': 0,
    'average_rating': 4.6923075,
    'categories': ['Howto & Style'],
    'channel': 'channel name',
    'channel_id': 'channel id',
    'channel_url': 'channel url',
    'duration': 635,
    'extractor': 'youtube',
    'extractor_key': 'Youtube',
    'id': 'some long id',
    'is_live': None,
    'like_count': 24,
    'subtitles': {},
    'title': "The video's title",
    'upload_date': '20190707',
    'uploader': 'uploader name',
    'uploader_id': 'uploader id',
    'uploader_url': 'uploader url',
    'view_count': 406,
    'webpage_url': 'webpage url',
    'webpage_url_basename': 'watch',
}

example_channel_json = {
    '_type': 'playlist',
    'channel_id': 'some id',
    'entries': [
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 1 id',
         'ie_key': 'Youtube',
         'title': 'video 1 title',
         'uploader': None,
         'url': 'video_1_url',
         'view_count': 58504,
         'webpage_url': 'https://youtube.com/watch?v=video_1_url'},
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 2 id',
         'ie_key': 'Youtube',
         'title': 'video 2 title',
         'uploader': None,
         'url': 'video_2_url',
         'view_count': 1413,
         'webpage_url': 'https://youtube.com/watch?v=video_2_url'},
    ],
    'extractor': 'youtube:tab',
    'extractor_key': 'YoutubeTab',
    'id': 'some id',
    'title': 'channel title',
    'uploader': 'the uploader',
    'webpage_url': 'channel url',
    'webpage_url_basename': 'videos',
}


@pytest.mark.asyncio
async def test_download_no_channel(test_session, video_download_manager, test_directory,
                                   mock_video_extract_info, mock_video_process_runner):
    """A video can be downloaded even if it does not have a Channel."""
    channel_dir = test_directory / 'NO CHANNEL'
    channel_dir.mkdir(parents=True)
    video_path = channel_dir / 'video.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)

    channel_downloader, video_downloader = video_download_manager.instances

    # Video has no channel
    info_json = copy(example_video_json)
    del info_json['channel']
    del info_json['channel_id']
    del info_json['channel_url']

    url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
    mock_video_extract_info.return_value = info_json
    with mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
        video_download_manager.create_download(url, video_downloader.name)
        await video_download_manager.wait_for_all_downloads()

    mock_video_process_runner.assert_called_once()

    video: Video = test_session.query(Video).one()
    assert str(video.video_path) == f'{channel_dir}/video.mp4'


@pytest.mark.asyncio
async def test_download_video_tags(test_session, video_download_manager, video_file_factory, test_directory,
                                   mock_video_extract_info, mock_video_process_runner, tag_factory):
    """A Video is tagged when Download record requires it."""
    video_path = video_file_factory()
    tag1, tag2 = tag_factory(), tag_factory()

    url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
    mock_video_extract_info.return_value = copy(example_video_json)
    with mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
        settings = dict(tag_names=[tag1.name, tag2.name])
        video_download_manager.create_download(url, video_downloader.name, settings=settings)
        await video_download_manager.wait_for_all_downloads()

    mock_video_process_runner.assert_called_once()

    video: Video = test_session.query(Video).one()
    assert [i.tag.name for i in video.file_group.tag_files] == [tag1.name, tag2.name]


@skip_circleci
@pytest.mark.asyncio
async def test_download_channel(test_session, simple_channel, video_download_manager, video_file,
                                mock_video_extract_info, mock_video_prepare_filename,
                                mock_video_process_runner):
    """Downloading (updating the catalog of) a Channel updates its info_json.

    If a Channel has `match_regex` only those videos with matching titles will be downloaded."""
    url = 'https://www.youtube.com/c/LearningSelfReliance/videos'

    channel_downloader, video_downloader = video_download_manager.instances

    mock_video_prepare_filename.return_value = video_file
    mock_video_extract_info.return_value = example_channel_json
    with mock.patch('modules.videos.downloader.get_channel') as mock_get_channel:
        mock_get_channel.return_value = simple_channel
        video_download_manager.create_download(url, channel_downloader.name, sub_downloader_name=video_downloader.name)
        # Download channel.
        await video_download_manager.wait_for_all_downloads()
        # Download videos.
        await video_download_manager.wait_for_all_downloads()

    # Let background tasks run.
    await asyncio.sleep(0)

    # Two videos are in the example channel.
    downloads = video_download_manager.get_once_downloads(test_session)
    downloads = filter(lambda i: 'watch' in i.url, downloads)
    assert {i.url for i in downloads} == \
           {'https://youtube.com/watch?v=video_2_url', 'https://youtube.com/watch?v=video_1_url'}
    assert all(i.status == 'complete' for i in downloads)

    # A channel with `match_regex` only returns matching video URLs.
    simple_channel.match_regex = '.*(2).*'
    test_session.query(Download).delete()
    test_session.commit()
    with mock.patch('modules.videos.downloader.get_channel') as mock_get_channel:
        mock_get_channel.return_value = simple_channel
        video_download_manager.recurring_download(url, 100, channel_downloader.name,
                                                  sub_downloader_name=video_downloader.name)
        await video_download_manager.wait_for_all_downloads()
    downloads = video_download_manager.get_once_downloads(test_session)
    assert [i.url for i in downloads] == ['https://youtube.com/watch?v=video_2_url']
    assert downloads[0].settings == {
        'channel_id': 1,
        'channel_url': 'https://www.youtube.com/c/LearningSelfReliance/videos',
    }


def test_get_or_create_channel(test_session):
    """A Channel may need to be created for an arbitrary download.

    Attempt to use an existing Channel if we can match it.
    """
    c1 = Channel(name='foo', source_id='foo', url='foo')
    c2 = Channel(name='bar', source_id='bar')
    c3 = Channel(name='baz', source_id='baz', url='baz')
    c4 = Channel(name='qux')
    test_session.add_all([c1, c2, c3, c4])
    test_session.commit()

    # All existing channels should be used.
    tests = [
        (dict(source_id='foo'), c1),
        (dict(url='foo'), c1),
        (dict(url='foo', source_id='bar'), c2),  # source_id has priority.
        (dict(name='foo', source_id='bar'), c2),
        (dict(source_id='bar'), c2),
        (dict(source_id='baz'), c3),
        (dict(name='qux'), c4),
    ]
    for kwargs, expected in tests:
        channel = get_or_create_channel(**kwargs)
        assert expected.id == channel.id, f'Expected {expected} for {kwargs} but got {channel}'

    # A new channel is created.  It will not be automatically downloaded.
    channel = get_or_create_channel(source_id='quux', name='quux', url='quux')
    assert channel.id == 5
    assert channel.source_id == 'quux'
    assert channel.name == 'quux'
    assert channel.url == 'quux'

    # New channel can be retrieved.
    assert get_or_create_channel(source_id='quux') == channel


def test_channel_downloader_hidden(video_download_manager):
    """
    ChannelDownloader should not be presented to the User.
    """
    downloaders = video_download_manager.list_downloaders()
    assert [i.__json__() for i in downloaders] == [(dict(name='video', pretty_name='Videos')), ]


def test_bad_downloader(test_session, video_download_manager):
    """
    Attempting to use an unknown downloader should raise an error.
    """
    with pytest.raises(InvalidDownload):
        video_download_manager.create_download('https://example.com', downloader_name='bad downloader')


@pytest.mark.asyncio
async def test_channel_download_no_frequency(test_session, video_download_manager, simple_channel):
    """
    A Channel without a download frequency creates a once-download.
    """
    # simple_channel has no download record.
    assert video_download_manager.get_downloads(test_session) == []

    download_channel(simple_channel.id)


@pytest.mark.asyncio
async def test_video_download(test_session, test_directory, simple_channel, video_download_manager,
                              mock_video_process_runner, image_file):
    """A video download is performed, files are grouped."""
    simple_channel.source_id = example_video_json['channel_id']
    simple_channel.directory = test_directory / 'videos/channel name'
    simple_channel.directory.mkdir(parents=True)

    video_path = simple_channel.directory / 'a video.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)
    # Create a poster file which was downloaded.
    poster_path = video_path.with_suffix('.png')
    image_file.rename(poster_path)

    url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info, \
            mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_extract_info.return_value = example_video_json
        mock_prepare_filename.return_value = (video_path, {'id': 'foo'})

        video_download_manager.create_download(url, video_downloader.name)
        await video_download_manager.wait_for_all_downloads()

        mock_video_process_runner.assert_called_once()
        download_id, video_url, _, out_dir = mock_video_process_runner.call_args[0]

    download: Download = test_session.query(Download).one()
    assert video_url == download.url
    assert test_session.query(Channel).one()

    video: Video = test_session.query(Video).one()
    assert video.video_path.is_absolute() and video.video_path == video_path, 'Video path is not absolute'
    assert video.video_path.is_absolute() and video.poster_path == poster_path, 'Video poster was not discovered'


@pytest.mark.asyncio
async def test_download_result(test_session, test_directory, video_download_manager, mock_video_process_runner,
                               mock_video_extract_info, image_file):
    """VideoDownloader returns a DownloadResult when complete."""
    channel_directory = test_directory / 'videos/channel name'
    channel_directory.mkdir(parents=True)
    video_file = channel_directory / 'the video.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_file)
    image_file.rename(video_file.with_suffix('.jpg'))

    mock_video_extract_info.return_value = example_video_json
    with mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_prepare_filename.return_value = [video_file, {'id': 'foo'}]
        video_download_manager.create_download('https://example.com', video_downloader.name)
        await video_download_manager.wait_for_all_downloads()
        # Sleep to allow background tasks to finish.
        await asyncio.sleep(1)

    download: Download = test_session.query(Download).one()
    assert download.url == 'https://example.com'
    assert download.location == '/videos/channel/1/video/1'

    # Video has its files.
    video = test_session.query(Video).one()
    assert video.video_path.is_file(), 'Video file was not found.'
    assert video.poster_path.is_file(), 'Poster file was not found.'


@pytest.mark.asyncio
async def test_download_destination(test_session, test_directory, video_download_manager,
                                    mock_video_process_runner, mock_video_extract_info, mock_video_prepare_filename):
    """A Video can be downloaded to a directory other than it's Channel's directory."""
    # yt-dlp would return the video json.
    mock_video_extract_info.return_value = example_video_json
    # Download process is successful with no logs.
    mock_video_process_runner.return_value = (0, {'stdout': '', 'stderr': ''})
    # This result will be ignored during the test, we just need some value so the download does not fail.
    mock_video_prepare_filename.return_value = str(test_directory / 'test video.mp4')

    video_download_manager.create_download('https://example.com/1', downloader_name=VideoDownloader.name)
    await video_download_manager.wait_for_all_downloads()
    # Output directory matches the channel directory.
    assert mock_video_prepare_filename.call_args_list[0].kwargs['ydl'].params['outtmpl']['default'] \
        .startswith(f'{test_directory}/videos/channel name/%(uploader)s')

    mock_video_prepare_filename.reset_mock()

    settings = dict(destination=f'{test_directory}/custom')
    video_download_manager.create_download('https://example.com/2', downloader_name=VideoDownloader.name,
                                           settings=settings)
    await video_download_manager.wait_for_all_downloads()
    # Output directory matches the custom directory specified.
    assert mock_video_prepare_filename.call_args_list[0].kwargs['ydl'].params['outtmpl']['default'] \
        .startswith(f'{test_directory}/custom/%(uploader)s')


example_playlist_json = {
    '_type': 'playlist',
    'availability': None,
    'channel': 'the channel name',
    'channel_follower_count': None,
    'channel_id': 'the channel id',
    'channel_url': 'channel url',
    'description': '',
    'entries': [
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 2 id',
         'ie_key': 'Youtube',
         'title': 'video 2 title',
         'uploader': None,
         'url': 'https://www.youtube.com/shorts/video_2_url',
         'view_count': 1413,
         'webpage_url': 'https://www.youtube.com/shorts/video_2_url'},
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 1 id',
         'ie_key': 'Youtube',
         'title': 'video 1 title',
         'uploader': None,
         'url': 'https://www.youtube.com/watch?v=video_1_url',
         'view_count': 58504,
         'webpage_url': 'https://www.youtube.com/watch?v=video_1_url'},
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 3 id',
         'ie_key': 'Youtube',
         'title': 'video 3 title',
         'uploader': None,
         'url': 'https://youtube.com/watch?v=video_3_url',
         'view_count': 58504,
         'webpage_url': 'https://youtube.com/watch?v=video_3_url'},
    ],
    'extractor': 'youtube:tab',
    'extractor_key': 'YoutubeTab',
    'id': 'the playlist id',
    'modified_date': '20220426',
    'original_url': 'original url',
    'playlist_count': 10,
    'requested_entries': None,
    'tags': [],
    'title': 'some title',
    'uploader': 'Playlist Uploader',
    'uploader_id': 'uploader id',
    'uploader_url': 'uploader url',
    'view_count': 22298,
    'webpage_url': 'webpage url',
    'webpage_url_basename': 'playlist',
    'webpage_url_domain': 'youtube.com',
}


@pytest.mark.asyncio
async def test_download_playlist(test_session, test_directory, mock_video_extract_info, video_download_manager,
                                 video_file):
    """All videos in a playlist can be downloaded for it's Channel."""
    download = Download(url='playlist url')
    test_session.add(download)
    channel = get_or_create_channel(example_playlist_json['channel_id'], download.url, example_channel_json['uploader'])
    video = Video.from_paths(test_session, video_file)
    video.channel_id = channel.id
    video.source_id = 'video 1 id'
    video.file_group.url = 'https://www.youtube.com/watch?v=video_1_url'
    test_session.commit()

    mock_video_extract_info.return_value = example_playlist_json  # Playlist info is fetched first.

    with mock.patch('modules.videos.downloader.VideoDownloader.do_download') as mock_video_do_download:
        mock_video_do_download.return_value = DownloadResult(success=True)  # Don't download the videos.
        result = await channel_downloader.do_download(download)
    assert result.success is True, 'Download was not successful'
    assert set(result.downloads) == {
        'https://www.youtube.com/watch?v=video_2_url',  # Shorts is converted to regular URL.
        'https://youtube.com/watch?v=video_3_url',
    }
