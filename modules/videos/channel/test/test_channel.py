import pathlib
import unittest

from modules.videos.models import Channel
from modules.videos.test.common import create_channel_structure
from wrolpi.db import get_db_session
from wrolpi.test.common import wrap_test_db


class TestChannel(unittest.TestCase):

    @wrap_test_db
    @create_channel_structure(
        {
            'Foo': ['vid1.mp4'],
        }
    )
    def test_channel(self, tempdir):
        with get_db_session() as session:
            channel = session.query(Channel).one()
            self.assertIsInstance(channel.directory, pathlib.Path)
