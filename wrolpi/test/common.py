import functools
import random
import string

import mock
import psycopg2
from dictorm import DictDB
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from wrolpi.common import setup_relations


def test_db_wrapper(func):
    """
    Wrap a test so that when calling wrolpi.common.get_db, it returns a testing database cloned from the wrolpi
    template.
    """

    def wrapped(*a, **kw):
        # This is the Docker postgres container
        db_args = dict(
            user='postgres',
            password='postgres',
            host='127.0.0.1',
            port=54321,
        )

        TESTING_DB_NAME = 'wrolpi_testing_' + ''.join(random.choices(string.ascii_lowercase, k=20))

        # Set isolation level such that was can copy the schema of the "wrolpi" database for testing
        with psycopg2.connect(dbname='postgres', **db_args) as db_conn:
            db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            # Cleanup the old testing db (if any), then copy the schema
            curs = db_conn.cursor()
            drop_testing = f'DROP DATABASE IF EXISTS {TESTING_DB_NAME}'
            curs.execute(drop_testing)
            curs.execute(f'CREATE DATABASE {TESTING_DB_NAME} TEMPLATE wrolpi')

        def get_db():
            testing_db_conn = psycopg2.connect(
                dbname=TESTING_DB_NAME,  # use that new testing db!
                **db_args
            )
            testing_db = DictDB(testing_db_conn)
            setup_relations(testing_db)
            return testing_db_conn, testing_db

        with mock.patch('wrolpi.common.get_db', get_db):
            try:
                return func(*a, **kw)
            finally:
                with psycopg2.connect(dbname='postgres', **db_args) as db_conn:
                    db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                    curs = db_conn.cursor()
                    curs.execute(drop_testing)

    functools.wraps(wrapped, func)
    return wrapped
