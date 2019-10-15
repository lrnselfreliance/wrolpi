import os
import pathlib
from functools import partial
from pathlib import Path
from typing import Union, Tuple

import yaml
from dictorm import And, Or

from wrolpi.common import get_db_context, sanitize_link

MY_DIR = Path(__file__).parent
CONFIG_PATH = MY_DIR / 'local.yaml'
EXAMPLE_CONFIG_PATH = MY_DIR / 'example.yaml'
DOWNLOADER_SECTION = 'downloader'
SPECIAL_CONFIG_SECTIONS = ['DEFAULT', DOWNLOADER_SECTION]
REQUIRED_OPTIONS = ['name', 'directory']


def get_config() -> dict:
    with open(CONFIG_PATH, 'rt') as fh:
        config = yaml.load(fh, Loader=yaml.Loader)
    return config


def get_downloader_config() -> dict:
    config = get_config()
    downloader = config[DOWNLOADER_SECTION]
    return downloader


def get_channels_config() -> dict:
    config = get_config()
    download_collection = config['download_collection']
    return download_collection


def save_settings_config(downloader=None):
    """Save the channel settings to the config."""
    config = dict()
    config['downloader'] = downloader or get_downloader_config()
    download_collection = config['download_collection'] = {}

    # Add channel sections
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channels = Channel.get_where().order_by('LOWER(name) ASC')
        for channel in channels:
            section = download_collection[channel['link']] = {}
            section['name'] = channel['name'] or ''
            section['url'] = channel['url'] or ''
            section['directory'] = channel['directory'] or ''
            section['match_regex'] = channel['match_regex'] or ''

    with open(CONFIG_PATH, 'wt') as fh:
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
            conflicting_channels = list(get_conflicting_channels(db, link=link, name_=name))
            Channel = db['channel']
            if not conflicting_channels:
                # Channel added to config, create it in the postgres
                channel = Channel(link=link)
            elif len(conflicting_channels) == 1:
                # Channel already exists, update it
                channel = conflicting_channels[0]
            else:
                raise Exception('Too many channels match this section.')

            # Only name and directory are required
            channel['name'] = config[section]['name']
            channel['directory'] = directory

            channel['url'] = config[section].get('url')
            channel['match_regex'] = config[section].get('match_regex')
            channel.flush()
    return 0


class UnknownDirectory(Exception):
    pass


def resolve_project_path(path: str, mkdir=False) -> Path:
    """Make a best-guess as to a file's location.

    If the path is absolute, return it even if it doesn't exist.
    First, guess that the path is relative to the project directory.
    Second, guess that the path is relative to the video root directory.
    """
    # TODO this function will allow an attacker to check if any directory exists
    if str(path).startswith('/'):
        return Path(path)

    path = Path(path)

    # First, guess that the path is relative to the project directory.
    project_dir = MY_DIR.parents[2]  # WROLPi's top directory
    guess = project_dir / path
    if guess.exists():
        return guess

    # Second, guess that the path is relative to the video root directory.
    config = get_downloader_config()
    video_root_directory = config['video_root_directory']
    guess = Path(video_root_directory) / path
    if guess.exists():
        return guess
    elif mkdir:
        # The path doesn't exist, make it
        os.mkdir(guess)
        return guess

    raise UnknownDirectory(f'Path does not exist: {path}')


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


def get_conflicting_channels(db, id=None, url=None, name_=None, link=None, directory=None):
    """Return all channels that have any of to provided values"""
    if not any([id, url, name_, link, directory]):
        raise Exception('Cannot search for channel with no arguments')

    Channel = db['channel']
    if id:
        conflicting_channels = Channel.get_where(
            And(
                Or(
                    Channel['url'] == url,
                    Channel['name'] == name_,
                    Channel['link'] == link,
                    Channel['directory'] == directory,
                ),
                Channel['id'] != id,
            )
        )
    else:
        conflicting_channels = Channel.get_where(
            Or(
                Channel['url'] == url,
                Channel['name'] == name_,
                Channel['link'] == link,
                Channel['directory'] == directory,
            )
        )
    return list(conflicting_channels)
