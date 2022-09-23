import pathlib
import shutil
from copy import copy
from itertools import zip_longest
from unittest import mock

import pytest
from yt_dlp.utils import UnsupportedError

from modules.videos.channel.lib import download_channel
from modules.videos.downloader import find_all_missing_videos, VideoDownloader, \
    ChannelDownloader, get_or_create_channel, channel_downloader
from modules.videos.models import Channel, Video
from wrolpi.db import get_db_context
from wrolpi.downloader import DownloadManager, Download, DownloadResult
from wrolpi.errors import InvalidDownload
from wrolpi.files.models import File
from wrolpi.test.common import TestAPI
from wrolpi.test.test_downloader import HTTPDownloader
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_find_all_missing_videos(test_session, channel_factory, video_factory):
    channel1 = channel_factory(url='some url')
    channel1.info_json = {'entries': [{'id': 'foo', 'view_count': 0}]}
    test_session.commit()

    # Two videos are already downloaded.
    video_factory()
    video_factory()

    # No missing videos
    assert [] == [i async for i in find_all_missing_videos(channel1.id)]

    # Create a video that has no video file.
    video = Video(title='needs to be downloaded', channel_id=channel1.id, source_id='foo')
    test_session.add(video)
    test_session.commit()

    missing = [i async for i in find_all_missing_videos(channel1.id)]
    assert len(missing) == 1

    # The video returned is the one we faked.
    id_, source_id, entry = missing[0]
    # Two videos were created for this test already.
    assert id_ == 3
    # The fake entry we added is regurgitated back.
    assert entry == channel1.info_json['entries'][0]


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


class TestVideosDownloaders(TestAPI):

    def setUp(self) -> None:
        super().setUp()
        self.vd = VideoDownloader()
        self.cd = ChannelDownloader()
        self.mgr = DownloadManager()
        self.mgr.register_downloader(self.vd)
        self.mgr.register_downloader(self.cd)

        self.videos_dir = pathlib.Path(self.tmp_dir.name) / 'videos'
        self.videos_dir.mkdir()

    def test_video_valid_url(self):
        # A specific video can be downloaded.
        self.assertTrue(self.vd.valid_url('https://www.youtube.com/watch?v=31jPEBiAC3c')[0])

        # A channel cannot be downloaded.
        self.assertFalse(self.vd.valid_url('https://www.youtube.com/c/LearningSelfReliance/videos')[0])
        self.assertFalse(self.vd.valid_url('https://www.youtube.com/c/LearningSelfReliance')[0])

    def test_channel_valid_url(self):
        # An entire domain cannot be downloaded.
        self.assertFalse(self.cd.valid_url('https://example.com')[0])
        self.assertFalse(self.cd.valid_url('https://youtube.com')[0])

        # Cannot download a single video.
        self.assertFalse(self.cd.valid_url('https://www.youtube.com/watch?v=31jPEBiAC3c')[0])

        # Can download entire channels.
        self.assertTrue(self.cd.valid_url('https://www.youtube.com/c/LearningSelfReliance/videos')[0])
        self.assertTrue(self.cd.valid_url('https://www.youtube.com/c/LearningSelfReliance')[0])

        # Can download entire playlists.
        self.assertTrue(
            self.cd.valid_url('https://www.youtube.com/playlist?list=PLCdlMQeP-TbG12nkBCt0E96yr3EfwcH4E')[0])

    def test_get_downloader(self):
        # The correct Downloader is gotten.
        self.assertEqual(self.mgr.get_downloader('https://www.youtube.com/c/LearningSelfReliance/videos')[0], self.cd)
        self.assertEqual(self.mgr.get_downloader('https://www.youtube.com/c/LearningSelfReliance')[0], self.cd)
        self.assertEqual(self.mgr.get_downloader('https://www.youtube.com/watch?v=31jPEBiAC3c')[0], self.vd)


@pytest.mark.asyncio
async def test_video_download_no_channel(test_session, video_download_manager, video_factory, test_directory,
                                         mock_video_extract_info, mock_video_process_runner):
    """A video can be downloaded even if it does not have a Channel."""
    channel_dir = test_directory / 'NO CHANNEL'
    channel_dir.mkdir(parents=True)
    video_path = channel_dir / 'video.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)

    # Video has no channel
    info_json = copy(example_video_json)
    del info_json['channel']
    del info_json['channel_id']
    del info_json['channel_url']

    url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
    mock_video_extract_info.return_value = info_json
    with mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
        video_download_manager.create_download(url)
        await video_download_manager.wait_for_all_downloads()

    mock_video_process_runner.assert_called_once()

    video: Video = test_session.query(Video).one()
    assert str(video.video_path) == f'{channel_dir}/video.mp4'


@pytest.mark.asyncio
async def test_download_channel(test_session, simple_channel, video_download_manager, video_file,
                                mock_video_extract_info, mock_video_prepare_filename,
                                mock_video_process_runner):
    """Downloading (updating the catalog of) a Channel creates download records for all of it's missing videos.

    If a Channel has `match_regex` only those videos with matching titles will be downloaded."""
    url = 'https://www.youtube.com/c/LearningSelfReliance/videos'

    mock_video_prepare_filename.return_value = video_file
    mock_video_extract_info.return_value = example_channel_json
    with mock.patch('modules.videos.downloader.get_channel') as mock_get_channel:
        mock_get_channel.return_value = simple_channel
        video_download_manager.create_download(url)
        await video_download_manager.wait_for_all_downloads()

    # Two videos are in the example channel.
    downloads = video_download_manager.get_once_downloads(test_session)
    downloads = filter(lambda i: 'watch' in i.url, downloads)
    expected = ['https://youtube.com/watch?v=video_2_url', 'https://youtube.com/watch?v=video_1_url']
    for download, expected in zip_longest(downloads, expected):
        assert download.url == expected
        # Download is run only for test.
        assert download.status == 'complete'

    # A channel with `match_regex` only returns matching video URLs.
    simple_channel.match_regex = '.*(2).*'
    test_session.query(Download).delete()
    test_session.commit()
    with mock.patch('modules.videos.downloader.get_channel') as mock_get_channel:
        mock_get_channel.return_value = simple_channel
        video_download_manager.recurring_download(url, 100)
        await video_download_manager.wait_for_all_downloads()
    downloads = video_download_manager.get_once_downloads(test_session)
    assert [i.url for i in downloads] == ['https://youtube.com/watch?v=video_2_url']


def test_get_or_create_channel(test_session):
    """
    A Channel may need to be created for an arbitrary download.  Attempt to use an existing Channel if we can
    match it.
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
        try:
            channel = get_or_create_channel(**kwargs)
        except Exception as e:
            raise Exception(f'get_or_create_channel failed with {kwargs=}') from e
        assert expected.id == channel.id, f'Expected {expected} for {kwargs} but got {channel}'

    # A new channel is created.  It will not be automatically downloaded.
    channel = get_or_create_channel(source_id='quux', name='quux', url='quux')
    assert channel.id == 5
    assert channel.source_id == 'quux'
    assert channel.name == 'quux'
    assert channel.url == 'quux'

    # New channel can be retrieved.
    assert get_or_create_channel(source_id='quux') == channel


@pytest.mark.asyncio
async def test_download_info_save(test_session, video_download_manager, mock_video_extract_info,
                                  mock_video_prepare_filename,
                                  mock_video_process_runner):
    """
    An info dict from Downloader.valid_url is saved to the Downloader and can be used by the Downloader later.
    """
    mock_video_extract_info.return_value = {'some': 'info'}
    mock_video_prepare_filename.return_value = 'some path'
    video_download_manager.create_download('https://www.youtube.com/watch?v=HQ_62YwcA80')
    await video_download_manager.wait_for_all_downloads()
    assert mock_video_extract_info.call_count == 2  # Only called twice.  The "info" gathering call was skipped.


@pytest.mark.asyncio
async def test_selected_downloader(test_session, video_download_manager, successful_download):
    """
    A user can specify which Downloader to use, no other should ever be used (even if the Download fails).
    """
    # The test HTTP Downloader will claim to be able to handle any HTTP URL; will pretend to have downloaded anything.
    http_downloader = HTTPDownloader()
    mock_do_download = http_downloader.do_download = mock.MagicMock()
    mock_do_download.return_value = successful_download
    mock_http_valid_url = http_downloader.valid_url = mock.MagicMock()
    mock_http_valid_url.return_value = (True, None)
    video_download_manager.register_downloader(http_downloader)

    def check_attempts(attempts):
        assert test_session.query(Download).one().attempts == attempts

    # DownloadManager will attempt to choose the Downloader.
    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:
        mock_extract_info.side_effect = UnsupportedError('not this one')
        video_download_manager.create_download('https://example.com')
        await video_download_manager.wait_for_all_downloads()
        mock_http_valid_url.assert_called_once()
        mock_extract_info.assert_called_once()
        mock_do_download.assert_called_once()

    check_attempts(1)

    mock_http_valid_url.reset_mock()
    mock_do_download.reset_mock()

    # DownloadManager will only use the HTTPDownloader.
    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:
        video_download_manager.create_download('https://example.com', downloader='http')
        await video_download_manager.wait_for_all_downloads()
        # DownloadManager does not try to find the Download, it trusts the "downloader" param.
        mock_extract_info.assert_not_called()
        mock_http_valid_url.assert_not_called()
        # DownloadManager called do_download.
        mock_do_download.assert_called_once()

    check_attempts(2)

    mock_http_valid_url.reset_mock()
    mock_do_download.reset_mock()

    # DownloadManager will only use the HTTPDownloader, even if the download fails.
    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:
        mock_do_download.side_effect = Exception('oh no!')
        video_download_manager.create_download('https://example.com', downloader='http')
        await video_download_manager.wait_for_all_downloads()
        # DownloadManager does not try to find the Download, it trusts the "downloader" param.
        mock_extract_info.assert_not_called()
        mock_http_valid_url.assert_not_called()
        # DownloadManager called do_download.
        mock_do_download.assert_called_once()

    check_attempts(3)


def test_channel_downloader_hidden(video_download_manager):
    """
    ChannelDownloader should not be presented to the User.
    """
    downloaders = video_download_manager.list_downloaders()
    assert [i.__json__() for i in downloaders] == [(dict(name='video', pretty_name='Videos')), ]


@pytest.mark.asyncio
def test_bad_downloader(test_session, video_download_manager):
    """
    Attempting to use an unknown downloader should raise an error.
    """
    with pytest.raises(InvalidDownload):
        video_download_manager.create_download('https://example.com', downloader='bad downloader')


def test_channel_download_no_download(test_session, video_download_manager, simple_channel):
    """
    A Channel without an existing Download cannot be downloaded.  This is to avoid the situation where a single
    video has been downloaded in a Channel, but the User has not requested downloading of all videos in the channel.
    """
    # simple_channel has no download record.
    assert video_download_manager.get_downloads(test_session) == []

    with pytest.raises(InvalidDownload):
        download_channel(simple_channel.id)


@pytest.mark.asyncio
async def test_invalid_download_url(test_session, test_download_manager, mock_video_extract_info):
    """An invalid url should not be attempted again."""
    _, session = get_db_context()
    with mock.patch('modules.videos.downloader.VideoDownloader.valid_url') as mock_valid_url, \
            mock.patch('wrolpi.downloader.DownloadManager.get_downloader') as mock_get_downloader:
        video_downloader = VideoDownloader()
        test_download_manager.register_downloader(video_downloader)
        mock_get_downloader.return_value = (video_downloader, None)
        mock_valid_url.return_value = (True, {})  # url is valid, but is not a video URL.
        mock_video_extract_info.side_effect = UnsupportedError('oops')
        test_download_manager.create_download('invalid url', downloader=VideoDownloader.name)
        await test_download_manager.wait_for_all_downloads()

    download = session.query(Download).one()
    assert download.status == 'failed'


@pytest.mark.asyncio
async def test_video_download_1(test_session, test_directory, simple_channel, video_download_manager,
                                mock_video_process_runner, image_file):
    """A video download is performed, files are associated."""
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

        video_download_manager.create_download(url)
        await video_download_manager.wait_for_all_downloads()

        mock_video_process_runner.assert_called_once()
        video_url, _, out_dir = mock_video_process_runner.call_args[0]

    download: Download = test_session.query(Download).one()
    assert video_url == download.url
    assert test_session.query(Channel).one()

    video: Video = test_session.query(Video).one()
    assert video.video_path.is_absolute(), 'Video path is not absolute'
    assert video.poster_path == poster_path, 'Video poster was not discovered'
    assert video.validated, 'Video was not validated'
    assert video.video_file and video.video_file.indexed, 'Video was not indexed'


@pytest.mark.asyncio
async def test_download_result(test_session, test_directory, video_download_manager, mock_video_process_runner,
                               mock_video_extract_info):
    """VideoDownloader returns a DownloadResult when complete."""
    channel_directory = test_directory / 'videos/channel name'
    channel_directory.mkdir(parents=True)
    video_file = channel_directory / 'the video.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_file)

    mock_video_extract_info.return_value = example_video_json
    with mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename:
        mock_prepare_filename.return_value = [video_file, {'id': 'foo'}]
        video_download_manager.create_download('https://example.com')
        await video_download_manager.wait_for_all_downloads()

    download: Download = test_session.query(Download).one()
    assert download.url == 'https://example.com'
    assert download.location == '/videos/channel/1/video/1'


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
async def test_download_playlist(test_session, test_directory, mock_video_extract_info, video_download_manager):
    """All videos in a playlist can be downloaded for it's Channel."""
    download = Download(url='playlist url')
    test_session.add(download)
    channel = get_or_create_channel(example_playlist_json['channel_id'], download.url, example_channel_json['uploader'])
    video_file = File(path=test_directory / 'video file.mp4')
    test_session.add(video_file)
    test_session.add(Video(url='https://www.youtube.com/watch?v=video_1_url',
                           source_id='video 1 id', channel_id=channel.id, video_file=video_file))
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
