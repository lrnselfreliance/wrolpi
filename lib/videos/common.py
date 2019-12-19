import json
import os
import pathlib
import tempfile
from functools import partial
from pathlib import Path
from typing import Union, Tuple

import yaml
from dictorm import Dict, DictDB

from lib.common import sanitize_link, logger
from lib.db import get_db_context
from lib.errors import UnknownFile, UnknownChannel, UnknownDirectory, ChannelNameConflict, ChannelURLConflict, \
    ChannelLinkConflict, ChannelDirectoryConflict
from lib.vars import DOCKERIZED, TEST_VIDEO_PATH

logger = logger.getChild('videos')

MY_DIR: Path = Path(__file__).parent
CONFIG_PATH = MY_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = MY_DIR / 'example.yaml'
REQUIRED_OPTIONS = ['name', 'directory']

VIDEO_QUERY_LIMIT = 20


def get_config() -> dict:
    config_path = CONFIG_PATH if Path(CONFIG_PATH).exists() else EXAMPLE_CONFIG_PATH
    with open(str(config_path), 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return config


def get_downloader_config() -> dict:
    config = get_config()
    downloader = config['downloader']
    return downloader


def get_channels_config() -> dict:
    config = get_config()
    channels = config['channels']
    return channels


def save_settings_config(downloader=None):
    """Save the channel settings to the config."""
    config = dict()
    config['downloader'] = downloader or get_downloader_config()
    config_channels = config['channels'] = {}

    # Add channel sections
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channels = Channel.get_where().order_by('LOWER(name) ASC')
        for channel in channels:
            section = config_channels[channel['link']] = {}
            section['name'] = channel['name'] or ''
            section['url'] = channel['url'] or ''
            section['directory'] = channel['directory'] or ''
            section['match_regex'] = channel['match_regex'] or ''

    with open(str(CONFIG_PATH), 'wt') as fh:
        yaml.dump(config, fh)
    return 0


class ConfigError(Exception):
    pass


def import_settings_config():
    """Import channel settings to the DB.  Existing channels will be updated."""
    config = get_channels_config()

    with get_db_context(commit=True) as (db_conn, db):
        for section in config:
            for option in (o for o in REQUIRED_OPTIONS if o not in config[section]):
                raise ConfigError(f'Channel "{section}" is required to have "{option}"')

            name, directory = config[section]['name'], config[section]['directory']

            link = sanitize_link(name)
            Channel = db['channel']
            channel = Channel.get_one(link=link)

            if not channel:
                # Channel not yet in the DB, add it
                channel = Channel(link=link)

            # Only name and directory are required
            channel['name'] = config[section]['name']
            channel['directory'] = directory

            channel['url'] = config[section].get('url')
            channel['match_regex'] = config[section].get('match_regex')
            channel.flush()
    return 0


def get_video_root() -> Path:
    """
    Get video_root_directory from config.
    """
    config = get_downloader_config()
    video_root_directory = config['video_root_directory']
    video_root_directory = Path(video_root_directory)
    return video_root_directory


def get_absolute_channel_directory(directory: str) -> Path:
    directory = get_video_root() / directory
    if not directory.exists():
        raise UnknownDirectory(f'Channel directory does not exist! {directory}')
    return directory


VALID_VIDEO_KINDS = {'video', 'caption', 'poster', 'description', 'info_json'}


def get_absolute_video_path(video: Dict, kind: str = 'video') -> Path:
    if kind not in VALID_VIDEO_KINDS:
        raise Exception(f'Unknown video path kind {kind}')
    directory = get_absolute_channel_directory(video['channel']['directory'])
    path = video[kind + '_path']
    if directory and path:
        return directory / path
    raise UnknownFile(f'Unknown {kind} for video {video["id"]}')


def get_absolute_video_caption(video: Dict) -> Path:
    return get_absolute_video_path(video, 'caption')


def get_absolute_video_poster(video: Dict) -> Path:
    return get_absolute_video_path(video, 'poster')


def get_absolute_video_description(video: Dict) -> Path:
    return get_absolute_video_path(video, 'description')


def get_absolute_video_info_json(video: Dict) -> Path:
    return get_absolute_video_path(video, 'info_json')


def get_video_description(video: Dict) -> bytes:
    """Get the description text block from a video's description meta-file.  Return an empty string if not possible."""
    try:
        path = get_absolute_video_description(video)
        if path.exists():
            with open(str(path), 'rb') as fh:
                contents = fh.read()
                return contents
    except UnknownFile:
        pass
    return b''


def get_video_info_json(video: Dict) -> dict:
    """Get the info_json object from a video's meta-file.  Return an empty dict if not possible."""
    try:
        path = get_absolute_video_info_json(video)
        if path.exists():
            with open(str(path), 'rb') as fh:
                contents = json.load(fh)
                return contents
    except UnknownFile:
        pass
    return {}


def any_extensions(filename: str, extensions=None):
    """Return True only if a file ends with any of the possible extensions"""
    return any(filename.endswith(ext) for ext in extensions or [])


match_video_extensions = partial(any_extensions, extensions={'mp4', 'webm', 'flv'})


def generate_video_paths(directory: Union[str, pathlib.Path], relative_to=None) -> Tuple[str, pathlib.Path]:
    """
    Generate a list of video paths in the provided directory.
    """
    directory = pathlib.Path(directory)

    for child in directory.iterdir():
        if child.is_file() and match_video_extensions(str(child)):
            child = child.absolute()
            if relative_to:
                yield child.relative_to(relative_to)
            else:
                yield child
        elif child.is_dir():
            yield from generate_video_paths(child)


def check_for_channel_conflicts(db, id=None, url=None, name=None, link=None, directory=None):
    """
    Search for any channels that conflict with the provided args, raise a relevant exception if any conflicts are found.
    """
    if not any([id, url, name, link, directory]):
        raise Exception('Cannot search for channel with no arguments')

    logger.debug(f'Checking for channel conflicts: id={id} url={url} name={name} link={link} directory={directory}')

    Channel = db['channel']
    # A channel can't conflict with itself
    if id:
        base_where = Channel.get_where(Channel['id'] != id)
    else:
        base_where = Channel.get_where()

    if url:
        conflicts = base_where.refine(Channel['url'] == url)
        if list(conflicts):
            raise ChannelURLConflict()
    if name:
        conflicts = base_where.refine(Channel['name'] == name)
        if list(conflicts):
            raise ChannelNameConflict()
    if link:
        conflicts = base_where.refine(Channel['link'] == link)
        if list(conflicts):
            raise ChannelLinkConflict()
    if directory:
        conflicts = base_where.refine(Channel['directory'] == directory)
        if list(conflicts):
            raise ChannelDirectoryConflict()


def verify_config():
    video_root_directory = get_video_root()
    if not video_root_directory.exists() or not video_root_directory.is_absolute():
        if DOCKERIZED:
            raise Exception(f'Video root directory is not absolute, or does not exist! {video_root_directory}  '
                            f'Have you mounted your media directory in docker-compose.yml?')
        raise Exception(f'Video root directory is not absolute, or does not exist! {video_root_directory}  '
                        f'Have you updated your local.yaml with the video_root_directory?')


def get_channel_videos(db: DictDB, link: str, offset: int = 0):
    Channel, Video = db['channel'], db['video']
    channel = Channel.get_one(link=link)
    if not channel:
        raise UnknownChannel('Unknown Channel')
    total = len(Video.get_where(channel_id=channel['id']))
    videos = Video.get_where(channel_id=channel['id']).order_by(
        'upload_date DESC, LOWER(title) ASC, LOWER(video_path) ASC').limit(VIDEO_QUERY_LIMIT).offset(offset)
    return videos, total


class TemporaryVideo:
    """
    Contextmanager that creates a real mp4 file that contains 1000 bytes of sample video data.
    """

    def __init__(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        self.name = self.temp_file.name
        with open(str(TEST_VIDEO_PATH), 'rb') as fh1, open(self.name, 'wb') as fh2:
            fh2.write(fh1.read(1000))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Always remove the temp file
        self.temp_file.close()
        os.remove(self.name)

    def __str__(self):
        return self.name
