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
from typing import List, Tuple, Optional
from uuid import uuid1

import mock
import websockets
import yaml
from sanic_openapi.api import Response
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wrolpi.common import EXAMPLE_CONFIG_PATH, get_config, Base, QUEUES, set_test_media_directory
from wrolpi.db import postgres_engine, get_db_args
from wrolpi.root_api import BLUEPRINTS, api_app
from wrolpi.vars import PROJECT_DIR

TEST_CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)


def get_test_db_engine():
    suffix = str(uuid1()).replace('-', '')
    db_name = f'wrolpi_testing_{suffix}'
    conn = postgres_engine.connect()
    conn.execute(f'DROP DATABASE IF EXISTS {db_name}')
    conn.execute(f'CREATE DATABASE {db_name}')
    conn.execute('commit')

    test_args = get_db_args(db_name)
    test_engine = create_engine('postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**test_args))
    return test_engine


def test_db() -> Tuple[Engine, Session]:
    """
    Create a unique SQLAlchemy engine/session for a test.
    """
    test_engine = get_test_db_engine()
    if test_engine.engine.url.database == 'wrolpi':
        raise ValueError('Refusing the test on wrolpi database!')

    # Create all tables.  No need to check if they exist because this is a test DB.
    Base.metadata.create_all(test_engine, checkfirst=False)
    session = sessionmaker(bind=test_engine)()
    return test_engine, session


def wrap_test_db(func):
    """
    Wrap a test so that when calling wrolpi.common.get_db, it returns a testing database cloned from the api
    template.
    """

    def wrapped(*a, **kw):
        test_engine, session = test_db()

        def fake_get_db_context():
            """Get the testing db"""
            return test_engine, session

        try:
            with mock.patch('wrolpi.db._get_db_session', fake_get_db_context):
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
    def assertGreater(a, b, msg: str = None):
        assert a > b, msg

    @staticmethod
    def assertLess(a, b, msg: str = None):
        assert a < b, msg

    @staticmethod
    def assertEqual(a, b, msg: str = None):
        assert a == b, msg or f'{a} != {b}'

    @staticmethod
    def assertRaises(exception, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except exception:
            pass

    @classmethod
    def assertDictContains(cls, d1: dict, d2: dict):
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

    def assertError(self, response, http_status: int, code=None):
        self.assertEqual(response.status_code, http_status)
        if code:
            self.assertEqual(response.json['code'], code)

    @staticmethod
    def assertTruth(value, expected):
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


class ExtendedTestCase(PytestCase, unittest.TestCase):
    """
    Add any specialized test methods to this class.
    """
    pass


ROUTES_ATTACHED = False


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

    @classmethod
    def setUpClass(cls) -> None:
        global ROUTES_ATTACHED
        if ROUTES_ATTACHED is False:
            # Attach any blueprints for the test.
            for bp in BLUEPRINTS:
                api_app.blueprint(bp)
            ROUTES_ATTACHED = True

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
def build_test_directories(paths: List[str]) -> pathlib.Path:
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
    dir_ = get_config().get('media_directory')
    dir_ = pathlib.Path(dir_).absolute()
    with tempfile.TemporaryDirectory(dir=dir_) as temp_dir:
        root = pathlib.Path(temp_dir)

        directories = filter(lambda i: i.endswith('/'), paths)
        for directory in directories:
            (root / directory).mkdir(parents=True)

        files = filter(lambda i: not i.endswith('/'), paths)
        for file in files:
            file = root / file
            parents = file.parents
            parents[0].mkdir(parents=True, exist_ok=True)
            (root / file).touch()

        yield root.absolute()


async def get_all_ws_messages(ws) -> List[dict]:
    messages = []
    while True:
        try:
            message = await ws.recv()
        except websockets.exceptions.ConnectionClosedOK:
            break
        messages.append(json.loads(message))
    return messages
