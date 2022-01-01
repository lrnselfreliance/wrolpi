from contextlib import contextmanager
from typing import ContextManager, Tuple, List

import psycopg2
import sqlalchemy.exc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from wrolpi.common import logger, Base
from wrolpi.vars import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DOCKERIZED, PYTEST

logger = logger.getChild(__name__)


def get_db_args(dbname: str = None):
    db_args = dict(
        dbname=dbname or DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    if DOCKERIZED:
        # Deployed in docker, use the docker database.
        db_args['user'] = 'postgres'
        db_args['host'] = 'db'
        db_args['port'] = 5432
    elif PYTEST:
        # Pytest is running but we're not in docker, use the exposed docker container port.
        db_args['user'] = 'postgres'
        db_args['port'] = 54321

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
    """
    This function allows the database to be wrapped during testing.  See: api.test.common.wrap_test_db
    """
    global LOGGED_ARGS
    if LOGGED_ARGS is False:
        # Print the DB args for troubleshooting.
        LOGGED_ARGS = True
        logging_args = db_args.copy()
        logging_args['password'] = '***'
        logger.debug(f'DB args: {logging_args}')

    session = session_maker()
    return engine, session


def get_db_context() -> Tuple[create_engine, Session]:
    """
    Get a DB engine and session.
    """
    return _get_db_session()


@contextmanager
def get_db_session(commit: bool = False) -> ContextManager[Session]:
    """
    Context manager that creates a DB session.  This will automatically rollback changes, unless `commit` is True.
    """
    _, session = get_db_context()
    try:
        yield session
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
    """
    Context manager that yields a DictCursor to execute raw SQL statements.
    """
    local_engine, session = get_db_context()
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


def get_ranked_models(ranked_ids: List[int], model: Base, session: Session = None) -> List[Base]:
    """
    Get all objects whose ids are in the `ranked_ids`, order them by their position in `ranked_ids`.
    """
    if session:
        results = session.query(model).filter(model.id.in_(ranked_ids)).all()
        results = sorted(results, key=lambda i: ranked_ids.index(i.id))
        return results

    with get_db_session() as session:
        results = session.query(model).filter(model.id.in_(ranked_ids)).all()
        results = sorted(results, key=lambda i: ranked_ids.index(i.id))
        return results
