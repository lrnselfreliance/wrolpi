import json
import pathlib
import tempfile
import unittest
from unittest import mock

from wrolpi.common import set_test_media_directory
from wrolpi.media_path import MediaPath
from wrolpi.root_api import CustomJSONEncoder


class TestMediaPath(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        set_test_media_directory(pathlib.Path(self.test_dir.name))
        path = pathlib.Path(self.test_dir.name).absolute()
        self.patch = mock.patch('wrolpi.media_path.get_media_directory', lambda: path)
        self.patch.start()

    def tearDown(self):
        set_test_media_directory(None)
        self.test_dir.cleanup()
        self.patch.stop()

    def test_errors(self):
        self.assertRaises(ValueError, MediaPath, '')
        self.assertRaises(ValueError, MediaPath, '/')

    def test_json(self):
        p = MediaPath('foo')
        result = json.dumps(p, cls=CustomJSONEncoder)
        self.assertEqual(result, '"foo"')

    def test_paths(self):
        # Paths may be relative to media directory.
        d = MediaPath('foo')
        self.assertEqual(d._path, pathlib.Path(f'{self.test_dir.name}/foo'))

        # Absolute paths must be in media directory.
        d = MediaPath(f'{self.test_dir.name}/foo')
        self.assertEqual(d._path, pathlib.Path(f'{self.test_dir.name}/foo'))

        # Error is raised when the path is not in the media path.
        self.assertRaises(ValueError, MediaPath, '/tmp/foo')

    def test_repr(self):
        d = MediaPath('foo')
        assert self.test_dir.name not in repr(d)
        assert self.test_dir.name not in str(d)
