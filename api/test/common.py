import pathlib
import tempfile
import unittest
from contextlib import contextmanager
from functools import wraps, partialmethod
from http import HTTPStatus
from queue import Empty, Queue
from shutil import copyfile
from typing import List
from uuid import uuid1

import mock
import psycopg2
import yaml
from dictorm import DictDB
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sanic_openapi.api import Response

from api.api import api_app, attach_routes
from api.common import EXAMPLE_CONFIG_PATH, get_config, ProgressReporter, insert_parameter
from api.db import setup_relationships, get_db_context
from api.vars import DOCKERIZED, PROJECT_DIR
from api.videos.api import refresh_queue, download_queue
from api.videos.lib import refresh_channel_videos

# Attach the default routes
attach_routes(api_app)

TEST_CONFIG_PATH = tempfile.NamedTemporaryFile(mode='rt', delete=False)


def wrap_test_db(func):
    """
    Wrap a test so that when calling api.common.get_db, it returns a testing database cloned from the api
    template.
    """

    def wrapped(*a, **kw):
        # This is the Docker db container
        db_args = dict(
            user='postgres',
            password='wrolpi',
            host='127.0.0.1',
            port=54321,
        )

        if DOCKERIZED:
            db_args['host'] = 'db'
            db_args['port'] = 5432

        # Every test gets it's own DB
        suffix = str(uuid1()).replace('-', '')
        testing_db_name = f'wrolpi_testing_{suffix}'

        # Set isolation level such that was can copy the schema of the "api" database for testing
        with psycopg2.connect(dbname='postgres', **db_args) as db_conn:
            db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            # Cleanup the old testing db (if any), then copy the schema
            curs = db_conn.cursor()
            drop_testing = f'DROP DATABASE IF EXISTS {testing_db_name}'
            curs.execute(drop_testing)
            curs.execute(f'CREATE DATABASE {testing_db_name} TEMPLATE wrolpi')

            class FakePool:

                def putconn(self, conn, *a, **kw):
                    pass

            # Connect to the new testing DB.  Reset all tables and sequences
            testing_db_conn = psycopg2.connect(dbname=testing_db_name, **db_args)
            testing_curs = testing_db_conn.cursor()
            testing_curs.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            table_names = [i for (i,) in testing_curs.fetchall()]
            testing_curs.execute('; '.join(f'TRUNCATE {table} RESTART IDENTITY CASCADE' for table in table_names))
            testing_db_conn.commit()

            try:
                testing_db = DictDB(testing_db_conn)
                setup_relationships(testing_db)

                def fake_get_db():
                    """Get the testing db"""
                    return FakePool(), testing_db_conn, testing_db, None

                with mock.patch('api.db.get_db', fake_get_db):
                    result = func(*a, **kw)
                    return result

            finally:
                testing_db_conn.close()
                db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                curs.execute(drop_testing)

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
        for k2 in d2.keys():
            assert d1, f'dict 1 is empty: {d1}'
            assert d2, f'dict 1 is empty: {d2}'
            assert k2 in d1, f'dict 1 does not contain {k2}'
            assert d1[k2] == d2[k2], f'{k2} of value "{d1[k2]}" does not equal {d2[k2]} in dict 1'

    def assertError(self, response, http_status: int, code=None):
        self.assertEqual(response.status_code, http_status)
        if code:
            self.assertEqual(response.json['code'], code)


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

                with get_db_context(commit=True) as (db_conn, db):
                    Channel, Video = db['channel'], db['video']
                    for channel in structure:
                        channel = Channel(directory=str(tempdir / channel), name=channel).flush()
                        refresh_channel_videos(channel, reporter)

                return func(*args, **kwargs)

        return wrapped

    return wrapper
