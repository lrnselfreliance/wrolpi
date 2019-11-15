import os

CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'
DOCKERIZED = True if os.environ.get('DOCKER', '').startswith('t') else False
