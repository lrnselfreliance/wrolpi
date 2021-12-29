import pathlib
from copy import copy
from datetime import datetime
from unittest import mock

from yt_dlp.utils import UnsupportedError

from modules.videos.channel.lib import spread_channel_downloads
from modules.videos.downloader import find_all_missing_videos, VideoDownloader, \
    ChannelDownloader, get_or_create_channel
from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from wrolpi.dates import local_timezone
from wrolpi.db import get_db_session, get_db_context
from wrolpi.downloader import DownloadManager, Download, DownloadFrequency
from wrolpi.test.common import wrap_test_db, TestAPI


class FakeYDL:

    @staticmethod
    def extract_info(*a, **kw):
        return {
            'entries': [
                {'id': 1},
            ],
        }


class TestDownloader(TestAPI):
    @wrap_test_db
    @create_channel_structure(
        {
            'channel1': ['vid1.mp4'],
            'channel2': ['vid2.mp4']
        }
    )
    def test_find_all_missing_videos(self, tempdir):
        with get_db_session(commit=True) as session:
            channel1, channel2 = session.query(Channel).order_by(Channel.id).all()
            channel1.url = channel2.url = 'some url'
            channel1.info_json = {'entries': [{'id': 'foo'}]}

        # No missing videos
        self.assertEqual([], list(find_all_missing_videos()))

        # Create a video that has no video file.
        with get_db_session(commit=True) as session:
            video = Video(title='needs to be downloaded', channel_id=channel1.id, source_id='foo')
            session.add(video)

        missing = list(find_all_missing_videos())
        self.assertEqual(len(missing), 1)

        # The video returned is the one we faked.
        id_, source_id, entry = missing[0]
        # Two videos were created for this test already.
        self.assertEqual(id_, 3)
        # The fake entry we added is regurgitated back.
        self.assertEqual(entry, channel1.info_json['entries'][0])


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
    'entries': [
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 1 id',
         'ie_key': 'Youtube',
         'title': 'video 1 title',
         'uploader': None,
         'url': 'video_1_url',
         'view_count': 58504},
        {'_type': 'url',
         'description': None,
         'duration': None,
         'id': 'video 2 id',
         'ie_key': 'Youtube',
         'title': 'video 2 title',
         'uploader': None,
         'url': 'video_2_url',
         'view_count': 1413},
    ],
    'extractor': 'youtube:tab',
    'extractor_key': 'YoutubeTab',
    'id': 'some id',
    'title': 'channel title',
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

    @staticmethod
    def _make_video_files(channel_dir):
        video_path = channel_dir / 'video.mp4'
        poster_path = channel_dir / 'video.jpg'
        description_path = channel_dir / 'video.description'
        info_json_path = channel_dir / 'video.info.json'
        video_path.touch()
        poster_path.touch()
        description_path.touch()
        info_json_path.touch()
        return video_path, poster_path, description_path, info_json_path

    @wrap_test_db
    def test_video_download(self):
        channel_dir = self.videos_dir / 'channel name'
        channel_dir.mkdir(parents=True)

        # Video paths
        video_path, poster_path, description_path, info_json_path = self._make_video_files(channel_dir)

        with get_db_session() as session:
            url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
            with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info, \
                    mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename, \
                    mock.patch('modules.videos.downloader.VideoDownloader.process_runner') as mock_process_runner:
                mock_extract_info.return_value = example_video_json
                mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
                mock_process_runner.return_value = 0

                self.mgr.create_download(url, session)

                mock_process_runner.assert_called_once()
                video_url, _, out_dir = mock_process_runner.call_args[0]

            download: Download = session.query(Download).one()
            self.assertEqual(video_url, download.url)
            channel: Channel = session.query(Channel).one()
            self.assertEqual(channel.directory, channel_dir)

            video: Video = session.query(Video).one()
            self.assertEqual(video.video_path, video_path)
            self.assertEqual(video.description_path, description_path)
            self.assertEqual(video.poster_path, poster_path)
            self.assertEqual(video.info_json_path, info_json_path)
            self.assertTrue(video.video_path.path.is_absolute())
            self.assertTrue(video.poster_path.path.is_absolute())
            self.assertTrue(video.description_path.path.is_absolute())
            self.assertTrue(video.info_json_path.path.is_absolute())

    @wrap_test_db
    def test_video_download_no_channel(self):
        _, session = get_db_context()

        channel_dir = self.videos_dir / 'NO CHANNEL'
        channel_dir.mkdir(parents=True)

        # Video paths
        video_path, _, _, _ = self._make_video_files(channel_dir)

        # Video has no channel
        info_json = copy(example_video_json)
        del info_json['channel']
        del info_json['channel_id']
        del info_json['channel_url']

        url = 'https://www.youtube.com/watch?v=31jPEBiAC3c'
        with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info, \
                mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename, \
                mock.patch('modules.videos.downloader.VideoDownloader.process_runner') as mock_process_runner:
            mock_extract_info.return_value = info_json
            mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
            mock_process_runner.return_value = 0

            self.mgr.create_download(url, session)

            mock_process_runner.assert_called_once()

        video: Video = session.query(Video).one()
        self.assertEqual(str(video.video_path.path), f'{channel_dir}/video.mp4')

    @wrap_test_db
    def test_channel_download(self):
        _, session = get_db_context()

        url = 'https://www.youtube.com/c/LearningSelfReliance/videos'
        session.add(Channel(url=url, link='foo'))

        channel_dir = self.videos_dir / 'NO CHANNEL'
        channel_dir.mkdir(parents=True)
        video_path, _, _, _ = self._make_video_files(channel_dir)

        with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info, \
                mock.patch('modules.videos.downloader.VideoDownloader.prepare_filename') as mock_prepare_filename, \
                mock.patch('modules.videos.downloader.VideoDownloader.process_runner') as mock_process_runner:
            mock_extract_info.return_value = example_channel_json
            mock_prepare_filename.return_value = (video_path, {'id': 'foo'})
            mock_process_runner.return_value = 0
            self.mgr.create_download(url, session)

        # Two videos are in the example channel.
        downloads = self.mgr.get_new_downloads(session)
        expected = ['https://youtube.com/watch?v=HQ_62YwcA80', 'https://youtube.com/watch?v=4gSz6W4Gv-o']
        for download, expected in zip(downloads, expected):
            self.assertEqual(download.url, expected)
            # Download is skipped for test.
            self.assertEqual(download.status, 'new')

    @wrap_test_db
    def test_invalid_download_url(self):
        _, session = get_db_context()
        with mock.patch('modules.videos.downloader.VideoDownloader.valid_url') as mock_valid_url, \
                mock.patch('modules.videos.downloader.YDL') as mock_ydl:
            mock_valid_url.return_value = (True, None)
            mock_ydl.extract_info.side_effect = UnsupportedError('oops')
            self.mgr.create_download('url', session)

    @wrap_test_db
    @mock.patch('modules.videos.channel.lib.today', lambda: local_timezone(datetime(2020, 1, 1, 0, 0, 0)))
    def test_spread_channel_downloads(self):
        with get_db_session(commit=True) as session:
            channel1 = Channel(name='channel1', link='channel1', url='https://example.com/1',
                               download_frequency=DownloadFrequency.weekly)
            channel2 = Channel(name='channel2', link='channel2', url='https://example.com/2',
                               download_frequency=DownloadFrequency.weekly)
            session.add_all([channel1, channel2])

        def check_frequencies(expected):
            with get_db_session(commit=True) as session:
                downloads = list(session.query(Download).all())
                self.assertLength(downloads, expected)
                for download in downloads:
                    next_download = expected[download.url]
                    self.assertEqual(next_download, str(download.next_download),
                                     f'{download.url} frequency {next_download} != {download.next_download}')

        # Spread the downloads out.
        spread_channel_downloads()

        expected = {
            'https://example.com/1': '2020-01-08 00:00:00-07:00',
            'https://example.com/2': '2020-01-11 12:00:00-07:00',
        }
        check_frequencies(expected)

        with get_db_session(commit=True) as session:
            channel3 = Channel(name='channel3', link='channel3', url='https://example.com/3',
                               download_frequency=DownloadFrequency.daily)
            channel4 = Channel(name='channel4', link='channel4', url='https://example.com/4',
                               download_frequency=DownloadFrequency.weekly)
            # 5 and 6 should be ignored.
            channel5 = Channel(name='channel5', link='channel5', url='https://example.com/5')
            channel6 = Channel(name='channel6', link='channel6', download_frequency=DownloadFrequency.daily)
            session.add_all([channel3, channel4, channel5, channel6])

        spread_channel_downloads()
        expected = {
            'https://example.com/1': '2020-01-08 00:00:00-07:00',
            'https://example.com/2': '2020-01-10 08:00:00-07:00',
            'https://example.com/3': '2020-01-02 00:00:00-07:00',
            'https://example.com/4': '2020-01-12 16:00:00-07:00',
        }
        check_frequencies(expected)

    @wrap_test_db
    def test_get_or_create_channel(self):
        """
        A Channel may need to be created for an arbitrary download.  Attempt to use an existing Channel if we can
        match it.
        """
        with get_db_session(commit=True) as session:
            c1 = Channel(name='foo', link='foo', source_id='foo', url='foo')
            c2 = Channel(name='bar', link='bar', source_id='bar')
            c3 = Channel(name='baz', link='baz', source_id='baz', url='baz')
            c4 = Channel(name='qux', link='qux')
            session.add_all([c1, c2, c3, c4])

        # All existing channels should be used.
        tests = [
            (dict(source_id='foo'), c1),
            (dict(link='foo'), c1),
            (dict(url='foo'), c1),
            (dict(url='foo', source_id='bar'), c2),  # source_id is preferred.
            (dict(name='foo', source_id='bar'), c2),
            (dict(source_id='bar'), c2),
            (dict(source_id='baz'), c3),
            (dict(name='qux'), c4),
            (dict(link='qux'), c4),
        ]
        for kwargs, expected in tests:
            channel = get_or_create_channel(**kwargs)
            self.assertEqual(expected.id, channel.id, f'Expected {expected} got {channel}')

        # A new channel is created.  It will not be automatically downloaded.
        channel = get_or_create_channel(source_id='quux', name='quux', url='quux')
        self.assertEqual(channel.id, 5)
        self.assertEqual(channel.source_id, 'quux')
        self.assertEqual(channel.name, 'quux')
        self.assertEqual(channel.link, 'quux')
        self.assertEqual(channel.url, 'quux')
        self.assertIsNone(channel.download_frequency)

        # New channel can be retrieved.
        self.assertEqual(get_or_create_channel(source_id='quux'), channel)


def test_download_info_save(test_session, video_download_manager):
    """
    An info dict from Downloader.valid_url is saved to the Downloader and can be used by the Downloader later.
    """
    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:
        mock_extract_info.return_value = {'some': 'info'}
        video_download_manager.create_download('https://www.youtube.com/watch?v=HQ_62YwcA80', test_session)
        mock_extract_info.assert_called_once()
