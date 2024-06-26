import asyncio
import json
import pathlib
import tempfile
from datetime import timedelta
from http import HTTPStatus

import mock
import pytest

from modules.videos.downloader import ChannelDownloader
from modules.videos.models import Channel, ChannelDownload
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager, Download, DownloadResult
from wrolpi.test.common import assert_dict_contains


def test_get_channels(test_directory, channel_factory, test_client):
    channel_factory()
    channel_factory()
    channel_factory()
    request, response = test_client.get('/api/videos/channels')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['channels']) == 3


def test_get_video(test_client, test_session, simple_channel, video_factory):
    """Test that you get can information about a video.  Test that video file can be gotten."""
    now_ = now()
    video1 = video_factory(channel_id=simple_channel.id, title='vid1')
    video1.file_group.published_datetime = now_
    video2 = video_factory(channel_id=simple_channel.id, title='vid2')
    video2.file_group.published_datetime = now_ + timedelta(seconds=1)
    test_session.commit()

    # Test that a 404 is returned when no video exists
    _, response = test_client.get('/api/videos/video/10')
    assert response.status_code == HTTPStatus.NOT_FOUND, response.json
    assert response.json == {'code': 'UNKNOWN_VIDEO',
                             'error': 'Cannot find Video with id 10',
                             'message': 'The video could not be found.'}

    # Get the video info we inserted
    _, response = test_client.get('/api/videos/video/1')
    assert response.status_code == HTTPStatus.OK, response.json
    assert_dict_contains(response.json['file_group'], {'title': 'vid1'})

    # The next video is included.
    assert response.json['prev'] is None
    assert_dict_contains(response.json['next'], {'title': 'vid2'})


def test_channel_no_download_frequency(test_client, test_session, test_directory, simple_channel):
    """A channel does not require a download frequency."""
    # No downloads are scheduled.
    assert len(download_manager.get_downloads(test_session)) == 0

    # Get the Channel
    request, response = test_client.get('/api/videos/channels/1')
    channel = response.json['channel']
    assert not channel['channel_downloads']

    # Update the Channel with a frequency.
    new_download = {'urls': [simple_channel.url], 'frequency': 10, 'downloader': ChannelDownloader.name}
    request, response = test_client.post('/api/download', json=new_download)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json

    # Download is scheduled.  ChannelDownload was created.
    assert len(download_manager.get_downloads(test_session)) == 1
    request, response = test_client.get('/api/videos/channels/1')
    channel = response.json['channel']
    assert channel['channel_downloads']
    channel_downloads = channel['channel_downloads']
    assert len(channel_downloads) == 1 and channel_downloads[0]['url'] == simple_channel.url
    assert test_session.query(ChannelDownload).one()
    download_id = channel['channel_downloads'][0]['id']

    # Deleting the Download deletes the ChannelDownload.
    request, response = test_client.delete(f'/api/download/{download_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json
    assert not download_manager.get_downloads(test_session)
    assert not test_session.query(ChannelDownload).all()


def test_video_file_name(test_session, simple_video, test_client):
    """If a Video has no title, the front-end can use the file name as the title."""
    _, resp = test_client.get(f'/api/videos/video/{simple_video.id}')
    assert resp.status_code == HTTPStatus.OK
    assert resp.json['file_group']['video']['video_path'] == 'simple_video.mp4'
    assert resp.json['file_group']['video'].get('stem') == 'simple_video'


def test_channel_conflicts(test_client, test_session, test_directory):
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()
    new_channel = dict(
        directory=channel_directory,
        name='Example Channel 1',
        url='https://example.com/channel1',
    )

    def _post_channel(channel):
        return test_client.post('/api/videos/channels', content=json.dumps(channel))

    # Create it
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.CREATED

    # Name is an exact match
    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = dict(
        directory=channel_directory2,
        name='Example Channel 1',
    )
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_NAME_CONFLICT',
                                       'error': 'The channel name is already taken.',
                                       'message': 'The channel name is already taken.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Could not validate the contents of the request',
                             'message': 'Could not validate the contents of the request'}

    # Directory was already used
    new_channel = dict(
        directory=channel_directory,
        name='name is fine',
    )
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_DIRECTORY_CONFLICT',
                                       'error': 'The directory is already used by another channel.',
                                       'message': 'The directory is already used by another channel.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Could not validate the contents of the request',
                             'message': 'Could not validate the contents of the request'}

    # URL is already used
    channel_directory3 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory3).mkdir()
    new_channel = dict(
        directory=channel_directory3,
        name='name is fine',
        url='https://example.com/channel1',
    )
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_URL_CONFLICT',
                                       'error': 'The URL is already used by another channel.',
                                       'message': 'The URL is already used by another channel.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Could not validate the contents of the request',
                             'message': 'Could not validate the contents of the request'}


def test_channel_empty_url_doesnt_conflict(test_client, test_session, test_directory):
    """Two channels with empty URLs shouldn't conflict"""
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()

    new_channel = {
        'name': 'Fooz',
        'directory': channel_directory,
    }
    request, response = test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.json
    location = response.headers['Location']

    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = {
        'name': 'Barz',
        'directory': channel_directory2,
    }
    request, response = test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.json
    assert location != response.headers['Location']


@pytest.mark.asyncio
async def test_channel_download_requires_refresh(
        test_async_client, test_session, mock_video_extract_info, download_channel, video_download_manager,
        video_factory, events_history):
    """A Channel cannot be downloaded until it has been refreshed.

    Videos already downloaded are not downloaded again."""
    vid = video_factory(channel_id=download_channel.id, with_video_file=True, with_poster_ext='jpg')
    vid.file_group.url = 'https://example.com/1'
    d = download_channel.channel_downloads[0].download
    d.next_download = None
    test_session.commit()
    assert not d.next_download

    def assert_refreshed(expected: bool):
        channel: Channel = test_session.query(Channel).one()
        assert channel.refreshed == expected
        assert bool(channel.info_json) == expected

    await test_async_client.sanic_app.dispatch('wrolpi.download.')

    assert_refreshed(False)
    test_session.commit()

    downloaded_urls = []

    async def do_download(_, download):
        # Track all downloaded URLs.
        downloaded_urls.append(download.url)
        return DownloadResult(success=True)

    with mock.patch('modules.videos.downloader.VideoDownloader.do_download', do_download), \
            mock.patch('wrolpi.files.lib.apply_indexers'):  # TODO why does apply_indexers break this test?
        entries = [
            dict(id=vid.source_id, view_count=0, webpage_url='https://example.com/1'),  # Already downloaded.
            dict(id='not downloaded', view_count=0, webpage_url='https://example.com/2'),
        ]
        mock_video_extract_info.return_value = dict(entries=entries, url=download_channel.url, uploader='some uploader',
                                                    channel_id='the id', id='the id')
        await video_download_manager.do_downloads()
        await video_download_manager.wait_for_all_downloads()
        # Give time for background tasks to finish.  :(
        await asyncio.sleep(1)

    # Channel was refreshed before downloading videos.
    assert_refreshed(True)
    assert d.next_download
    # Only the missing video was downloaded.
    assert downloaded_urls == ['https://example.com/2']

    # Should not send refresh events because downloads are automated.
    assert list(events_history) == []


def test_channel_post_directory(test_session, test_client, test_directory):
    """A Channel can be created with or without an existing directory."""
    # Channel can be created with a directory which is not on disk.
    data = dict(name='foo', directory='foo')
    request, response = test_client.post('/api/videos/channels', content=json.dumps(data))
    assert response.status_code == HTTPStatus.CREATED
    directory = test_session.query(Channel).filter_by(id=1).one().directory
    assert (test_directory / 'foo') == directory
    assert not directory.is_dir()
    assert directory.is_absolute()

    # Channel can be created and have its directory be created.
    data = dict(name='bar', directory='bar', mkdir=True)
    request, response = test_client.post('/api/videos/channels', content=json.dumps(data))
    assert response.status_code == HTTPStatus.CREATED
    directory = test_session.query(Channel).filter_by(id=2).one().directory
    assert (test_directory / 'bar') == directory
    assert directory.is_dir()
    assert directory.is_absolute()


def test_channel_by_id(test_session, test_client, simple_channel, simple_video):
    request, response = test_client.get(f'/api/videos/channels/{simple_channel.id}')
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_channel_crud(test_session, test_async_client, test_directory, test_download_manager):
    channel_directory = test_directory / 'channel directory'
    channel_directory.mkdir()

    new_channel = dict(
        directory=str(channel_directory),
        name='   Example Channel 1  ',
        url='https://example.com/channel1',
    )

    # Channel doesn't exist
    request, response = await test_async_client.get('/api/videos/channels/examplechannel1')
    assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

    # Create it
    request, response = await test_async_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.content
    location = response.headers['Location']

    request, response = await test_async_client.get(location)
    assert response.status_code == HTTPStatus.OK, response.json
    created = response.json['channel']
    assert created
    assert created['id']
    # No frequency was provided.  No download exists.
    assert test_session.query(Download).count() == 0

    # Channel name leading/trailing whitespace should be stripped
    assert created['name'] == 'Example Channel 1'

    # Channel directory should be relative to the media directory
    assert not pathlib.Path(created['directory']).is_absolute(), \
        f'Channel directory is absolute: {created["directory"]}'

    # Can't create it again
    request, response = await test_async_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    async def put_and_fetch(new_channel_):
        request, response = await test_async_client.put(location, content=json.dumps(new_channel_))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
        request, response = await test_async_client.get(location)
        assert response.status_code == HTTPStatus.OK
        channel = response.json['channel']
        return channel

    # Update it
    new_channel['name'] = 'Example Channel 2'
    new_channel['directory'] = str(new_channel['directory'])  # noqa
    channel = await put_and_fetch(new_channel)
    assert channel['id'] == 1
    assert channel['name'] == 'Example Channel 2'
    assert channel['directory'] == channel_directory.name
    assert channel['url'] == 'https://example.com/channel1'

    # Can't update channel that doesn't exist
    request, response = await test_async_client.put('/api/videos/channels/doesnt_exist',
                                                    content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Delete the new channel
    request, response = await test_async_client.delete(location)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(Download).count() == 0

    # Cant delete it again
    request, response = await test_async_client.delete(location)
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_change_channel_url(test_async_client, test_session, test_download_manager, download_channel,
                                  test_download_manager_config):
    # Change the Channel's URL.
    download_channel.update({'url': 'https://example.com/new-url'})
    test_session.commit()

    channel = test_session.query(Channel).one()
    assert channel.url == 'https://example.com/new-url', "Channel's URL was not changed."


def test_search_videos_channel(test_client, test_session, video_factory):
    with get_db_session(commit=True) as session:
        channel1 = Channel(name='Foo')
        channel2 = Channel(name='Bar')
        session.add(channel1)
        session.add(channel2)
        session.flush()
        session.refresh(channel1)
        session.refresh(channel2)

    # Channels don't have videos yet
    d = dict(channel_id=channel1.id)
    request, response = test_client.post(f'/api/videos/search', content=json.dumps(d))
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['file_groups']) == 0

    with get_db_session(commit=True) as session:
        vid1 = video_factory(title='vid1', channel_id=channel2.id)
        vid2 = video_factory(title='vid2', channel_id=channel1.id)
        session.add(vid1)
        session.add(vid2)

    # Videos are gotten by their respective channels
    request, response = test_client.post(f'/api/videos/search', content=json.dumps(d))
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['file_groups']) == 1
    assert response.json['totals']['file_groups'] == 1
    assert_dict_contains(response.json['file_groups'][0],
                         dict(primary_path='vid2.mp4', video=dict(channel_id=channel1.id)))

    d = dict(channel_id=channel2.id)
    request, response = test_client.post(f'/api/videos/search', content=json.dumps(d))
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['file_groups']) == 1
    assert_dict_contains(response.json['file_groups'][0],
                         dict(primary_path='vid1.mp4', video=dict(channel_id=channel2.id)))


def test_get_channel_videos_pagination(test_session, simple_channel, video_factory, assert_video_search):
    for i in range(50):
        video_factory(channel_id=simple_channel.id)

    channel2 = Channel(name='Bar')
    test_session.add(channel2)
    test_session.flush()
    test_session.refresh(channel2)
    video_factory(channel_id=channel2.id)
    video_factory(title='vid2', channel_id=channel2.id, with_video_file=True)
    test_session.commit()

    # Get first, second, third, and empty pages of videos.
    tests = [
        # (offset, video_count)
        (0, 20),
        (20, 20),
        (40, 10),
        (50, 0),
    ]
    last_ids = []
    for offset, video_count in tests:
        _, response = assert_video_search(channel_id=simple_channel.id, order_by='published_datetime', offset=offset,
                                          limit=20)
        assert len(response.json['file_groups']) == video_count, 'Returned videos does not match'
        current_ids = [i['id'] for i in response.json['file_groups']]
        assert current_ids != last_ids, f'IDs are unchanged current_ids={current_ids}'
        last_ids = current_ids


@pytest.mark.asyncio
async def test_create_channel_download(test_async_client, test_session, simple_channel, tag_factory):
    tag = tag_factory()

    # Create ChannelDownload (which includes a Download).
    body = {'url': 'https://example.com/1', 'frequency': 42}
    request, response = await test_async_client.post(
        f'/api/videos/channels/{simple_channel.id}/download', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content
    download: Download = test_session.query(Download).one()
    assert download.url == 'https://example.com/1' and not download.settings.get('tag_names')

    # Create another ChannelDownload.  Previous ChannelDownload/Download are untouched.
    body = {'url': 'https://example.com/2', 'frequency': 55, 'settings': {'tag_names': [tag.name]}}
    request, response = await test_async_client.post(
        f'/api/videos/channels/{simple_channel.id}/download', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content
    download1, download2 = test_session.query(Download).order_by(Download.url).all()
    assert download1.url == 'https://example.com/1' and not download1.settings.get('tag_names')
    assert download2.url == 'https://example.com/2' and download2.settings.get('tag_names') == [tag.name, ]
    test_session.flush(simple_channel)
    assert len(simple_channel.channel_downloads) == 2

    # Change frequency of first ChannelDownload.
    body = {'url': 'https://example.com/1', 'frequency': 123, 'settings': {'title_include': 'foo,bar'}}
    request, response = await test_async_client.put(
        f'/api/videos/channels/{simple_channel.id}/download/{download1.id}', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content
    download1, download2 = test_session.query(Download).order_by(Download.url).all()
    assert download1.url == 'https://example.com/1'
    assert download1.settings == {'title_include': 'foo,bar'}
    assert download2.url == 'https://example.com/2' and download2.settings.get('tag_names') == [tag.name, ]
    test_session.flush(simple_channel)
    assert len(simple_channel.channel_downloads) == 2

    # Deleting Download delets ChannelDownload.
    request, response = await test_async_client.delete(f'/api/download/{download1.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(ChannelDownload).count() == 1
    assert test_session.query(Download).count() == 1
