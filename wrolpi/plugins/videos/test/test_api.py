import json
import tempfile
import unittest
from shutil import copyfile

import cherrypy
import mock
from cherrypy.test import helper

from wrolpi.common import get_db_context
from wrolpi.plugins.videos.api import APIRoot
from wrolpi.plugins.videos.common import import_settings_config, get_downloader_config, EXAMPLE_CONFIG_PATH
from wrolpi.test.common import test_db_wrapper

CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)


@mock.patch('wrolpi.plugins.videos.common.CONFIG_PATH', CONFIG_PATH.name)
class TestAPI(unittest.TestCase):

    def setUp(self) -> None:
        # Copy the example config to test against
        copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH.name)

    @test_db_wrapper
    def test_configs(self):
        original = get_downloader_config()
        self.assertNotEqual(original['video_root_directory'], 'foo')
        self.assertNotEqual(original['file_name_format'], 'bar')

        api = APIRoot()
        form_data = {
            'video_root_directory': 'foo',
            'file_name_format': 'bar',
        }
        api.settings.PUT(**form_data)

        self.assertEqual(import_settings_config(), 0)
        updated = get_downloader_config()
        diff = set(updated.items()).difference(set(original.items()))
        self.assertEqual(diff,
                         {
                             ('video_root_directory', 'foo'),
                             ('file_name_format', 'bar'),
                         })

    @test_db_wrapper
    def test_refresh(self):
        api = APIRoot()
        with get_db_context(commit=True) as (db_conn, db):
            Video = db['video']
            import_settings_config()

            # Insert a bogus video, it should be removed
            bogus = Video(video_path='bar').flush()
            assert bogus['id'], 'Failed to insert a bogus video for removal'

        # TODO this test is very fragile :(
        streamer = api.settings.refresh.POST()
        statuses = list(streamer)
        self.assertIn('Verifying videos in DB exist in file system\n', statuses)
        self.assertIn('Deleting video files no longer in file system\n', statuses)
        self.assertIn('Checking Big Buck Bunny directory for new videos\n', statuses)
        self.assertEqual('stream-complete\n', statuses[-1])

        with get_db_context() as (db_conn, db):
            Video, Channel = db['video'], db['channel']
            self.assertEqual(Channel.count(), 1)
            self.assertGreater(Video.count(), 1)

    @test_db_wrapper
    def test_channel(self):
        api = APIRoot()
        new_channel = dict(
            directory='/tmp/channel1',
            match_regex='asdf',
            name='Example Channel 1',
            url='https://example.com/channel1',
        )

        with get_db_context() as (db_conn, db):
            Channel = db['channel']

            # Channel doesn't exist
            existing = api.channel.GET('examplechannel1', db)
            self.assertIn('error', existing)

            # Create it
            result = api.channel.POST(db, **new_channel)
            self.assertIn('success', result)
            response = api.channel.GET('examplechannel1', db)
            created = json.loads(response)['channel']
            self.assertIsNotNone(created)
            self.assertIsNotNone(created['id'])

            # Can't create it again
            result = api.channel.POST(db, **new_channel)
            self.assertIn('error', result)

            # Update it
            new_channel['name'] = 'Example Channel 2'
            new_channel['directory'] = str(new_channel['directory'])
            result = api.channel.PUT('examplechannel1', db, **new_channel)
            self.assertIn('success', result)
            updated = Channel.get_one(link='examplechannel1')
            self.assertIsNotNone(updated['id'])
            self.assertEqual(updated['name'], new_channel['name'])

            # Can't update channel that doesn't exist
            result = api.channel.PUT('DoesntExist', db, **new_channel)
            self.assertIn('error', result)

            # Delete the new channel
            result = api.channel.DELETE('examplechannel1', db)
            self.assertIn('success', result)
