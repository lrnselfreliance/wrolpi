import contextlib
import json
import pathlib
import tempfile
import unittest
from contextlib import contextmanager
from functools import wraps, partialmethod
from http import HTTPStatus
from itertools import zip_longest
from queue import Empty, Queue
from shutil import copyfile
from typing import List, Tuple
from uuid import uuid1

import mock
import websockets
import yaml
from sanic_openapi.api import Response
from sqlalchemy import MetaData
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from api.api import api_app, attach_routes
from api.common import EXAMPLE_CONFIG_PATH, get_config, ProgressReporter, insert_parameter, Base
from api.db import get_db_context, postgres_engine, get_db_args
from api.vars import PROJECT_DIR
from api.videos.api import refresh_queue, download_queue
from api.videos.lib import refresh_channel_videos
from api.videos.models import Channel

# Attach the default routes
attach_routes(api_app)

TEST_CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)


def reset_database_tables(engine):
    """
    Remove all rows from every table in a database.
    """
    # curs = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    # tables = curs.fetchall()
    # if tables:
    #     table_names = [i for (i,) in curs.fetchall()]
    #     conn.execute('; '.join(f'TRUNCATE {table} RESTART IDENTITY CASCADE' for table in table_names))
    #     conn.execute('commit')

    meta = MetaData()

    with contextlib.closing(engine.connect()) as con:
        trans = con.begin()
        for table in reversed(meta.sorted_tables):
            con.execute(table.delete())
        trans.commit()


def get_test_db_engine():
    suffix = str(uuid1()).replace('-', '')
    db_name = f'wrolpi_testing_{suffix}'
    conn = postgres_engine.connect()
    conn.execute(f'DROP DATABASE IF EXISTS {db_name}')
    conn.execute(f'CREATE DATABASE {db_name} TEMPLATE wrolpi')
    conn.execute('commit')

    test_args = get_db_args(db_name)
    test_engine = create_engine('postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**test_args))
    reset_database_tables(test_engine)
    return test_engine


def test_db() -> Tuple[Engine, Session]:
    """
    Create a unique SQLAlchemy engine/session for a test.
    """
    test_engine = get_test_db_engine()
    Base.metadata.create_all(test_engine)
    session = sessionmaker(bind=test_engine)()
    return test_engine, session


def wrap_test_db(func):
    """
    Wrap a test so that when calling api.common.get_db, it returns a testing database cloned from the api
    template.
    """

    def wrapped(*a, **kw):
        test_engine, session = test_db()

        def fake_get_db_context():
            """Get the testing db"""
            return test_engine, session

        try:
            with mock.patch('api.db._get_db_session', fake_get_db_context):
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


class ExtendedTestCase(unittest.TestCase):
    """
    Add any specialized test methods to this class.
    """

    @staticmethod
    def assertDictContains(d1: dict, d2: dict):
        if hasattr(d1, '__dict__'):
            d1 = d1.__dict__
        if hasattr(d2, '__dict__'):
            d2 = d2.__dict__

        for k2 in d2.keys():
            assert d1, f'dict 1 is empty: {d1}'
            assert d2, f'dict 1 is empty: {d2}'
            assert k2 in d1, f'dict 1 does not contain {k2}'
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


class TestAPI(ExtendedTestCase):

    def setUp(self) -> None:
        self.patch = mock.patch('api.common.CONFIG_PATH', TEST_CONFIG_PATH.name)
        self.patch.start()
        # Copy the example config to test against
        copyfile(str(EXAMPLE_CONFIG_PATH), TEST_CONFIG_PATH.name)
        # Setup the testing video root directory
        config = get_config()
        config['media_directory'] = str(PROJECT_DIR / 'test')
        with open(TEST_CONFIG_PATH.name, 'wt') as fh:
            fh.write(yaml.dump(config))

    def tearDown(self) -> None:
        self.patch.stop()
        # Clear out any messages in queues
        get_all_messages_in_queue(refresh_queue)
        get_all_messages_in_queue(download_queue)

    def assertHTTPStatus(self, response: Response, status: int):
        self.assertEqual(response.status_code, status)

    assertOK = partialmethod(assertHTTPStatus, status=HTTPStatus.OK)
    assertCONFLICT = partialmethod(assertHTTPStatus, status=HTTPStatus.CONFLICT)
    assertNO_CONTENT = partialmethod(assertHTTPStatus, status=HTTPStatus.NO_CONTENT)


@contextmanager
def build_test_directories(paths: List[str]) -> pathlib.Path:
    """
    Create directories based on the provided structure.

    Example:
        >>> create_db_structure([
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


def create_db_structure(structure):
    """
    Create a directory containing the specified structure of channels and videos.  Create DB entries for these
    channels and videos.

    Example:
        >>> s = {'channel1': ['vid1.mp4'], 'channel2': ['vid1.mp4', 'vid2.mp4', 'vid2.en.vtt']}
        >>> create_db_structure(s)

        Creates directories like so:
            channel1/vid1.mp4
            channel2/vid1.mp4
            channel2/vid2.mp4
            channel2/vid2.en.vtt

        Channels like so:
            Channel(name='channel1', directory='channel1')
            Channel(name='channel2', directory='channel2')

        And, Videos like so:
            Video(channel_id=1, video_path='vid1.mp4')
            Video(channel_id=2, video_path='vid1.mp4')
            Video(channel_id=2, video_path='vid2.mp4', caption_path='vid2.en.vtt')
    """

    def wrapper(func):
        @wraps(func)
        @wrap_test_db
        def wrapped(*args, **kwargs):
            # Dummy queue and reporter to receive messages.
            q = Queue()
            reporter = ProgressReporter(q, 2)

            # Convert the channel/video structure to a file structure for the test.
            file_structure = []
            for channel, paths in structure.items():
                for path in paths:
                    file_structure.append(f'{channel}/{path}')
                file_structure.append(f'{channel}/')

            with build_test_directories(file_structure) as tempdir:
                args, kwargs = insert_parameter(func, 'tempdir', tempdir, args, kwargs)

                with get_db_context(commit=True) as (engine, session):
                    for channel in structure:
                        channel = Channel(directory=str(tempdir / channel), name=channel)
                        session.add(channel)
                        session.flush()
                        session.refresh(channel)
                        refresh_channel_videos(channel, reporter)

                return func(*args, **kwargs)

        return wrapped

    return wrapper


async def get_all_ws_messages(ws) -> List[dict]:
    messages = []
    while True:
        try:
            message = await ws.recv()
        except websockets.exceptions.ConnectionClosedOK:
            break
        messages.append(json.loads(message))
    return messages
