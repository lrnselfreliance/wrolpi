import pytest

from modules.videos.channel.lib import spread_channel_downloads
from modules.videos.models import Channel
from wrolpi.downloader import DownloadFrequency


@pytest.fixture
def simple_channel(test_session, test_directory) -> Channel:
    """
    Get a Channel with the minimum properties.  This Channel has no download!
    """
    channel = Channel(
        directory=test_directory,
        name='Example Channel 1',
        url='https://example.com/channel1',
        download_frequency=None,  # noqa
        link='examplechannel1',
    )
    test_session.add(channel)
    test_session.commit()
    return channel


@pytest.fixture
def download_channel(simple_channel) -> Channel:
    """
    Get a test Channel that has a download frequency.
    """
    # Add a frequency to the test channel, then give it a download.
    simple_channel.download_frequency = DownloadFrequency.weekly
    spread_channel_downloads()
    return simple_channel
