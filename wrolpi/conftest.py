"""
Fixtures for Pytest tests.
"""
import asyncio
import pathlib
import shutil
import tempfile
from typing import List, Callable, Union, Dict
from typing import Tuple, Set
from unittest import mock
from unittest.mock import MagicMock
from uuid import uuid1, uuid4

import pytest
from PIL import Image
from sanic_testing.testing import SanicTestClient
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from wrolpi.common import iterify
from wrolpi.common import set_test_media_directory, Base, set_test_config
from wrolpi.dates import set_test_now
from wrolpi.db import postgres_engine, get_db_args
from wrolpi.downloader import DownloadManager, DownloadResult, set_test_download_manager_config, Download
from wrolpi.root_api import BLUEPRINTS, api_app
from wrolpi.vars import PROJECT_DIR


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
        tmp_path.chmod(0o40755)
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
async def test_download_manager(
        test_session,  # session is required because downloads can start without the test DB in place.
        test_download_manager_config,
):
    manager = DownloadManager()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    manager.enable(loop)

    yield manager

    manager.stop()


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


@pytest.fixture
def video_file(test_directory) -> pathlib.Path:
    """Return a copy of the example Big Buck Bunny video in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', destination)

    yield destination


@pytest.fixture
def corrupted_video_file(test_directory) -> pathlib.Path:
    """Return a copy of the corrupted video file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.mp4'
    shutil.copy(PROJECT_DIR / 'test/corrupted.mp4', destination)

    yield destination


@pytest.fixture
def image_file(test_directory) -> pathlib.Path:
    """Create a small image file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.jpeg'
    Image.new('RGB', (25, 25), color='grey').save(destination)
    yield destination


@pytest.fixture
def vtt_file1(test_directory) -> pathlib.Path:
    """Return a copy of the example1 VTT file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.en.vtt'
    shutil.copy(PROJECT_DIR / 'test/example1.en.vtt', destination)
    yield destination


@pytest.fixture
def vtt_file2(test_directory) -> pathlib.Path:
    """Return a copy of the example2 VTT file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.en.vtt'
    shutil.copy(PROJECT_DIR / 'test/example2.en.vtt', destination)
    yield destination


@pytest.fixture
def srt_file3(test_directory) -> pathlib.Path:
    """Return a copy of the example3 SRT file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.en.srt'
    shutil.copy(PROJECT_DIR / 'test/example3.en.srt', destination)
    yield destination


@pytest.fixture
def bad_vtt_file(test_directory) -> pathlib.Path:
    """Return a copy of the bad_caption VTT file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.en.vtt'
    shutil.copy(PROJECT_DIR / 'test/bad_caption.en.vtt', destination)
    yield destination


@pytest.fixture
def make_files_structure(test_directory) -> Callable[[Union[List, Dict]], List[pathlib.Path]]:
    def create_files(paths: List) -> List[pathlib.Path]:
        files = []

        @iterify(list)
        def touch_paths(paths_):
            for name in paths_:
                path = test_directory / name
                if name.endswith('/'):
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                yield path

        if isinstance(paths, list):
            files = touch_paths(paths)
        elif isinstance(paths, Dict):
            files = touch_paths(paths.keys())
            for path, content in paths.items():
                path = test_directory / path
                if isinstance(content, str):
                    path.write_text(content)
                elif isinstance(content, bytes):
                    path.write_bytes(content)
        return files

    return create_files


@pytest.fixture
def wrol_mode_fixture(test_config, test_download_manager):
    from wrolpi.common import enable_wrol_mode, disable_wrol_mode

    def set_wrol_mode(enabled: bool):
        if enabled:
            enable_wrol_mode(test_download_manager)
        else:
            disable_wrol_mode(test_download_manager)

    return set_wrol_mode


@pytest.fixture
def mock_create_subprocess_shell():
    def mocker(communicate_return=None, return_code=None, communicate_side_effect = None):
        async def communicate(*a, **kw):
            if communicate_side_effect:
                return communicate_side_effect()
            return communicate_return or (None, None)

        async def create_subprocess_shell(*a, **kw):
            proc = MagicMock()
            proc.communicate = communicate
            proc.returncode = return_code if return_code is not None else 0
            return proc

        return create_subprocess_shell

    return mocker
