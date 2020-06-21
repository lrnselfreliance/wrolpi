import json
import pathlib
import tempfile
from http import HTTPStatus
from queue import Empty

import mock
import pytest

from api.api import api_app, attach_routes
from api.db import get_db_context
from api.errors import UnknownFile
from api.test.common import wrap_test_db, get_all_messages_in_queue, TestAPI
from api.videos.api import refresh_queue
from api.videos.downloader import upsert_video

# Attach the default routes
attach_routes(api_app)


class TestVideoAPI(TestAPI):

    @wrap_test_db
    def test_get_channels(self):
        # No channels exist yet
        request, response = api_app.test_client.get('/api/videos/channels')
        assert response.status_code == HTTPStatus.OK
        assert response.json == {'channels': []}

        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']
            foo = Channel(name='Foo').flush()
            bar = Channel(name='Bar').flush()
            baz = Channel(name='Baz').flush()
            Video(channel_id=foo['id'], video_path='foo').flush()
            Video(channel_id=bar['id'], video_path='bar').flush()

        request, response = api_app.test_client.get('/api/videos/channels')
        assert response.status_code == HTTPStatus.OK
        # Channels are sorted by name
        self.assertDictContains(response.json['channels'][0], {'id': 2, 'name': 'Bar', 'video_count': 1})
        self.assertDictContains(response.json['channels'][1], {'id': 3, 'name': 'Baz', 'video_count': 0})
        self.assertDictContains(response.json['channels'][2], {'id': 1, 'name': 'Foo', 'video_count': 1})

    @wrap_test_db
    def test_channel(self):
        with tempfile.TemporaryDirectory() as media_dir, \
                mock.patch('api.videos.common.get_media_directory', lambda: pathlib.Path(media_dir)):
            channel_directory = tempfile.TemporaryDirectory(dir=media_dir).name
            pathlib.Path(channel_directory).mkdir()
            new_channel = dict(
                directory=channel_directory,
                match_regex='asdf',
                name='Example Channel 1',
                url='https://example.com/channel1',
            )

            # Channel doesn't exist
            request, response = api_app.test_client.get('/api/videos/channels/examplechannel1')
            assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

            # Create it
            request, response = api_app.test_client.post('/api/videos/channels', data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.CREATED
            location = response.headers['Location']
            request, response = api_app.test_client.get(location)
            created = response.json['channel']
            self.assertIsNotNone(created)
            self.assertIsNotNone(created['id'])

            # Channel directory should be relative to the media directory
            assert not pathlib.Path(created['directory']).is_absolute(), \
                f'Channel directory is absolute: {created["directory"]}'

            # Get the link that was computed
            new_channel['link'] = response.json['channel']['link']
            assert new_channel['link']

            # Can't create it again
            request, response = api_app.test_client.post('/api/videos/channels', data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.BAD_REQUEST

            # Update it
            new_channel['name'] = 'Example Channel 2'
            new_channel['directory'] = str(new_channel['directory'])
            request, response = api_app.test_client.put(location, data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
            request, response = api_app.test_client.get(location)
            assert response.status_code == HTTPStatus.OK
            self.assertDictContains(response.json['channel'], {
                'id': 1,
                'name': 'Example Channel 2',
                'directory': channel_directory,
                'match_regex': 'asdf',
                'url': 'https://example.com/channel1',
            })

            # Patch it
            patch = {'name': 'new name'}
            request, response = api_app.test_client.patch(location, data=json.dumps(patch))
            assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
            request, response = api_app.test_client.get(location)
            assert response.status_code == HTTPStatus.OK
            self.assertDictContains(response.json['channel'], {
                'id': 1,
                'name': 'new name',
                'directory': channel_directory,
                'match_regex': 'asdf',
                'url': 'https://example.com/channel1',
            })

            # Can't update channel that doesn't exist
            request, response = api_app.test_client.put('/api/videos/channels/doesnt_exist',
                                                        data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.NOT_FOUND

            # Delete the new channel
            request, response = api_app.test_client.delete(location)
            assert response.status_code == HTTPStatus.NO_CONTENT

            # Cant delete it again
            request, response = api_app.test_client.delete(location)
            assert response.status_code == HTTPStatus.NOT_FOUND

    @wrap_test_db
    def test_channel_conflicts(self):
        with tempfile.TemporaryDirectory() as media_dir, \
                mock.patch('api.videos.common.get_media_directory', lambda: pathlib.Path(media_dir)):
            channel_directory = tempfile.TemporaryDirectory(dir=media_dir).name
            pathlib.Path(channel_directory).mkdir()
            new_channel = dict(
                directory=channel_directory,
                match_regex='asdf',
                name='Example Channel 1',
                url='https://example.com/channel1',
            )

            def _post_channel(channel):
                return api_app.test_client.post('/api/videos/channels', data=json.dumps(channel))

            # Create it
            request, response = _post_channel(new_channel)
            assert response.status_code == HTTPStatus.CREATED

            # Name is an exact match
            channel_directory2 = tempfile.TemporaryDirectory(dir=media_dir).name
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
            channel_directory2 = tempfile.TemporaryDirectory(dir=media_dir).name
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
            channel_directory3 = tempfile.TemporaryDirectory(dir=media_dir).name
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

    @wrap_test_db
    def test_channel_empty_url_doesnt_conflict(self):
        """Two channels with empty URLs shouldn't conflict"""
        with tempfile.TemporaryDirectory() as media_dir, \
                mock.patch('api.videos.common.get_media_directory', lambda: pathlib.Path(media_dir)):
            channel_directory = tempfile.TemporaryDirectory(dir=media_dir).name
            pathlib.Path(channel_directory).mkdir()

            new_channel = {
                'name': 'Fooz',
                'directory': channel_directory,
            }
            request, response = api_app.test_client.post('/api/videos/channels', data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.CREATED, response.json
            location = response.headers['Location']

            channel_directory2 = tempfile.TemporaryDirectory(dir=media_dir).name
            pathlib.Path(channel_directory2).mkdir()
            new_channel = {
                'name': 'Barz',
                'directory': channel_directory2,
            }
            request, response = api_app.test_client.post('/api/videos/channels', data=json.dumps(new_channel))
            assert response.status_code == HTTPStatus.CREATED, response.json
            assert location != response.headers['Location']

    @wrap_test_db
    def test_refresh_videos(self):
        # There should be no messages until a refresh is called
        pytest.raises(Empty, refresh_queue.get_nowait)

        # Setup a fake channel directory
        with get_db_context() as (db_conn, db), \
                tempfile.TemporaryDirectory() as channel_dir:
            channel_path = pathlib.Path(channel_dir)

            Video, Channel = db['video'], db['channel']

            # Files in subdirectories should be found and handled properly
            subdir = (channel_path / 'subdir')
            subdir.mkdir()

            # These are the types of files that will be found first
            vid1 = pathlib.Path(subdir / 'channel name_20000101_abcdefghijk_title.mp4')
            vid1.touch()
            vid2 = pathlib.Path(channel_path / 'channel name_20000102_bcdefghijkl_title.webm')
            vid2.touch()

            # These files are associated with the video files above, and should be found "near" them
            poster1 = pathlib.Path(subdir / 'channel name_20000101_abcdefghijk_title.jpg')
            poster1.touch()
            poster2 = pathlib.Path(channel_path / 'channel name_20000102_bcdefghijkl_title.jpg')
            poster2.touch()

            # Create a channel, associate videos with it.
            channel = Channel(directory=channel_dir).flush()
            video1 = upsert_video(db, vid1, channel)
            video2 = upsert_video(db, vid2, channel)
            db_conn.commit()
            self.assertEqual({i['video_path'] for i in channel['videos']}, {'subdir/' + vid1.name, vid2.name})

            # Poster files were found
            self.assertEqual(video1['poster_path'], 'subdir/' + poster1.name)
            self.assertEqual(video2['poster_path'], poster2.name)

            # Add a bogus file, this should be removed during the refresh
            self.assertNotIn('foo', {i['video_path'] for i in channel['videos']})
            Video(video_path='foo', channel_id=channel['id']).flush()
            self.assertIn('foo', {i['video_path'] for i in channel['videos']})
            self.assertEqual(len(channel['videos']), 3)

            # Add a video that isn't in the DB, it should be found and any meta files associated with it
            vid3 = pathlib.Path(channel_path / 'channel name_20000103_cdefghijklm_title.flv')
            vid3.touch()
            description3 = pathlib.Path(channel_path / 'channel name_20000103_cdefghijklm_title.description')
            description3.touch()

            # A orphan meta-file should be ignored.  This shouldn't show up anywhere.  But, it shouldn't be deleted.
            # WROLPi should never delete a file.
            poster3 = pathlib.Path(channel_path / 'channel name_20000104_defghijklmn_title.jpg')
            poster3.touch()

            # Finally, call the refresh.  Again, it should remove the "foo" video, then discover this 3rd video
            # file and it's description.
            api_app.test_client.post('/api/videos:refresh')

            # Bogus file was removed
            self.assertNotIn('foo', {i['video_path'] for i in channel['videos']})

            # Final channel video list we built
            expected = {
                ('subdir/' + vid1.name, 'subdir/' + poster1.name, None),  # in a subdirectory, no description
                (vid2.name, poster2.name, None),  # no description
                (vid3.name, None, description3.name),  # no poster
            }
            self.assertEqual(
                {(i['video_path'], i['poster_path'], i['description_path']) for i in channel['videos']},
                expected
            )

            assert poster3.is_file(), 'Orphan jpg file was deleted!  WROLPi should never delete files.'

        # During the refresh process, messages are pushed to a queue, make sure there are messages there
        messages = get_all_messages_in_queue(refresh_queue)
        assert 'refresh-started' in [i.get('code') for i in messages]

    @wrap_test_db
    def test_get_channel_videos(self):
        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']
            channel1 = Channel(name='Foo', link='foo').flush()
            channel2 = Channel(name='Bar', link='bar').flush()

        # Channels don't have videos yet
        d = dict(channel_link=channel1['link'])
        request, response = api_app.test_client.post(f'/api/videos/search', data=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 0

        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']
            Video(title='vid1', channel_id=channel2['id'], video_path='foo').flush()
            Video(title='vid2', channel_id=channel1['id'], video_path='foo').flush()

        # Videos are gotten by their respective channels
        request, response = api_app.test_client.post(f'/api/videos/search', data=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 1
        assert response.json['totals']['videos'] == 1
        self.assertDictContains(response.json['videos'][0], dict(id=2, title='vid2', channel_id=channel1['id']))

        d = dict(channel_link=channel2['link'])
        request, response = api_app.test_client.post(f'/api/videos/search', data=json.dumps(d))
        assert response.status_code == HTTPStatus.OK
        assert len(response.json['videos']) == 1
        self.assertDictContains(response.json['videos'][0], dict(id=1, title='vid1', channel_id=channel2['id']))

    @wrap_test_db
    def test_get_video(self):
        """
        Test that you get can information about a video.  Test that video file can be gotten.
        """

        def raise_unknown_file(_):
            raise UnknownFile()

        with get_db_context(commit=True) as (db_conn, db), \
                mock.patch('api.videos.common.get_absolute_video_info_json', raise_unknown_file):
            Channel, Video = db['channel'], db['video']
            channel = Channel(name='Foo', link='foo').flush()
            Video(title='vidd', channel_id=channel['id']).flush()

            # Test that a 404 is returned when no video exists
            _, response = api_app.test_client.get('/api/videos/video/10')
            assert response.status_code == HTTPStatus.NOT_FOUND, response.json
            assert response.json == {'code': 1, 'error': 'The video could not be found.'}

            # Get the video info we inserted
            _, response = api_app.test_client.get('/api/videos/video/1')
            assert response.status_code == HTTPStatus.OK, response.json
            self.assertDictContains(response.json['video'], {'title': 'vidd'})

    @wrap_test_db
    def test_get_video_prev_next(self):
        """
        Test that the previous and next videos will be retrieved when fetching a video.
        """

        def raise_unknown_file(_):
            raise UnknownFile()

        with get_db_context(commit=True) as (db_conn, db), \
                mock.patch('api.videos.common.get_absolute_video_info_json', raise_unknown_file):
            Channel, Video = db['channel'], db['video']
            channel = Channel(name='Foo', link='foo').flush()
            for i in range(1, 5):
                Video(title=f'vid{i}', channel_id=channel['id']).flush()

            # The first video has no previous video.
            _, response = api_app.test_client.get('/api/videos/video/1')
            self.assertIsNone(response.json['prev'])
            self.assertDictContains(response.json['next'], {'title': 'vid2'})

            # The second video has a previous, and next.
            _, response = api_app.test_client.get('/api/videos/video/2')
            self.assertDictContains(response.json['prev'], {'title': 'vid1'})
            self.assertDictContains(response.json['next'], {'title': 'vid3'})

            # The forth video has no next.
            _, response = api_app.test_client.get('/api/videos/video/4')
            self.assertDictContains(response.json['prev'], {'title': 'vid3'})
            self.assertIsNone(response.json['next'])

    @wrap_test_db
    def test_get_channel_videos_pagination(self):
        with get_db_context(commit=True) as (db_conn, db):
            Channel, Video = db['channel'], db['video']
            channel1 = Channel(name='Foo', link='foo').flush()

            for i in range(50):
                Video(title=f'Foo.Video{i}', channel_id=channel1['id'], video_path='foo').flush()

            channel2 = Channel(name='Bar', link='bar').flush()
            Video(title='vid2', channel_id=channel2['id'], video_path='foo').flush()

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
            d = dict(channel_link=channel1['link'], order_by='id', offset=offset)
            _, response = api_app.test_client.post(f'/api/videos/search', data=json.dumps(d))
            assert response.status_code == HTTPStatus.OK
            assert len(response.json['videos']) == video_count
            current_ids = [i['id'] for i in response.json['videos']]
            assert current_ids != last_ids, f'IDs are unchanged {current_ids=}'
            last_ids = current_ids

    @wrap_test_db
    def test_video_search(self):
        """
        Test that videos can be searched and that their order is by their textsearch rank.
        """
        # These captions have repeated letters so they will be higher in the ranking
        videos = [
            ('1', 'b b b b e d d'),
            ('2', '2 b b b d'),
            ('3', 'b b'),
            ('4', 'b e e'),
            ('5', ''),
        ]
        with get_db_context(commit=True) as (db_conn, db):
            Video = db['video']
            for title, caption in videos:
                Video(title=title, caption=caption, video_path='foo').flush()

        def do_search(search_str, limit=20):
            d = json.dumps({'search_str': search_str, 'limit': limit})
            _, resp = api_app.test_client.post('/api/videos/search', data=d)
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
