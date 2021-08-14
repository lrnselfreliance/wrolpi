from contextlib import contextmanager
from typing import Tuple, ContextManager

import psycopg2
import sqlalchemy.exc
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from api.common import logger
from api.vars import DOCKERIZED

logger = logger.getChild(__name__)


def get_db_args(dbname: str = None):
    db_args = dict(
        dbname=dbname or 'wrolpi',
        user='postgres',
        password='wrolpi',
        host='127.0.0.1',
        port=54321,
    )
    if DOCKERIZED:
        # Deployed in docker, use the docker database.
        db_args['host'] = 'db'
        db_args['port'] = 5432

    return db_args


# This engine is used to modify the databases.
connect_args = dict(application_name='wrolpi_api_super')
postgres_args = get_db_args('postgres')
postgres_engine = create_engine('postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**postgres_args),
                                execution_options={'isolation_level': 'AUTOCOMMIT'}, connect_args=connect_args)

# This engine is used for all normal tasks (except testing).
db_args = get_db_args()
connect_args = dict(application_name='wrolpi_api')
uri = 'postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**db_args)
engine = create_engine(uri, poolclass=NullPool, connect_args=connect_args)
session_maker = sessionmaker(bind=engine)

LOGGED_ARGS = False


def _get_db_session():
    """This function allows the database to be wrapped during testing.  See: api.test.common.wrap_test_db"""
    global LOGGED_ARGS
    if LOGGED_ARGS is False:
        # Print the DB args for troubleshooting.
        LOGGED_ARGS = True
        logging_args = db_args.copy()
        logging_args['password'] = '***'
        logger.debug(f'DB args: {logging_args}')

    session = session_maker()
    return engine, session


@contextmanager
def get_db_context(commit: bool = False) -> ContextManager[Tuple[Engine, Session]]:
    """Context manager that creates a DB session.  This will automatically rollback changes, unless `commit` is True."""
    local_engine, session = _get_db_session()
    try:
        yield local_engine, session
        if commit:
            session.commit()
    except sqlalchemy.exc.DatabaseError:
        session.rollback()
        raise
    finally:
        # Rollback only if a transaction hasn't been committed.
        if session.transaction.is_active:
            session.rollback()


@contextmanager
def get_db_curs(commit: bool = False):
    """Context manager that yields a DictCursor to execute raw SQL statements."""
    local_engine, session = _get_db_session()
    connection = local_engine.raw_connection()
    curs = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        yield curs
        if commit:
            connection.commit()
    except sqlalchemy.exc.DatabaseError:
        session.rollback()
        raise
    finally:
        # Rollback only if a transaction hasn't been committed.
        if session.transaction.is_active:
            connection.rollback()
