from contextlib import contextmanager
from typing import Tuple

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from api.common import logger
from api.vars import DOCKERIZED

db_logger = logger.getChild(__name__)

Base = declarative_base()


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
postgres_args = get_db_args('postgres')
postgres_engine = create_engine('postgresql://{user}:{password}@{host}:{port}/postgres'.format(**postgres_args),
                                execution_options={'isolation_level': 'AUTOCOMMIT'})

# This engine is used for all normal tasks (except testing).
db_args = get_db_args()
engine = create_engine('postgresql://{user}:{password}@{host}:{port}/postgres'.format(**db_args))
session_maker = sessionmaker(bind=engine)


@contextmanager
def get_db_context(commit: bool = False) -> Tuple[Engine, Session]:
    """Context manager that creates a DB session.  This will automatically rollback changes, unless `commit` is True."""
    Base.metadata.create_all(engine)
    session = session_maker()
    yield engine, session
    if commit:
        session.commit()
    else:
        session.rollback()


@contextmanager
def get_db_curs(commit: bool = False):
    connection = engine.raw_connection()
    Base.metadata.create_all(engine)
    curs = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    yield curs
    if commit:
        connection.commit()
    else:
        connection.rollback()
