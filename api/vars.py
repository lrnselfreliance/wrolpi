import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parents[1]
EXAMPLE_VIDEOS_DIR: pathlib.Path = PROJECT_DIR / 'test/example_videos'
TEMPLATES_DIR: pathlib.Path = (PROJECT_DIR / 'templates').absolute()
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
CONFIG_PATH = PROJECT_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = PROJECT_DIR / 'example.yaml'
PUBLIC_HOST = os.environ.get('PUBLIC_HOST')
PUBLIC_PORT = os.environ.get('PUBLIC_PORT')

TEST_VIDEO_PATH = EXAMPLE_VIDEOS_DIR / 'blender/big_buck_bunny_720p_1mb.mp4'
LAST_MODIFIED_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
DATE_FORMAT = '%Y-%M-%D'
