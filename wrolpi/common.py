import configparser
import logging
import os
import string
import sys
from contextlib import contextmanager
from threading import Semaphore
from typing import Tuple
from uuid import uuid4

import psycopg2 as psycopg2
from dictorm import DictDB
from jinja2 import Environment, FileSystemLoader
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Jinja2 environment
env = Environment(loader=FileSystemLoader('.'))

CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'


def get_wrolpi_config():
    config = configparser.RawConfigParser()
    config.read(CONFIG_PATH)
    try:
        return config[WROLPI_CONFIG_SECTION]
    except KeyError:
        logger.fatal('Cannot load WROLPi.cfg config!')
        sys.exit(1)


class ReallyThreadedConnectionPool(ThreadedConnectionPool):
    def __init__(self, minconn, maxconn, *args, **kwargs):
        self._semaphore = Semaphore(maxconn)
        super().__init__(minconn, maxconn, *args, **kwargs)

    def getconn(self, *args, **kwargs):
        self._semaphore.acquire()
        return super().getconn(*args, **kwargs)

    def putconn(self, *args, **kwargs):
        super().putconn(*args, **kwargs)
        self._semaphore.release()


POOL_SINGLETON = None


def get_db():
    # Default database is local development
    db_args = dict(
        dbname='wrolpi',
        user='postgres',
        password='postgres',
        host='127.0.0.1',
        port=54321,
    )
    if os.environ.get('DOCKER', '').lower().startswith('t'):
        # This database connection is when deployed using docker
        db_args = dict(
            dbname='wrolpi',
            user='postgres',
            password='postgres',
            host='postgres',
            port=5432,
        )

    global POOL_SINGLETON
    if not POOL_SINGLETON:
        POOL_SINGLETON = ReallyThreadedConnectionPool(5, 100, **db_args, connect_timeout=5)

    key = str(uuid4())
    db_conn = POOL_SINGLETON.getconn(key=key)

    db = DictDB(db_conn)
    setup_relationships(db)
    return POOL_SINGLETON, db_conn, db, key


@contextmanager
def get_db_context(commit=False) -> Tuple[psycopg2.connect, DictDB]:
    """Context manager that creates a DB connection as well as a DictDB object.  Commits when
    requested, otherwise it will always rollback."""
    db_pool, db_conn, db, key = get_db()
    yield db_conn, db
    if commit:
        db_conn.commit()
    else:
        db_conn.rollback()

    try:
        db_pool.putconn(db_conn, key=key, close=False)
    except KeyError:
        # connection with this key was already closed
        logger.debug('Failed to putconn, already closed?')


def setup_relationships(db):
    """Assign all relationships between DictORM Tables."""
    Channel = db['channel']
    Video = db['video']
    Channel['videos'] = Channel['id'].many(Video['channel_id'])
    Video['channel'] = Video['channel_id'] == Channel['id']


URL_CHARS = string.ascii_lowercase + string.digits


def sanitize_link(link: str) -> str:
    """Remove any non-url safe characters, all will be lowercase."""
    new_link = ''.join(i for i in str(link).lower() if i in URL_CHARS)
    return new_link
