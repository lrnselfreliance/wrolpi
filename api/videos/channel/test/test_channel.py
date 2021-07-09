import pathlib
import unittest

from api.db import get_db_context
from api.test.common import wrap_test_db, create_db_structure
from api.videos.models import Channel


class TestChannel(unittest.TestCase):

    @wrap_test_db
    @create_db_structure(
        {
            'Foo': ['vid1.mp4'],
        }
    )
    def test_channel(self, tempdir):
        with get_db_context() as (engine, session):
            channel = session.query(Channel).one()
            self.assertIsInstance(channel.directory, pathlib.Path)
