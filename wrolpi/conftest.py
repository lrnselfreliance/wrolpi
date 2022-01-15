"""
Fixtures for Pytest tests.
"""
import os
import pathlib
import tempfile
from typing import Tuple
from unittest import mock
from uuid import uuid1

import pytest
import pytest_asyncio
import yaml
from sanic_testing.testing import SanicTestClient
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from wrolpi.common import set_test_media_directory, Base, get_example_config
from wrolpi.db import postgres_engine, get_db_args
from wrolpi.downloader import DownloadManager
from wrolpi.root_api import BLUEPRINTS, api_app

os.environ['DB_PORT'] = '54321'


def get_test_db_engine():
    suffix = str(uuid1()).replace('-', '')
    db_name = f'wrolpi_testing_{suffix}'
    conn = postgres_engine.connect()
    conn.execute(f'DROP DATABASE IF EXISTS {db_name}')
    conn.execute(f'CREATE DATABASE {db_name}')
    conn.execute('commit')
    conn.close()

    test_args = get_db_args(db_name)
    test_engine = create_engine('postgresql://{user}:{password}@{host}:{port}/{dbname}'.format(**test_args))
    return test_engine


def test_db() -> Tuple[Engine, Session]:
    """
    Create a unique SQLAlchemy engine/session for a test.
    """
    test_engine = get_test_db_engine()
    if test_engine.engine.url.database == 'wrolpi':
        raise ValueError('Refusing the test on wrolpi database!')

    # Create all tables.  No need to check if they exist because this is a test DB.
    Base.metadata.create_all(test_engine, checkfirst=False)
    session = sessionmaker(bind=test_engine)()
    return test_engine, session


@pytest_asyncio.fixture()
def test_session() -> Session:
    """
    Pytest Fixture to get a test database session.
    """
    test_engine, session = test_db()

    def fake_get_db_session():
        """Get the testing db"""
        return test_engine, session

    try:
        with mock.patch('wrolpi.db._get_db_session', fake_get_db_session):
            yield session
    finally:
        session.rollback()
        session.close()
        test_engine.dispose()
        conn = postgres_engine.connect()
        conn.execute(f'DROP DATABASE IF EXISTS {test_engine.engine.url.database}')
        conn.close()


@pytest_asyncio.fixture(autouse=True)
def test_directory() -> pathlib.Path:
    """
    Overwrite the media directory with a temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        assert tmp_path.is_dir()
        set_test_media_directory(tmp_path)
        yield tmp_path


@pytest_asyncio.fixture(autouse=True)
def test_config():
    """
    Create a test config based off the example config.
    """
    test_config_path = tempfile.NamedTemporaryFile(mode='rt')
    with mock.patch('wrolpi.vars.CONFIG_PATH', test_config_path.name), \
            mock.patch('wrolpi.common.CONFIG_PATH', test_config_path.name):
        config = get_example_config()
        with open(test_config_path.name, 'wt') as fh:
            fh.write(yaml.dump(config))
        yield pathlib.Path(test_config_path.name)


ROUTES_ATTACHED = False


@pytest.fixture(autouse=True)
def test_client() -> SanicTestClient:
    """
    Get a Sanic Test Client with all default routes attached.
    """
    global ROUTES_ATTACHED
    if ROUTES_ATTACHED is False:
        # Attach any blueprints for the test.
        for bp in BLUEPRINTS:
            api_app.blueprint(bp)
        ROUTES_ATTACHED = True

    return api_app.test_client


@pytest.fixture
def test_download_manager():
    manager = DownloadManager()
    return manager
