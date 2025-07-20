"""
Fixtures for Pytest tests.
"""
import asyncio
import copy
import http.server
import json
import logging
import multiprocessing
import pathlib
import shutil
import sys
import tempfile
import threading
import zipfile
from abc import ABC
from datetime import datetime
from itertools import zip_longest
from typing import List, Callable, Dict, Sequence, Union, Coroutine, Awaitable, Optional
from typing import Tuple, Set
from unittest import mock
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid1, uuid4

import pytest
import sqlalchemy
import yaml
from PIL import Image
from sanic_testing.reusable import ReusableClient
from sanic_testing.testing import SanicASGITestClient
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import root api so blueprints are attached.
import wrolpi.root_api  # noqa
from wrolpi import flags
from wrolpi.api_utils import api_app
from wrolpi.cmd import CommandResult
from wrolpi.common import iterify, log_level_context, enable_wrol_mode, disable_wrol_mode, timer, TRACE_LEVEL
from wrolpi.common import logger, await_background_tasks as await_background_tasks_
from wrolpi.common import set_test_media_directory, Base, set_test_config
from wrolpi.contexts import attach_shared_contexts, initialize_configs_contexts
from wrolpi.dates import set_test_now
from wrolpi.db import postgres_engine, get_db_args
from wrolpi.downloader import DownloadManager, DownloadResult, Download, Downloader, \
    downloads_manager_config_context
from wrolpi.errors import UnrecoverableDownloadError
from wrolpi.files.models import Directory, FileGroup
from wrolpi.switches import await_switches as await_switches_
from wrolpi.tags import Tag, upsert_tag
from wrolpi.vars import PROJECT_DIR

logger = logger.getChild(__name__)


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
    """Create a unique SQLAlchemy engine/session for a test."""
    test_engine = get_test_db_engine()
    if test_engine.engine.url.database == 'wrolpi':
        raise ValueError('Refusing the test on wrolpi database!')

    # Create all tables.  No need to check if they exist because this is a test DB.
    Base.metadata.create_all(test_engine, checkfirst=False)
    session = sessionmaker(bind=test_engine)()
    return test_engine, session


@pytest.fixture()
def test_session() -> Session:
    """Pytest Fixture to get a test database session."""
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
def test_debug_logger(request):
    """The tests use debug logging by default.  Use pytest's verbosity level if set."""
    level = logging.INFO
    verbose = request.config.option.verbose
    if verbose == 2:
        # -vv
        level = logging.DEBUG
    elif verbose == 3:
        # -vvv
        level = TRACE_LEVEL

    with log_level_context(level):
        yield


@pytest.fixture
def test_directory() -> pathlib.Path:
    """
    Overwrite the media directory with a temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir).resolve()
        tmp_path.chmod(0o40755)
        assert tmp_path.is_dir()
        set_test_media_directory(tmp_path)
        yield tmp_path


@pytest.fixture
def test_wrolpi_config(test_directory) -> pathlib.Path:
    """
    Create a test config based off the example config.
    """
    config_path = test_directory / 'config/wrolpi.yaml'
    set_test_config(True)
    yield config_path
    set_test_config(False)


ROUTES_ATTACHED = False


@pytest.fixture()
def test_client(test_directory) -> ReusableClient:
    """Get a Reusable Sanic Test Client with all default routes attached.

    (A non-reusable client would turn on for each request)
    """
    attach_shared_contexts(api_app)

    initialize_configs_contexts(api_app)

    for _ in range(5):
        # Sometimes the Sanic client tries to use a port already in use, try again...
        try:
            client = ReusableClient(api_app)
            with client:
                yield client
            break
        except OSError as e:
            # Ignore errors where the port was already in use.
            if 'address already in use' not in str(e):
                raise
    else:
        raise RuntimeError('Test never got unused port')


@api_app.on_response
async def background_task_listener(request, response):
    """Wait for all background tasks to finish before returning API response while testing."""
    await await_switches_()


@pytest.fixture
async def async_client(test_directory) -> SanicASGITestClient:
    """Get an Async Sanic Test Client with all default routes attached."""
    api_app.signalize()
    attach_shared_contexts(api_app)
    initialize_configs_contexts(api_app)

    client = SanicASGITestClient(api_app)

    try:
        yield client
    finally:
        api_app.stop()
        logger.debug('Destroying async_client')


@pytest.fixture
def test_download_manager_config(async_client, test_directory) -> pathlib.Path:
    with downloads_manager_config_context():
        (test_directory / 'config').mkdir(exist_ok=True)
        config_path = test_directory / 'config/download_manager.yaml'
        yield config_path


@pytest.fixture
async def await_switches(async_client):
    """Returns the `switches.await_switches` function, but primes the Sanic App to actually handle signals."""
    await async_client.get('/api')
    return await_switches_


@pytest.fixture
async def await_background_tasks(async_client):
    """Returns the `switches.await_switches` function, but primes the Sanic App to actually handle signals."""
    await async_client.get('/api')
    return await_background_tasks_


@pytest.fixture
async def test_download_manager(
        async_client,
        test_session,  # session is required because downloads can start without the test DB in place.
        test_download_manager_config,
) -> DownloadManager:
    with timer('test_download_manager'):
        # Needed to use signals in
        manager = DownloadManager()
        await manager.enable()

    yield manager

    manager.stop()


@pytest.fixture
def fake_now() -> Callable:
    try:
        set_test_now(datetime(2000, 1, 1))
        yield set_test_now
    finally:
        # reset now() to its original functionality.
        set_test_now(None)  # noqa


@pytest.fixture
def successful_download() -> DownloadResult:
    return DownloadResult(success=True)


@pytest.fixture
def failed_download() -> DownloadResult:
    return DownloadResult(error='wrolpi.conftest failed_download error', success=False)


@pytest.fixture
def assert_download_urls(test_session) -> Callable[[Set[str]], None]:
    def asserter(expected_urls: Set[str]):
        downloads = test_session.query(Download).all()
        urls = {i.url for i in downloads}
        if urls != set(expected_urls):
            raise AssertionError(f'Download URLs do not match: {urls} != {expected_urls}')

    return asserter


@pytest.fixture
def assert_downloads(test_session) -> Callable[[List[Dict]], None]:
    from wrolpi.test.common import assert_dict_contains

    def asserter(expected: List[Dict]):
        downloads = test_session.query(Download).order_by(Download.url)
        for download_, expected_ in zip_longest(downloads, expected):
            assert_dict_contains(download_.__json__(), expected_)
        if (count := test_session.query(Download).count()) != len(expected):
            raise AssertionError(f'Download count does not match: {count} != {len(expected)}')

    return asserter


@pytest.fixture
def test_downloader(test_download_manager) -> Downloader:
    class TestDownloader(Downloader, ABC):
        """A testing Downloader"""
        name = 'test_downloader'

        def __repr__(self):
            return '<TESTING Downloader>'

        do_download = AsyncMock()

        def set_test_success(self):
            async def _(*a, **kwargs):
                # Sleep so download happens after testing is waiting.
                await asyncio.sleep(1)
                return DownloadResult(success=True)

            self.do_download.side_effect = _

        def set_test_failure(self):
            async def _(*a, **kwargs):
                # Sleep so download happens after testing is waiting.
                await asyncio.sleep(1)
                return DownloadResult(success=False)

            self.do_download.side_effect = _

        def set_test_exception(self, exception: Exception = Exception('Test downloader exception')):
            async def _(*a, **kwargs):
                # Sleep so download happens after testing is waiting.
                await asyncio.sleep(1)
                raise exception

            self.do_download.side_effect = _

        def set_test_unrecoverable_exception(self):
            async def _(*a, **kwargs):
                # Sleep so download happens after testing is waiting.
                await asyncio.sleep(1)
                raise UnrecoverableDownloadError()

            self.do_download.side_effect = _

    test_downloader = TestDownloader()
    # Default to successful download.
    test_downloader.set_test_success()
    test_download_manager.register_downloader(test_downloader)

    return test_downloader


@pytest.fixture
def video_file(test_directory) -> pathlib.Path:
    """Return a copy of the example Big Buck Bunny video in the `test_directory`."""
    destination = test_directory / f'video-{uuid4()}.mp4'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', destination)

    yield destination


@pytest.fixture
def corrupted_video_file(test_directory) -> pathlib.Path:
    """Return a copy of a corrupted video file in the `test_directory`."""
    destination = test_directory / f'corrupted-{uuid4()}.mp4'
    shutil.copy(PROJECT_DIR / 'test/corrupted.mp4', destination)

    yield destination


@pytest.fixture
def video_file_factory(test_directory) -> Callable[[pathlib.Path], pathlib.Path]:
    """Return a copy of the example Big Buck Bunny video in the `test_directory`."""

    def _(path: pathlib.Path = None) -> pathlib.Path:
        destination = path or test_directory / f'{uuid4()}.mp4'
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', destination)

        return destination

    return _


@pytest.fixture
def video_bytes() -> bytes:
    return (PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4').read_bytes()


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
def srt_text() -> str:
    return (PROJECT_DIR / 'test/example3.en.srt').read_text()


@pytest.fixture
def srt_file3(test_directory) -> pathlib.Path:
    """Return a copy of the example3 SRT file in the `test_directory`."""
    destination = test_directory / f'{uuid4()}.en.srt'
    shutil.copy(PROJECT_DIR / 'test/example3.en.srt', destination)
    yield destination


@pytest.fixture
def example_pdf(test_directory) -> pathlib.Path:
    destination = test_directory / 'pdf example.pdf'
    shutil.copy(PROJECT_DIR / 'test/pdf example.pdf', destination)
    yield destination


@pytest.fixture
def example_epub(test_directory) -> pathlib.Path:
    destination = test_directory / 'ebook example.epub'
    shutil.copy(PROJECT_DIR / 'test/ebook example.epub', destination)
    yield destination


@pytest.fixture
def example_mobi(test_directory) -> pathlib.Path:
    destination = test_directory / 'ebook example.mobi'
    shutil.copy(PROJECT_DIR / 'test/ebook example.mobi', destination)
    yield destination


@pytest.fixture
def example_doc(test_directory) -> pathlib.Path:
    destination = test_directory / 'example word.doc'
    shutil.copy(PROJECT_DIR / 'test/example word.doc', destination)
    yield destination


@pytest.fixture
def example_docx(test_directory) -> pathlib.Path:
    destination = test_directory / 'example word.docx'
    shutil.copy(PROJECT_DIR / 'test/example word.docx', destination)
    yield destination


@pytest.fixture
def make_files_structure(test_directory) -> Callable[[Union[List[Union[pathlib.Path, str]], dict]], List[pathlib.Path]]:
    """
    A fixture which creates test files passed to it.  If a list is provided, empty files will be created at those
    locations.  If a dict is provided, files will be created containing the value of the dict item.
    """

    def create_files(paths: Union[List, Dict], file_groups: bool = False, session: Session = None) \
            -> List[pathlib.Path]:
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

        if file_groups:
            for idx, path in enumerate(files):
                fg = FileGroup.from_paths(session, path)
                fg.do_index()
                files[idx] = fg
        return sorted(files) if isinstance(paths, dict) else files

    return create_files


async def set_wrol_mode(enabled: bool):
    if enabled:
        enable_wrol_mode()
    else:
        await disable_wrol_mode()


@pytest.fixture
def wrol_mode_fixture(test_wrolpi_config, test_download_manager) -> Callable[[bool], Coroutine]:
    return set_wrol_mode


@pytest.fixture
def mock_create_subprocess_shell() -> Callable:
    def mocker(communicate_return=None, return_code=None, communicate_side_effect=None):
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


@pytest.fixture
def mock_run_command():
    """Mock wrolpi.cmd's `run_command` using `TESTING_RUN_COMMAND_RESULT`."""
    default = CommandResult(
        return_code=0,
        cancelled=False,
        stdout=b'mock_run_command fixture stdout',
        stderr=b'mock_run_command fixture stderr',
        elapsed=0,
        pid=123,
    )

    with mock.patch('wrolpi.cmd.TESTING_RUN_COMMAND_RESULT') as mock_TESTING_RUN_COMMAND_RESULT:
        mock_TESTING_RUN_COMMAND_RESULT.return_value = default

        def do_mock(new_result):
            mock_TESTING_RUN_COMMAND_RESULT.return_value = new_result

        yield do_mock


@pytest.fixture
def run_command_bad_result() -> CommandResult:
    return CommandResult(1, False, b'run_command_bad_result stdout', b'run_command_bad_result stderr', 0, 123)


@pytest.fixture
def events_history(async_client):
    """Give each test its own Events history."""
    yield api_app.shared_ctx.events_history


FLAGS_LOCK = multiprocessing.Lock()


@pytest.fixture()
def flags_lock():
    """Wait for exclusive access to flags before testing."""
    try:
        FLAGS_LOCK.acquire(timeout=60)
        flags.TESTING_LOCK.set()
        yield
    finally:
        flags.TESTING_LOCK.clear()
        FLAGS_LOCK.release()


@pytest.fixture()
def tag_factory(test_session) -> Callable[[Optional[str]], Awaitable[Tag]]:
    names = ['one', 'two', 'three', 'four', 'five', 'six']
    count = 1

    async def factory(name: str = None) -> Tag:
        if not name:
            name = names.pop(0)
        tag = await upsert_tag(name, f'#{str(count) * 6}', session=test_session)
        return tag

    return factory


@pytest.fixture
def assert_files(test_session, test_directory):
    def _(files: List[Dict]):
        from wrolpi.files.models import FileGroup
        for expected in files:
            primary_path = test_directory / expected.pop('path')
            try:
                file: FileGroup = test_session.query(FileGroup).filter_by(primary_path=primary_path).one()
            except sqlalchemy.orm.exc.NoResultFound as e:
                raise ValueError(f'No FileGroup found with {primary_path=}') from e

            for key, value in expected.items():
                attr = getattr(file, key)
                if attr != value:
                    raise AssertionError(f'{primary_path} {attr} != {value}')

    return _


@pytest.fixture
def assert_file_groups(test_session, test_directory):
    from wrolpi.test.common import assert_dict_contains

    def _(file_groups: List[Dict], assert_count: bool = True):
        from wrolpi.files.models import FileGroup
        for expected in file_groups:
            if 'primary_path' not in expected:
                raise Exception('You must specify the primary path for this fixture!')

            primary_path = str(test_directory / expected.pop('primary_path'))
            try:
                file_group: FileGroup = test_session.query(FileGroup).filter_by(primary_path=primary_path).one()
            except Exception as e:
                raise ValueError(f'No FileGroup found with {primary_path=}') from e

            # Compare file dictionaries.
            files = expected.pop('files', None)
            if files:
                for exp, actual in zip_longest(files, file_group.files):
                    assert_dict_contains(actual, exp)

            for key, value in expected.items():
                attr = getattr(file_group, key)
                if isinstance(value, dict):
                    assert_dict_contains(attr, value)
                elif attr != value:
                    raise AssertionError(f'{file_group}.{key} {attr=} != {value}')

        if assert_count is True:
            if (count := test_session.query(FileGroup).count()) != len(file_groups):
                raise AssertionError(f'FileGroup count does not match {count} != {len(file_groups)}')

    return _


@pytest.fixture
def assert_files_search(test_client):
    from wrolpi.test.common import assert_dict_contains

    def _(search_str: str, expected: List[dict]):
        content = json.dumps({'search_str': search_str})
        request, response = test_client.post('/api/files/search', content=content)
        for file_group, exp in zip_longest(response.json['file_groups'], expected):
            assert_dict_contains(file_group, exp)

        assert len(response.json['file_groups']) == len(expected)

    return _


SINGLEFILE_CONTENTS = '''<html><!--
 Page saved with SingleFile 
 url: {url} 
 saved date: Thu May 12 2022 00:38:02 GMT+0000 (Coordinated Universal Time)
--><head><meta charset="utf-8">

<meta name="msapplication-TileColor" content="#2d89ef">
<meta name="theme-color" content="#000000">

{title}

<body>
some body contents
</body>

</html>
'''


@pytest.fixture
def singlefile_contents_factory():
    def _(title: str = '', url: str = 'https://example.com') -> str:
        contents = copy.deepcopy(SINGLEFILE_CONTENTS)
        contents = contents.format(
            title=f'<title>{title}</title>',
            url=url,
        )
        return contents

    return _


@pytest.fixture
def example_singlefile(test_directory, singlefile_contents_factory) -> pathlib.Path:
    archive = test_directory / 'archive'
    archive.mkdir(exist_ok=True)
    singlefile = archive / 'singlefile.html'
    singlefile.write_text(singlefile_contents_factory())
    return singlefile


@pytest.fixture
def image_bytes_factory():
    def _() -> bytes:
        with tempfile.NamedTemporaryFile(suffix='.png') as fh:
            Image.new('RGB', (1, 1), color='grey').save(fh)
            fh.seek(0)
            image = fh.read()
            return image

    return _


@pytest.fixture
def insert_file_group(test_session, test_directory):
    """Inserts a FileGroup based on the provided paths.  Does not verify if the files exist."""

    def _(paths: List[pathlib.Path]):
        files = [dict(path=str(i), mimetype='fake') for i in paths]
        params = dict(
            primary_path=str(paths[0]),
            files=json.dumps(files),
        )
        test_session.execute('INSERT INTO file_group '
                             '(indexed, primary_path, files) VALUES '
                             '(true, :primary_path, :files)', params)

    return _


@pytest.fixture
def test_tags_config(test_directory):
    from wrolpi.tags import test_tags_config
    with test_tags_config():
        (test_directory / 'config').mkdir(exist_ok=True)
        config_path = test_directory / 'config/tags.yaml'
        yield config_path


@pytest.fixture
def assert_tags_config(test_tags_config):
    def _(tags: dict = None):
        from wrolpi.test.common import assert_dict_contains
        with test_tags_config.open('rt') as fh:
            contents = yaml.load(fh, Loader=yaml.Loader)

        if tags:
            for key, item in tags.items():
                assert key in contents['tags']
                assert_dict_contains(item, contents['tags'][key])
        else:
            # Expect no tags to be saved.
            assert not contents['tags']

    return _


@pytest.fixture
def zip_file_factory(test_directory):
    def _() -> bytes:
        with tempfile.NamedTemporaryFile() as fh:
            with zipfile.ZipFile(fh, 'w') as zip_file:
                zip_file.write(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4')

            fh.seek(0)
            return fh.read()

    return _


@pytest.fixture
def assert_directories(test_session, test_directory):
    def _(expected: Sequence[str]):
        directories = test_session.query(Directory).all()
        names = {str(i.path.relative_to(test_directory)) for i in directories}
        assert names == set(expected)

    return _


FORM_PART = b'''-----------------------------sanic\r
Content-Disposition: form-data; name="{name}"\r
\r
{value}\r
\r
'''

FORM_FILENAME_PART = b'''-----------------------------sanic\r
Content-Disposition: form-data; name="{name}"; filename="{filename}"\r
Content-Type: application/octet-stream\r
\r
{value}\r
\r
'''


@pytest.fixture
def make_multipart_form():
    def _(forms: List[dict]):
        boundary = b'-----------------------------sanic\r\n'
        new_forms = []
        for form in forms:
            name, value, filename = form['name'].encode(), form['value'], form.get('filename', '').encode()
            value = value if isinstance(value, bytes) else str(value).encode()
            part = FORM_PART
            if filename:
                part = FORM_FILENAME_PART
                part.replace(b'{filename}', filename)
            part = part.replace(b'{name}', name)
            part = part.replace(b'{value}', value)
            new_forms.append(part)
        body = boundary + boundary.join(new_forms) + boundary
        return body

    return _


@pytest.fixture
def simple_file_server(test_directory):
    # Use a random port for testing
    server_address = ('', 0)  # 0 means pick any available port

    class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # Pass the directory to the handler
            self.directory = kwargs['directory']
            super().__init__(*args, **kwargs)

    # Create the server
    server = http.server.HTTPServer(
        server_address,
        # Hack to pass `test_directory` as `self.directory` to `SimpleHTTPRequestHandler`
        lambda *args, **kwargs:
        CustomHTTPRequestHandler(*args, directory=str(test_directory), **kwargs))

    # Start the server in a background thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True  # So the server dies when the main thread dies
    server_thread.start()

    try:
        yield server
    finally:
        # Cleanup
        server.shutdown()
        server.server_close()
        server_thread.join()


@pytest.fixture
def mock_downloader_download_file():
    """Mock the Downloader.download_file method."""
    contents = None

    async def _download_file(self, id_, url, destination):
        name = url.split('/')[-1]
        output_path = destination / name
        output_path.write_bytes(contents or b'')
        return output_path

    with mock.patch('wrolpi.downloader.Downloader.download_file', _download_file):
        def set_contents(contents_):
            nonlocal contents
            contents = contents_

        yield set_contents


@pytest.fixture
def start_status_worker():
    """Enable the status worker for testing."""
    with mock.patch('wrolpi.status.DISABLE_STATUS_WORKER', False):
        yield
