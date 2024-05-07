import multiprocessing
import os
import pathlib
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
# running on circlci
CIRCLECI = os.environ.get('CIRCLECI', '').strip().lower() == 'true'


def truthy_arg(value: str) -> bool:
    """Attempts to convert `value` from console arguments to a boolean value.

    >>> truthy_arg('true')
    True
    >>> truthy_arg('True')
    True
    >>> truthy_arg('t')
    True
    >>> truthy_arg('1')
    True
    >>> truthy_arg('yes')
    True
    >>> truthy_arg('0')
    False
    >>> truthy_arg('false')
    False
    >>> truthy_arg('f')
    False
    >>> truthy_arg('no')
    False
    """
    v = str(value).lower()
    return v == 'true' or v == 't' or v == '1' or v == 'yes' or v == 'y'


# Get the media directory from the environment.
DEFAULT_MEDIA_DIRECTORY = Path('/media/wrolpi')
MEDIA_DIRECTORY = Path(os.environ.get('MEDIA_DIRECTORY', DEFAULT_MEDIA_DIRECTORY))

CONFIG_DIR: Path = MEDIA_DIRECTORY / 'config'
MODULES_DIR: Path = PROJECT_DIR / 'modules'

DEFAULT_TIMEZONE_STR = 'America/Boise'
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

API_HOST = os.environ.get('API_HOST', '127.0.0.1')
API_PORT = os.environ.get('API_PORT', '8081')
API_WORKERS = os.environ.get('API_WORKERS', multiprocessing.cpu_count())
API_AUTO_RELOAD = truthy_arg(os.environ.get('API_AUTO_RELOAD', DOCKERIZED))
API_ACCESS_LOG = truthy_arg(os.environ.get('API_ACCESS_LOG', DOCKERIZED))
API_DEBUG = truthy_arg(os.environ.get('API_DEBUG', False))

FILE_REFRESH_CHUNK_SIZE = int(os.environ.get('FILE_CHUNK_SIZE', 100))
FILE_MAX_PDF_SIZE = int(os.environ.get('FILE_MAX_PDF_SIZE', 40_000_000))
FILE_MAX_TEXT_SIZE = int(os.environ.get('FILE_MAX_TEXT_SIZE', 100_000))

VIDEO_COMMENTS_FETCH_COUNT = int(os.environ.get('VIDEO_COMMENTS_FETCH_COUNT', 80))
YTDLP_CACHE_DIR = os.environ.get('YTDLP_CACHE_DIR', '/tmp/ytdlp_cache')

DEFAULT_HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116 Safari/537.36',
}

RPI_DEVICE_PATH = pathlib.Path('/proc/device-tree/model')
RPI_DEVICE_MODEL_CONTENTS = RPI_DEVICE_PATH.read_text() if RPI_DEVICE_PATH.is_file() else None
IS_RPI4 = 'Raspberry Pi 4' in RPI_DEVICE_MODEL_CONTENTS if RPI_DEVICE_MODEL_CONTENTS else False
IS_RPI5 = 'Raspberry Pi 5' in RPI_DEVICE_MODEL_CONTENTS if RPI_DEVICE_MODEL_CONTENTS else False
IS_RPI = IS_RPI4 or IS_RPI5

SIMULTANEOUS_DOWNLOAD_DOMAINS = int(os.environ.get('SIMULTANEOUS_DOWNLOAD_DOMAINS', 4))
