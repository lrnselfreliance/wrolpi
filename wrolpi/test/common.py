import functools
from uuid import uuid1

import mock
import psycopg2
from dictorm import DictDB
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from wrolpi.common import setup_relationships


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

        # Every test gets it's own DB
        suffix = str(uuid1()).replace('-', '')
        testing_db_name = f'wrolpi_testing_{suffix}'

        # Set isolation level such that was can copy the schema of the "wrolpi" database for testing
        with psycopg2.connect(dbname='postgres', **db_args) as db_conn:
            db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            # Cleanup the old testing db (if any), then copy the schema
            curs = db_conn.cursor()
            drop_testing = f'DROP DATABASE IF EXISTS {testing_db_name}'
            curs.execute(drop_testing)
            curs.execute(f'CREATE DATABASE {testing_db_name} TEMPLATE wrolpi')

            class FakePool:

                def putconn(self, conn, *a, **kw):
                    pass

            # Connect to the new testing DB.  Reset all tables and sequences
            testing_db_conn = psycopg2.connect(dbname=testing_db_name, **db_args)
            testing_curs = testing_db_conn.cursor()
            testing_curs.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            table_names = [i for (i,) in testing_curs.fetchall()]
            testing_curs.execute('; '.join(f'TRUNCATE {table} RESTART IDENTITY CASCADE' for table in table_names))
            testing_db_conn.commit()

            try:
                testing_db = DictDB(testing_db_conn)
                setup_relationships(testing_db)

                def _get_db():
                    """Get the testing db"""
                    return FakePool(), testing_db_conn, testing_db, None

                with mock.patch('wrolpi.tools.get_db', _get_db):
                    return func(*a, **kw)

            finally:
                testing_db_conn.close()
                db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                curs.execute(drop_testing)

    functools.wraps(wrapped, func)
    return wrapped
