import os
import pathlib

PROJECT_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent
EXAMPLE_VIDEOS_DIR: pathlib.Path = PROJECT_DIR / 'test/example_videos'
TEMPLATES_DIR: pathlib.Path = (PROJECT_DIR / 'templates').absolute()
DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

TEST_VIDEO_PATH = EXAMPLE_VIDEOS_DIR / 'blender/big_buck_bunny_720p_1mb.mp4'
