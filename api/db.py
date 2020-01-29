import threading
from contextlib import contextmanager
from threading import Semaphore
from typing import Tuple

import psycopg2
from dictorm import DictDB
from psycopg2._psycopg import connection
from psycopg2.errors import InFailedSqlTransaction
from psycopg2.pool import ThreadedConnectionPool

from api.vars import DOCKERIZED


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


def get_db(dbname=None) -> Tuple[SemaphoreThreadedConnectionPool, connection, DictDB, int]:
    # Default database is local development
    db_args = dict(
        dbname=dbname or 'wrolpi',
        user='postgres',
        password='postgres',
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

    try:
        db = DictDB(db_conn)
    except InFailedSqlTransaction:
        # Connection has unresolvable error, recreate the pool
        POOL_SINGLETON.closeall()
        POOL_SINGLETON = SemaphoreThreadedConnectionPool(0, 20, **db_args, connect_timeout=5)
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

    db_pool.putconn(db_conn, key=key, close=True)


def setup_relationships(db):
    """Assign all relationships between DictORM Tables."""
    Channel = db['channel']
    Video = db['video']
    Channel['videos'] = Channel['id'].many(Video['channel_id'])
    Video['channel'] = Video['channel_id'] == Channel['id']
