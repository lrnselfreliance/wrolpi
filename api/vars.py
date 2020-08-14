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

# These are the supported video formats.  These are in order of their preference.
VIDEO_EXTENSIONS = ('mp4', 'ogg', 'webm', 'flv')
