import json
from http import HTTPStatus

import pytest

from modules.videos.downloader import VideoDownloader
from modules.videos.models import Channel, ChannelDownload
from modules.videos.models import Video
from wrolpi.downloader import Download, DownloadFrequency, download_manager, RSSDownloader


def test_delete_channel_no_url(test_session, test_client, channel_factory):
    """
    A Channel can be deleted even if it has no URL.
    """
    channel = channel_factory()
    channel.url = None
    test_session.commit()

    channel.delete_with_videos()


@pytest.mark.asyncio
async def test_delete_channel_with_videos(test_session, test_async_client, channel_factory, video_factory):
    """Videos are disowned when their Channel is deleted."""
    channel = channel_factory()
    video = video_factory(channel_id=channel.id)
    video_path, video_id = video.video_path, video.id
    test_session.commit()

    # Delete the Channel.
    request, response = await test_async_client.delete(f'/api/videos/channels/{channel.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Video still exists, but has no channel.
    video: Video = test_session.query(Video).one()
    assert video.video_path == video_path and video.id == video_id, 'Video entry should not be changed'
    assert video.video_path.is_file(), 'Video should not be deleted'
    assert not video.channel_id and not video.channel, 'Video should not have a Channel'


@pytest.mark.asyncio
async def test_nested_channel_directories(test_session, test_async_client, test_directory, channel_factory,
                                          video_factory):
    """Channel directories cannot contain another Channel's directory."""
    (test_directory / 'foo').mkdir()
    channel1_directory = test_directory / 'foo/one'
    channel_factory(directory=channel1_directory)
    test_session.commit()

    # Channel 2 cannot be in Channel 1's directory.
    channel2_directory = channel1_directory / 'two'
    channel2_directory.mkdir()
    content = dict(
        name='channel 2',
        directory=str(channel2_directory),
    )
    request, response = await test_async_client.post('/api/videos/channels', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['cause'] and \
           response.json['cause']['message'] == 'The directory is already used by another channel.'

    # Channel 3 cannot be above Channel 1's directory.
    content = dict(
        name='channel 3',
        directory=str(test_directory),
    )
    request, response = await test_async_client.post('/api/videos/channels', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['cause'] and \
           response.json['cause']['message'] == 'The directory is already used by another channel.'


@pytest.mark.asyncio()
async def test_channel_download_relationships(test_session, download_channel):
    """Test relationships of ChannelDownload."""
    test_session.flush()

    download = test_session.query(Download).one()
    cd = test_session.query(ChannelDownload).one()
    channel = test_session.query(Channel).one()
    assert len(channel.channel_downloads) == 1
    assert channel.channel_downloads[0] == cd
    assert channel.channel_downloads[0].download == download

    test_session.commit()

    download = test_session.query(Download).one()
    cd = test_session.query(ChannelDownload).one()
    channel = test_session.query(Channel).one()
    assert len(channel.channel_downloads) == 1
    assert channel.channel_downloads[0] == cd
    assert channel.channel_downloads[0].download == download \
           and channel.channel_downloads[0].download.url == 'https://example.com/channel1'
    assert download.frequency == DownloadFrequency.weekly
    assert download.settings['destination'] == str(channel.directory)

    # Deleting Download deletes the ChannelDownload, but not the Channel.
    download.delete()
    assert not test_session.query(Download).all()
    assert not test_session.query(ChannelDownload).all()
    assert test_session.query(Channel).one(), 'Channel should not have been deleted.'

    # Create a Download again.
    download_channel.get_or_create_download('https://example.com/1', test_session, reset_attempts=True)
    assert test_session.query(Download).count() == 1
    assert test_session.query(ChannelDownload).count() == 1
    # Delete the Channel, and any relationships.
    download_channel.delete_with_videos()
    assert test_session.query(Download).count() == 0
    assert test_session.query(ChannelDownload).count() == 0


@pytest.mark.asyncio()
async def test_create_channel_download(test_session, simple_channel):
    """A ChannelDownload is created if a Download is created for a Channel's directory."""
    test_session.flush()

    settings = dict(destination=str(simple_channel.directory))
    download_manager.create_download('https://example.com/2', RSSDownloader.name, test_session,
                                     sub_downloader_name=VideoDownloader.name, settings=settings)
    download = test_session.query(Download).one()
    assert download.settings['destination'] == str(simple_channel.directory)
    cd = test_session.query(ChannelDownload).one()
    assert cd.channel == simple_channel
