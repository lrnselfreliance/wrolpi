import asyncio
import collections
import inspect
import json
import logging
import os
import queue
import string
from copy import deepcopy
from datetime import datetime, date
from functools import wraps
from multiprocessing import Event, Queue
from pathlib import Path
from typing import Union, Callable, Tuple, Dict, Mapping, List
from urllib.parse import urlunsplit
from uuid import UUID

import sanic
import yaml
from cachetools import cached, TTLCache
from sanic import Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse
from sanic_openapi import doc
from sanic_openapi.doc import Field
from websocket import WebSocket

from api.errors import APIError, API_ERRORS, ValidationError, MissingRequiredField, ExcessJSONFields, NoBodyContents, \
    WROLModeEnabled
from api.vars import CONFIG_PATH, EXAMPLE_CONFIG_PATH, PUBLIC_HOST, PUBLIC_PORT, LAST_MODIFIED_DATE_FORMAT

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

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
    event = Event()
    EVENTS.append((name, event))

    @blueprint.websocket(uri)
    async def local_websocket(_: Request, ws: WebSocket):
        feed_logger.info(f'client connected to {ws}')
        feed_logger.debug(f'event.is_set: {event.is_set()}')
        any_messages = False
        while q.qsize() or event.is_set():
            # Pass along messages from the queue until its empty, or the event is cleared.  Give up after 1 second so
            # the worker can take another request.
            try:
                msg = q.get(timeout=QUEUE_TIMEOUT)
                any_messages = True
                feed_logger.debug(f'got message {msg}')
                dump = json.dumps(msg)
                await ws.send(dump)

                # yield back to the event loop
                await asyncio.sleep(0)
            except queue.Empty:  # pragma: no cover
                # No messages yet, try again while event is set
                feed_logger.debug(f'no messages in queue')
                pass
        feed_logger.debug(f'loop complete')

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


def validate_data(model: type, data: dict):
    """
    Convert a JSON object to the model's specification.  If the JSON object matches the model's specification, this
    function will return a python dict of that data.  If it doesn't match, this will return a Sanic response object
    containing an error.
    """
    if not data:
        raise NoBodyContents()

    new_data = {}
    # Get the public attributes of the model
    attrs = [i for i in dir(model) if not str(i).startswith('__')]
    # Convert each json value to it's respective doc field's python type
    #  i.e. "json value" -> doc.String -> str
    missing_fields = []
    for attr in attrs:
        field = getattr(model, attr)
        try:
            if isinstance(field, doc.String):
                new_data[attr] = str(data.pop(attr))
            elif isinstance(field, doc.Integer):
                new_data[attr] = int(data.pop(attr))
            elif isinstance(field, doc.Tuple):
                new_data[attr] = tuple(data.pop(attr))
            elif isinstance(field, doc.UUID):
                new_data[attr] = UUID(data.pop(attr))
            elif isinstance(field, doc.Boolean):
                new_data[attr] = string_to_boolean(data.pop(attr))
            elif isinstance(field, doc.Float):
                new_data[attr] = float(data.pop(attr))
            elif isinstance(field, doc.Dictionary):
                new_data[attr] = dict(data.pop(attr))
            elif isinstance(field, doc.List):
                new_data[attr] = list(data.pop(attr))
            elif isinstance(field, Trinary):
                val = data.pop(attr)
                if val is not None:
                    val = string_to_boolean(val)
                new_data[attr] = val
            else:
                raise ValidationError(f'Bad field type {field} specified in the API model!')
        except KeyError:
            if field.required:
                missing_fields.append(attr)

    if missing_fields:
        raise MissingRequiredField(f'Missing fields: {missing_fields}')

    if data:
        raise ExcessJSONFields(f'Extra fields: {data.keys()}')

    return new_data


def validate_doc(summary: str = None, consumes=None, produces=None, responses=(), tag: str = None):
    """
    Apply Sanic OpenAPI docs to the wrapped route.  Perform simple validation on requests.
    """

    def wrapper(func):
        @wraps(func)
        def wrapped(request, *a, **kw):
            try:
                if consumes:
                    if 'data' in kw:
                        raise OverflowError(f'data kwarg already being passed to {func}')

                    data = validate_data(consumes, request.json)
                    if isinstance(data, sanic.response.HTTPResponse):
                        # Error in validation
                        return data
                    result = func(request, *a, **kw, data=data)
                    return result
                return func(request, *a, **kw)
            except ValidationError as e:
                error = API_ERRORS[type(e)]
                body = {
                    'error': error['message'],
                    'code': error['code'],
                }

                if e.__cause__:
                    cause = e.__cause__
                    cause = API_ERRORS[type(cause)] if cause else None
                    body['cause'] = {'error': cause['message'], 'code': cause['code']}

                r = response.json(body, error['status'])
                return r
            except APIError as e:
                # The endpoint returned a standardized APIError, convert it to a json response
                error = API_ERRORS[type(e)]
                r = response.json({'error': error['message'], 'code': error['code']}, error['status'])
                return r

        # Apply the docs to the wrapped function so sanic-openapi can find the wrapped function when
        # building the schema.  If these docs are applied to `func`, sanic-openapi won't be able to lookup `wrapped`
        if summary:
            wrapped = doc.summary(summary)(wrapped)
        if consumes:
            wrapped = doc.consumes(consumes, location='body')(wrapped)
        if produces:
            wrapped = doc.produces(produces)(wrapped)
        for resp in responses:
            wrapped = doc.response(*resp)(wrapped)
        if tag:
            wrapped = doc.tag(tag)(wrapped)

        return wrapped

    return wrapper


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

    logger.debug(f'Writing config to file: {CONFIG_PATH}')
    with open(str(CONFIG_PATH), 'wt') as fh:
        yaml.dump(new_config, fh)


class JSONEncodeDate(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.timestamp()
        elif isinstance(obj, date):
            return datetime(obj.year, obj.month, obj.day).timestamp()
        return super(JSONEncodeDate, self).default(obj)


@wraps(response.json)
def json_response(*a, **kwargs) -> HTTPResponse:
    """
    Handles encoding dates/datetimes in JSON.
    """
    return response.json(*a, **kwargs, cls=JSONEncodeDate, dumps=json.dumps)


def today():
    """Return today's date."""
    return datetime.now().date()


class Trinary(Field):
    """
    A field for API docs.  Can be True/False/None.
    """

    def __init__(self, *a, **kw):
        kw['choices'] = (True, False, None)
        super().__init__(*a, **kw)

    def serialize(self):
        return {"type": "trinary", **super().serialize()}


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


def date_range(start: datetime, end: datetime, steps: int) -> List[datetime]:
    delta = (end - start) // steps
    return [start + (delta * i) for i in range(steps)]
