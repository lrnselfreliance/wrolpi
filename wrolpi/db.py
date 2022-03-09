from contextlib import contextmanager
from functools import wraps
from typing import ContextManager, Tuple, List, Union

import psycopg2
import sqlalchemy.exc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from wrolpi.common import logger, Base, partition
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
    local_engine, session = _get_db_session()
    if PYTEST and not local_engine.url.database.startswith('wrolpi_testing_'):
        raise ValueError(f'Running tests, but a test database is not being used!! {local_engine.url=}')
    return local_engine, session


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


def optional_session(commit: Union[callable, bool] = False):
    """
    Wraps a function, if a Session is passed it will be used.  Otherwise, a new session will be
    created and passed to the function.
    """

    def find_session(*f_args, session: Session = None, **f_kwargs):
        session = f_kwargs.get('session', session)
        if not session:
            # Find the session in the args.
            session, new_args = partition(lambda i: isinstance(i, Session), f_args)
            if session:
                session = session[0]
                f_args = tuple(new_args)
        return session, f_args, f_kwargs

    def call_func(func, session, args, kwargs):
        if session:
            return func(*args, session=session, **kwargs)
        else:
            with get_db_session() as session:
                return func(*args, session=session, **kwargs)

    def wrapper(*w_args, **w_kwargs):
        if len(w_args) == 1 and len(w_kwargs) == 0 and callable(w_args[0]):
            func = w_args[0]

            @wraps(func)
            def wrapped(*args, session: Session = None, **kwargs):
                session, args, kwargs = find_session(*args, session=session, **kwargs)
                return call_func(func, session, args, kwargs)

            return wrapped
        else:
            session_, w_args, w_kwargs = find_session(*w_args, **w_kwargs)
            return call_func(commit, session_, w_args, w_kwargs)

    return wrapper


@optional_session
def get_ranked_models(ranked_ids: List[int], model: Base, session: Session = None) -> List[Base]:
    """
    Get all objects whose ids are in the `ranked_ids`, order them by their position in `ranked_ids`.
    """
    results = session.query(model).filter(model.id.in_(ranked_ids)).all()
    results = sorted(results, key=lambda i: ranked_ids.index(i.id))
    return results
