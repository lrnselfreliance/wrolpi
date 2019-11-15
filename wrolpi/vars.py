import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent
STATIC_DIR: pathlib.Path = (PROJECT_DIR / 'static').absolute()
TEMPLATES_DIR: pathlib.Path = (PROJECT_DIR / 'templates').absolute()
CONFIG_PATH = 'config.cfg'
WROLPI_CONFIG_SECTION = 'WROLPi'
DOCKERIZED = True if os.environ.get('DOCKER', '').startswith('t') else False
