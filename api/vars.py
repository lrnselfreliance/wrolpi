import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1]
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
CONFIG_PATH = PROJECT_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = PROJECT_DIR / 'example.yaml'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%D'
MINIMUM_CHANNEL_KEYS = {'id', 'name', 'directory', 'url', 'video_count', 'link'}
MINIMUM_INFO_JSON_KEYS = {'description'}
MINIMUM_VIDEO_KEYS = {'id', 'title', 'upload_date', 'duration', 'channel', 'channel_id', 'favorite', 'size',
                      'poster_path', 'caption_path', 'video_path', 'info_json', 'channel', 'viewed'}
DEFAULT_DOWNLOAD_FREQUENCY = 60 * 60 * 24 * 7  # weekly

# These are the supported video formats.  These are in order of their preference.
VIDEO_EXTENSIONS = ('mp4', 'ogg', 'webm', 'flv')

UNRECOVERABLE_ERRORS = {
    '404: Not Found',
    'requires payment',
    'Content Warning',
    'Did not get any data blocks',
}
