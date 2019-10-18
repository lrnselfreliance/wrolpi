import configparser
import logging
import string
import sys

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
