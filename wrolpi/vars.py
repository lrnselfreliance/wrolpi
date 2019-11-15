import os
import pathlib

cwd = pathlib.Path(__file__).parent
STATIC_DIR = (cwd.parent / 'static').absolute()
CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'
DOCKERIZED = True if os.environ.get('DOCKER', '').startswith('t') else False
