import asyncio
import atexit
import contextlib
import inspect
import json
import logging
import logging.config
import multiprocessing
import os
import pathlib
import re
import shutil
import string
import sys
import tempfile
from asyncio import Task
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from itertools import islice, filterfalse, tee
from multiprocessing.managers import DictProxy
from pathlib import Path
from types import GeneratorType
from typing import Union, Callable, Tuple, Dict, List, Iterable, Optional, Generator, Any, Set, Coroutine
from urllib.parse import urlparse, urlunsplit

import aiohttp
import bs4
import yaml
from aiohttp import ClientResponse, ClientSession
from bs4 import BeautifulSoup
from selenium import webdriver
from sqlalchemy import types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from wrolpi.dates import now, from_timestamp, seconds_to_timestamp
from wrolpi.errors import WROLModeEnabled, NativeOnly, UnrecoverableDownloadError, LogLevelError
from wrolpi.vars import PYTEST, DOCKERIZED, CONFIG_DIR, MEDIA_DIRECTORY, DEFAULT_HTTP_HEADERS

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] [%(process)d] [%(name)s:%(lineno)d] [%(levelname)s] %(message)s'
        },
        'detailed': {
            'format': '[%(asctime)s] [%(process)d] [%(name)s:%(lineno)d] [%(levelname)s] %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'  # Use standard output
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO'
    }
}

# Apply logging config.
logger = logging.getLogger()
logging.config.dictConfig(LOGGING_CONFIG)

logger_ = logger.getChild(__name__)


def set_log_level(level, warn_level: bool = True):
    """Set the level of the root logger so all children that have been created (or will be created) share the same
    level.

    @warning: Child processes will not share this level.  See set_global_log_level
    """
    logger.setLevel(level)

    # Always warn about the log level, so we know what should have been logged.
    effective_level = logger.getEffectiveLevel()
    level_name = logging.getLevelName(effective_level)
    if warn_level:
        logger.warning(f'Logging level: {level_name}')

    # Enable debug logging in SQLAlchemy when logging is NOTSET.
    sa_logger = logging.getLogger('sqlalchemy.engine')
    sa_level = logging.DEBUG if level == logging.NOTSET else logging.WARNING
    sa_logger.setLevel(sa_level)

    # Hide sanic access logs when not at least "INFO".
    sanic_access = logging.getLogger('sanic.access')
    sanic_level = logging.INFO if level <= 20 else logging.WARNING
    sanic_access.setLevel(sanic_level)


def set_global_log_level(log_level: int):
    """Set the global (shared between processes) log level."""
    if not isinstance(log_level, int) or not 0 <= log_level <= 40:
        raise LogLevelError()
    from wrolpi.api_utils import api_app
    with api_app.shared_ctx.log_level.get_lock():
        api_app.shared_ctx.log_level.value = log_level


@contextlib.contextmanager
def log_level_context(level):
    starting_level = logger.getEffectiveLevel()
    set_log_level(level, warn_level=False)
    yield
    set_log_level(starting_level, warn_level=False)


__all__ = [
    'Base',
    'ConfigFile',
    'DownloadFileInfo',
    'DownloadFileInfoLink',
    'ModelHelper',
    'WROLPI_CONFIG',
    'aiohttp_get',
    'aiohttp_head',
    'aiohttp_post',
    'api_param_limiter',
    'apply_modelers',
    'apply_refresh_cleanup',
    'background_task',
    'cancel_background_tasks',
    'cancel_refresh_tasks',
    'cancelable_wrapper',
    'chain',
    'chdir',
    'check_media_directory',
    'chunks',
    'chunks_by_stem',
    'compile_tsvector',
    'cum_timer',
    'date_range',
    'LOGGING_CONFIG',
    'disable_wrol_mode',
    'download_file',
    'enable_wrol_mode',
    'escape_file_name',
    'extract_domain',
    'extract_headlines',
    'extract_html_text',
    'format_html_string',
    'format_json_file',
    'get_absolute_media_path',
    'get_download_info',
    'get_files_and_directories',
    'get_global_statistics',
    'get_html_soup',
    'get_media_directory',
    'get_relative_to_media_directory',
    'get_title_from_html',
    'get_warn_once',
    'get_wrolpi_config',
    'html_screenshot',
    'insert_parameter',
    'iterify',
    'limit_concurrent',
    'logger',
    'make_media_directory',
    'minimize_dict',
    'native_only',
    'partition',
    'recursive_map',
    'register_modeler',
    'register_refresh_cleanup',
    'remove_whitespace',
    'resolve_generators',
    'run_after',
    'set_global_log_level',
    'set_log_level',
    'set_test_config',
    'set_test_media_directory',
    'slow_logger',
    'split_lines_by_length',
    'timer',
    'truncate_generator_bytes',
    'truncate_object_bytes',
    'tsvector',
    'url_strip_host',
    'walk',
    'wrol_mode_check',
    'wrol_mode_enabled',
    'zig_zag',
]

# Base is used for all SQLAlchemy models.
Base = declarative_base()


class ModelHelper:

    def dict(self, *_, **__) -> dict:
        d = {i.name: getattr(self, i.name) for i in self.__table__.columns}  # noqa
        return d

    @classmethod
    def upsert(cls, file, session: Session) -> Base:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def get_by_path(path, session) -> Base:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def find_by_paths(paths, session) -> List:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def get_by_id(id_: int, session: Session = None) -> Optional[Base]:
        """Attempts to get a model instance by its id.  Returns None if no instance can be found."""
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def find_by_id(id_: int, session: Session = None) -> Base:
        """Get a model instance by its id, raise an error if no instance is found."""
        raise NotImplementedError('This model has not defined this method.')

    def flush(self):
        """A convenience function which flushes this record using its DB Session."""
        Session.object_session(self).flush([self])


class tsvector(types.TypeDecorator):
    impl = types.UnicodeText


@compiles(tsvector, 'postgresql')
def compile_tsvector(element, compiler, **kw):
    return 'tsvector'


URL_CHARS = string.ascii_lowercase + string.digits


def find_file(directory: pathlib.Path, name: str, depth=1) -> Optional[pathlib.Path]:
    """Recursively searches a directory for a file with the provided name."""
    if depth == 0:
        return

    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name == name:
            return path
        if path.is_dir() and (result := find_file(path, name, depth - 1)):
            return result


TEST_MEDIA_DIRECTORY = None


def set_test_media_directory(path):
    global TEST_MEDIA_DIRECTORY
    if isinstance(path, pathlib.Path):
        TEST_MEDIA_DIRECTORY = path
    elif path:
        TEST_MEDIA_DIRECTORY = pathlib.Path(path)
    else:
        TEST_MEDIA_DIRECTORY = None


def get_media_directory() -> Path:
    """Get the media directory.

    This will typically be /opt/wrolpi, or something else from the .env.

    During testing, this function returns TEST_MEDIA_DIRECTORY.
    """
    global TEST_MEDIA_DIRECTORY

    if PYTEST and not TEST_MEDIA_DIRECTORY:
        raise RuntimeError('No test media directory set during testing!!')

    if isinstance(TEST_MEDIA_DIRECTORY, pathlib.Path):
        if not str(TEST_MEDIA_DIRECTORY).startswith('/tmp'):
            raise RuntimeError('Refusing to run test outside tmp directory!')
        return TEST_MEDIA_DIRECTORY

    return MEDIA_DIRECTORY


class ConfigFile:
    """
    This class keeps track of the contents of a config file.  You can update the config (and it's file) by
    calling .update().
    """
    file_name: str = None
    default_config: dict = None
    width: int = None

    def __init__(self):
        self.width = self.width or 90

        if PYTEST:
            # Do not load a global config on import while testing.  A global instance should never be used for testing.
            self._config = self.default_config.copy()
            return

    def __repr__(self):
        return f'<{self.__class__.__name__} file={self.get_file()}>'

    def initialize(self, multiprocessing_dict: Optional[DictProxy] = None):
        """Initializes this config dict using the default config and the config file."""
        config_file = self.get_file()
        # Use the provided multiprocessing.Manager().dict(), or dict() for testing.
        self._config = multiprocessing_dict or dict()
        # Use the default settings to initialize the config.
        self._config.update(deepcopy(self.default_config))
        if config_file.is_file():
            # Use the config file to get the values the user set.
            with config_file.open('rt') as fh:
                self._config.update(yaml.load(fh, Loader=yaml.Loader))
        return self

    def _get_backup_filename(self):
        """Returns the path for the backup file for today."""
        # TODO what if the RPi clock is not working?  Change this so the "version" of the config is used each day.
        path = get_media_directory() / f'config/backup/{self.file_name}'
        date_str = now().strftime('%Y%m%d')
        name = f'{path.stem}-{date_str}{path.suffix}'
        path = path.with_name(name)
        return path

    def save(self):
        """
        Write this config to its file.

        Use the existing config file as a template; if any values are missing in the new config, use the values from the
        config file.
        """
        from wrolpi.api_utils import api_app

        config_file = self.get_file()
        # Don't overwrite a real config while testing.
        if PYTEST and not str(config_file).startswith('/tmp'):
            raise ValueError(f'Refusing to save config file while testing: {config_file}')

        # Only one process can write to a config.
        lock = api_app.shared_ctx.config_save_lock
        acquired = lock.acquire(block=True, timeout=5.0)

        try:
            # Config directory may not exist.
            if not config_file.parent.is_dir():
                config_file.parent.mkdir()

            backup_file = self._get_backup_filename()

            # Read the existing config, replace all values, then save.
            if config_file.is_file():
                with config_file.open('rt') as fh:
                    config = yaml.load(fh, Loader=yaml.Loader)
                # Copy the existing config to the backup directory.  One for each day.
                if not backup_file.parent.exists():
                    backup_file.parent.mkdir(parents=True)
                shutil.copy(config_file, backup_file)
            else:
                # Config file does not yet exist.
                config = dict()

            config.update({k: v for k, v in self._config.items() if v is not None})
            logger.debug(f'Saving config: {config_file}')
            with config_file.open('wt') as fh:
                yaml.dump(config, fh, width=self.width)
                # Wait for data to be written before releasing lock.
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            if acquired:
                lock.release()

    def get_file(self) -> Path:
        if not self.file_name:
            raise NotImplementedError(f'You must define a file name for this {self.__class__.__name__} config.')

        if PYTEST:
            return get_media_directory() / f'config/{self.file_name}'

        return CONFIG_DIR / self.file_name

    def update(self, config: dict):
        """Update any values of this config.  Save the config to its file."""
        config = {k: v for k, v in config.items() if k in self._config}
        self._config.update(config)
        self.save()

    def dict(self) -> dict:
        """Get a deepcopy of this config."""
        if not hasattr(self, '_config'):
            raise NotImplementedError('You cannot use a global config while testing!')

        return deepcopy(self._config)


class WROLPiConfig(ConfigFile):
    file_name = 'wrolpi.yaml'
    default_config = dict(
        archive_directory='archive',
        download_on_startup=True,
        download_timeout=0,
        hotspot_device='wlan0',
        hotspot_on_startup=True,
        hotspot_password='wrolpi hotspot',
        hotspot_ssid='WROLPi',
        ignore_outdated_zims=False,
        ignored_directories=list(),
        map_directory='map',
        throttle_on_startup=False,
        videos_directory='videos',
        wrol_mode=False,
        zims_directory='zims',
    )

    def get_file(self) -> Path:
        """WROLPiConfig must be discovered so that other config files can be found."""
        if not self.file_name:
            raise NotImplementedError(f'You must define a file name for this {self.__class__.__name__} config.')

        if PYTEST:
            return get_media_directory() / f'config/{self.file_name}'

        # Use the usual "/media/wrolpi/config/wrolpi.yaml" if it exists.
        default_config_path = CONFIG_DIR / self.file_name
        if default_config_path.is_file():
            return default_config_path

        # Search the media directory for the special "wrolpi.yaml" file.  Assume the first one found is the config.
        # Use a depth of 3; multiple drives may exist and the config directory may be down in a second drive.
        if config_path := find_file(get_media_directory(), self.file_name, 3):
            return config_path

        # Not testing, and can't find file deep in media directory.  Use the default.
        return default_config_path

    @property
    def download_on_startup(self) -> bool:
        return self._config['download_on_startup']

    @download_on_startup.setter
    def download_on_startup(self, value: bool):
        self.update({'download_on_startup': value})

    @property
    def download_timeout(self) -> int:
        return self._config['download_timeout']

    @download_timeout.setter
    def download_timeout(self, value: int):
        self.update({'download_timeout': value})

    @property
    def hotspot_device(self) -> str:
        return self._config['hotspot_device']

    @hotspot_device.setter
    def hotspot_device(self, value: str):
        self.update({'hotspot_device': value})

    @property
    def hotspot_on_startup(self) -> bool:
        return self._config['hotspot_on_startup']

    @hotspot_on_startup.setter
    def hotspot_on_startup(self, value: bool):
        self.update({'hotspot_on_startup': value})

    @property
    def hotspot_password(self) -> str:
        return self._config['hotspot_password']

    @hotspot_password.setter
    def hotspot_password(self, value: str):
        self.update({'hotspot_password': value})

    @property
    def hotspot_ssid(self) -> str:
        return self._config['hotspot_ssid']

    @hotspot_ssid.setter
    def hotspot_ssid(self, value: str):
        self.update({'hotspot_ssid': value})

    @property
    def ignore_outdated_zims(self) -> bool:
        return self._config['ignore_outdated_zims']

    @ignore_outdated_zims.setter
    def ignore_outdated_zims(self, value: bool):
        self.update({'ignore_outdated_zims': value})

    @property
    def throttle_on_startup(self) -> bool:
        return self._config['throttle_on_startup']

    @throttle_on_startup.setter
    def throttle_on_startup(self, value: bool):
        self.update({'throttle_on_startup': value})

    @property
    def wrol_mode(self) -> bool:
        return self._config['wrol_mode']

    @wrol_mode.setter
    def wrol_mode(self, value: bool):
        self.update({'wrol_mode': value})

    @property
    def ignored_directories(self) -> List[str]:
        return self._config['ignored_directories']

    @ignored_directories.setter
    def ignored_directories(self, value: List[str]):
        self.update({'ignored_directories': value})

    @property
    def videos_directory(self) -> str:
        return self._config['videos_directory']

    @videos_directory.setter
    def videos_directory(self, value: str):
        self.update({'videos_directory': value})

    @property
    def archive_directory(self) -> str:
        return self._config['archive_directory']

    @archive_directory.setter
    def archive_directory(self, value: str):
        self.update({'archive_directory': value})

    @property
    def map_directory(self) -> str:
        return self._config['map_directory']

    @map_directory.setter
    def map_directory(self, value: str):
        self.update({'map_directory': value})

    @property
    def zims_directory(self) -> str:
        return self._config['zims_directory']

    @zims_directory.setter
    def zims_directory(self, value: str):
        self.update({'zims_directory': value})


WROLPI_CONFIG: WROLPiConfig = WROLPiConfig()
TEST_WROLPI_CONFIG: WROLPiConfig = None


def get_wrolpi_config() -> WROLPiConfig:
    """Read the global WROLPi yaml config file."""
    global TEST_WROLPI_CONFIG
    if isinstance(TEST_WROLPI_CONFIG, WROLPiConfig):
        return TEST_WROLPI_CONFIG

    global WROLPI_CONFIG
    return WROLPI_CONFIG


def set_test_config(enable: bool):
    global TEST_WROLPI_CONFIG
    TEST_WROLPI_CONFIG = WROLPiConfig() if enable else None


def wrol_mode_enabled() -> bool:
    """Return True if WROL Mode is enabled."""
    return get_wrolpi_config().wrol_mode


def wrol_mode_check(func):
    """Wraps a function so that it cannot be called when WROL Mode is enabled."""

    @wraps(func)
    def check(*a, **kw):
        if wrol_mode_enabled():
            raise WROLModeEnabled()

        # WROL Mode is not enabled, run the function as normal.
        result = func(*a, **kw)
        return result

    return check


def enable_wrol_mode():
    """
    Modify config to enable WROL Mode.

    Stop downloads and Download Manager.
    """
    logger_.warning('ENABLING WROL MODE')
    get_wrolpi_config().wrol_mode = True
    from wrolpi.downloader import download_manager
    download_manager.stop()


async def disable_wrol_mode():
    """
    Modify config to disable WROL Mode.

    Start downloads and Download Manager.
    """
    logger_.warning('DISABLING WROL MODE')
    get_wrolpi_config().wrol_mode = False
    from wrolpi.downloader import download_manager
    await download_manager.enable()


def insert_parameter(func: Callable, parameter_name: str, item, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
    """Insert a parameter wherever it fits in the Callable's signature."""
    sig = inspect.signature(func)
    if parameter_name not in sig.parameters:
        raise TypeError(f'Function {func} MUST have a {parameter_name} parameter!')

    args = list(args)

    index = list(sig.parameters).index(parameter_name)
    args.insert(index, item)
    args = tuple(args)

    return args, kwargs


def iterify(kind: type = list):
    """Convenience function to convert the output of the wrapped function to the type provided."""

    def wrapper(func):
        @wraps(func)
        def wrapped(*a, **kw):
            result = func(*a, **kw)
            return kind(result)

        return wrapped

    return wrapper


dt_or_d = Union[datetime, date]


def date_range(start: dt_or_d, end: dt_or_d, steps: int) -> List[dt_or_d]:
    delta = (end - start) // steps
    return [start + (delta * i) for i in range(steps)]


WHITESPACE = re.compile(r'\s')


def remove_whitespace(s: str) -> str:
    return WHITESPACE.sub('', s)


RUN_AFTER = False


def run_after(after: callable, *args, **kwargs) -> callable:
    """Run the `after` function sometime in the future ofter the wrapped function returns."""
    if not inspect.iscoroutinefunction(after):
        synchronous_after = after

        async def after(*a, **kw):
            return synchronous_after(*a, **kw)

    def wrapper(func: callable):
        if PYTEST and RUN_AFTER is False:
            return func

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapped(*a, **kw):
                results = await func(*a, **kw)
                coro = after(*args, **kwargs)
                asyncio.ensure_future(coro)
                return results
        else:
            @wraps(func)
            def wrapped(*a, **kw):
                results = func(*a, **kw)
                coro = after(*args, **kwargs)
                asyncio.ensure_future(coro)
                return results

        return wrapped

    return wrapper


MEDIA_DIRECTORY_PERMISSIONS = 0o40755


def check_media_directory():
    """
    Check that the media directory exists and has the correct permissions.  Log an error if the directory
    is unusable.
    """
    result = True
    media_directory = get_media_directory()
    if not media_directory.is_dir():
        logger_.error(f'Media directory does not exist: {media_directory}')
        return False

    permissions = media_directory.stat().st_mode
    if permissions != MEDIA_DIRECTORY_PERMISSIONS:
        logger_.error(f'Media directory has the wrong permissions: {oct(permissions)}')
        result = False

    if not media_directory.is_mount():
        logger_.warning('Media directory is not a mount.')

    try:
        # Write a file into the media directory, log an error if this is not possible.  This file should be cleaned up
        # by tempfile.
        with tempfile.NamedTemporaryFile(dir=media_directory) as tf:
            tf.write(b'test')
    except Exception as e:
        logger_.error(f'Could not write to media directory: {media_directory}', exc_info=e)
        result = False

    return result


def get_absolute_media_path(path: str) -> Path:
    """
    Get the absolute path of file/directory within the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_absolute_media_path('videos/blender')
    Path('/media/videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    if not path:
        raise ValueError('Path cannot be empty!')
    path = get_media_directory() / path
    return path


def get_relative_to_media_directory(path: Union[str, Path]) -> Path:
    """
    Get the path for a file/directory relative to the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_relative_to_media_directory('/media/videos/blender')
    Path('videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    absolute = get_absolute_media_path(path)
    return absolute.relative_to(get_media_directory())


def minimize_dict(d: dict, keys: Iterable) -> Optional[dict]:
    """Return a new dictionary that contains only the keys provided."""
    if d is None:
        return
    return {k: d[k] for k in set(keys) & d.keys()}


def make_media_directory(path: Union[str, Path]):
    """Make a directory relative within the media directory."""
    media_dir = get_media_directory()
    path = media_dir / str(path)
    path.mkdir(parents=True)


def extract_domain(url):
    """
    Extract the domain from a URL.  Remove leading www.

    >>> extract_domain('https://www.example.com/foo')
    'example.com'
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    if not domain:
        raise ValueError(f'URL does not have a domain: {url=}')
    domain = domain.decode() if hasattr(domain, 'decode') else domain
    if domain.startswith('www.'):
        # Remove leading www.
        domain = domain[4:]
    return domain


def api_param_limiter(maximum: int, default: int = 20) -> callable:
    """Create a function which restricts the maximum number that can be returned.
    Useful for restricting API limit params.

    >>> limiter = api_param_limiter(100)
    >>> limiter(0)
    0
    >>> limiter(100)
    100
    >>> limiter(150)
    100
    """

    def limiter_(i: int) -> int:
        if not i:
            # Limit is not valid, use the default.
            return default
        return min(int(i), maximum)

    return limiter_


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and true entries

    >>> is_even = lambda i: not i % 2
    >>> partition(is_even, range(10))
    ([0, 2, 4, 6, 8], [1, 3, 5, 7, 9])
    """
    t1, t2 = tee(iterable)
    return list(filter(pred, t2)), list(filterfalse(pred, t1))


@contextlib.contextmanager
def chdir(directory: Union[pathlib.Path, str, None] = None, with_home: bool = False):
    """
    Change the Python working directory in this context.  If no directory is passed, a TemporaryDirectory will be used.

    This also changes the $HOME environment variable to match.
    """
    home_exists = 'HOME' in os.environ
    home = os.environ.get('HOME')
    cwd = os.getcwd()
    if directory is None:
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                if with_home:
                    os.environ['HOME'] = d
                yield
            finally:
                os.chdir(cwd)
                if home_exists:
                    os.environ['HOME'] = home
                else:
                    del os.environ['HOME']
            return

    try:
        os.chdir(directory)
        if with_home:
            os.environ['HOME'] = str(directory)
        yield
    finally:
        os.chdir(cwd)
        if home_exists:
            os.environ['HOME'] = home
        else:
            del os.environ['HOME']
    return


ZIG_TYPE = Union[int, float, complex, Decimal, datetime]


def zig_zag(low: ZIG_TYPE, high: ZIG_TYPE) -> Generator[ZIG_TYPE, None, None]:
    """
    Generate numbers between `low` and `high` that are
    spread out evenly.  Produces infinite results.

    >>> list(zig_zag(0, 10))
    [0, 5, 2, 7, 1, 3, 6, 8, 0, 1, 3, 4, 5, 6, 8, 9]
    >>> list(zig_zag(0, 5))
    [0, 2, 1, 3, 0, 1, 3, 4]
    >>> list(zig_zag(50.0, 100.0))
    [50.0, 75.0, 62.5, 87.5, 56.25, 68.75, 81.25, 93.75, 53.125, 59.375, 65.625]
    """
    output_type = type(low)
    if not isinstance(high, type(low)):
        raise ValueError(f'high and low must be same type')
    if isinstance(low, datetime) and isinstance(high, datetime):
        low, high = low.timestamp(), high.timestamp()
        output_type = from_timestamp

    # Special thanks to my wife for helping me solve this! :*
    results = set()
    num = low
    divisor = 2
    diff = high - low
    while True:
        if num not in results:
            yield output_type(num)
            results.add(num)
        num += diff / divisor
        if num >= high:
            divisor *= 2
            num = low + (diff / divisor)


def walk(path: Path) -> Generator[Path, None, None]:
    """Recursively walk a directory structure yielding all files and directories."""
    if not path.is_dir():
        raise ValueError('Can only walk a directory.')

    for path in path.iterdir():
        yield path
        if path.is_dir():
            yield from walk(path)


def get_files_and_directories(directory: Path):
    """Walk a directory, return a tuple of all files and all directories within.  (Not recursive)."""
    if not directory.exists():
        raise FileNotFoundError(f'Directory does not exist: {directory}')
    if not directory.is_dir():
        raise ValueError('Can only walk a directory.')

    directories, files = partition(lambda i: i.is_dir(), directory.iterdir())
    return files, directories


# These characters are invalid in Windows or Linux.
INVALID_FILE_CHARS = re.compile(r'[/<>:|"\\?*%!\n\r]')

SPACE_FILE_CHARS = re.compile(r'(  +)|(\t+)')


def escape_file_name(name: str) -> str:
    """Remove any invalid characters in a file name."""
    name = name.replace(' | ', ' - ')
    name = SPACE_FILE_CHARS.sub(' ', name)
    name = INVALID_FILE_CHARS.sub('', name)
    return name.strip()


def native_only(func: callable):
    """Wraps a function.  Raises NativeOnly if run while Dockerized."""

    @wraps(func)
    def wrapped(*a, **kw):
        if DOCKERIZED:
            raise NativeOnly('Only supported on a Raspberry Pi')
        return func(*a, **kw)

    return wrapped


def recursive_map(obj: Any, func: callable):
    """
    Apply `func` to all values of any dictionaries; or items in any list/set/tuple.

    >>> recursive_map({'foo ': ' bar '}, lambda i: i.strip() if hasattr(i, 'strip') else i)
    {'foo ': 'bar'}
    >>> recursive_map(['foo ', ' bar '], lambda i: i.strip() if hasattr(i, 'strip') else i)
    ['foo', 'bar']
    """
    if isinstance(obj, dict):
        obj = obj.copy()
        for key, value in obj.items():
            obj[key] = recursive_map(value, func)
        return obj
    elif isinstance(obj, (list, set, tuple)):
        type_ = type(obj)
        return type_(map(lambda i: recursive_map(i, func), obj))
    return func(obj)


@contextlib.asynccontextmanager
async def aiohttp_session(timeout: int = None) -> ClientSession:
    """Convenience function because aiohttp timeout cannot be None."""
    if timeout:
        timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        async with aiohttp.ClientSession(timeout=timeout) as session:
            yield session
    else:
        async with aiohttp.ClientSession() as session:
            yield session


async def aiohttp_post(url: str, json_, timeout: int = None) -> Tuple[Dict, int]:
    """Perform an async aiohttp POST request.  Return the json contents."""
    async with aiohttp_session(timeout) as session:
        async with session.post(url, json=json_) as response:
            return await response.json(), response.status


async def aiohttp_get(url: str, timeout: int = None, headers: dict = None) -> Tuple[bytes, int]:
    """Perform an async aiohttp GET request.  Return the contents."""
    async with aiohttp_session(timeout) as session:
        async with session.get(url, headers=headers) as response:
            return await response.content.read(), response.status


async def aiohttp_head(url: str, timeout: int = None) -> Tuple[ClientResponse, int]:
    """Perform an async aiohttp HEAD request.  Return the contents."""
    async with aiohttp_session(timeout) as session:
        async with session.head(url) as response:
            return response, response.status


async def speed_test(url: str) -> int:
    """Request the last megabyte of the provided url, return the content length divided by the time elapsed (speed)."""
    response, status = await aiohttp_head(url)
    content_length = response.headers['Content-Length']
    start_bytes = int(content_length) - 10485760
    range_ = f'bytes={start_bytes}-{content_length}'
    start_time = datetime.now()
    content, status = await aiohttp_get(url, headers={'Range': range_})
    elapsed = int((datetime.now() - start_time).total_seconds())
    return len(content) // elapsed


async def get_fastest_mirror(urls: List[str]) -> str:
    """Perform a speed test on each URL, return the fastest."""
    fastest_url = urls[0]
    fastest_speed = 0
    for url in urls:
        try:
            speed = await speed_test(url)
        except Exception as e:
            logger.error(f'Speedtest of {url} failed', exc_info=e)
            continue

        if speed > fastest_speed:
            fastest_url = url

    return fastest_url


@dataclass
class DownloadFileInfoLink:
    """Represents an HTTP "Link" Header."""
    url: str
    rel: str
    type: str
    priority: int
    geo: str


@dataclass
class DownloadFileInfo:
    """Information about a file that can be downloaded."""
    name: str = None
    size: int = None
    type: str = None
    accept_ranges: str = None
    status: int = None
    location: str = None
    links: List[DownloadFileInfoLink] = None


FILENAME_MATCHER = re.compile(r'.*filename="(.*)"')


async def get_download_info(url: str, timeout: int = 60) -> DownloadFileInfo:
    """Gets information (name, size, etc.) about a downloadable file at the provided URL."""
    response, status = await aiohttp_head(url, timeout)
    logger_.debug(f'{response.headers=}')
    try:
        links = response.headers.getall('Link')
    except KeyError:
        links = None

    new_links = list()
    if links:
        # Convert "Link" header strings to DownloadFileInfoLink.
        for idx, link in enumerate(links):
            url, *props = link.split(';')
            url = url[1:-1]
            properties = dict()
            for prop in props:
                name, value = prop.strip().split('=')
                properties[name] = value
            new_links.append(DownloadFileInfoLink(
                url,
                properties.get('rel').strip() if 'rel' in properties else None,
                properties.get('type').strip() if 'type' in properties else None,
                int(properties.get('pri').strip()) if 'pri' in properties else None,
                properties.get('geo').strip() if 'geo' in properties else None,
            ))

    info = DownloadFileInfo(
        type=response.headers.get('Content-Type'),
        size=int(response.headers['Content-Length']) if 'Content-Length' in response.headers else None,
        accept_ranges=response.headers.get('Accept-Ranges'),
        status=response.status,
        location=response.headers.get('Location'),
        links=new_links,
    )

    disposition = response.headers.get('Content-Disposition')

    if disposition and 'filename' in disposition:
        if (match := FILENAME_MATCHER.match(disposition)) and (groups := match.groups()):
            info.name = groups[0]
    else:
        # No Content-Disposition with filename, use the Location or URL name.
        if info.location:
            parsed = urlparse(info.location)
        else:
            parsed = urlparse(url)
        info.name = parsed.path.split('/')[-1]

    return info


download_logger = logger_.getChild('download')


async def download_file(url: str, output_path: pathlib.Path = None, info: DownloadFileInfo = None,
                        timeout: int = 7 * 24 * 60 * 60):
    """Uses aiohttp to download an HTTP file.  Performs a speed test when mirrors are found, downloads from the fastest
    mirror.

    Attempts to resume the file if `output_path` already exists.

    @warning: Timeout default is a week because of large downloads.
    """
    info = info or await get_download_info(url, timeout)

    if output_path.is_file() and info.size == output_path.stat().st_size:
        download_logger.warning(f'Already downloaded {repr(str(url))} to {repr(str(output_path))}')
        return

    if info.links and (mirror_urls := [i.url for i in info.links if i.rel == 'duplicate']):
        # Mirrors are available, find the fastest.
        download_logger.info(f'Performing download speed test on mirrors: {mirror_urls}')
        url = await get_fastest_mirror(mirror_urls)
        info = await get_download_info(url, timeout)

    logger_.debug(f'Final DownloadInfo fetched {info}')
    total_size = info.size

    download_logger.info(f'Starting download of {url} with {total_size} total bytes')
    if info.accept_ranges == 'bytes' or not output_path.is_file():
        with output_path.open('ab') as fh:
            headers = DEFAULT_HTTP_HEADERS.copy()
            # Check the position of append, if it is 0 then we do not need to resume.
            position = fh.tell()
            if position:
                headers['Range'] = f'bytes={position}-'

            async with aiohttp_session(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    response: ClientResponse
                    if response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                        download_logger.warning(f'Server responded with 416, file is probably already downloaded')
                        return

                    if position and response.status != HTTPStatus.PARTIAL_CONTENT:
                        raise UnrecoverableDownloadError(
                            f'Tried to resume {repr(str(url))} but got status {response.status}')

                    # May or may not be using Range.  Append each chunk to the output file.
                    last_report = datetime.now()
                    bytes_received = 0
                    async for data in response.content.iter_any():
                        fh.write(data)

                        bytes_received += len(data)
                        if (elapsed := (datetime.now() - last_report).total_seconds()) > 10:
                            # Report download speed every 10 seconds.
                            bytes_per_second = int(bytes_received // elapsed)
                            download_logger.debug(f'{bytes_received=} {elapsed=} {bytes_per_second=}')
                            size = fh.tell()
                            bytes_remaining = total_size - size
                            seconds_remaining = bytes_remaining // bytes_per_second
                            percent = int((size / total_size) * 100)
                            download_logger.info(
                                f'Downloading {url} at'
                                f' rate={human_bandwidth(bytes_per_second)}'
                                f' estimate={seconds_to_timestamp(seconds_remaining)}')
                            download_logger.debug(f'Downloading {url} {total_size=} {size=} {percent=}')
                            last_report = datetime.now()
                            bytes_received = 0

                        # Sleep to catch cancel.
                        await asyncio.sleep(0)
    elif output_path.is_file():
        # TODO support downloading files that cannot be resumed.
        raise UnrecoverableDownloadError(f'Cannot resume download {url}')


def human_bandwidth(bps: int) -> str:
    """Convert bits per second to a more readable format.

    >>> human_bandwidth(2000)
    # '2 Kbps'
    """
    units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps']
    unit = 0
    while bps > 1000 and unit <= len(units):
        bps /= 1000
        unit += 1

    return f'{int(bps)} {units[unit]}'


modelers = []


def register_modeler(modeler: callable):
    modelers.append(modeler)
    return modeler


async def apply_modelers():
    for modeler in modelers:
        logger_.info(f'Applying modeler {modeler.__name__}')
        try:
            await modeler()
        except Exception as e:
            logger_.error(f'Modeler {modeler.__name__} raised error', exc_info=e)
            if PYTEST:
                raise
        # Sleep to catch cancel.
        await asyncio.sleep(0)


REFRESH_CLEANUP = []


def register_refresh_cleanup(func: callable):
    REFRESH_CLEANUP.append(func)
    return func


async def apply_refresh_cleanup():
    # TODO convert all functions to async so refresh functions can be used.
    for func in REFRESH_CLEANUP:
        slow_message = f'After refresh cleanup {func.__name__} took %(elapsed)s seconds'
        with slow_logger(5, slow_message, logger__=logger_):
            try:
                logger_.info(f'Applying refresh cleanup {func.__name__}')
                func()
            except Exception as e:
                logger_.error(f'Refresh cleanup {func.__name__} failed!', exc_info=e)
                if PYTEST:
                    raise
        # Sleep to catch cancel.
        await asyncio.sleep(0)


def chunks(it: Iterable, size: int):
    """Split an iterable into iterables of the defined length."""
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def chunks_by_stem(it: List[Union[pathlib.Path, str, int]], size: int) -> Generator[List[pathlib.Path], None, None]:
    """
    Attempt to split a list of paths near the defined size.  Keep groups of files together when they share
    matching names.

    >>> files = ['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png', '3.mp4']
    >>> chunks_by_stem(files, 2)
    [['1.mp4', '1.txt'], ['2.mp4', '2.txt', '2.png'], ['3.mp4']]
    >>> chunks_by_stem(files, 3)
    [['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png'], ['3.mp4']]
    """
    if not isinstance(size, int) or size < 1:
        raise ValueError('size must be a positive integer')

    if not it or len(it) < size:
        yield sorted(it)
        return

    if not isinstance(it, list):
        raise ValueError('iterable must a list')

    from wrolpi.files.lib import split_path_stem_and_suffix
    it = sorted(it.copy())
    index = size
    last_stem = None
    while it:
        if index >= len(it):
            # Ran out of items, yield what is left.
            yield it
            return
        path = it[index]
        stem, _ = split_path_stem_and_suffix(path)
        if last_stem and stem != last_stem:
            # Found a break in the path names, yield and reset.
            chunk, it = it[:index], it[index:]
            index = size
            last_stem = None
            yield chunk
            continue
        # Didn't find a name change, try again.
        last_stem = stem
        index += 1


@contextlib.contextmanager
def timer(name, level: str = 'debug'):
    """Prints out the time elapsed during the call of some block.

    Example:
        with timer('sleepy'):
            time.sleep(10)

    """
    before = datetime.now()
    log_method = getattr(logger_, level)
    try:
        yield
    finally:
        elapsed = (datetime.now() - before).total_seconds()
        log_method(f'{name} elapsed {elapsed} seconds')


def async_timer(coro: Coroutine, name: str = 'async timer', level: str = 'debug') -> callable:
    """Returns a new coroutine which prints out time elapsed when calling the coroutine."""

    async def _():
        with timer(name, level):
            return await coro

    return _()


@contextlib.contextmanager
def slow_logger(max_seconds: int, message: str, logger__=logger_, level=logging.WARNING):
    """Only logs when the context duration exceeds the `max_seconds`."""
    before = now()
    try:
        yield
    finally:
        elapsed = (now() - before).total_seconds()
        if elapsed >= max_seconds:
            logger__.log(level, message % dict(elapsed=elapsed))


TIMERS = dict()


@contextlib.contextmanager
def cum_timer(name: str):
    """Track time usage within this context's name.  The cumulative calls to this context will be printed on exit."""
    before = now()
    try:
        yield
    finally:
        total_seconds = (now() - before).total_seconds()
        existing_seconds, calls = TIMERS.get(name, (0, 0))
        TIMERS[name] = (existing_seconds + total_seconds, calls + 1)


@atexit.register
def print_timer():
    """Print any cumulative timers that have been stored during exit."""
    if not TIMERS:
        return

    total = sum(i[0] for i in TIMERS.values())
    for name, (seconds, calls) in sorted(TIMERS.items(), key=lambda i: i[1]):
        percent = int((seconds / total) * 100)
        seconds = round(seconds, 5)
        print(f'CUM_TIMER: {repr(name)} elapsed {seconds} cumulative seconds ({percent}%)'
              f' {calls} calls', file=sys.stderr)


def limit_concurrent(limit: int, throw: bool = False):
    """Wrapper that limits the amount of concurrently running functions."""
    sema = multiprocessing.Semaphore(value=limit)

    def wrapper(func: callable):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    if throw:
                        raise ValueError(f'Reached concurrent limit! {func=}')
                    return
                try:
                    return await func(*a, **kw)
                finally:
                    sema.release()

            return wrapped
        else:
            @wraps(func)
            def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    if throw:
                        raise ValueError(f'Reached concurrent limit! {func=}')
                    return
                try:
                    return func(*a, **kw)
                finally:
                    sema.release()

            return wrapped

    return wrapper


def truncate_object_bytes(obj: Union[List[str], str, None, Generator], maximum_bytes: int) -> Union[List[str], str]:
    """
    Shorten an object.  This is useful when inserting something into a tsvector.

    >>> i = ['foo',  'foo',  'foo',  'foo',  'foo', 'foo',  'foo',  'foo',  'foo',  'foo']
    >>> truncate_object_bytes(i, 100)
    ['foo',  'foo',  'foo',  'foo',  'foo']
    """
    if not obj:
        # Can't decrease an empty object.
        return obj
    size = sys.getsizeof(obj)
    if size < maximum_bytes:
        return obj
    index = -1 * round(len(obj) * .2)
    obj = obj[:index or -1]
    return truncate_object_bytes(obj, maximum_bytes)


def truncate_generator_bytes(gen: Generator, maximum_bytes: int) -> Generator:
    """Yield from a generator until the chunk sizes go over the maximum_bytes."""
    total_size = 0
    while total_size < maximum_bytes:
        try:
            chunk = next(gen)
            total_size += sys.getsizeof(chunk)
            yield chunk
        except StopIteration:
            return


BACKGROUND_TASKS = set()


def add_background_task(task: Task):
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


def background_task(coro) -> Task:
    """Convenience function which creates an asyncio task for the provided coroutine.

    The task is stored in a global set of background tasks so the task will not be discarded by the garbage collector.
    """

    async def error_logger():
        try:
            await coro
        except Exception as e:
            logger_.error('Background task had error:', exc_info=e)

    task = asyncio.create_task(error_logger())
    add_background_task(task)
    return task


async def cancel_background_tasks():
    """Cancels any background async tasks, if any."""
    if BACKGROUND_TASKS:
        logger_.warning(f'Canceling {len(BACKGROUND_TASKS)} background tasks')
        for task in BACKGROUND_TASKS:
            task.cancel()
            await asyncio.gather(*BACKGROUND_TASKS)


def get_warn_once(message: str, logger__: logging.Logger, level=logging.ERROR):
    """Create a function that will report an error only once.

    This is used when a function will be called many times, but the error is not important."""
    event = multiprocessing.Event()

    def warn_once(exception: Exception):
        if not event.is_set():
            logger__.log(level, message, exc_info=exception)
            event.set()

    return warn_once


def get_global_statistics():
    from wrolpi.db import get_db_curs
    with get_db_curs() as curs:
        curs.execute('select pg_database_size(current_database())')
        db_size = curs.fetchall()[0][0]

    return dict(
        db_size=db_size,
    )


REFRESH_TASKS: List[Task] = []


async def cancel_refresh_tasks():
    """Cancel all refresh tasks, if any."""
    if REFRESH_TASKS:
        logger_.warning(f'Canceling {len(REFRESH_TASKS)} refreshes')
        for task in REFRESH_TASKS:
            task.cancel()
        await asyncio.gather(*REFRESH_TASKS)


def cancelable_wrapper(func: callable):
    """Wraps an async function so that it will be canceled by `cancel_refresh_tasks`."""

    @wraps(func)
    async def wrapped(*args, **kwargs):
        if PYTEST:
            return await func(*args, **kwargs)

        task = background_task(func(*args, **kwargs))
        REFRESH_TASKS.append(task)

    return wrapped


WHITESPACE_SPLITTER = re.compile(r'\s+')
TAB = re.compile(r'\t+')


def split_lines_by_length(text: str, max_line_length: int = 38) -> str:
    """
    Break up any long lines along word boundaries.

    Newlines are preserved, but whitspace (spaces/tabs) is replaced with one space.

    @param max_line_length: The most amount of characters a line will contain.  38 is default for mobile vertical.

    >>> split_lines_by_length('Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do')
    'Lorem ipsum dolor sit amet,\nconsectetur adipiscing elit, sed do'
    """
    if not text:
        return text

    text = TAB.sub(' ', text)
    new_text = ''
    for line in text.splitlines():
        if len(line) > max_line_length:
            # This line is too long, break it up.
            new_line = ''
            words = WHITESPACE_SPLITTER.split(line)
            while words:
                word = words.pop(0)
                if len(possible_line := f'{new_line} {word}') <= max_line_length:
                    new_line = possible_line
                else:
                    # New word makes the line too long, start a new line.
                    new_text += f'\n{new_line.strip()}'
                    new_line = word
            new_text += f'\n{new_line}'
        else:
            new_text += f'\n{line}'
    return new_text.lstrip('\n')


def resolve_generators(obj: Union[Dict, List]) -> Any:
    """Recursively find generators within an object/list, resolve them.

    Returns a new object/list without any generators."""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, Tuple):
        return tuple(resolve_generators(i) for i in obj)
    elif isinstance(obj, Set):
        return {resolve_generators(i) for i in obj}
    elif isinstance(obj, Dict):
        return {resolve_generators(i): resolve_generators(j) for i, j in obj.items()}
    elif isinstance(obj, range):
        return list(obj)
    elif isinstance(obj, GeneratorType) or isinstance(obj, Iterable):
        return [resolve_generators(i) for i in obj]
    return obj


def url_strip_host(url: str) -> str:
    """Return a relative URL without the host or scheme.

    >>> url_strip_host('https://example.com/foo')
    '/foo'
    """
    url = urlparse(url)
    url = urlunsplit(('', '', url.path, url.query, url.fragment))
    return url or '/'


def get_html_soup(html: Union[bytes, str]) -> bs4.BeautifulSoup:
    soup = BeautifulSoup(html, features='html.parser')
    return soup


def extract_html_text(html: str) -> str:
    soup = get_html_soup(html)

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    text = soup.body.get_text()

    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks_ = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks_ if chunk)

    return text


def extract_headlines(entries: List[str], search_str: str) -> List[Tuple[str, float]]:
    """Use Postgres to extract Headlines and ranks of the `search_str` from the provided entries."""
    from wrolpi.db import get_db_curs

    source = json.dumps([{'content': i} for i in entries])
    with get_db_curs() as curs:
        stmt = '''
        WITH vectored AS (
            -- Convert the "source" json to a recordset.
            with source as (select * from json_to_recordset(%s::json) AS (content TEXT))
            select
                to_tsvector('english'::regconfig, source.content) AS vector,
                source.content
            from source
        )
        SELECT
            ts_headline(vectored.content, websearch_to_tsquery(%s), 'MaxFragments=10, MaxWords=8, MinWords=7'),
            ts_rank(vectored.vector, websearch_to_tsquery(%s))
        FROM vectored
        '''
        curs.execute(stmt, [source, search_str, search_str])
        headlines = [tuple(i) for i in curs.fetchall()]

    return headlines


def format_json_file(file: pathlib.Path, indent: int = 2):
    """Reformat the contents of a JSON file to include indentation to increase readability."""
    if not indent or indent <= 0:
        raise RuntimeError('Ident must be greater than 0')
    if not file or not file.is_file():
        raise RuntimeError(f'File does not exist: {file}')

    with file.open('rt') as fh:
        content = json.load(fh)

    copy = file.with_suffix('.json2')
    try:
        with copy.open('wt') as fh:
            json.dump(content, fh, indent=indent)
        copy.rename(file)
    finally:
        if copy.is_file():
            copy.unlink()


def format_html_string(html: str) -> str:
    if not html.strip():
        raise RuntimeError('Refusing to format empty HTMl string.')

    soup = BeautifulSoup(html, features='lxml')
    return soup.prettify()


def format_html_file(file: pathlib.Path):
    """Reformat the contents of an HTML file to include indentation to increase readability."""
    if not file or not file.is_file():
        raise RuntimeError(f'File does not exist: {file}')

    pretty = format_html_string(file.read_text())

    copy = file.with_suffix('.html2')
    try:
        with copy.open('wt') as fh:
            fh.write(pretty)
        copy.rename(file)
    finally:
        if copy.is_file():
            copy.unlink()


def html_screenshot(html: bytes) -> bytes:
    """Return a PNG screenshot of the provided HTML."""
    # Set Chromium to headless.  Use a wide window size so that screenshot will be the "desktop" version of the page.
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    options.add_argument('window-size=1280x720')

    with tempfile.NamedTemporaryFile('wb', suffix='.html') as fh:
        fh.write(html)
        fh.flush()

        with webdriver.Chrome(chrome_options=options) as driver:
            driver.get(f'file://{fh.name}')
            driver.set_window_size(1280, 720)
            screenshot = driver.get_screenshot_as_png()
            return screenshot


def chain(iterable: Union[List, Tuple], length: int) -> List:
    """
    Steps through the provided list and generates slices of the provided length.

    >>> list(chain([1, 2, 3, 4], 2))
    [[1, 2], [2, 3], [3, 4]]

    >>> list(chain([1, 2, 3, 4], 3))
    [[1, 2, 3], [2, 3, 4]]
    """
    if not iterable:
        return

    position = 0
    maximum = 1 + len(iterable) - length
    yielded = False
    while position < maximum:
        tick = iterable[position:position + length]
        yield tick
        yielded = True
        position += 1
    if not yielded:
        # Not enough items to iterate.  Yield the original iterable.
        yield iterable


def get_title_from_html(html: str, url: str = None) -> str:
    """
    Try and get the title from the
    """
    soup = get_html_soup(html)
    try:
        return soup.title.string.strip()
    except Exception:  # noqa
        logger.debug(f'Unable to extract title {url}')
