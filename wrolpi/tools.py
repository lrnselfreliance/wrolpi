import threading
from contextlib import contextmanager
from threading import Semaphore
from typing import Tuple

import cherrypy
import psycopg2 as psycopg2
from dictorm import DictDB
from psycopg2.pool import ThreadedConnectionPool

from wrolpi.common import logger, setup_relationships, DOCKERIZED


class DBTool(cherrypy.Tool):
    """Setup and attach a DB to a request before the handler gets it.  Teardown the DB after
    a request."""

    def __init__(self):
        self.pool = None
        self.conn = None
        self.db = None
        self.key = None
        cherrypy.Tool.__init__(self, 'before_handler', self.setup_db, priority=25)

    def setup_db(self):
        self.pool, self.conn, self.db, self.key = get_db()
        req = cherrypy.request
        req.params['db'] = self.db
        cherrypy.request.hooks.attach('on_end_request', self.teardown_db, priority=25)

    def teardown_db(self):
        try:
            self.pool.putconn(self.conn, key=self.key, close=True)
        except KeyError:
            # Connection already returned?
            logger.debug(f'Failed to return db connection {self.key}')


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


def get_db(dbname=None):
    # Default database is local development
    db_args = dict(
        dbname=dbname or 'wrolpi',
        user='postgres',
        password='postgres',
        host='127.0.0.1',
        port=54321,
    )
    if DOCKERIZED:
        # Deployed in docker, use the docker postgres
        db_args['host'] = 'postgres'
        db_args['port'] = 5432

    global POOL_SINGLETON
    if not POOL_SINGLETON:
        POOL_SINGLETON = SemaphoreThreadedConnectionPool(0, 20, **db_args, connect_timeout=5)

    key = threading.get_ident()
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

    db_pool.putconn(db_conn, key=key, close=True)


CTX_SETUP = False


def setup_ctx():
    """Setup the Sanic ctx.  Do this only once."""
    global CTX_SETUP
    if CTX_SETUP is False:
        CTX_SETUP = True
