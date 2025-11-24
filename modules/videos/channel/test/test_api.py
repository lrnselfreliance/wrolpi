import json
import pathlib
import shutil
import tempfile
from datetime import timedelta
from http import HTTPStatus

import mock
import pytest

from modules.videos.common import get_videos_directory
from modules.videos.conftest import simple_channel
from modules.videos.downloader import ChannelDownloader
from modules.videos.lib import save_channels_config, get_channels_config
from modules.videos.models import Channel, Video
from wrolpi.common import get_relative_to_media_directory, walk
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.downloader import Download, DownloadResult
from wrolpi.files.models import Directory
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


@pytest.mark.asyncio
async def test_channel_no_download_frequency(async_client, test_session, test_directory, simple_channel,
                                             test_download_manager):
    """A channel does not require a download frequency."""
    # No downloads are scheduled.
    assert len(test_download_manager.get_downloads(test_session)) == 0

    # Get the Channel
    request, response = await async_client.get('/api/videos/channels/1')
    assert response.status_code == HTTPStatus.OK
    channel = response.json['channel']
    assert not channel['downloads']

    # Update the Channel with a frequency.
    new_download = {'urls': [simple_channel.url], 'frequency': 10, 'downloader': ChannelDownloader.name}
    request, response = await async_client.post('/api/download', json=new_download)
    assert response.status_code == HTTPStatus.CREATED, response.json

    # Download is scheduled.  Download is related to Channel.
    assert len(test_download_manager.get_downloads(test_session)) == 1
    request, response = await async_client.get('/api/videos/channels/1')
    channel = response.json['channel']
    assert channel['downloads']
    downloads = channel['downloads']
    assert len(downloads) == 1 and downloads[0]['url'] == simple_channel.url
    assert test_session.query(Download).one()
    download_id = channel['downloads'][0]['id']

    # Deleting Download does not delete Channel.
    request, response = await async_client.delete(f'/api/download/{download_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json
    assert not test_download_manager.get_downloads(test_session)
    assert not test_session.query(Download).all()
    assert test_session.query(Channel).count() == 1


def test_video_file_name(test_session, simple_video, test_client):
    """If a Video has no title, the front-end can use the file name as the title."""
    _, resp = test_client.get(f'/api/videos/video/{simple_video.id}')
    assert resp.status_code == HTTPStatus.OK
    assert resp.json['file_group']['video']['video_path'] == 'simple_video.mp4'
    assert resp.json['file_group']['video'].get('stem') == 'simple_video'


@pytest.mark.asyncio
async def test_channel_conflicts(async_client, test_session, test_directory):
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()
    new_channel = dict(
        directory=channel_directory,
        name='Example Channel 1',
        url='https://example.com/channel1',
    )

    async def _post_channel(channel):
        return await async_client.post('/api/videos/channels', content=json.dumps(channel))

    # Create it
    request, response = await _post_channel(new_channel)
    assert response.status_code == HTTPStatus.CREATED

    # Name is an exact match
    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = dict(
        directory=channel_directory2,
        name='Example Channel 1',
    )
    request, response = await _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_NAME_CONFLICT',
                                       'error': 'Bad Request',
                                       'message': 'The channel name is already taken.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Bad Request',
                             'message': 'Could not validate the contents of the request'}

    # Directory was already used
    new_channel = dict(
        directory=channel_directory,
        name='name is fine',
    )
    request, response = await _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_DIRECTORY_CONFLICT',
                                       'error': 'Bad Request',
                                       'message': 'The directory is already used by another channel.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Bad Request',
                             'message': 'Could not validate the contents of the request'}

    # URL is already used
    channel_directory3 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory3).mkdir()
    new_channel = dict(
        directory=channel_directory3,
        name='name is fine',
        url='https://example.com/channel1',
    )
    request, response = await _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'cause': {'code': 'CHANNEL_URL_CONFLICT',
                                       'error': 'Bad Request',
                                       'message': 'The URL is already used by another channel.'},
                             'code': 'VALIDATION_ERROR',
                             'error': 'Bad Request',
                             'message': 'Could not validate the contents of the request'}


def test_channel_empty_url_doesnt_conflict(test_client, test_session, test_directory):
    """Two channels with empty URLs shouldn't conflict"""
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()

    new_channel = dict(name='Fooz', directory=channel_directory)
    request, response = test_client.post('/api/videos/channels', json=new_channel)
    assert response.status_code == HTTPStatus.CREATED, response.json
    location = response.headers['Location']

    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = dict(name='Barz', directory=channel_directory2)
    request, response = test_client.post('/api/videos/channels', json=new_channel)
    assert response.status_code == HTTPStatus.CREATED, response.json
    assert location != response.headers['Location']


@pytest.mark.asyncio
async def test_channel_download_requires_refresh(
        async_client, test_session, mock_video_extract_info, download_channel, video_download_manager,
        video_factory, events_history, await_switches):
    """A Channel cannot be downloaded until it has been refreshed.

    Videos already downloaded are not downloaded again."""
    vid = video_factory(channel_id=download_channel.id, with_video_file=True, with_poster_ext='jpg')
    vid.file_group.url = 'https://example.com/1'
    d = download_channel.downloads[0]
    d.next_download = None
    test_session.commit()
    assert not d.next_download

    def assert_refreshed(expected: bool):
        channel: Channel = test_session.query(Channel).one()
        assert channel.refreshed == expected
        assert bool(channel.info_json) == expected

    await async_client.sanic_app.dispatch('wrolpi.download.download')

    assert_refreshed(False)
    test_session.commit()

    downloaded_urls = []

    async def do_download(_, download):
        # Track all downloaded URLs.
        downloaded_urls.append(download.url)
        return DownloadResult(success=True)

    with mock.patch('modules.videos.downloader.VideoDownloader.do_download', do_download):
        entries = [
            dict(id=vid.source_id, view_count=0, webpage_url='https://example.com/1'),  # Already downloaded.
            dict(id='not downloaded', view_count=0, webpage_url='https://example.com/2'),
        ]
        mock_video_extract_info.return_value = dict(entries=entries, url=download_channel.url, uploader='some uploader',
                                                    channel_id='the id', id='the id')
        await video_download_manager.do_downloads()
        await video_download_manager.wait_for_all_downloads()
        await await_switches()

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
    assert directory.is_dir()
    assert directory.is_absolute()


def test_channel_by_id(test_session, test_client, simple_channel, simple_video):
    request, response = test_client.get(f'/api/videos/channels/{simple_channel.id}')
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_channel_crud(test_session, async_client, test_directory, test_download_manager):
    channel_directory = test_directory / 'channel directory'
    channel_directory.mkdir()

    new_channel = dict(
        directory=str(channel_directory),
        name='   Example Channel 1  ',
        url='https://example.com/channel1',
    )

    # Channel doesn't exist
    request, response = await async_client.get('/api/videos/channels/examplechannel1')
    assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

    # Create it
    request, response = await async_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.content
    location = response.headers['Location']

    request, response = await async_client.get(location)
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
    request, response = await async_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    async def put_and_fetch(new_channel_):
        request, response = await async_client.put(location, content=json.dumps(new_channel_))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
        request, response = await async_client.get(location)
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
    request, response = await async_client.put('/api/videos/channels/doesnt_exist',
                                               content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Delete the new channel
    request, response = await async_client.delete(location)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(Download).count() == 0

    # Cant delete it again
    request, response = await async_client.delete(location)
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_change_channel_url(async_client, test_session, test_download_manager, download_channel,
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


@pytest.mark.asyncio
async def test_get_channel_videos_pagination(test_session, video_factory, assert_video_search, channel_factory):
    # Create two channels, one with 50 videos...
    channel1, channel2 = channel_factory(), channel_factory()
    for i in range(50):
        video_factory(channel_id=channel1.id)
    # The other channel only has one video.
    video_factory(channel_id=channel2.id)
    video_factory(title='vid2', channel_id=channel2.id)
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
        _, response = await assert_video_search(channel_id=channel1.id, order_by='published_datetime',
                                                offset=offset,
                                                limit=20)
        assert len(response.json['file_groups']) == video_count, \
            f'Returned videos does not match for ({offset}, {video_count})'
        current_ids = [i['id'] for i in response.json['file_groups']]
        assert current_ids != last_ids, f'IDs are unchanged current_ids={current_ids}'
        last_ids = current_ids


@pytest.mark.asyncio
async def test_channel_download_id(async_client, test_session, tag_factory, simple_channel, test_download_manager,
                                   test_downloader):
    tag = await  tag_factory()

    # A recurring Download can be displayed on a Channel's page.
    body = dict(
        urls=['https://example.com/channel1'],
        tag_names=[tag.name],
        downloader=test_downloader.name,
        settings=dict(channel_id=simple_channel.id),
        frequency=120,
    )
    request, response = await async_client.post(f'/api/download', json=body)
    assert response.status_code == HTTPStatus.CREATED
    download = test_session.query(Download).one()
    assert download.url == 'https://example.com/channel1'
    assert download.channel_id == simple_channel.id

    # A Channel relationship can be removed from a Download.
    body = dict(
        urls=['https://example.com/channel1'],
        tag_names=[tag.name],
        downloader=test_downloader.name,
        settings=dict(),
        frequency=240,
    )
    request, response = await async_client.put(f'/api/download/{download.id}', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    download = test_session.query(Download).one()
    assert download.channel_id is None
    assert download.frequency == 240

    # A once-Download cannot be associated with a Channel.
    body = dict(
        urls=['https://example.com/channel1'],
        tag_names=[tag.name],
        downloader=test_downloader.name,
        settings=dict(channel_id=simple_channel.id),
    )
    request, response = await async_client.put(f'/api/download/{download.id}', json=body)
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_tag_channel(async_client, test_session, test_directory, channel_factory, tag_factory, video_factory,
                           test_channels_config, test_download_manager, test_downloader):
    """A single Tag can be applied to a Channel."""
    # Create channel directory in the usual videos directory.
    videos_directory = get_videos_directory()
    channel = channel_factory(name='Channel Name', download_frequency=120)
    channel_directory = channel.directory
    tag = await tag_factory('Tag Name')
    v1, v2 = video_factory(title='video1', channel_id=channel.id), video_factory(title='video2', channel_id=channel.id)
    # Create recurring download which uses the Channel's directory.
    download = test_download_manager.recurring_download('https://example.com/1', 60, test_downloader.name,
                                                        destination=str(test_directory / 'videos/Channel Name'))
    test_session.commit()
    save_channels_config()
    assert get_channels_config().channels[0]['directory'] == str(test_directory / 'videos/Channel Name')
    # Channel download downloads into the Channel's directory.
    assert channel.downloads[0].destination == test_directory / 'videos/Channel Name'
    # Make extra file in the Channel's directory, it should be moved.
    (channel_directory / 'extra file.txt').write_text('extra file contents')
    # Channel directory is in the Videos directory.
    assert channel.directory == channel_directory
    # Videos are in the Channel's Directory.
    assert str(get_relative_to_media_directory(v1.video_path)) == 'videos/Channel Name/video1.mp4'
    assert str(get_relative_to_media_directory(v2.video_path)) == 'videos/Channel Name/video2.mp4'
    video_files = [i for i in walk(videos_directory) if i.is_file()]
    assert len(video_files) == 3
    # Channel's directory is indexed.
    assert [i.path for i in test_session.query(Directory)] == [channel.directory, ]

    body = dict(tag_name=tag.name, directory='videos/Tag Name/Channel Name')
    request, response = await async_client.post(f'/api/videos/channels/{channel.id}/tag', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT

    channel = test_session.query(Channel).one()
    assert channel.tag_name == tag.name
    # Channel was moved to Tag's directory, old directory was removed
    new_channel_directory = test_directory / 'videos/Tag Name/Channel Name'
    assert channel.directory == new_channel_directory, 'Channel directory should have been changed.'
    assert new_channel_directory.is_dir(), 'Channel should have been moved.'
    assert next(new_channel_directory.iterdir(), None), 'Channel videos should have been moved.'
    assert not channel_directory.exists(), 'Old Channel directory should have been deleted.'
    # Channel download goes into the Channel's directory.
    d1, d2 = test_session.query(Download).all()
    assert d1.destination == test_directory / 'videos/Tag Name/Channel Name', f'{d1} was not moved'
    assert d2.destination == test_directory / 'videos/Tag Name/Channel Name', f'{d2} was not moved'
    # Directory record was replaced.
    assert [i.path for i in test_session.query(Directory)] == [channel.directory, ]

    # Videos were moved
    v1, v2 = test_session.query(Video).order_by(Video.id).all()
    assert str(get_relative_to_media_directory(v1.video_path)) == 'videos/Tag Name/Channel Name/video1.mp4'
    assert str(get_relative_to_media_directory(v2.video_path)) == 'videos/Tag Name/Channel Name/video2.mp4'
    # Extra file was also moved.
    assert (new_channel_directory / 'extra file.txt').read_text() == 'extra file contents'
    # No new files were created.
    assert len([i for i in walk(videos_directory) if i.is_file()]) == 3

    assert get_channels_config().channels[0]['directory'] == str(test_directory / 'videos/Tag Name/Channel Name')

    # Remove tag, Channel/Videos should be moved back.
    body = dict(tag_name=None, directory='videos/Channel Name')
    request, response = await async_client.post(f'/api/videos/channels/{channel.id}/tag', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content.decode()
    channel = test_session.query(Channel).one()
    assert channel.tag_name is None
    assert str(channel.directory) == str(test_directory / 'videos/Channel Name')
    v1, v2 = test_session.query(Video).order_by(Video.id).all()
    assert str(get_relative_to_media_directory(v1.video_path)) == 'videos/Channel Name/video1.mp4'
    assert str(get_relative_to_media_directory(v2.video_path)) == 'videos/Channel Name/video2.mp4'
    assert not (test_directory / 'videos/Tag Name/Channel Name').exists()
    # Downloads are moved back.
    d1, d2 = test_session.query(Download).all()
    assert d1.destination == test_directory / 'videos/Channel Name', f'{d1} was not moved'
    assert d2.destination == test_directory / 'videos/Channel Name', f'{d2} was not moved'
    assert [i.path for i in test_session.query(Directory)] == [channel.directory, ]

    # Channel can be Tagged, without moving directories.
    body = dict(tag_name=tag.name)
    request, response = await async_client.post(f'/api/videos/channels/{channel.id}/tag', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content.decode()
    channel = test_session.query(Channel).one()
    assert channel.tag_name == 'Tag Name'
    assert str(channel.directory) == str(test_directory / 'videos/Channel Name')
    assert str(get_relative_to_media_directory(v1.video_path)) == 'videos/Channel Name/video1.mp4'
    assert str(get_relative_to_media_directory(v2.video_path)) == 'videos/Channel Name/video2.mp4'
    # Downloads were not changed.
    d1, d2 = test_session.query(Download).all()
    assert d1.destination == test_directory / 'videos/Channel Name', f'{d1} was not moved'
    assert d2.destination == test_directory / 'videos/Channel Name', f'{d2} was not moved'
    assert [i.path for i in test_session.query(Directory)] == [channel.directory, ]


@pytest.mark.asyncio
async def test_create_channel_with_tag(async_client, test_session, test_directory, tag_factory):
    """A Channel can be created with a single Tag."""
    tag = await tag_factory()
    assert not (test_directory / 'some/deep/new/directory').exists()

    body = dict(
        name='Channel Name',
        directory='some/deep/new/directory',
        tag_name=tag.name,
    )
    request, response = await async_client.post('/api/videos/channels', json=body)
    assert response.status_code == HTTPStatus.CREATED, response.content.decode()

    channel = test_session.query(Channel).one()
    assert channel.tag_name == tag.name
    assert channel.directory == (test_directory / 'some/deep/new/directory')
    assert (test_directory / 'some/deep/new/directory').is_dir()


@pytest.mark.asyncio
async def test_move_channel(async_client, test_session, test_directory, channel_factory, tag_factory,
                            video_factory, test_channels_config, test_download_manager, test_downloader):
    """A Channel can be moved."""
    channel = channel_factory(name='Channel Name')
    vid1 = video_factory(channel_id=channel.id)
    vid2 = video_factory(channel_id=channel.id)
    test_session.commit()

    assert str(channel.directory) == str(test_directory / 'videos/Channel Name')
    assert str(vid1.video_path).startswith(str(test_directory / 'videos/Channel Name/'))
    assert str(vid2.video_path).startswith(str(test_directory / 'videos/Channel Name/'))

    body = dict(
        name=channel.name,
        directory=str(test_directory / 'videos/New Directory'),
    )
    request, response = await async_client.put(f'/api/videos/channels/{channel.id}', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content.decode()
    channel = Channel.find_by_id(channel.id)
    assert str(channel.directory) == str(test_directory / 'videos/New Directory')
    assert str(vid1.video_path).startswith(str(test_directory / 'videos/New Directory/'))
    assert str(vid2.video_path).startswith(str(test_directory / 'videos/New Directory/'))
    assert [i.path for i in test_session.query(Directory)] == [test_directory / 'videos/New Directory', ]


@pytest.mark.asyncio
async def test_move_channel_after_terminal_move(async_client, test_session, test_directory, channel_factory,
                                                tag_factory, video_factory, test_channels_config, test_download_manager,
                                                test_downloader):
    """A Channel can be moved in the UI after being moved in the Terminal."""
    channel = channel_factory(name='Channel Name')
    vid1 = video_factory(channel_id=channel.id)
    test_session.commit()

    assert str(channel.directory) == str(test_directory / 'videos/Channel Name')
    assert str(vid1.video_path).startswith(str(test_directory / 'videos/Channel Name/'))

    # mv 'videos/Channel Name' 'videos/New Directory'
    shutil.move(channel.directory, test_directory / 'videos/New Directory')

    body = dict(
        name=channel.name,
        directory=str(test_directory / 'videos/New Directory'),
    )
    request, response = await async_client.put(f'/api/videos/channels/{channel.id}', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.content.decode()
    channel = Channel.find_by_id(channel.id)
    vid1 = test_session.query(Video).one()
    assert str(channel.directory) == str(test_directory / 'videos/New Directory')
    assert str(vid1.video_path).startswith(str(test_directory / 'videos/New Directory/'))


@pytest.mark.asyncio
async def test_search_tagged_channels(async_client, test_session, channel_factory, tag_factory,
                                      video_factory):
    """Tagged Channels can be searched."""
    tag = await tag_factory()
    test_session.commit()

    # Can search when empty.
    body = dict(tag_names=[tag.name])
    request, response = await async_client.post('/api/videos/channels/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['channels']) == 0, 'No Channels should be tagged'

    channel1 = channel_factory(tag_name=tag.name)
    channel2 = channel_factory()
    test_session.commit()

    body = dict(tag_names=[tag.name])
    request, response = await async_client.post('/api/videos/channels/search', json=body)
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['channels']) == 1, 'Only one Channel is tagged'
    assert response.json['channels'][0]['id'] == channel1.id
