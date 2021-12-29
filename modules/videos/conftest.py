import pathlib
import shutil
from uuid import uuid4

import mock
import pytest

from modules.videos.channel.lib import spread_channel_downloads
from modules.videos.downloader import VideoDownloader, ChannelDownloader
from modules.videos.models import Channel, Video
from wrolpi.common import sanitize_link
from wrolpi.downloader import DownloadFrequency, DownloadManager
from wrolpi.vars import PROJECT_DIR


@pytest.fixture
def simple_channel(test_session, test_directory) -> Channel:
    """
    Get a Channel with the minimum properties.  This Channel has no download!
    """
    channel = Channel(
        directory=test_directory,
        name='Simple Channel',
        url='https://example.com/channel1',
        download_frequency=None,  # noqa
        link='simplechannel',
    )
    test_session.add(channel)
    test_session.commit()
    return channel


@pytest.fixture
def channel_factory(test_session, test_directory):
    """
    Create a random Channel with a directory, but no frequency.
    """

    def _():
        name = str(uuid4())
        directory = test_directory / name
        directory.mkdir()
        channel = Channel(
            directory=directory,  # noqa
            name=name,
            url=f'https://example.com/{name}',
            download_frequency=None,  # noqa
            link=sanitize_link(name),
        )
        test_session.add(channel)
        test_session.commit()
        return channel

    return _


@pytest.fixture
def download_channel(test_session, test_directory) -> Channel:
    """
    Get a test Channel that has a download frequency.
    """
    # Add a frequency to the test channel, then give it a download.
    channel = Channel(
        directory=test_directory,
        name='Download Channel',
        url='https://example.com/channel1',
        download_frequency=DownloadFrequency.weekly,
        link='downloadchannel',
    )
    test_session.add(channel)
    test_session.commit()
    spread_channel_downloads()
    return channel


@pytest.fixture
def simple_video(test_session, test_directory, simple_channel) -> Video:
    """
    A Video with a video file whose channel is the Simple Channel.
    """
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
    def _(channel_id: int = None):
        title = str(uuid4())
        path = str(test_directory / f'{title}.mp4')
        video = Video(video_path=path, title=title, channel_id=channel_id, source_id=title)
        test_session.add(video)
        return video

    return _


@pytest.fixture
def video_download_manager(test_download_manager) -> DownloadManager:
    """
    Get a DownloadManager ready to download Videos and Channels.
    """
    channel_downloader = ChannelDownloader('video_channel')
    video_downloader = VideoDownloader('video', priority=40)

    test_download_manager.register_downloader(channel_downloader)
    test_download_manager.register_downloader(video_downloader)

    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:  # prevent real downloads
        mock_extract_info.side_effect = Exception('You must patch modules.videos.downloader.YDL.extract_info!')
        yield test_download_manager
