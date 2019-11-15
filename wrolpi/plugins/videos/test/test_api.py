import json
import pathlib
import tempfile
import unittest
from http import HTTPStatus
from shutil import copyfile

import mock
import yaml

from wrolpi.plugins.videos.common import import_settings_config, get_downloader_config, EXAMPLE_CONFIG_PATH, get_config
from wrolpi.plugins.videos.downloader import insert_video
from wrolpi.test.common import wrap_test_db
from wrolpi.db import get_db_context
from wrolpi.web import webapp, attach_routes

CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)
cwd = pathlib.Path(__file__).parents[4]

# Attach the default routes
attach_routes(webapp)


@mock.patch('wrolpi.plugins.videos.common.CONFIG_PATH', CONFIG_PATH.name)
class TestAPI(unittest.TestCase):

    def setUp(self) -> None:
        # Copy the example config to test against
        copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH.name)
        # Setup the testing video root directory
        config = get_config()
        config['downloader']['video_root_directory'] = cwd / 'test/example_videos'
        with open(CONFIG_PATH.name, 'wt') as fh:
            fh.write(yaml.dump(config))

    @wrap_test_db
    def test_configs(self):
        original = get_downloader_config()
        self.assertNotEqual(original['video_root_directory'], 'foo')
        self.assertNotEqual(original['file_name_format'], 'bar')

        data = {'video_root_directory': 'foo', 'file_name_format': 'bar'}
        webapp.test_client.put('/api/videos/settings', data=json.dumps(data))

        self.assertEqual(import_settings_config(), 0)
        updated = get_downloader_config()
        diff = set(updated.items()).difference(set(original.items()))
        expected = {('video_root_directory', 'foo'), ('file_name_format', 'bar')}
        self.assertEqual(diff, expected)

    @wrap_test_db
    def test_refresh(self):
        with get_db_context(commit=True) as (db_conn, db):
            Video = db['video']
            import_settings_config()

            # Insert a bogus video, it should be removed
            bogus = Video(video_path='bar').flush()
            assert bogus and bogus['id'], 'Failed to insert a bogus video for removal'

        request, response = webapp.test_client.post('/api/videos/settings/refresh')
        assert response.status_code == HTTPStatus.OK

        with get_db_context() as (db_conn, db):
            Video, Channel = db['video'], db['channel']
            self.assertEqual(Channel.count(), 1)
            self.assertGreater(Video.count(), 1)

    @wrap_test_db
    def test_channel(self):
        channel_directory = tempfile.TemporaryDirectory().name
        pathlib.Path(channel_directory).mkdir()
        new_channel = dict(
            directory=channel_directory,
            match_regex='asdf',
            name='Example Channel 1',
            url='https://example.com/channel1',
        )

        # Channel doesn't exist
        request, response = webapp.test_client.get('/api/videos/channel/examplechannel1')
        assert response.status_code == HTTPStatus.NOT_FOUND, f'Channel exists: {response.json}'

        # Create it
        request, response = webapp.test_client.post('/api/videos/channel', data=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.CREATED
        location = response.headers['Location']
        request, response = webapp.test_client.get(location)
        created = response.json['channel']
        self.assertIsNotNone(created)
        self.assertIsNotNone(created['id'])

        # Get the link that was decided
        new_channel['link'] = response.json['channel']['link']
        assert new_channel['link']

        # Can't create it again
        request, response = webapp.test_client.post('/api/videos/channel', data=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.BAD_REQUEST

        # Update it
        new_channel['name'] = 'Example Channel 2'
        new_channel['directory'] = str(new_channel['directory'])
        request, response = webapp.test_client.put(location, data=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.OK, response.status_code

        # Can't update channel that doesn't exist
        request, response = webapp.test_client.put('/api/videos/channel/doesnt_exist', data=json.dumps(new_channel))
        assert response.status_code == HTTPStatus.NOT_FOUND

        # Delete the new channel
        request, response = webapp.test_client.delete(location)
        assert response.status_code == HTTPStatus.OK

        # Cant delete it again
        request, response = webapp.test_client.delete(location)
        assert response.status_code == HTTPStatus.NOT_FOUND

    @wrap_test_db
    def test_refresh_videos(self):
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
            video1 = insert_video(db, vid1, channel)
            video2 = insert_video(db, vid2, channel)
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
            request, response = webapp.test_client.post('/api/videos/settings/refresh')

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
