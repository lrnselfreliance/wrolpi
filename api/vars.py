import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1]
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
CONFIG_DIR = PROJECT_DIR / 'config'
CONFIG_PATH = CONFIG_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = CONFIG_DIR / 'example.yaml'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

DEFAULT_TIMEZONE_STR = 'US/Mountain'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
MINIMUM_CHANNEL_KEYS = {'id', 'name', 'directory', 'url', 'video_count', 'link'}
MINIMUM_INFO_JSON_KEYS = {'description'}
MINIMUM_VIDEO_KEYS = {'id', 'title', 'upload_date', 'duration', 'channel', 'channel_id', 'favorite', 'size',
                      'poster_path', 'caption_path', 'video_path', 'info_json', 'channel', 'viewed', 'source_id'}
DEFAULT_DOWNLOAD_FREQUENCY = 60 * 60 * 24 * 7  # weekly
DEFAULT_DOWNLOAD_TIMEOUT = 60.0 * 10.0  # Ten minutes

# These are the supported video formats.  These are in order of their preference.
VIDEO_EXTENSIONS = ('mp4', 'ogg', 'webm', 'flv')

UNRECOVERABLE_ERRORS = {
    '404: Not Found',
    'requires payment',
    'Content Warning',
    'Did not get any data blocks',
    'Sign in to confirm your age',
    'This live stream recording is not available.',
    'members-only content',
}

DEFAULT_FILE_PERMISSIONS = 0o644
