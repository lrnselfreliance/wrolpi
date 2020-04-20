import collections
import json
import logging
import os
import queue
import string
from collections import namedtuple
from datetime import datetime, date
from functools import wraps
from multiprocessing import Event, Queue
from pathlib import Path
from typing import Union
from urllib.parse import urlunsplit
from uuid import UUID

import sanic
import yaml
from sanic import Sanic, Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse
from sanic_openapi import doc
from websocket import WebSocket

from api.errors import APIError, API_ERRORS, ValidationError, MissingRequiredField, ExcessJSONFields, NoBodyContents
from api.vars import CONFIG_PATH, EXAMPLE_CONFIG_PATH, PUBLIC_HOST, PUBLIC_PORT, DATE_FORMAT

sanic_app = Sanic()

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def get_loop():
    return sanic.Sanic.loop


URL_CHARS = string.ascii_lowercase + string.digits


def sanitize_link(link: str) -> str:
    """Remove any non-url safe characters, all will be lowercase."""
    new_link = ''.join(i for i in str(link).lower() if i in URL_CHARS)
    return new_link


def string_to_boolean(s: str) -> bool:
    return str(s).lower() in {'true', 't', '1', 'on'}


def boolean_arg(request, arg_name):
    """Return True only if the specified query arg is truthy"""
    value = request.args.get(arg_name)
    return string_to_boolean(value)


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
            except queue.Empty:
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
URL_COMPONENTS = namedtuple('Components', ['scheme', 'netloc', 'path', 'query', 'fragment'])


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
        return int((current / total) * 100)

    return progress_calculator


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
                cause = API_ERRORS[type(e.__cause__)]
                body = {
                    'error': error['message'],
                    'code': error['code'],
                    'cause': {'error': cause['message'], 'code': cause['code']}
                }
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


class FeedReporter:
    """
    I am used to consistently send messages and progress(s) to a Websocket Feed.
    """

    def __init__(self, q: Queue, progress_count: int = 1):
        self.queue: Queue = q
        self.progresses = [{'now': 0, 'total': 0} for _ in range(progress_count)]
        self.calculators = [lambda _: None for _ in range(progress_count)]

    def message(self, msg: str):
        msg = dict(message=msg, progresses=self.progresses)
        self.queue.put(msg)

    def error(self, msg: str):
        msg = dict(code='error', error=msg, progresses=self.progresses)
        self.queue.put(msg)

    def code(self, code: str):
        msg = dict(code=code, progresses=self.progresses)
        self.queue.put(msg)

    def set_progress_total(self, idx: int, total: int):
        self.progresses[idx]['total'] = total
        self.calculators[idx] = make_progress_calculator(total)

    def set_progress(self, idx: int, progress: int, message: str = None):
        self.progresses[idx]['now'] = self.calculators[idx](progress)
        self.queue.put({'progresses': self.progresses, 'message': message})


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
        modified_since = datetime.strptime(modified_since, DATE_FORMAT)
        if last_modified >= modified_since:
            raise FileNotModified()

    last_modified = last_modified.strftime(DATE_FORMAT)
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
        if k in b and k in a and isinstance(b[k], collections.Mapping):
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

    new_config = combine_dicts(config, local_config, example_config)

    with open(str(CONFIG_PATH), 'wt') as fh:
        yaml.dump(new_config, fh)
        # asynchronous


class JSONEncodeDate(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime(DATE_FORMAT)
        elif isinstance(obj, date):
            return obj.strftime(DATE_FORMAT)
        return super(JSONEncodeDate, self).default(obj)


@wraps(response.json)
def json_response(*a, **kwargs) -> HTTPResponse:
    """
    Handles encoding dates/datetimes in JSON.
    """
    return response.json(*a, **kwargs, cls=JSONEncodeDate, dumps=json.dumps)
