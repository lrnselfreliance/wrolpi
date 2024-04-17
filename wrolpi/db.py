import inspect
import types
from contextlib import contextmanager
from functools import wraps
from typing import ContextManager, Tuple, List, Union, Type, Generator

import psycopg2
import psycopg2.extensions
import sqlalchemy
import sqlalchemy.exc
from psycopg2._psycopg import cursor
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
    elif PYTEST:
        # Pytest is running, but we're not in docker, use the exposed docker container port.
        db_args['user'] = 'postgres'

    return db_args


# This engine is used to modify the databases.
connect_args = dict(application_name='wrolpi_api_super')
postgres_args = get_db_args('postgres')
postgres_engine = sqlalchemy.create_engine(
    'postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**postgres_args),
    execution_options={'isolation_level': 'AUTOCOMMIT'}, connect_args=connect_args)

# This engine is used for all normal tasks (except testing).
db_args = get_db_args()
connect_args = dict(application_name='wrolpi_api', connect_timeout=1)
uri = 'postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**db_args)
engine = sqlalchemy.create_engine(uri, poolclass=NullPool, connect_args=connect_args)
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


def get_db_context() -> Tuple[sqlalchemy.create_engine, Session]:
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
def get_db_conn(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_DEFAULT):
    local_engine, session = get_db_context()
    connection = local_engine.raw_connection()
    connection.set_isolation_level(isolation_level)
    try:
        yield connection, session
    except sqlalchemy.exc.DatabaseError:
        session.rollback()
        raise
    finally:
        # Rollback only if a transaction hasn't been committed.
        if session.transaction.is_active:
            connection.rollback()


@contextmanager
def get_db_curs(commit: bool = False, isolation_level=psycopg2.extensions.ISOLATION_LEVEL_DEFAULT):
    """
    Context manager that yields a DictCursor to execute raw SQL statements.
    """
    with get_db_conn(isolation_level=isolation_level) as (connection, session):
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


def optional_session(commit: Union[callable, bool] = False) -> callable:
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
            result = func(*args, session=session, **kwargs)
            if commit:
                session.commit()
        else:
            with get_db_session() as session:
                result = func(*args, session=session, **kwargs)
                if commit:
                    session.commit()
        return result

    def wrapper(*w_args, **w_kwargs):
        if len(w_args) == 1 and len(w_kwargs) == 0 and callable(w_args[0]):
            func = w_args[0]

            if inspect.iscoroutinefunction(func):
                @wraps(func)
                async def wrapped(*args, session: Session = None, **kwargs):
                    session, args, kwargs = find_session(*args, session=session, **kwargs)
                    return await call_func(func, session, args, kwargs)
            else:
                @wraps(func)
                def wrapped(*args, session: Session = None, **kwargs):
                    session, args, kwargs = find_session(*args, session=session, **kwargs)
                    return call_func(func, session, args, kwargs)

            return wrapped
        else:
            # No params were passed to this wrapper, `commit` is actually the function we are wrapping.
            session_, w_args, w_kwargs = find_session(*w_args, **w_kwargs)
            return call_func(commit, session_, w_args, w_kwargs)

    return wrapper


@optional_session
def get_ranked_models(ranked_primary_keys: List, model: Type[Base], session: Session = None) -> List[Base]:
    """Get all objects whose primary keys are in the `ranked_primary_keys`, preserve their order."""
    pkey = sqlalchemy.inspect(model).primary_key[0]
    pkey_name = pkey.name
    results = list(session.query(model).filter(pkey.in_(ranked_primary_keys)).all())
    results = sorted(results, key=lambda i: ranked_primary_keys.index(getattr(i, pkey_name)))
    return results


def mogrify(curs: cursor, values: Union[List, Generator]) -> str:
    values = list(values) if isinstance(values, types.GeneratorType) else values.copy()
    count = len(values[0])
    # If `count = 3`, then s = '(%s,%s,%s)'
    s = '(' + ','.join("%s" for _ in range(count)) + ')'
    result = ',\n'.join([curs.mogrify(s, i).decode() for i in values])
    return result
