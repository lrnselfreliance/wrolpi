import json
import pathlib
import tempfile
import time
from datetime import timedelta
from http import HTTPStatus

import mock
import pytest

from modules.videos.channel.lib import delete_channel
from modules.videos.models import Channel
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
    video1.upload_date = now_
    video2 = video_factory(channel_id=simple_channel.id, title='vid2')
    video2.upload_date = now_ + timedelta(seconds=1)
    test_session.commit()

    # Test that a 404 is returned when no video exists
    _, response = test_client.get('/api/videos/video/10')
    assert response.status_code == HTTPStatus.NOT_FOUND, response.json
    assert response.json == {'code': 1, 'api_error': 'The video could not be found.', 'message': ''}

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
    assert channel['download_frequency'] is None

    # Update the Channel with a frequency.
    new_channel = dict(
        directory=channel['directory'],
        name=channel['name'],
        url=channel['url'],
        download_frequency=10,
    )
    request, response = test_client.put(f'/api/videos/channels/{simple_channel.id}',
                                        content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json

    # Download is scheduled.
    assert len(download_manager.get_downloads(test_session)) == 1

    # Remove the frequency.
    new_channel = dict(
        directory=channel['directory'],
        name=channel['name'],
        url=channel['url'],
        download_frequency=None,
    )
    request, response = test_client.put(f'/api/videos/channels/{simple_channel.id}',
                                        content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json


@pytest.mark.asyncio
def test_channel_frequency_update(download_channel, test_client, test_session, test_download_manager):
    """
    A Channel's Download record is updated when the Channel's frequency is updated.
    """
    old_frequency = download_channel.get_download().frequency
    assert old_frequency

    data = dict(
        directory=str(download_channel.directory),
        name=download_channel.name,
        url=download_channel.url,
        download_frequency=100,
    )
    request, response = test_client.put(f'/api/videos/channels/{download_channel.id}', json=data)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json

    download = download_channel.get_download()
    assert download.frequency == 100

    # Only one download
    downloads = test_session.query(Download).all()
    assert len(list(downloads)) == 1


@pytest.mark.asyncio
async def test_channel_download_crud(test_session, simple_channel, test_downloader_config):
    """Modifying a Channel modifies it's Download."""
    assert simple_channel.url
    assert simple_channel.download_frequency is None

    simple_channel.update({'download_frequency': 1000})
    test_session.commit()

    download: Download = test_session.query(Download).one()
    assert simple_channel.get_download() == download
    assert simple_channel.url == download.url
    assert simple_channel.download_frequency == download.frequency

    # Increase the frequency to 1 second.
    simple_channel.update({'download_frequency': 1})
    test_session.commit()
    assert simple_channel.url == download.url
    assert simple_channel.download_frequency == download.frequency == 1
    assert test_session.query(Download).count() == 1

    # Changing the Channel's URL changes the download's URL.
    simple_channel.update({'url': 'https://example.com/new url'})
    test_session.commit()
    assert simple_channel.url == 'https://example.com/new url'
    assert simple_channel.download_frequency == download.frequency == 1
    assert test_session.query(Download).count() == 1

    # Removing the Channel's frequency removes the download.
    simple_channel.update({'download_frequency': None})
    test_session.commit()
    assert test_session.query(Download).count() == 0

    # Removing the URL is supported.
    simple_channel.update({'url': None})
    test_session.commit()

    # Adding a URL is supported.
    simple_channel.update({'url': 'https://example.com'})
    test_session.commit()

    # Adding a frequency adds a Download.
    simple_channel.update({'download_frequency': 1})
    test_session.commit()
    assert test_session.query(Download).count() == 1
    next_download = simple_channel.get_download().next_download
    assert next_download

    # Next download isn't overwritten.
    time.sleep(1)
    simple_channel.update({'name': 'new name'})
    test_session.commit()
    assert simple_channel.get_download().next_download == next_download

    # Deleting a Channel deletes it's Download.
    delete_channel(channel_id=simple_channel.id)
    assert test_session.query(Download).count() == 0


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
        match_regex='asdf',
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
    assert response.json == {'error': 'Could not validate the contents of the request', 'code': 10,
                             'cause': {'error': 'The channel name is already taken.', 'code': 5}}

    # Directory was already used
    new_channel = dict(
        directory=channel_directory,
        name='name is fine',
    )
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'error': 'Could not validate the contents of the request', 'code': 10,
                             'cause': {'code': 7, 'error': 'The directory is already used by another channel.'}}

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
    assert response.json == {'error': 'Could not validate the contents of the request', 'code': 10,
                             'cause': {'code': 6, 'error': 'The URL is already used by another channel.'}}


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
async def test_channel_download_requires_refresh(test_session, download_channel, video_download_manager, video_factory,
                                                 events_history):
    """A Channel cannot be downloaded until it has been refreshed.

    Videos already downloaded are not downloaded again."""
    vid = video_factory(channel_id=download_channel.id, with_video_file=True, with_poster_ext='jpg')
    vid.url = 'https://example.com/1'
    d = download_channel.get_download()
    test_session.commit()
    assert not d.next_download

    def assert_refreshed(expected: bool):
        channel: Channel = test_session.query(Channel).one()
        assert channel.refreshed == expected
        if expected:
            assert channel.info_json
        else:
            assert not channel.info_json

    assert_refreshed(False)
    test_session.commit()

    downloaded_urls = []

    async def do_download(_, download):
        # Track all downloaded URLs.
        downloaded_urls.append(download.url)
        return DownloadResult(success=True)

    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info, \
            mock.patch('modules.videos.downloader.VideoDownloader.do_download', do_download), \
            mock.patch('wrolpi.files.lib.apply_indexers'):  # TODO why does apply_indexers break this test?
        entries = [
            dict(id=vid.source_id, view_count=0, webpage_url='https://example.com/1'),  # Already downloaded.
            dict(id='not downloaded', view_count=0, webpage_url='https://example.com/2'),
        ]
        mock_extract_info.return_value = {'entries': entries, 'url': 'foo', 'uploader': 'some uploader',
                                          'channel_id': 'the id', 'id': 'the id'}
        await video_download_manager.do_downloads()
        await video_download_manager.wait_for_all_downloads()

    # Channel was refreshed before downloading videos.
    assert_refreshed(True)
    assert d.next_download
    # Only the missing video was downloaded.
    assert downloaded_urls == ['https://example.com/2']

    # Should not send refresh events because downloads are automated.
    assert events_history == []


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


def test_channel_crud(test_session, test_client, test_directory, test_download_manager):
    channel_directory = test_directory / 'channel directory'
    channel_directory.mkdir()

    new_channel = dict(
        directory=str(channel_directory),
        match_regex='asdf',
        name='   Example Channel 1  ',
        url='https://example.com/channel1',
    )

    # Channel doesn't exist
    request, response = test_client.get('/api/videos/channels/examplechannel1')
    assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

    # Create it
    request, response = test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.json
    location = response.headers['Location']

    request, response = test_client.get(location)
    assert response.status_code == HTTPStatus.OK, response.json
    created = response.json['channel']
    assert created
    assert created['id']
    # No frequency was provided.  No download exists.
    assert not created['download_frequency']
    assert test_session.query(Download).count() == 0

    # Channel name leading/trailing whitespace should be stripped
    assert created['name'] == 'Example Channel 1'

    # Channel directory should be relative to the media directory
    assert not pathlib.Path(created['directory']).is_absolute(), \
        f'Channel directory is absolute: {created["directory"]}'

    # Can't create it again
    request, response = test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    def put_and_fetch(new_channel_):
        request, response = test_client.put(location, content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
        request, response = test_client.get(location)
        assert response.status_code == HTTPStatus.OK
        channel = response.json['channel']
        return channel

    # Update it
    new_channel['name'] = 'Example Channel 2'
    new_channel['directory'] = str(new_channel['directory'])  # noqa
    new_channel['download_frequency'] = 60
    channel = put_and_fetch(new_channel)
    assert channel['id'] == 1
    assert channel['name'] == 'Example Channel 2'
    assert channel['directory'] == channel_directory.name
    assert channel['match_regex'] == 'asdf'
    assert channel['url'] == 'https://example.com/channel1'
    # Download was created.
    assert channel['download_frequency']
    assert (downloads := test_download_manager.get_downloads(test_session)) and len(downloads) == 1 and downloads[
        0].url == new_channel['url']

    # Update with no download frequency.
    new_channel['download_frequency'] = None
    channel = put_and_fetch(new_channel)
    assert channel['download_frequency'] is None
    # Download was deleted.
    assert len(test_download_manager.get_downloads(test_session)) == 0

    # Can't update channel that doesn't exist
    request, response = test_client.put('/api/videos/channels/doesnt_exist',
                                        content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Delete the new channel
    request, response = test_client.delete(location)
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Cant delete it again
    request, response = test_client.delete(location)
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_change_channel_url(test_client, test_session, test_download_manager, download_channel,
                            test_download_manager_config):
    # Change the Channel's URL.
    download_channel.update({'url': 'https://example.com/new-url'})
    test_session.commit()

    download = test_session.query(Download).one()
    assert download.url == download_channel.url == 'https://example.com/new-url', \
        "Channel's download URL was not changed."

    download_channel.update({'download_frequency': None})
    assert not list(test_session.query(Download).all())


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


def test_get_channel_videos_pagination(test_client, test_session, simple_channel, video_factory, assert_video_search):
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
        _, response = assert_video_search(channel_id=simple_channel.id, order_by='id', offset=offset, limit=20)
        assert len(response.json['file_groups']) == video_count, 'Returned videos does not match'
        current_ids = [i['id'] for i in response.json['file_groups']]
        assert current_ids != last_ids, f'IDs are unchanged current_ids={current_ids}'
        last_ids = current_ids
