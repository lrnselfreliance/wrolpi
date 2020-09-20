import threading
from contextlib import contextmanager
from threading import Semaphore
from typing import Tuple

import psycopg2
from dictorm import DictDB
from psycopg2._psycopg import connection
from psycopg2.errors import InFailedSqlTransaction
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool

from api.common import logger
from api.vars import DOCKERIZED

db_logger = logger.getChild(__name__)


class SemaphoreThreadedConnectionPool(ThreadedConnectionPool):
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


def get_simple_db(dbname=None):
    # Default database is local development
    db_args = dict(
        dbname=dbname or 'wrolpi',
        user='postgres',
        password='wrolpi',
        host='127.0.0.1',
        port=54321,
    )
    if DOCKERIZED:
        # Deployed in docker, use the docker db
        db_args['host'] = 'db'
        db_args['port'] = 5432

    global POOL_SINGLETON
    if not POOL_SINGLETON:
        POOL_SINGLETON = SemaphoreThreadedConnectionPool(0, 20, **db_args, connect_timeout=5)

    key = threading.get_ident()
    db_conn = POOL_SINGLETON.getconn(key=key)

    return POOL_SINGLETON, db_conn, key, db_args


@contextmanager
def get_db_curs(commit=False) -> psycopg2.connect:
    db_pool, db_conn, key, _ = get_simple_db()

    curs = db_conn.cursor(cursor_factory=DictCursor)
    yield curs

    if commit:
        db_conn.commit()
    else:
        db_conn.rollback()

    db_pool.putconn(db_conn, key=key, close=True)


def get_db(dbname=None) -> Tuple[SemaphoreThreadedConnectionPool, connection, DictDB, int]:
    db_pool, db_conn, key, db_args = get_simple_db(dbname)

    try:
        db = DictDB(db_conn)
    except (InFailedSqlTransaction, psycopg2.InterfaceError) as e:
        # Connection has unresolvable error, recreate the pool
        db_logger.warning('DB connection pool in a failed state, recreating pool...', exc_info=e)
        db_pool.closeall()
        db_pool = SemaphoreThreadedConnectionPool(0, 20, **db_args, connect_timeout=5)
        db = DictDB(db_conn)

    setup_relationships(db)
    return db_pool, db_conn, db, key


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

    db_pool.putconn(db_conn, key=key, close=True)


def setup_relationships(db):
    """Assign all relationships between DictORM Tables."""
    Channel = db['channel']
    Video = db['video']
    Channel['videos'] = Channel['id'].many(Video['channel_id'])
    Video['channel'] = Video['channel_id'] == Channel['id']

    Inventory = db['inventory']
    Item = db['item']
    Inventory['items'] = Inventory['id'].many(Item['inventory_id'])
