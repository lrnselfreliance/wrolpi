import configparser
import logging
import os
import sqlite3
import string
import sys
from contextlib import contextmanager
from typing import Tuple

import psycopg2 as psycopg2
from dictorm import DictDB
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Jinja2 environment
env = Environment(loader=FileSystemLoader('.'))

CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'


def get_wrolpi_config():
    config = configparser.RawConfigParser()
    config.read(CONFIG_PATH)
    try:
        return config[WROLPI_CONFIG_SECTION]
    except KeyError:
        logger.fatal('Cannot load WROLPi.cfg config!')
        sys.exit(1)


def get_db():
    # NOTE: This will be overwritten by wrolpi.
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
    db_conn = psycopg2.connect(**db_args)
    db = DictDB(db_conn)
    if 'channel' in db:
        db['channel']['videos'] = db['channel']['id'].many(db['video']['channel_id'])
    return db_conn, db


@contextmanager
def get_db_context(commit=False) -> Tuple[psycopg2.connect, DictDB]:
    """Context manager that creates a DB connection as well as a DictDB object.  Commits when
    requested, otherwise it will always rollback."""
    db_conn, db = get_db()
    try:
        yield db_conn, db
        if commit:
            db_conn.commit()
        else:
            db_conn.rollback()
    finally:
        db_conn.close()


def setup_relations(db):
    """Assign all relations between DictORM Tables."""
    Channel = db['channel']
    Video = db['video']
    Channel['videos'] = Channel['id'].many(Video['channel_id'])
    Video['channel'] = Video['channel_id'] == Channel['id']


def config_values_to_booleans(section):
    for key, value in section.items():
        if value.lower() in {'true', 't'}:
            section[key] = True
        elif value.lower() in {'false', 'f'}:
            section[key] = False
    return section


URL_CHARS = string.ascii_lowercase + string.digits


def sanitize_link(link):
    """Remove any non-url safe characters, all will be lowercase."""
    return ''.join(i for i in str(link).lower() if i in URL_CHARS)
