import json
import logging
import queue
import string
import subprocess
from collections import namedtuple
from functools import wraps
from http import HTTPStatus
from multiprocessing import Event, Queue
from typing import Tuple
from urllib.parse import urlunsplit
from uuid import UUID

import sanic
from attr import dataclass
from dictorm import ResultsGenerator
from sanic import Sanic, Blueprint, response
from sanic.request import Request
from sanic_openapi import doc
from websocket import WebSocket

sanic_app = Sanic()

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def get_loop():
    return sanic.Sanic.loop


def setup_relationships(db):
    """Assign all relationships between DictORM Tables."""
    Channel = db['channel']
    Video = db['video']
    Channel['videos'] = Channel['id'].many(Video['channel_id'])
    Video['channel'] = Video['channel_id'] == Channel['id']


URL_CHARS = string.ascii_lowercase + string.digits


def sanitize_link(link: str) -> str:
    """Remove any non-url safe characters, all will be lowercase."""
    new_link = ''.join(i for i in str(link).lower() if i in URL_CHARS)
    return new_link


MAX_LINKS = 9


def create_pagination_pages(current_page, last_page, padding=MAX_LINKS):
    """Create a list of page numbers.  The current page should have an equal amount of padding pages on each side of it.
    If the padding pages would overflow (< 1 or > last_page), pad the opposite side.  Always include first and last
    page.  Insert '..' when page numbers are skipped.

        Examples:
            >>> create_pagination_pages(9, 20, padding=9)
            [1, '..', 5, 6, 7, 8, 9, 10, 11, 12, 13, '..', 20]
            ^     ^               ^                  ^     ^-- last page
            |     |               |- current page    |
            |     |                                  |
            |     |----------------------------------+---- padding on both sides
            |
            |-------- 1 is always included

            >>> create_pagination_pages(1, 5, padding=9)
            [1, 2, 3, 4, 5]
            >>> create_pagination_dict(1, 12, padding=9)
            [1, 2, 3, 4, 5, 6, 7, 8, 9, '..', 12]
    """
    pages = [current_page, ]
    while len(pages) < min(padding, last_page):
        # Add to the front and back of the pages list only when we haven't overflowed
        if pages[0] > 1:
            pages.insert(0, pages[0] - 1)
        if pages[-1] < last_page:
            pages.append(pages[-1] + 1)
    # Always include the first and last pages
    if pages[-1] != last_page:
        pages.append(last_page)
    if pages[0] != 1:
        pages.insert(0, 1)

    # Insert skips if numbers were skipped if the list is long enough
    if len(pages) > 2 and pages[1] != 2:
        pages.insert(1, '..')
    if len(pages) > 2 and pages[-1] - pages[-2] > 1:
        pages.insert(-1, '..')
    return pages


@dataclass(order=True)
class Pagination:
    offset: int
    limit: int
    more: bool
    total: int
    active_page: int
    links: list


def create_pagination_dict(offset, limit, more=None, total=None) -> Pagination:
    """Create the dict that the pagination template needs to build the pagination links."""
    current_page = (offset // limit) + 1
    links = []
    pagination = Pagination(offset, limit, more, total, current_page, links)

    if total:
        last_page = (total // limit) + 1
    elif more is not None:
        last_page = ((offset + limit) // limit) + 1
    else:
        raise Exception('Cannot generate pagination without at least `more` or `total`.')

    pages = create_pagination_pages(current_page, last_page, MAX_LINKS)
    for page in pages:
        if isinstance(page, int):
            sub_offset = int(page * limit) - limit
            links.append({'sub_offset': sub_offset, 'page': page})
        else:
            links.append({'disabled': True, 'page': page})
        if current_page == page:
            links[-1]['active'] = True

    if more is False:
        del links[-1]

    return pagination


def get_pagination_with_generator(results_gen: ResultsGenerator, offset: int, limit: int = 20, total=None) \
        -> Tuple[list, Pagination]:
    """Offset a results generator and create a pagination dict"""
    results_gen = results_gen.offset(offset)
    results = [i for (i, _) in zip(results_gen, range(limit))]
    more = None
    if not total:
        try:
            next(results_gen)
            more = True
        except StopIteration:
            more = False

    pagination = create_pagination_dict(offset, limit, more, total)

    return results, pagination


def boolean_arg(request, arg_name):
    """Return True only if the specified query arg is equal to 'true'"""
    value = request.args.get(arg_name)
    return value == 'true'


def get_http_file_info(url):
    """Call a wget subprocess to get information about a file"""
    size = None
    filename = str(url).rfind('/')[-1]
    proc = subprocess.run(['/usr/bin/wget', '--spider', '--timeout=10', url], stdin=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    stderr = proc.stderr
    for line in stderr.split(b'\n'):
        if line.startswith(b'Length:'):
            line = line.decode()
            size = line.partition('Length: ')[2].split(' ')[0]
            return size, filename
        # TODO get content-disposition for filename
        # TODO handle non-zero exits
    else:
        raise LookupError(f'Unable to get length of {url}')


async def download_file(url: str, size: int, destination: str):
    pass


DEFAULT_QUEUE_SIZE = 1000


def attach_websocket_with_queue(uri: str, blueprint: Blueprint, maxsize: int = DEFAULT_QUEUE_SIZE):
    """
    Build the objects needed to run a websocket which will pass on messages from a multiprocessing.Queue.

    :param uri: the Sanic URI that the websocket will listen on
    :param blueprint: the Sanic Blueprint to attach the websocket to
    :param maxsize: the maximum size of the Queue
    :return:
    """
    q = Queue(maxsize=maxsize)
    event = Event()

    @blueprint.websocket(uri)
    async def local_websocket(_: Request, ws: WebSocket):
        while q.qsize() or event.is_set():
            # Pass along messages from the queue until its empty, or the event is cleared.  Give up after 1 second so
            # the worker can take another request.
            try:
                msg = q.get(timeout=1)
            except queue.Empty:
                # No more messages
                break
            dump = json.dumps(msg)
            await ws.send(dump)

        # No messages left, stream is complete
        await ws.send(json.dumps({'message': 'stream-complete'}))

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
    components = URL_COMPONENTS(scheme=scheme, netloc=f'{SANIC_HOST}:{SANIC_PORT}', path=path,
                                query=query, fragment=fragment)
    unparsed = str(urlunsplit(components))
    return unparsed


def make_progress_calculator(total):
    """
    Create a function that calculates the percentage of completion.
    """

    def progress_calculator(current):
        return int((current / total) * 100)

    return progress_calculator


def validate_data(model, data):
    new_data = {}
    # Get the public attributes of the model
    attrs = [i for i in dir(model) if not str(i).startswith('__')]
    # Convert each json value to it's respective doc field's python type
    #  i.e. doc.String -> str
    error = None
    for attr in attrs:
        field = getattr(model, attr)
        if isinstance(field, doc.String):
            new_data[attr] = str(data.pop(attr))
        elif isinstance(field, doc.Integer):
            new_data[attr] = int(data.pop(attr))
        elif isinstance(field, doc.Tuple):
            new_data[attr] = tuple(data.pop(attr))
        elif isinstance(field, doc.UUID):
            new_data[attr] = UUID(data.pop(attr))
        elif isinstance(field, doc.Boolean):
            new_data[attr] = bool(data.pop(attr))
        elif isinstance(field, doc.Float):
            new_data[attr] = float(data.pop(attr))
        elif isinstance(field, doc.Dictionary):
            new_data[attr] = dict(data.pop(attr))
        elif isinstance(field, doc.List):
            new_data[attr] = list(data.pop(attr))
        else:
            error = {'error': 'Invalid field type', 'field': attr}

    if data:
        # Excess JSON keys
        error = {'error': 'Excess JSON keys', 'keys': [data.keys()]}

    if not error:
        return new_data
    return response.json(error, HTTPStatus.BAD_REQUEST)


def validate_doc(summary: str = None, consumes=None, produces=None, responses=(), tag: str = None):
    """
    Apply Sanic OpenAPI docs to the wrapped route.  Perform simple validation on requests.
    """

    def wrapper(func):
        @wraps(func)
        def wrapped(request, *a, **kw):
            if consumes:
                data = validate_data(consumes, request.json)
                if isinstance(data, sanic.response.HTTPResponse):
                    # Error in validation
                    return data
                return func(request, data, *a, **kw)
            return func(request, *a, **kw)

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
