import json
import pathlib
import shutil
from uuid import uuid4

import mock
import pytest
from PIL import Image

from modules.videos.downloader import VideoDownloader, ChannelDownloader
from modules.videos.lib import set_test_channels_config, set_test_downloader_config
from modules.videos.models import Channel, Video
from wrolpi.downloader import DownloadFrequency, DownloadManager, Download
from wrolpi.vars import PROJECT_DIR


@pytest.fixture
def simple_channel(test_session, test_directory) -> Channel:
    """Get a Channel with the minimum properties.  This Channel has no download!"""
    channel = Channel(
        directory=test_directory,
        name='Simple Channel',
        url='https://example.com/channel1',
        download_frequency=None,  # noqa
    )
    test_session.add(channel)
    test_session.commit()
    return channel


@pytest.fixture
def channel_factory(test_session, test_directory):
    """Create a random Channel with a directory, but no frequency."""

    def _(source_id: str = None, download_frequency: DownloadFrequency = None, url: str = None, name: str = None):
        name = name or str(uuid4())
        directory = test_directory / name
        directory.mkdir()
        channel = Channel(
            directory=directory,  # noqa
            name=name,
            url=url or f'https://example.com/{name}',
            download_frequency=download_frequency,
            source_id=source_id,
        )
        test_session.add(channel)
        test_session.commit()
        return channel

    return _


@pytest.fixture
def download_channel(test_session, test_directory, video_download_manager) -> Channel:
    """
    Get a test Channel that has a download frequency.
    """
    # Add a frequency to the test channel, then give it a download.
    channel = Channel(
        directory=test_directory,
        name='Download Channel',
        url='https://example.com/channel1',
        download_frequency=DownloadFrequency.weekly,
    )
    download = Download(url=channel.url, downloader='video_channel', frequency=channel.download_frequency)
    test_session.add_all([channel, download])
    test_session.commit()
    return channel


@pytest.fixture
def simple_video(test_session, test_directory, simple_channel) -> Video:
    """A Video with an empty video file whose channel is the Simple Channel."""
    video_path = test_directory / 'simple_video.mp4'
    video_path.touch()
    video = Video(video_path=video_path, channel_id=simple_channel.id)
    test_session.add(video)
    test_session.commit()
    video = test_session.query(Video).filter_by(id=video.id).one()
    return video


@pytest.fixture
def video_file(test_directory) -> pathlib.Path:
    destination = test_directory / f'{uuid4()}.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', destination)

    yield destination

    destination.unlink()


@pytest.fixture
def video_factory(test_session, test_directory):
    """Creates Videos for testing."""

    def factory(channel_id: int = None, title: str = None, upload_date=None, with_video_file: bool = False,
                with_info_json: dict = None, with_poster_ext: str = None, with_caption_file: bool = False):
        title = title or str(uuid4())
        if channel_id:
            path = test_directory / f'{title}.mp4'
        else:
            (test_directory / 'videos/NO CHANNEL').mkdir(parents=True, exist_ok=True)
            path = test_directory / f'videos/NO CHANNEL/{title}.mp4'

        if with_video_file:
            shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', path)

        info_json_path = None
        if with_info_json is True:
            # User requests a info json file, but does not provide one.
            info_json_path = path.with_suffix('.info.json')
            info_json_path.write_text(json.dumps({}))
        elif with_info_json:
            # Use the provided object as the json.
            info_json_path = path.with_suffix('.info.json')
            info_json_path.write_text(json.dumps(with_info_json))

        poster_path = None
        if with_poster_ext:
            poster_path = path.with_suffix(f'.{with_poster_ext}')
            Image.new('RGB', (25, 25)).save(poster_path)

        caption_path = None
        if with_caption_file:
            caption_path = path.with_suffix('.en.vtt')
            caption_path.touch()

        video = Video(video_path=str(path), title=title, channel_id=channel_id, source_id=title,
                      info_json_path=info_json_path, poster_path=poster_path, caption_path=caption_path,
                      upload_date=upload_date)
        test_session.add(video)
        return video

    return factory


@pytest.fixture
def video_download_manager(test_download_manager) -> DownloadManager:
    """
    Get a DownloadManager ready to download Videos and Channels.
    """
    channel_downloader = ChannelDownloader()
    video_downloader = VideoDownloader(priority=40)

    test_download_manager.register_downloader(channel_downloader)
    test_download_manager.register_downloader(video_downloader)

    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:  # prevent real downloads
        mock_extract_info.side_effect = Exception('You must patch modules.videos.downloader.YDL.extract_info!')
        yield test_download_manager


@pytest.fixture
def test_channels_config(test_directory):
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/channels.yaml'
    set_test_channels_config(True)
    yield config_path
    set_test_channels_config(False)


@pytest.fixture
def test_downloader_config(test_directory):
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/downloader.yaml'
    set_test_downloader_config(True)
    yield config_path
    set_test_downloader_config(False)


@pytest.fixture
def mock_video_extract_info():
    with mock.patch('modules.videos.downloader.extract_info') as mock_extract_info:
        yield mock_extract_info


@pytest.fixture
def mock_video_prepare_filename():
    with mock.patch('modules.videos.downloader.prepare_filename') as mock_prepare_filename:
        yield mock_prepare_filename


@pytest.fixture
def mock_video_process_runner():
    with mock.patch('modules.videos.downloader.VideoDownloader.process_runner') as mock_process_runner:
        mock_process_runner.return_value = (0, {})
        yield mock_process_runner
