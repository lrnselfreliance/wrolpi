from queue import Empty
from uuid import uuid1

import mock
import psycopg2
from dictorm import DictDB
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from lib.common import setup_relationships


def wrap_test_db(func):
    """
    Wrap a test so that when calling lib.common.get_db, it returns a testing database cloned from the lib
    template.
    """

    def wrapped(*a, **kw):
        # This is the Docker db container
        db_args = dict(
            user='postgres',
            password='postgres',
            host='127.0.0.1',
            port=54321,
        )

        # Every test gets it's own DB
        suffix = str(uuid1()).replace('-', '')
        testing_db_name = f'wrolpi_testing_{suffix}'

        # Set isolation level such that was can copy the schema of the "lib" database for testing
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

                with mock.patch('lib.db.get_db', _get_db), \
                     mock.patch('lib.api.get_db', _get_db):
                    result = func(*a, **kw)
                    return result

            finally:
                testing_db_conn.close()
                db_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                curs.execute(drop_testing)

    return wrapped


def get_all_messages_in_queue(q):
    messages = []
    while True:
        try:
            msg = q.get_nowait()
            messages.append(msg)
        except Empty:
            break
    return messages
