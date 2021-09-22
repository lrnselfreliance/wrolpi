import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1].absolute()
CONFIG_DIR: pathlib.Path = PROJECT_DIR / 'config'
CONFIG_PATH: pathlib.Path = CONFIG_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH: pathlib.Path = CONFIG_DIR / 'example.yaml'
MODULES_DIR: pathlib.Path = PROJECT_DIR / 'modules'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

DEFAULT_TIMEZONE_STR = 'America/Boise'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATETIME_FORMAT_MS = '%Y-%m-%d %H:%M:%S.%f'

DEFAULT_FILE_PERMISSIONS = 0o644
