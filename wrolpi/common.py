import configparser
import logging
import string
import sys
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import Tuple

import sanic
from attr import dataclass
from dictorm import ResultsGenerator
from jinja2 import Environment, FileSystemLoader
from marshmallow import Schema, ValidationError
from sanic import Sanic
from sanic.exceptions import abort, InvalidUsage
from sanic.request import Request

from wrolpi.vars import CONFIG_PATH, WROLPI_CONFIG_SECTION, PROJECT_DIR

sanic_app = Sanic()

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Jinja2 environment
env = Environment(loader=FileSystemLoader(str(PROJECT_DIR.absolute())))


def get_loop():
    return sanic.Sanic.loop


def get_wrolpi_config():
    config = configparser.RawConfigParser()
    config.read(CONFIG_PATH)
    try:
        return config[WROLPI_CONFIG_SECTION]
    except KeyError:
        logger.fatal('Cannot load WROLPi.cfg config!')
        sys.exit(1)


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
        -> Tuple[list, dict]:
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


ls_logger = logger.getChild('load_schema')


def load_schema(schema: Schema):
    """Load JSON data from Sanic Request into the provided Schema"""

    def _load_schema(func):
        @wraps(func)
        def wrapped(request: Request, *a, **kw):
            try:
                # TODO do this intelligently
                raw_data = request.json
                ls_logger.debug(f'request json: {request.json}')
            except InvalidUsage:
                raw_data = request.form
                ls_logger.debug(f'request form: {request.form}')

            try:
                data = schema.load(raw_data)
            except ValidationError as e:
                abort(HTTPStatus.BAD_REQUEST, str(e))

            response = func(request, *a, **kw, data=data)
            return response

        return wrapped

    return _load_schema
