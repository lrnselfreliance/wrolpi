import asyncio
import collections
import contextlib
import inspect
import json
import logging
import os
import pathlib
import queue
import re
import string
import tempfile
from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from itertools import islice, filterfalse, tee
from multiprocessing import Event, Queue, Lock, Manager
from pathlib import Path
from typing import Union, Callable, Tuple, Dict, List, Iterable, Optional, Generator, Any
from urllib.parse import urlunsplit, urlparse

import yaml
from sanic import Blueprint
from sanic.request import Request
from sqlalchemy import types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base

from wrolpi.dates import DEFAULT_TIMEZONE
from wrolpi.errors import WROLModeEnabled, NativeOnly
from wrolpi.vars import PUBLIC_HOST, PUBLIC_PORT, PYTEST, MODULES_DIR, \
    DOCKERIZED, CONFIG_DIR, MEDIA_DIRECTORY

logger = logging.getLogger()
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Base is used for all SQLAlchemy models.
Base = declarative_base()


class ModelHelper:

    def dict(self) -> dict:
        d = {i.name: getattr(self, i.name) for i in self.__table__.columns}  # noqa
        return d


class PathColumn(types.TypeDecorator):
    impl = types.String

    def process_bind_param(self, value, dialect):
        if isinstance(value, Path):
            return value
        elif value:
            return str(value)

    def process_result_value(self, value, dialect):
        if value:
            return Path(value)


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


def string_to_boolean(s: str) -> bool:
    return str(s).lower() in {'true', 't', '1', 'on'}


DEFAULT_QUEUE_SIZE = 1000
QUEUE_TIMEOUT = 10

feed_logger = logger.getChild('ws_feed')

EVENTS = []
QUEUES = []


def create_websocket_feed(name: str, uri: str, blueprint: Blueprint, maxsize: int = DEFAULT_QUEUE_SIZE):
    """
    Build the objects needed to run a websocket which will pass on messages from a multiprocessing.Queue.

    :param name: the name that will be reported in the global event feeds
    :param uri: the Sanic URI that the websocket will listen on
    :param blueprint: the Sanic Blueprint to attach the websocket to
    :param maxsize: the maximum size of the Queue
    :return:
    """
    q = Queue(maxsize=maxsize)
    QUEUES.append(q)
    event = Event()
    EVENTS.append((name, event))

    @blueprint.websocket(uri)
    async def local_websocket(_: Request, ws):
        feed_logger.info(f'client connected to {ws}')
        feed_logger.debug(f'event.is_set: {event.is_set()}')
        any_messages = False
        while q.qsize() or event.is_set():
            # Pass along messages from the queue until its empty, or the event is cleared.  Give up after 1 second so
            # the worker can take another request.
            try:
                msg = q.get(timeout=QUEUE_TIMEOUT)
                any_messages = True
                dump = json.dumps(msg)
                await ws.send(dump)

                # yield back to the event loop
                await asyncio.sleep(0)
            except queue.Empty:  # pragma: no cover
                # No messages yet, try again while event is set
                pass
        feed_logger.info(f'loop complete')

        if any_messages is False:
            await ws.send(json.dumps({'code': 'no-messages'}))

        # No messages left, stream is complete
        await ws.send(json.dumps({'code': 'stream-complete'}))

    return q, event


# The following code is used to consistently construct URLs that will reference this service.
SANIC_HOST = None
SANIC_PORT = None
URL_COMPONENTS = collections.namedtuple('Components', ['scheme', 'netloc', 'path', 'query', 'fragment'])


def set_sanic_url_parts(host, port):
    """
    Set the global parts of this service's URL.  This is used to consistently construct URLs that will reference this
    service.
    """
    global SANIC_HOST
    global SANIC_PORT
    SANIC_HOST = host
    SANIC_PORT = port


def get_sanic_url(scheme: str = 'http', path: str = None, query: list = None, fragment: str = None):
    """
    Build a URL with the provided parts that references this running service.
    """
    host = PUBLIC_HOST or SANIC_HOST
    port = PUBLIC_PORT or SANIC_PORT
    components = URL_COMPONENTS(scheme=scheme, netloc=f'{host}:{port}', path=path,
                                query=query, fragment=fragment)
    unparsed = str(urlunsplit(components))
    return unparsed


class ConfigFile:
    """
    This class keeps track of the contents of a config file.  You can update the config by calling
    .update(), or by creating a property that does so.  Save your changes using .save().
    """
    file_name: str = None
    default_config: dict = None

    def __init__(self, global_: bool = False):
        if PYTEST and global_:
            # Do not load a global config on import while testing.  A global instance will never be used for testing.
            return

        config_file = self.get_file()
        self.file_lock = Lock()
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
        self.file_lock.acquire(block=True, timeout=5.0)

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
            self.file_lock.release()

    def get_file(self) -> Path:
        if not self.file_name:
            raise NotImplementedError(f'You must define a file name for this {self.__class__.__name__} config.')

        if PYTEST:
            return get_media_directory() / f'config/{self.file_name}'

        return CONFIG_DIR / self.file_name

    def update(self, config: dict):
        """
        Update any values of this config.  Save the config to its file.
        """
        config = {k: v for k, v in config.items() if k in self._config}
        self._config.update(config)
        self.save()

    def dict(self):
        """
        Get a deepcopy of this config.
        """
        if not hasattr(self, '_config'):
            raise NotImplementedError('You cannot use a global config while testing!')

        return deepcopy(self._config)


class WROLPiConfig(ConfigFile):
    file_name = 'wrolpi.yaml'
    default_config = dict(
        download_on_startup=True,
        hotspot_on_startup=True,
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
    def hotspot_on_startup(self) -> bool:
        return self._config['hotspot_on_startup']

    @hotspot_on_startup.setter
    def hotspot_on_startup(self, value: bool):
        self.update({'hotspot_on_startup': value})

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
    if enable:
        TEST_WROLPI_CONFIG = WROLPiConfig()
    else:
        TEST_WROLPI_CONFIG = None


def wrol_mode_enabled() -> bool:
    """Return True if WROL Mode is enabled."""
    return get_config().wrol_mode


def set_wrol_mode(enable: bool):
    """Enable or disable WROL Mode for all processes.  This also updates the config file."""
    get_config().wrol_mode = enable


def wrol_mode_check(func):
    """
    Wraps a function so that it cannot be called when WROL Mode is enabled.
    """

    @wraps(func)
    def check(*a, **kw):
        if wrol_mode_enabled():
            raise WROLModeEnabled()

        # WROL Mode is not enabled, run the function as normal.
        result = func(*a, **kw)
        return result

    return check


def insert_parameter(func: Callable, parameter_name: str, item, args: Tuple, kwargs: Dict) -> Tuple[Tuple, Dict]:
    """
    Insert a parameter wherever it fits in the Callable's signature.
    """
    sig = inspect.signature(func)
    if parameter_name not in sig.parameters:
        raise TypeError(f'Function {func} MUST have a {parameter_name} parameter!')

    args = list(args)

    index = list(sig.parameters).index(parameter_name)
    args.insert(index, item)
    args = tuple(args)

    return args, kwargs


def iterify(kind: type = list):
    """
    Convenience function to convert the output of the wrapped function to the type provided.
    """

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


def chunks(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


WHITESPACE = re.compile(r'\s')


def remove_whitespace(s: str) -> str:
    return WHITESPACE.sub('', s)


def run_after(after: callable, *args, **kwargs) -> callable:
    """
    Run the `after` function sometime in the future ofter the wrapped function returns.
    """
    if not inspect.iscoroutinefunction(after):
        synchronous_after = after

        async def after(*a, **kw):
            return synchronous_after(*a, **kw)

    def wrapper(func: callable):
        if PYTEST:
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
    """
    Return a new dictionary that contains only the keys provided.
    """
    if d is None:
        return
    return {k: d[k] for k in set(keys) & d.keys()}


def make_media_directory(path: Union[str, Path]):
    """
    Make a directory relative within the media directory.
    """
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
    domain = domain.decode() if hasattr(domain, 'decode') else domain
    if domain.startswith('www.'):
        # Remove leading www.
        domain = domain[4:]
    return domain


def import_modules():
    """
    Import all WROLPi Modules in the modules directory.  Raise an ImportError if there are no modules.
    """
    try:
        modules = [i.name for i in MODULES_DIR.iterdir() if i.is_dir() and not i.name.startswith('_')]
        for module in modules:
            module = f'modules.{module}.api'
            logger.debug(f'Importing {module}')
            __import__(module, globals(), locals(), [], 0)
    except ImportError as e:
        logger.fatal('No modules could be found!', exc_info=e)
        raise
    return modules


def api_param_limiter(maximum: int, default: int = 20) -> callable:
    """
    Create a function which restricts the maximum number that can be returned.
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


@contextlib.contextmanager
def temporary_directory_path(*a, **kw):
    with tempfile.TemporaryDirectory(*a, **kw) as d:
        yield pathlib.Path(d)


def partition(pred, iterable):
    """
    Use a predicate to partition entries into false entries
    and true entries
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
    """Recursively Walk a directory structure yielding all files and directories."""
    for path in path.iterdir():
        yield path
        if path.is_dir():
            yield from walk(path)


# These characters are invalid in Windows or Linux.
INVALID_FILE_CHARS = re.compile(r'[/<>:\|"\\\?\*]')


def escape_file_name(name: str) -> str:
    """Replace any invalid characters in a file name with "_"."""
    return INVALID_FILE_CHARS.sub('', name)


def native_only(func: callable):
    """Wraps a function.  Raises NativeOnly if run while Dockerized."""

    @wraps(func)
    def wrapped(*a, **kw):
        if DOCKERIZED:
            raise NativeOnly('Only supported on a Raspberry Pi')
        return func(*a, **kw)

    return wrapped


def read_yaml(path: Path):
    with path.open('rt') as fh:
        return yaml.load(fh, Loader=yaml.Loader)


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
