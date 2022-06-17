"""
Fixtures for Pytest tests.
"""
import pathlib
import tempfile
from typing import Tuple, Set
from unittest import mock
from uuid import uuid1

import pytest
from sanic_testing.testing import SanicTestClient
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from wrolpi.common import set_test_media_directory, Base, set_test_config
from wrolpi.dates import set_test_now
from wrolpi.db import postgres_engine, get_db_args
from wrolpi.downloader import DownloadManager, DownloadResult, set_test_download_manager_config, Download
from wrolpi.root_api import BLUEPRINTS, api_app


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


@pytest.fixture()
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


@pytest.fixture(autouse=True)
def test_directory() -> pathlib.Path:
    """
    Overwrite the media directory with a temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)
        assert tmp_path.is_dir()
        set_test_media_directory(tmp_path)
        yield tmp_path


@pytest.fixture(autouse=True)
def test_config(test_directory) -> pathlib.Path:
    """
    Create a test config based off the example config.
    """
    config_path = test_directory / 'config/wrolpi.yaml'
    set_test_config(True)
    yield config_path
    set_test_config(False)


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
def test_download_manager_config(test_directory):
    (test_directory / 'config').mkdir(exist_ok=True)
    config_path = test_directory / 'config/download_manager.yaml'
    set_test_download_manager_config(True)
    yield config_path
    set_test_download_manager_config(False)


@pytest.fixture
def test_download_manager(test_download_manager_config):
    manager = DownloadManager()
    return manager


@pytest.fixture
def fake_now():
    try:
        yield set_test_now
    finally:
        # reset now() to its original functionality.
        set_test_now(None)  # noqa


@pytest.fixture
def successful_download():
    return DownloadResult(success=True)


@pytest.fixture
def failed_download():
    return DownloadResult(error='pytest.fixture failed_download error', success=False)


@pytest.fixture
def assert_download_urls(test_session):
    def asserter(urls: Set[str]):
        downloads = test_session.query(Download).all()
        assert {i.url for i in downloads} == set(urls)

    return asserter
