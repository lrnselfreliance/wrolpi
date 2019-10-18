import os
from contextlib import contextmanager
from threading import Semaphore
from typing import Tuple
from uuid import uuid4

import cherrypy
import psycopg2 as psycopg2
from dictorm import DictDB
from psycopg2.pool import ThreadedConnectionPool

from wrolpi.common import logger, setup_relationships


class DBTool(cherrypy.Tool):
    """Setup and attach a DB to a request before the handler gets it.  Teardown the DB after
    a request."""

    def __init__(self):
        self.pool = None
        self.conn = None
        self.db = None
        cherrypy.Tool.__init__(self, 'before_handler', self.setup_db, priority=25)

    def setup_db(self):
        self.pool, self.conn, self.db, self.key = get_db()
        req = cherrypy.request
        req.params['db'] = self.db

    def _setup(self):
        cherrypy.Tool._setup(self)
        cherrypy.request.hooks.attach('on_end_request', self.teardown_db, priority=25)

    def teardown_db(self):
        try:
            self.pool.putconn(self.conn, key=self.key, close=False)
        except KeyError:
            # connection with this key was already closed
            logger.debug('Failed to putconn, already closed?')


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
        POOL_SINGLETON = SemaphoreThreadedConnectionPool(5, 100, **db_args, connect_timeout=5)

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
