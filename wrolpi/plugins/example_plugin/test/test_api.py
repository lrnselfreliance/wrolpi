"""
This will test your code (you're going to test your code, right?).  Here are some simple tests.

Keep your tests simple!  Don't test things like the full HTML of an endpoint, what if the base.html is changed out from
under you?
"""
import unittest

from wrolpi.common import get_db_context
from wrolpi.plugins.example_plugin.api import APIRoot
from wrolpi.plugins.example_plugin.common import hello
from wrolpi.test.common import test_db_wrapper


class TestAPI(unittest.TestCase):

    def test_hello(self):
        self.assertEqual(hello(), 'world')

    @test_db_wrapper
    def test_get(self):
        api = APIRoot()
        with get_db_context() as (db_conn, db):
            self.assertEqual(api.settings.GET(db), '{"hello": "world"}')
