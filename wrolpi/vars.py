import os
import pathlib
import sys

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1].absolute()
CONFIG_DIR: pathlib.Path = PROJECT_DIR / 'config'
CONFIG_PATH: pathlib.Path = CONFIG_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH: pathlib.Path = CONFIG_DIR / 'example.yaml'
MODULES_DIR: pathlib.Path = PROJECT_DIR / 'modules'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
# tests are running
PYTEST = 'pytest' in sys.modules

DEFAULT_TIMEZONE_STR = 'America/Boise'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATETIME_FORMAT_MS = '%Y-%m-%d %H:%M:%S.%f'

DEFAULT_FILE_PERMISSIONS = 0o644

DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('DB_PORT', 5432))
DB_NAME = os.environ.get('DB_NAME', 'wrolpi')
DB_USER = os.environ.get('DB_USER', 'wrolpi')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'wrolpi')
