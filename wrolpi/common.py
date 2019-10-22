import configparser
import logging
import string
import sys
from typing import Tuple

from dictorm import ResultsGenerator
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger('wrolpi')
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Jinja2 environment
env = Environment(loader=FileSystemLoader('.'))

CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'


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


def create_pagination_dict(offset, limit, more) -> dict:
    """Create the dict that the pagination template needs to build the pagination links."""
    pagination = dict()
    pagination['offset'] = offset
    pagination['limit'] = limit
    pagination['more'] = more

    active_page = (offset // limit) + 1
    pagination['active_page'] = active_page

    links = []
    for sub_offset in range(0, offset + limit, limit):
        link = dict()
        links.append(link)
        link['sub_offset'] = sub_offset
        link['page'] = (sub_offset // limit) + 1
        if link['page'] == active_page:
            link['active'] = True

    links.append({'sub_offset': offset + limit, 'page': 'Next'})
    if not more:
        links[-1]['disabled'] = True

    pagination['links'] = links

    return pagination


def get_pagination(results_gen: ResultsGenerator, offset: int, limit: int = 20) -> Tuple[list, dict]:
    """Offset a results generator and create a pagination dict"""
    results_gen = results_gen.offset(offset)
    results = [i for (i, _) in zip(results_gen, range(limit))]
    try:
        next(results_gen)
        more = True
    except StopIteration:
        more = False

    pagination = create_pagination_dict(offset, limit, more)

    return results, pagination
