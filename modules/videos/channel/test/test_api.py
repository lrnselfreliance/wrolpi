import json
import os
import pathlib
import tempfile
from datetime import timedelta
from http import HTTPStatus
from queue import Empty

import mock
import pytest

from modules.videos.api import refresh_queue
from modules.videos.channel.lib import delete_channel
from modules.videos.common import get_no_channel_directory
from modules.videos.lib import upsert_video
from modules.videos.models import Channel, Video
from modules.videos.test.common import create_channel_structure
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager, Download
from wrolpi.errors import UnknownFile
from wrolpi.root_api import api_app
from wrolpi.test.common import wrap_test_db, TestAPI


class TestVideoAPI(TestAPI):

    @wrap_test_db
    @create_channel_structure(
        {
            'Foo': ['vid1.mp4'],
            'Bar': ['vid2.mp4'],
            'Baz': [],
        }
    )
    def test_get_channels(self, tempdir):
        request, response = api_app.test_client.get('/api/videos/channels')
        assert response.status_code == HTTPStatus.OK
        # Channels are sorted by name
        self.assertDictContains(response.json['channels'][0], {'id': 2, 'name': 'Bar', 'video_count': 1})
        self.assertDictContains(response.json['channels'][1], {'id': 3, 'name': 'Baz', 'video_count': 0})
        self.assertDictContains(response.json['channels'][2], {'id': 1, 'name': 'Foo', 'video_count': 1})

    @wrap_test_db
    def test_channel(self):
        channel_directory = tempfile.TemporaryDirectory(dir=self.tmp_dir.name).name
        channel_directory_name = channel_directory.split('/')[-1]
        pathlib.Path(channel_directory).mkdir()

        new_channel = dict(
            directory=channel_directory,
            match_regex='asdf',
            name='   Example Channel 1  ',
            url='https://example.com/channel1',
        )

        # Channel doesn't exist
        request, response = api_app.test_client.get('/api/videos/channels/examplechannel1')
        assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

        # Create it
        request, response = api_app.test_client.post('/api/videos/channels', content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.CREATED, response.json
        location = response.headers['Location']
        request, response = api_app.test_client.get(location)
        created = response.json['channel']
        self.assertIsNotNone(created)
        self.assertIsNotNone(created['id'])

        # Channel name leading/trailing whitespace should be stripped
        assert created['name'] == 'Example Channel 1'

        # Channel directory should be relative to the media directory
        assert not pathlib.Path(created['directory']).is_absolute(), \
            f'Channel directory is absolute: {created["directory"]}'

        # Get the link that was computed
        new_channel['link'] = response.json['channel']['link']
        assert new_channel['link']

        # Can't create it again
        request, response = api_app.test_client.post('/api/videos/channels', content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.BAD_REQUEST

        # Update it
        new_channel['name'] = 'Example Channel 2'
        new_channel['directory'] = str(new_channel['directory'])
        request, response = api_app.test_client.put(location, content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
        request, response = api_app.test_client.get(location)
        assert response.status_code == HTTPStatus.OK
        self.assertDictContains(response.json['channel'], {
            'id': 1,
            'name': 'Example Channel 2',
            'directory': channel_directory_name,
            'match_regex': 'asdf',
            'url': 'https://example.com/channel1',
        })

        # Can't update channel that doesn't exist
        request, response = api_app.test_client.put('/api/videos/channels/doesnt_exist',
                                                    content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.NOT_FOUND

        # Delete the new channel
        request, response = api_app.test_client.delete(location)
        assert response.status_code == HTTPStatus.NO_CONTENT

        # Cant delete it again
        request, response = api_app.test_client.delete(location)
        assert response.status_code == HTTPStatus.NOT_FOUND

    @wrap_test_db
    def test_refresh_no_channel(self):
        with get_db_session() as session:
            videos_path = pathlib.Path(self.tmp_dir.name) / 'videos'
            videos_path.mkdir()

            # A regular user-defined channel
            channel1_path = videos_path / 'channel1'
            channel1_path.mkdir()
            vid1 = channel1_path / 'MyChannelName_20000101_abcdefghijk_title1.mp4'
            vid1.touch()
            vid2 = channel1_path / 'MyChannelName_20000101_abcdefghijk_title2.mp4'
            vid2.touch()

            channel1 = Channel(name='channel1', link='channel1', directory=channel1_path)
            session.add(channel1)
            session.commit()

            # The special NO CHANNEL directory.
            no_channel_path = get_no_channel_directory()
            vid3 = no_channel_path / 'some video.mp4'
            vid3.touch()
            no_channel_subdir = no_channel_path / 'subdir'
            no_channel_subdir.mkdir()
            vid4 = no_channel_subdir / 'other video.mp4'
            vid4.touch()

            api_app.test_client.post('/api/videos/refresh')

            videos = session.query(Video).order_by(Video.title).all()
            self.assertEqual(len(videos), 4)

            # Add some fake videos, they should be removed.
            session.add(Video(title='vid5'))
            session.add(Video(title='vid6', channel_id=channel1.id))
            session.commit()

            videos = session.query(Video).order_by(Video.title).all()
            self.assertEqual(len(videos), 6)

            api_app.test_client.post('/api/videos/refresh')

            videos = session.query(Video).order_by(Video.title).all()
            self.assertEqual(len(videos), 4)

    @wrap_test_db
    def test_refresh_videos(self):
        # There should be no messages until a refresh is called.
        pytest.raises(Empty, refresh_queue.get_nowait)

        # Setup a fake channel directory.
        with get_db_session() as session:
            channel_path = pathlib.Path(self.tmp_dir.name)

            # Files in subdirectories should be found and handled properly.
            subdir = channel_path / 'subdir'
            subdir.mkdir()

            # These are the types of files that will be found first.
            vid1 = subdir / 'channel name_20000101_abcdefghijk_title.mp4'
            vid1.touch()
            vid2 = channel_path / 'channel name_20000102_bcdefghijkl_title.webm'
            vid2.touch()

            # This video is named the same as vid1, except for the file extension.  Its possible that this was
            # downloaded later, or maybe the old video format has fallen out of favor.  WROLPi should ignore this
            # duplicate file.
            vid1_alt = subdir / 'channel name_20000101_abcdefghijk_title.webm'
            vid1_alt.touch()

            # These files are associated with the video files above, and should be found "near" them.
            poster1 = subdir / 'channel name_20000101_abcdefghijk_title.jpg'
            poster1.touch()
            poster2 = channel_path / 'channel name_20000102_bcdefghijkl_title.jpg'
            poster2.touch()

            # Create a channel, associate videos with it.
            channel = Channel(directory=channel_path, link='foo', name='foo')
            session.add(channel)
            session.flush()
            session.refresh(channel)
            video1 = upsert_video(session, vid1, channel)
            video2 = upsert_video(session, vid2, channel)
            session.commit()
            self.assertEqual({str(i.video_path.path) for i in channel.videos},
                             {f'{channel_path}/subdir/{vid1.name}', f'{channel_path}/{vid2.name}'})

            # Poster files were found.
            self.assertEqual(video1.poster_path.path, subdir / poster1.name)
            self.assertEqual(video2.poster_path.path, channel_path / poster2.name)

            # Add a bogus file, this should be removed during the refresh
            self.assertNotIn('foo', {i.video_path.path for i in channel.videos})
            session.add(Video(video_path='foo', channel_id=channel.id))
            session.flush()
            session.refresh(channel)
            self.assertIn(f'{self.tmp_dir.name}/foo', {str(i.video_path.path) for i in channel.videos})
            self.assertEqual(len(channel.videos), 3)

            # Add a video that isn't in the DB, it should be found and any meta files associated with it
            vid3 = pathlib.Path(channel_path / 'channel name_20000103_cdefghijklm_title.flv')
            vid3.touch()
            description3 = pathlib.Path(channel_path / 'channel name_20000103_cdefghijklm_title.description')
            description3.touch()

            # An orphan meta-file should be ignored.  This shouldn't show up anywhere.  But, it shouldn't be deleted.
            poster3 = pathlib.Path(channel_path / 'channel name_20000104_defghijklmn_title.jpg')
            poster3.touch()

            # Finally, call the refresh.  Again, it should remove the "foo" video, then discover this 3rd video
            # file and it's description.
            api_app.test_client.post('/api/videos/refresh')

            # Bogus file was removed
            self.assertNotIn(f'{self.tmp_dir.name}/foo', {i.video_path.path for i in channel.videos})

            # Final channel video list we built
            expected = {
                ('subdir/' + vid1.name, 'subdir/' + poster1.name, None),  # in a subdirectory, no description
                (vid2.name, poster2.name, None),  # no description
                (vid3.name, None, description3.name),  # no poster
            }

            def str_or_none(i):
                return str(i.__json__()) if i else None

            self.assertEqual(
                {(str_or_none(i.video_path), str_or_none(i.poster_path), str_or_none(i.description_path))
                 for i in channel.videos},
                expected
            )

            assert poster3.is_file(), 'Orphan jpg file was deleted!'

    @wrap_test_db
    def test_get_channel_videos(self):
        with get_db_session(commit=True) as session:
            channel1 = Channel(name='Foo', link='foo')
            channel2 = Channel(name='Bar', link='bar')
            session.add(channel1)
            session.add(channel2)
            session.flush()
            session.refresh(channel1)
            session.refresh(channel2)

        # Channels don't have videos yet
        d = dict(channel_link=channel1.link)
        request, response = api_app.test_client.post(f'/api/videos/search', content=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 0

        with get_db_session(commit=True) as session:
            vid1 = Video(title='vid1', channel_id=channel2.id, video_path='foo')
            vid2 = Video(title='vid2', channel_id=channel1.id, video_path='foo')
            session.add(vid1)
            session.add(vid2)

        # Videos are gotten by their respective channels
        request, response = api_app.test_client.post(f'/api/videos/search', content=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 1
        assert response.json['totals']['videos'] == 1
        self.assertDictContains(response.json['videos'][0], dict(id=2, title='vid2', channel_id=channel1.id))

        d = dict(channel_link=channel2.link)
        request, response = api_app.test_client.post(f'/api/videos/search', content=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 1
        self.assertDictContains(response.json['videos'][0], dict(id=1, title='vid1', channel_id=channel2.id))

    @wrap_test_db
    def test_get_video(self):
        """
        Test that you get can information about a video.  Test that video file can be gotten.
        """

        def raise_unknown_file(_):
            raise UnknownFile()

        with get_db_session(commit=True) as session, \
                mock.patch('modules.videos.common.get_absolute_video_info_json', raise_unknown_file):
            channel = Channel(name='Foo', link='foo')
            session.add(channel)
            session.flush()
            session.refresh(channel)
            now_ = now()
            session.add(Video(title='vid1', channel_id=channel.id, upload_date=now_))
            session.add(Video(title='vid2', channel_id=channel.id, upload_date=now_ + timedelta(seconds=1)))

        # Test that a 404 is returned when no video exists
        _, response = api_app.test_client.get('/api/videos/video/10')
        assert response.status_code == HTTPStatus.NOT_FOUND, response.json
        assert response.json == {'code': 1, 'api_error': 'The video could not be found.', 'message': ''}

        # Get the video info we inserted
        _, response = api_app.test_client.get('/api/videos/video/1')
        assert response.status_code == HTTPStatus.OK, response.json
        self.assertDictContains(response.json['video'], {'title': 'vid1'})

        # The next video is included.
        self.assertIsNone(response.json['prev'])
        self.assertDictContains(response.json['next'], {'title': 'vid2'})

    @wrap_test_db
    def test_get_channel_videos_pagination(self):
        with get_db_session(commit=True) as session:
            channel1 = Channel(name='Foo', link='foo')
            session.add(channel1)
            session.flush()
            session.refresh(channel1)

            for i in range(50):
                session.add(Video(title=f'Foo.Video{i}', channel_id=channel1.id, video_path='foo'))

            channel2 = Channel(name='Bar', link='bar')
            session.add(channel2)
            session.flush()
            session.refresh(channel2)
            session.add(Video(title='vid2', channel_id=channel2.id, video_path='foo'))

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
            d = dict(channel_link=channel1.link, order_by='id', offset=offset)
            _, response = api_app.test_client.post(f'/api/videos/search', content=json.dumps(d))
            assert response.status_code == HTTPStatus.OK
            assert len(response.json['videos']) == video_count
            current_ids = [i['id'] for i in response.json['videos']]
            assert current_ids != last_ids, f'IDs are unchanged current_ids={current_ids}'
            last_ids = current_ids

    @wrap_test_db
    def test_channel_no_download_frequency(self):
        """A channel does not require a download frequency."""
        channel_directory = tempfile.TemporaryDirectory(dir=self.tmp_dir.name).name
        os.mkdir(channel_directory)

        new_channel = dict(
            directory=channel_directory,
            name='Example Channel 1',
            url='https://example.com/channel1',
            download_frequency=None,
        )

        # Create the Channel
        request, response = api_app.test_client.post('/api/videos/channels', content=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.CREATED
        location = response.headers['Location']

        # No downloads are scheduled.
        with get_db_session() as session:
            downloads = list(download_manager.get_new_downloads(session))
            self.assertEqual(len(downloads), 0)

        # Get the Channel
        request, response = api_app.test_client.get(location)
        channel = response.json['channel']
        self.assertEqual(channel['download_frequency'], None)

        # Update the Channel with a frequency.
        new_channel = dict(
            directory=channel['directory'],
            name=channel['name'],
            url=channel['url'],
            download_frequency=10,
        )
        request, response = api_app.test_client.put(f'/api/videos/channels/{channel["link"]}',
                                                    content=json.dumps(new_channel))
        self.assertEqual(response.status_code, 204, response.json)

        # Remove the frequency.
        new_channel = dict(
            directory=channel['directory'],
            name=channel['name'],
            url=channel['url'],
            download_frequency=None,
        )
        request, response = api_app.test_client.put(f'/api/videos/channels/{channel["link"]}',
                                                    content=json.dumps(new_channel))
        self.assertEqual(response.status_code, 204, response.json)


def test_channel_frequency_update(download_channel, test_client, test_session):
    """
    A Channel's Download record is updated when the Channel's frequency is updated.
    """
    old_frequency = download_channel.get_download().frequency
    assert old_frequency

    data = dict(
        directory=str(download_channel.directory.path),
        name=download_channel.name,
        url=download_channel.url,
        download_frequency=100,
    )
    request, response = test_client.put(f'/api/videos/channels/{download_channel.link}', json=data)
    assert response.status_code == HTTPStatus.NO_CONTENT, response.json

    download = download_channel.get_download()
    assert download.frequency == 100

    # Only one download
    downloads = test_session.query(Download).all()
    assert len(list(downloads)) == 1


def test_delete_channel_delete_download(download_channel, test_session):
    """
    Deleting a Channel deletes it's Download.
    """
    downloads = test_session.query(Download).all()
    assert all(i.url == download_channel.url for i in downloads)

    delete_channel(download_channel.link)

    downloads = test_session.query(Download).all()
    assert not list(downloads)


def test_video_search(test_session):
    """
    Test that videos can be searched and that their order is by their textsearch rank.
    """
    # These captions have repeated letters, so they will be higher in the ranking.
    videos = [
        ('1', 'b b b b e d d'),
        ('2', '2 b b b d'),
        ('3', 'b b'),
        ('4', 'b e e'),
        ('5', ''),
    ]
    for title, caption in videos:
        test_session.add(Video(title=title, caption=caption, video_path='foo'))
    test_session.commit()

    def do_search(search_str, limit=20):
        d = json.dumps({'search_str': search_str, 'limit': limit})
        _, resp = api_app.test_client.post('/api/videos/search', content=d)
        return resp

    def search_is_as_expected(resp, expected):
        assert resp.status_code == HTTPStatus.OK
        response_ids = [i['id'] for i in resp.json['videos']]
        assert response_ids == expected
        assert resp.json['totals']['videos'] == len(expected)

    # Repeated runs should return the same result
    for _ in range(2):
        # Only videos with a b are returned, ordered by the amount of b's
        response = do_search('b')
        search_is_as_expected(response, [1, 2, 3, 4])

    # Only two captions have e
    response = do_search('e')
    search_is_as_expected(response, [4, 1])

    # Only two captions have d
    response = do_search('d')
    search_is_as_expected(response, [1, 2])

    # 5 can be gotten by it's title
    response = do_search('5')
    search_is_as_expected(response, [5])

    # only video 1 has e and d
    response = do_search('e d')
    search_is_as_expected(response, [1])

    # video 1 and 4 have b and e, but 1 has more
    response = do_search('b e')
    search_is_as_expected(response, [1, 4])

    # Check totals are correct even with a limit
    response = do_search('b', 2)
    assert [i['id'] for i in response.json['videos']] == [1, 2]
    assert response.json['totals']['videos'] == 4


def test_video_file_name(test_session, simple_video, test_client):
    """
    If a Video has no title, the front-end can use the file name as the title.
    """
    _, resp = test_client.get(f'/api/videos/video/{simple_video.id}')
    assert resp.status_code == HTTPStatus.OK
    assert resp.json['video']['video_path'] == 'simple_video.mp4'
    assert resp.json['video'].get('stem') == 'simple_video'


def test_channel_conflicts(test_session, test_directory):
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()
    new_channel = dict(
        directory=channel_directory,
        match_regex='asdf',
        name='Example Channel 1',
        url='https://example.com/channel1',
    )

    def _post_channel(channel):
        return api_app.test_client.post('/api/videos/channels', content=json.dumps(channel))

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

    # Name matches when converted to link
    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = dict(
        directory=channel_directory2,
        name='Example channel 1',
    )
    request, response = _post_channel(new_channel)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == {'error': 'Could not validate the contents of the request', 'code': 10,
                             'cause': {'code': 11, 'error': 'Channel link already used by another channel'}}

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


def test_channel_empty_url_doesnt_conflict(test_session, test_directory):
    """Two channels with empty URLs shouldn't conflict"""
    channel_directory = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory).mkdir()

    new_channel = {
        'name': 'Fooz',
        'directory': channel_directory,
    }
    request, response = api_app.test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.json
    location = response.headers['Location']

    channel_directory2 = tempfile.TemporaryDirectory(dir=test_directory).name
    pathlib.Path(channel_directory2).mkdir()
    new_channel = {
        'name': 'Barz',
        'directory': channel_directory2,
    }
    request, response = api_app.test_client.post('/api/videos/channels', content=json.dumps(new_channel))
    assert response.status_code == HTTPStatus.CREATED, response.json
    assert location != response.headers['Location']


def test_download_channel_no_refresh(test_session, download_channel, video_download_manager):
    """
    A Channel cannot be downloaded until it has been refreshed.
    """

    def check_refreshed(expected: bool):
        channel = test_session.query(Channel).one()
        assert channel.refreshed == expected

    check_refreshed(False)
    test_session.commit()

    with mock.patch('modules.videos.downloader.YDL.extract_info') as mock_extract_info:
        mock_extract_info.return_value = {'entries': [], 'url': 'foo'}
        video_download_manager.do_downloads_sync()

    check_refreshed(True)


def test_channel_post_directory(test_session, test_client, test_directory):
    """A Channel can be created with or without an existing directory."""
    # Channel can be created with a missing directory.
    data = dict(name='foo', directory='foo')
    request, response = test_client.post('/api/videos/channels', content=json.dumps(data))
    assert response.status_code == HTTPStatus.CREATED
    directory = test_session.query(Channel).filter_by(link='foo').one().directory.path
    assert (test_directory / 'foo') == directory
    assert not directory.is_dir()
    assert directory.is_absolute()

    # Channel can be created and have its directory be created.
    data = dict(name='bar', directory='bar', mkdir=True)
    request, response = test_client.post('/api/videos/channels', content=json.dumps(data))
    assert response.status_code == HTTPStatus.CREATED
    directory = test_session.query(Channel).filter_by(link='bar').one().directory.path
    assert (test_directory / 'bar') == directory
    assert directory.is_dir()
    assert directory.is_absolute()
