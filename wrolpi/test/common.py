import json
import pathlib
import tempfile
import unittest
from contextlib import contextmanager
from functools import partialmethod
from http import HTTPStatus
from itertools import zip_longest
from queue import Empty
from shutil import copyfile
from typing import List, Optional

import mock
import websockets
import yaml
from sanic_openapi.api import Response

from wrolpi.common import EXAMPLE_CONFIG_PATH, get_config, QUEUES, set_test_media_directory, get_media_directory
from wrolpi.conftest import ROUTES_ATTACHED, test_db, test_client  # noqa
from wrolpi.db import postgres_engine
from wrolpi.vars import PROJECT_DIR

TEST_CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)


def wrap_test_db(func):
    """
    Wrap a test so that when calling wrolpi.common.get_db, it returns a testing database cloned from the api
    template.
    """

    def wrapped(*a, **kw):
        test_engine, session = test_db()

        def fake_get_db_session():
            """Get the testing db"""
            return test_engine, session

        try:
            with mock.patch('wrolpi.db._get_db_session', fake_get_db_session):
                # Run the test.
                result = func(*a, **kw)
                return result
        finally:
            session.rollback()
            session.close()
            test_engine.dispose()
            conn = postgres_engine.connect()
            conn.execute(f'DROP DATABASE IF EXISTS {test_engine.engine.url.database}')

    return wrapped


def get_all_messages_in_queue(q):
    """Get all messages in a Queue without waiting."""
    messages = []
    while True:
        try:
            msg = q.get_nowait()
            messages.append(msg)
        except Empty:
            break
    return messages


class PytestCase:
    """
    Replicate unittest.TestCase methods to bridge the gap between it and Pytest.
    """

    @staticmethod
    def assertGreater(a, b, msg: str = None):  # noqa
        assert a > b, msg

    @staticmethod
    def assertLess(a, b, msg: str = None):  # noqa
        assert a < b, msg

    @staticmethod
    def assertEqual(a, b, msg: str = None):  # noqa
        assert a == b, msg or f'{a} != {b}'

    @staticmethod
    def assertRaises(exception, func, *args, **kwargs):  # noqa
        try:
            func(*args, **kwargs)
        except exception:
            pass

    @classmethod
    def assertDictContains(cls, d1: dict, d2: dict):  # noqa
        if hasattr(d1, '__dict__'):
            d1 = d1.__dict__
        if hasattr(d2, '__dict__'):
            d2 = d2.__dict__

        for k2 in d2.keys():
            assert d1, f'dict 1 is empty: {d1}'
            assert d2, f'dict 1 is empty: {d2}'
            assert k2 in d1, f'dict 1 does not contain {k2}'
            if isinstance(d1[k2], dict):
                cls.assertDictContains(d1[k2], d2[k2])
            else:
                assert d1[k2] == d2[k2], f'{k2} of value "{d1[k2]}" does not equal {d2[k2]} in dict 1'

    def assertError(self, response, http_status: int, code=None):  # noqa
        self.assertEqual(response.status_code, http_status)
        if code:
            self.assertEqual(response.json['code'], code)

    @staticmethod
    def assertTruth(value, expected):  # noqa
        """
        Check that a value is Truthy or Falsy.
        """
        if expected is True:
            assert value, f'Value {value} should have been truthy'
        else:
            assert not value, f'Value {value} should have been falsey'

    assertTruthy = partialmethod(assertTruth, expected=True)
    assertFalsey = partialmethod(assertTruth, expected=False)

    def assertItemsTruthyOrFalsey(self, items_list: List, expected_list: List):
        for d1, d2 in zip_longest(items_list, expected_list):
            for d2_key in d2:
                if d1 is None:
                    raise ValueError('d1 is None')
                if d2 is None:
                    raise ValueError('d2 is None')
                self.assertTruth(d1[d2_key], d2[d2_key])

    @staticmethod
    def assertLength(a, b):  # noqa
        assert len(a) == len(b), f'{len(a)=} != {len(b)=}'


class ExtendedTestCase(PytestCase, unittest.TestCase):
    """
    Add any specialized test methods to this class.
    """
    pass


class TestAPI(ExtendedTestCase):

    def setUp(self) -> None:
        self.config_path_patch = mock.patch('wrolpi.vars.CONFIG_PATH', TEST_CONFIG_PATH.name)
        self.config_path_patch.start()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self.tmp_dir.name)
        set_test_media_directory(self.tmp_dir.name)
        # Copy the example config to test against
        copyfile(str(EXAMPLE_CONFIG_PATH), TEST_CONFIG_PATH.name)
        # Setup the testing video root directory
        config = get_config()
        config['media_directory'] = str(PROJECT_DIR / 'test')
        with open(TEST_CONFIG_PATH.name, 'wt') as fh:
            fh.write(yaml.dump(config))

    def tearDown(self) -> None:
        self.config_path_patch.stop()
        set_test_media_directory(None)
        # Clear out any messages in queues
        for q in QUEUES:
            get_all_messages_in_queue(q)

    def assertHTTPStatus(self, response: Response, status: int):
        self.assertEqual(response.status_code, status)

    assertOK = partialmethod(assertHTTPStatus, status=HTTPStatus.OK)
    assertCONFLICT = partialmethod(assertHTTPStatus, status=HTTPStatus.CONFLICT)
    assertNO_CONTENT = partialmethod(assertHTTPStatus, status=HTTPStatus.NO_CONTENT)


@contextmanager
def wrap_media_directory(path: Optional[pathlib.Path] = None):
    cleanup = False
    if not path:
        path = tempfile.TemporaryDirectory()
        cleanup = True

    set_test_media_directory(path.name)
    try:
        yield
    finally:
        set_test_media_directory(None)
        if cleanup:
            path.cleanup()


@contextmanager
def build_test_directories(paths: List[str], tmp_dir: pathlib.Path = None) -> pathlib.Path:
    """
    Create directories based on the provided structure.

    Example:
        >>> build_test_directories([
                'channel1/vid1.mp4',
                'channel2/vid1.mp4',
                'channel2/vid2.mp4',
                'channel2/vid2.en.vtt'
            ])

        Creates directories like so:
            channel1/vid1.mp4
            channel2/vid1.mp4
            channel2/vid2.mp4
            channel2/vid2.en.vtt
    """
    tmp_dir = tmp_dir or get_media_directory()

    directories = filter(lambda i: i.endswith('/'), paths)
    for directory in directories:
        (tmp_dir / directory).mkdir(parents=True)

    files = filter(lambda i: not i.endswith('/'), paths)
    for file in files:
        file = tmp_dir / file
        parents = file.parents
        parents[0].mkdir(parents=True, exist_ok=True)
        (tmp_dir / file).touch()

    yield tmp_dir.absolute()


async def get_all_ws_messages(ws) -> List[dict]:
    messages = []
    while True:
        try:
            message = await ws.recv()
        except websockets.exceptions.ConnectionClosedOK:
            break
        messages.append(json.loads(message))
    return messages
