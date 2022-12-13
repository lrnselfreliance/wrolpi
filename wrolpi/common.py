import asyncio
import atexit
import contextlib
import inspect
import logging
import multiprocessing
import os
import pathlib
import re
import string
import sys
import tempfile
from asyncio import Task
from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from itertools import islice, filterfalse, tee
from multiprocessing import Lock, Manager
from pathlib import Path
from typing import Union, Callable, Tuple, Dict, List, Iterable, Optional, Generator, Any
from urllib.parse import urlparse

import aiohttp
import yaml
from sqlalchemy import types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from wrolpi.dates import DEFAULT_TIMEZONE, now
from wrolpi.errors import WROLModeEnabled, NativeOnly
from wrolpi.vars import PYTEST, MODULES_DIR, \
    DOCKERIZED, CONFIG_DIR, MEDIA_DIRECTORY

logger = logging.getLogger()
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

__all__ = [
    'logger',
    'Base',
    'ModelHelper',
    'get_model_by_table_name',
    'tsvector',
    'compile_tsvector',
    'WROLPI_CONFIG',
    'sanitize_link',
    'ConfigFile',
    'get_config',
    'set_test_config',
    'wrol_mode_enabled',
    'wrol_mode_check',
    'enable_wrol_mode',
    'disable_wrol_mode',
    'insert_parameter',
    'iterify',
    'date_range',
    'remove_whitespace',
    'run_after',
    'set_test_media_directory',
    'get_media_directory',
    'check_media_directory',
    'get_absolute_media_path',
    'get_relative_to_media_directory',
    'get_files_and_directories',
    'minimize_dict',
    'make_media_directory',
    'extract_domain',
    'import_modules',
    'api_param_limiter',
    'partition',
    'chdir',
    'zig_zag',
    'walk',
    'escape_file_name',
    'native_only',
    'recursive_map',
    'aiohttp_post',
    'register_modeler',
    'apply_modelers',
    'register_after_refresh',
    'apply_after_refresh',
    'match_paths_to_suffixes',
    'chunks',
    'chunks_by_name',
    'timer',
    'cum_timer',
    'limit_concurrent',
    'truncate_object_bytes',
    'background_task',
    'get_warn_once',
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
    def find_by_path(path, session) -> Base:
        raise NotImplementedError('This model has not defined this method.')

    @staticmethod
    def find_by_paths(paths, session) -> List:
        raise NotImplementedError('This model has not defined this method.')

    @property
    def primary_path(self):
        raise NotImplementedError('This model has not defined this method.')


def get_model_by_table_name(table_name):
    """Find a model by its table name."""
    for klass in Base._decl_class_registry.values():
        if hasattr(klass, '__tablename__') and klass.__tablename__ == table_name:
            return klass


class tsvector(types.TypeDecorator):
    impl = types.UnicodeText


@compiles(tsvector, 'postgresql')
def compile_tsvector(element, compiler, **kw):
    return 'tsvector'


URL_CHARS = string.ascii_lowercase + string.digits


def sanitize_link(link: str) -> str:
    """Remove any non-url safe characters, all will be lowercase."""
    new_link = ''.join(i for i in str(link).lower() if i in URL_CHARS)
    return new_link


class ConfigFile:
    """
    This class keeps track of the contents of a config file.  You can update the config by calling
    .update(), or by creating a property that does so.  Save your changes using .save().
    """
    file_name: str = None
    default_config: dict = None

    def __init__(self, global_: bool = False):
        self.file_lock = Lock()

        if PYTEST:
            # Do not load a global config on import while testing.  A global instance will never be used for testing.
            self._config = self.default_config.copy()
            return

        config_file = self.get_file()
        self._config = Manager().dict()
        # Use the default settings to initialize the config.
        self._config.update(deepcopy(self.default_config))
        if config_file.is_file():
            # Use the config file to get the values the user set.
            with config_file.open('rt') as fh:
                self._config.update(yaml.load(fh, Loader=yaml.Loader))

    def __repr__(self):
        return f'<{self.__class__.__name__} file={self.get_file()}>'

    def save(self):
        """
        Write this config to its file.

        Use the existing config file as a template; if any values are missing in the new config, use the values from the
        config file.
        """
        config_file = self.get_file()
        # Don't overwrite a real config while testing.
        if PYTEST and not str(config_file).startswith('/tmp'):
            raise ValueError(f'Refusing to save config file while testing: {config_file}')

        # Only one process can write to the file.
        acquired = self.file_lock.acquire(block=True, timeout=5.0)

        try:
            # Config directory may not exist.
            if not config_file.parent.is_dir():
                config_file.parent.mkdir()

            # Read the existing config, replace all values, then save.
            if config_file.is_file():
                with config_file.open('rt') as fh:
                    config = yaml.load(fh, Loader=yaml.Loader)
            else:
                # Config file does not yet exist.
                config = dict()

            config.update({k: v for k, v in self._config.items() if v is not None})
            with config_file.open('wt') as fh:
                yaml.dump(config, fh)
        finally:
            if acquired:
                self.file_lock.release()

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

    def dict(self):
        """Get a deepcopy of this config."""
        if not hasattr(self, '_config'):
            raise NotImplementedError('You cannot use a global config while testing!')

        return deepcopy(self._config)


class WROLPiConfig(ConfigFile):
    file_name = 'wrolpi.yaml'
    default_config = dict(
        download_on_startup=True,
        download_timeout=0,
        hotspot_device='wlan0',
        hotspot_on_startup=True,
        hotspot_password='wrolpi hotspot',
        hotspot_ssid='WROLPi',
        throttle_on_startup=False,
        timezone=str(DEFAULT_TIMEZONE),
        wrol_mode=False,
    )

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
    def throttle_on_startup(self) -> bool:
        return self._config['throttle_on_startup']

    @throttle_on_startup.setter
    def throttle_on_startup(self, value: bool):
        self.update({'throttle_on_startup': value})

    @property
    def timezone(self) -> str:
        return self._config['timezone']

    @timezone.setter
    def timezone(self, value: str):
        self.update({'timezone': value})

    @property
    def wrol_mode(self) -> bool:
        return self._config['wrol_mode']

    @wrol_mode.setter
    def wrol_mode(self, value: bool):
        self.update({'wrol_mode': value})


WROLPI_CONFIG: WROLPiConfig = WROLPiConfig(global_=True)
TEST_WROLPI_CONFIG: WROLPiConfig = None


def get_config() -> WROLPiConfig:
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
    return get_config().wrol_mode


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


def enable_wrol_mode(download_manager=None):
    """
    Modify config to enable WROL Mode.

    Stop downloads and Download Manager.
    """
    logger.warning('ENABLING WROL MODE')
    get_config().wrol_mode = True
    if not download_manager:
        from wrolpi.downloader import download_manager
        download_manager.stop()
    else:
        # Testing.
        download_manager.stop()


def disable_wrol_mode(download_manager=None):
    """
    Modify config to disable WROL Mode.

    Start downloads and Download Manager.
    """
    logger.warning('DISABLING WROL MODE')
    get_config().wrol_mode = False
    if not download_manager:
        from wrolpi.downloader import download_manager
        download_manager.enable()
    else:
        # Testing.
        download_manager.enable()


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
        raise ValueError('No test media directory set during testing!!')

    if isinstance(TEST_MEDIA_DIRECTORY, pathlib.Path):
        return TEST_MEDIA_DIRECTORY

    return MEDIA_DIRECTORY


MEDIA_DIRECTORY_PERMISSIONS = 0o40755


def check_media_directory():
    """
    Check that the media directory exists and has the correct permissions.  Log an error if the directory
    is unusable.
    """
    result = True
    media_directory = get_media_directory()
    if not media_directory.is_dir():
        logger.error(f'Media directory does not exist: {media_directory}')
        result = False

    permissions = media_directory.stat().st_mode
    if permissions != MEDIA_DIRECTORY_PERMISSIONS:
        logger.error(f'Media directory has the wrong permissions: {oct(permissions)}')
        result = False

    if not media_directory.is_mount():
        logger.warning('Media directory is not a mount.')

    try:
        # Write a file into the media directory, log an error if this is not possible.  This file should be cleaned up
        # by tempfile.
        with tempfile.NamedTemporaryFile(dir=media_directory) as tf:
            tf.write(b'test')
    except Exception as e:
        logger.error(f'Could not write to media directory: {media_directory}', exc_info=e)
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


def import_modules():
    """Import all WROLPi Modules in the modules directory.  Raise an ImportError if there are no modules."""
    modules = [i.name for i in MODULES_DIR.iterdir() if
               i.is_dir() and not (i.name.startswith('_') or i.name.startswith('.'))]
    imported = []
    for module_name in modules:
        module = f'modules.{module_name}.api'
        logger.debug(f'Importing {module}')
        try:
            __import__(module, globals(), locals(), [], 0)
            imported.append(module_name)
        except ImportError as e:
            logger.fatal(f'Unable to import {module}', exc_info=e)
    return imported


def api_param_limiter(maximum: int, default: int = 20) -> callable:
    """Create a function which restricts the maximum number that can be returned.
    Useful for restricting API limit params.

    >>> limiter = api_param_limiter(100)
    >>> limiter(0)
    0
    >>> limiter(100)
    100
    >>> limiter(150)
    150
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
        output_type = datetime.fromtimestamp

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


def get_files_and_directories(path: Path):
    """Walk a directory, return a tuple of all files and all directories within.  (Not recursive)."""
    if not path.is_dir():
        raise ValueError('Can only walk a directory.')

    directories, files = partition(lambda i: i.is_dir(), path.iterdir())
    return files, directories


# These characters are invalid in Windows or Linux.
INVALID_FILE_CHARS = re.compile(r'[/<>:\|"\\\?\*%!]')


def escape_file_name(name: str) -> str:
    """Remove any invalid characters in a file name."""
    return INVALID_FILE_CHARS.sub('', name)


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


async def aiohttp_post(url: str, json_, timeout: int = None) -> Tuple[Dict, int]:
    """Perform an async aiohttp post request.  Return the json contents."""
    timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=json_) as response:
            return await response.json(), response.status


modelers = []


def register_modeler(modeler: callable):
    modelers.append(modeler)
    return modeler


def apply_modelers(files, session: Session):
    from wrolpi.files.lib import split_path_stem_and_suffix, get_mimetype

    if not files:
        return

    # Group all files by their common name (without the suffix).
    groups = {}
    for file in files:
        if not file.mimetype:
            file.mimetype = get_mimetype(file.path)
        stem, _ = split_path_stem_and_suffix(file.path)
        try:
            groups[stem].append(file)
        except KeyError:
            groups[stem] = [file, ]

    for modeler in modelers:
        modeler(groups, session)

    for stem, group in groups.items():
        # Index any files that were not claimed by modelers.
        for file in group:
            file.do_index()


after_refresh = []


def register_after_refresh(func: callable):
    after_refresh.append(func)
    return func


def apply_after_refresh():
    for func in after_refresh:
        logger.info(f'Applying after-refresh {func.__name__}')
        func()


@iterify(tuple)
def match_paths_to_suffixes(paths: List[pathlib.Path], suffix_groups: List[Tuple[str]]):
    paths = paths.copy()
    for group in suffix_groups:
        match = None
        for suffix in group:
            # Compare all suffixes in the group to the path's name.  Yield the first path that shares the first
            # suffix.  If no suffix matches any path, yield None.
            match = next(filter(lambda i: i.name.endswith(suffix), paths), None)
            if match:
                paths.pop(paths.index(match))
                break
        yield match


def chunks(it: Iterable, size: int):
    """Split an iterable into iterables of the defined length."""
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def chunks_by_name(it: List[Union[pathlib.Path, str]], size: int) -> Generator[List[pathlib.Path], None, None]:
    """
    Attempt to split a list of paths near the defined size.  Keep groups of files together when they share
    matching names.

    >>> files = ['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png', '3.mp4']
    >>> chunks_by_name(files, 2)
    [['1.mp4', '1.txt'], ['2.mp4', '2.txt', '2.png'], ['3.mp4']]
    >>> chunks_by_name(files, 3)
    [['1.mp4', '1.txt', '2.mp4', '2.txt', '2.png'], ['3.mp4']]
    """
    if not isinstance(size, int) or size < 1:
        raise ValueError('size must be a positive integer')

    if not it or len(it) < size:
        yield it
        return

    if not isinstance(it, list):
        raise ValueError('iterable must a list')

    from wrolpi.files.lib import split_path_stem_and_suffix
    it = sorted(it.copy())
    index = size
    last_name = None
    while it:
        if index >= len(it):
            # Ran out of items, yield what is left.
            yield it
            return
        path = it[index]
        name, _ = split_path_stem_and_suffix(path)
        if last_name and name != last_name:
            # Found a break in the path names, yield and reset.
            chunk, it = it[:index], it[index:]
            index = size
            last_name = None
            yield chunk
            continue
        # Didn't find a name change, try again.
        last_name = name
        index += 1


@contextlib.contextmanager
def timer(name):
    """Prints out the time elapsed during the call of some block."""
    before = datetime.now()
    try:
        yield
    finally:
        logger.warning(f'{name} elapsed {(datetime.now() - before).total_seconds()} seconds')


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


def truncate_object_bytes(obj: Union[List[str], str, None], maximum_bytes: int) -> List[str]:
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


BACKGROUND_TASKS = set()


def background_task(coro) -> Task:
    """Convenience function which creates an asyncio task for the provided coroutine.

    The task is stored in a global set of background tasks so the task will not be discarded by the garbage collector.
    """
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task


def get_warn_once(message: str, logger_: logging.Logger, level=logging.ERROR):
    """Create a function that will report an error only once.

    This is used when a function will be called many times, but the error is not important."""
    event = multiprocessing.Event()

    def warn_once(exception: Exception):
        if not event.is_set():
            logger_.log(level, message, exc_info=exception)
            event.set()

    return warn_once


def ordered_unique_list(lst: Iterable) -> List:
    """Return a new list that contains only the first occurrence of each item."""
    return list(dict.fromkeys(lst))
