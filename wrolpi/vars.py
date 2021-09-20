import os
import pathlib
from pathlib import Path

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1].absolute()
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
CONFIG_DIR = PROJECT_DIR / 'config'
CONFIG_PATH = CONFIG_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = CONFIG_DIR / 'example.yaml'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')
MODULES_DIR: Path = PROJECT_DIR / 'modules'

DEFAULT_TIMEZONE_STR = 'America/Boise'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

DEFAULT_FILE_PERMISSIONS = 0o644
