import pytest

from modules.videos.downloader import ChannelDownloader
from modules.videos.models import ChannelDownload
from wrolpi.downloader import Download, RSSDownloader
from wrolpi.migration import migrate_channel_downloads


@pytest.mark.asyncio
def test_channel_channel_downloads_migration(test_async_client, test_session, channel_factory, test_download_manager):
    """Test the 8d0d81bc9c34_channel_channel_downloads.py migration."""
    # A simple Channel which has a download for its URL.
    channel1 = channel_factory(url='https://example.com/channel1')
    # A Channel which has two Downloads.  One for it's URL, another which is an RSS feed in its directory.
    channel2 = channel_factory(url='https://example.com/channel2')
    download1 = Download(url=channel1.url, downloader=ChannelDownloader.name)
    download2a = Download(url='https://example.com/channel2/rss', downloader=RSSDownloader.name,
                          settings=dict(destination=str(channel2.directory)))
    download2b = Download(url='https://example.com/channel2', downloader=ChannelDownloader.name,
                          settings=dict(destination=str(channel2.directory)))
    # A Channel which has a URL, but no Downloads.
    channel3 = channel_factory()
    test_session.add_all([download1, download2a, download2b])
    test_session.commit()

    assert not channel1.channel_downloads
    assert channel2.directory and not channel2.channel_downloads
    assert not channel3.channel_downloads

    migrate_channel_downloads(test_session)

    assert channel1.channel_downloads
    assert channel2.channel_downloads
    assert not channel3.channel_downloads

    assert test_session.query(ChannelDownload).count() == 3
    cd1, cd2a, cd2b = test_session.query(ChannelDownload).order_by(ChannelDownload.download_url).all()
    assert cd1.download_url == channel1.url
    assert cd2a.download_url == 'https://example.com/channel2'
    assert cd2b.download_url == 'https://example.com/channel2/rss'
