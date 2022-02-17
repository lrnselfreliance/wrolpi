import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# The root of WROLPi.  Typically, /opt/wrolpi
PROJECT_DIR: Path = Path(__file__).parents[1].absolute()

# Load any .env file.  This may contain our MEDIA_DIRECTORY.
load_dotenv(PROJECT_DIR / '.env')

# Special environment variable set in the docker/api/Dockerfile.
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
# tests are running
PYTEST = 'pytest' in sys.modules

# Get the media directory from the environment.
DEFAULT_MEDIA_DIRECTORY = Path('/media/wrolpi')
MEDIA_DIRECTORY = Path(os.environ.get('MEDIA_DIRECTORY', DEFAULT_MEDIA_DIRECTORY))
if not MEDIA_DIRECTORY.is_dir() and not PYTEST:
    print(f'Media directory does not exist!  {MEDIA_DIRECTORY}')

CONFIG_DIR: Path = MEDIA_DIRECTORY / 'config'
MODULES_DIR: Path = PROJECT_DIR / 'modules'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

DEFAULT_TIMEZONE_STR = 'America/Boise'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATETIME_FORMAT_MS = '%Y-%m-%d %H:%M:%S.%f'
DEFAULT_CPU_FREQUENCY = 'ondemand'

DEFAULT_FILE_PERMISSIONS = 0o644

DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('DB_PORT', 5432))
DB_NAME = os.environ.get('DB_NAME', 'wrolpi')
DB_USER = os.environ.get('DB_USER', 'wrolpi')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'wrolpi')

EXAMPLE_CONFIG = {
    'hotspot_on_startup': True,
    'throttle_on_startup': False,
    'timezone': 'America/Boise',
    'wrol_mode': False,
}
