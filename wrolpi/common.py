import asyncio
import collections
import inspect
import json
import logging
import os
import pathlib
import queue
import re
import string
from copy import deepcopy
from datetime import datetime, date
from functools import wraps
from itertools import islice
from multiprocessing import Event, Queue
from pathlib import Path
from typing import Union, Callable, Tuple, Dict, Mapping, List, Iterable
from urllib.parse import urlunsplit

import yaml
from cachetools import cached, TTLCache
from sanic import Blueprint
from sanic.request import Request
from sqlalchemy import types
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base

from wrolpi.errors import WROLModeEnabled, UnknownDirectory
from wrolpi.vars import CONFIG_PATH, EXAMPLE_CONFIG_PATH, PUBLIC_HOST, PUBLIC_PORT, LAST_MODIFIED_DATE_FORMAT, \
    PROJECT_DIR

logger = logging.getLogger(__name__)
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


def make_progress_calculator(total):
    """
    Create a function that calculates the percentage of completion.
    """

    def progress_calculator(current) -> int:
        if current >= total:
            # Progress doesn't make sense, just return 100
            return 100
        percent = int((current / total) * 100)
        return percent

    return progress_calculator


class ProgressReporter:
    """
    I am used to consistently send messages and progress(s) to a Websocket Feed.
    """

    def __init__(self, q: Queue, progress_count: int = 1):
        self.queue: Queue = q
        self.progresses = [{'percent': 0, 'total': 0, 'value': 0} for _ in range(progress_count)]
        self.calculators = [lambda _: None for _ in range(progress_count)]

    def _update(self, idx: int, **kwargs):
        if 'message' in kwargs and kwargs['message'] is None:
            # Message can't be cleared.
            kwargs.pop('message')
        self.progresses[idx].update(kwargs)

    def _send(self, code: str = None):
        msg = dict(
            progresses=deepcopy(self.progresses)
        )
        if code:
            msg['code'] = code
        self.queue.put(msg)

    def message(self, idx: int, msg: str, code: str = None):
        self._update(idx, message=msg)
        self._send(code)

    def code(self, code: str):
        self._send(code)

    def error(self, idx: int, msg: str = None):
        self.message(idx, msg, 'error')

    def set_progress_total(self, idx: int, total: int):
        self.progresses[idx]['total'] = total
        self.calculators[idx] = make_progress_calculator(total)

    def send_progress(self, idx: int, value: int, msg: str = None):
        kwargs = dict(value=value, percent=self.calculators[idx](value), message=msg)
        self._update(idx, **kwargs)
        self._send()

    def finish(self, idx: int, msg: str = None):
        kwargs = dict(percent=100, message=msg)

        if self.progresses[idx]['total'] == 0:
            kwargs.update(dict(value=1, total=1))
        else:
            kwargs.update(dict(value=self.progresses[idx]['total']))

        self._update(idx, **kwargs)
        self._send()


class FileNotModified(Exception):
    pass


def get_modified_time(path: Union[Path, str]) -> datetime:
    """
    Return a datetime object containing the os modification time of the provided path.
    """
    modified = datetime.utcfromtimestamp(os.path.getmtime(str(path)))
    return modified


def get_last_modified_headers(request_headers: dict, path: Union[Path, str]) -> dict:
    """
    Get a dict containing the Last-Modified header for the provided path.  If If-Modified-Since is in the provided
    request headers, then this will raise a FileNotModified exception, which should be handled by
    `handle_FileNotModified`.
    """
    last_modified = get_modified_time(path)

    modified_since = request_headers.get('If-Modified-Since')
    if modified_since:
        modified_since = datetime.strptime(modified_since, LAST_MODIFIED_DATE_FORMAT)
        if last_modified >= modified_since:
            raise FileNotModified()

    last_modified = last_modified.strftime(LAST_MODIFIED_DATE_FORMAT)
    headers = {'Last-Modified': last_modified}
    return headers


def get_example_config() -> dict:
    config_path = EXAMPLE_CONFIG_PATH
    with open(str(config_path), 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return dict(config)


def get_local_config() -> dict:
    config_path = CONFIG_PATH
    with open(str(config_path), 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return dict(config)


def get_config() -> dict:
    try:
        return get_local_config()
    except FileNotFoundError:
        return get_example_config()


def combine_dicts(*dicts: dict) -> dict:
    """
    Recursively combine dictionaries, preserving the leftmost value.

    >>> a = dict(a='b', c=dict(d='e'))
    >>> b = dict(a='c', e='f')
    >>> combine_dicts(a, b)
    dict(a='b', c=dict(d='e'), e='f')
    """
    if len(dicts) == 0:
        raise IndexError('No dictionaries to iterate through')
    elif len(dicts) == 1:
        return dicts[0]
    a, b = dicts[-2:]
    c = dicts[:-2]
    new = {}
    keys = set(a.keys())
    keys = keys.union(b.keys())
    for k in keys:
        if k in b and k in a and isinstance(b[k], Mapping):
            value = combine_dicts(a[k], b[k])
        else:
            value = a.get(k, b.get(k))
        new[k] = value
    if c:
        return combine_dicts(*c, new)
    return new


def save_settings_config(config=None):
    """
    Save new settings to local.yaml, overwriting what is there.  This function updates the config file from three
    sources: the config object argument, the local config, then the example config; in that order.
    """
    config = config or {}
    example_config = get_example_config()
    # Remove the example channel, that shouldn't be saved to local
    example_config.pop('channels')
    try:
        local_config = get_local_config()
    except FileNotFoundError:
        # Local config does not yet exist, lets create it
        local_config = {}

    if 'channels' in config and 'channels' in local_config:
        del local_config['channels']

    if ('channels' in config or 'channels' in local_config) and 'channels' in example_config:
        del example_config['channels']

    new_config = combine_dicts(config, local_config, example_config)

    logger.info(f'Writing config to file: {CONFIG_PATH}')
    with open(str(CONFIG_PATH), 'wt') as fh:
        yaml.dump(new_config, fh)


@cached(cache=TTLCache(maxsize=1, ttl=30))
def wrol_mode_enabled() -> bool:
    """
    Return the boolean value of the `wrol_mode` in the config.
    """
    config = get_config()
    enabled = config.get('wrol_mode', False)
    return bool(enabled)


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


def remove_dict_value_whitespace(d: Dict) -> Dict:
    """
    Remove the whitespace around a the values in a dictionary.  Handles if the value isn't a string.
    """
    return {k: v.strip() if hasattr(v, 'strip') else v for k, v in d.items()}


def run_after(after: callable, *args, **kwargs) -> callable:
    """
    Run the `after` function sometime in the future ofter the wrapped function returns.
    """
    if not inspect.iscoroutinefunction(after):
        synchronous_after = after

        async def after(*a, **kw):
            return synchronous_after(*a, **kw)

    def wrapper(func: callable):
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
MEDIA_DIRECTORY = None


def set_test_media_directory(path):
    global TEST_MEDIA_DIRECTORY
    TEST_MEDIA_DIRECTORY = pathlib.Path(path) if path else None


def get_media_directory() -> Path:
    """
    Get the media directory configured in local.yaml.
    """
    global TEST_MEDIA_DIRECTORY
    global MEDIA_DIRECTORY

    if isinstance(TEST_MEDIA_DIRECTORY, pathlib.Path):
        return TEST_MEDIA_DIRECTORY

    if isinstance(MEDIA_DIRECTORY, pathlib.Path):
        return MEDIA_DIRECTORY

    config = get_config()
    media_directory = config['media_directory']
    media_directory = Path(media_directory)
    if not media_directory.is_absolute():
        # Media directory is relative.  Assume that is relative to the project directory.
        media_directory = PROJECT_DIR / media_directory
    MEDIA_DIRECTORY = media_directory.absolute()
    return MEDIA_DIRECTORY


def get_absolute_media_path(path: str) -> Path:
    """
    Get the absolute path of file/directory within the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_absolute_media_path('videos/blender')
    Path('/media/videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    media_directory = get_media_directory()
    if not path:
        raise ValueError(f'Cannot combine empty path with {media_directory}')
    path = media_directory / path
    if not path.exists():
        raise UnknownDirectory(f'path={path}')
    return path


def get_relative_to_media_directory(path: str) -> Path:
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


def minimize_dict(d: dict, keys: Iterable) -> dict:
    """
    Return a new dictionary that contains only the keys provided.
    """
    return {k: d[k] for k in set(keys) & d.keys()}


def make_media_directory(path: str):
    """
    Make a directory relative within the media directory.
    """
    media_dir = get_media_directory()
    path = media_dir / str(path)
    path.mkdir(parents=True)
