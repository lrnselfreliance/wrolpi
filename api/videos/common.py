import json
import os
import pathlib
import subprocess
from datetime import datetime
from functools import partial, lru_cache
from pathlib import Path
from typing import Union, Tuple, List, Optional, Set, Iterable

from dictorm import Dict, DictDB

from api.common import sanitize_link, logger, CONFIG_PATH, get_config, iterify
from api.db import get_db_context
from api.errors import UnknownFile, UnknownChannel, UnknownDirectory, ChannelNameConflict, ChannelURLConflict, \
    ChannelLinkConflict, ChannelDirectoryConflict
from api.vars import DOCKERIZED, PROJECT_DIR, VIDEO_EXTENSIONS

logger = logger.getChild(__name__)

REQUIRED_OPTIONS = ['name', 'directory']

VIDEO_QUERY_LIMIT = 20
VIDEO_QUERY_MAX_LIMIT = 100


def get_downloader_config() -> dict:
    config = get_config()
    downloader = config['downloader']
    return downloader


def get_channels_config() -> dict:
    config = get_config()
    channels = config['channels']
    return channels


def get_allowed_limit(limit: int) -> int:
    """
    Return the video limit int if it was passed, unless it is over the maximum limit.  If no limit is provided, return
    the default limit.
    """
    if limit:
        return min(int(limit), VIDEO_QUERY_MAX_LIMIT)
    return VIDEO_QUERY_LIMIT


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


@lru_cache(maxsize=1)
def get_media_directory() -> Path:
    """
    Get the media directory configured in local.yaml.
    """
    config = get_config()
    media_directory = config['media_directory']
    media_directory = Path(media_directory)
    if media_directory.is_absolute():
        return media_directory.absolute()
    media_directory = PROJECT_DIR / media_directory
    media_directory = media_directory.absolute()
    return media_directory


def get_absolute_media_path(path: str) -> Path:
    """
    Get the absolute path of file/directory within the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_absolute_media_path('videos/blender')
    Path('/media/videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    media_directory = get_media_directory()
    if not path:
        raise ValueError(f'Cannot combine empty path with {media_directory}')
    path = media_directory / path
    if not path.exists():
        raise UnknownDirectory(f'path={path}')
    return path


def get_relative_to_media_directory(path: str) -> Path:
    """
    Get the path for a file/directory relative to the config media directory.

    >>> get_media_directory()
    Path('/media')
    >>> get_relative_to_media_directory('/media/videos/blender')
    Path('videos/blender')

    :raises UnknownDirectory: the directory/path doesn't exist
    """
    absolute = get_absolute_media_path(path)
    return absolute.relative_to(get_media_directory())


VALID_VIDEO_KINDS = {'video', 'caption', 'poster', 'description', 'info_json'}


def get_absolute_video_path(video: Dict, kind: str = 'video') -> Path:
    if kind not in VALID_VIDEO_KINDS:
        raise Exception(f'Unknown video path kind {kind}')
    directory = get_absolute_media_path(video['channel']['directory'])
    path = video[kind + '_path']
    if directory and path:
        return directory / path
    raise UnknownFile()


get_absolute_video_caption = partial(get_absolute_video_path, kind='caption')
get_absolute_video_poster = partial(get_absolute_video_path, kind='poster')
get_absolute_video_description = partial(get_absolute_video_path, kind='description')
get_absolute_video_info_json = partial(get_absolute_video_path, kind='info_json')


def get_absolute_video_files(video: Dict) -> List[Path]:
    """
    Get all video files that exist.
    """
    getters = [
        get_absolute_video_description,
        get_absolute_video_caption,
        get_absolute_video_poster,
        get_absolute_video_info_json,
        get_absolute_video_path,
    ]

    def _get():
        for getter in getters:
            try:
                yield getter(video)
            except UnknownFile:
                pass

    return list(_get())


def get_video_info_json(video: Dict) -> Union[dict, None]:
    """Get the info_json object from a video's meta-file.  Return an empty dict if not possible."""
    if not video['channel']['directory']:
        return

    try:
        path = get_absolute_video_info_json(video)
        if path.exists():
            with open(str(path), 'rb') as fh:
                contents = json.load(fh)
                return contents
    except UnknownFile:
        return
    except UnknownDirectory:
        return


def any_extensions(filename: str, extensions: Iterable = ()):
    """
    Return True only if the file name ends with any of the possible extensions.
    Matches lower or upper case of the extension.
    """
    return any(filename.lower().endswith(ext) for ext in extensions)


match_video_extensions = partial(any_extensions, extensions=VIDEO_EXTENSIONS)


def generate_video_paths(directory: Union[str, pathlib.Path], relative_to=None) -> Tuple[str, pathlib.Path]:
    """
    Generate a list of video paths in the provided directory.
    """
    directory = pathlib.Path(directory)

    for child in directory.iterdir():
        if child.is_file() and match_video_extensions(child.name):
            child = child.absolute()
            if relative_to:
                yield child.relative_to(relative_to)
            else:
                yield child
        elif child.is_dir():
            yield from generate_video_paths(child)


@iterify(set)
def remove_duplicate_video_paths(paths: Iterable[Path]) -> Set[Path]:
    """
    Remove any duplicate paths from a given list.  Duplicate is defined as any file that shares the EXACT same
    name as another file, but with a different extension.  If a duplicate is found, only yield one of the paths.  The
    path that will be yielded will be whichever is first in the VIDEO_EXTESIONS tuple.

    i.e.
    >>> remove_duplicate_video_paths([Path('one.mp4'), Path('two.mp4'), Path('one.ogg')])
    {'one.mp4, 'two.mp4'}
    """
    new_paths = {}

    # Group all paths by their name, but without their extension.
    for path in set(paths):
        name, _, _ = path.name.rpartition(path.suffix)
        try:
            new_paths[name].append(path)
        except KeyError:
            new_paths[name] = [path]

    # Yield back the first occurrence of the preferred format for each video.
    for name, paths in new_paths.items():
        if len(paths) == 1:
            # This should be the most common case.  Most videos will only have one format.
            yield paths[0]
        else:
            path_strings = [i.name for i in paths]
            for ext in VIDEO_EXTENSIONS:
                try:
                    index = path_strings.index(f'{name}.{ext}')
                    yield paths[index]
                    break
                except ValueError:
                    # That extension is not in the paths.
                    pass
            else:
                # Somehow no format was found, yield back the first one.  This is probably caused by an unexpected video
                # format in the paths.
                yield paths[0]


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
    """
    Check that the local.yaml config file exists.  Check some basic expectations about it's structure.
    """
    if not pathlib.Path(CONFIG_PATH).exists():
        raise Exception(f'local.yaml does not exist, looked here: {CONFIG_PATH}')

    media_directory = get_media_directory()
    error = None
    if not media_directory.is_absolute():
        error = f'Media directory is not absolute! {media_directory}  '
    elif not media_directory.exists():
        error = f'Media directory does not exist! {media_directory}  '

    if error and DOCKERIZED:
        error += 'Have you mounted your media directory in docker-compose.yml?'
    elif error:
        error += 'Have you updated your local.yaml with the media_directory?'

    if error:
        raise Exception(error)


def get_channel_videos(db: DictDB, link: str, offset: int = 0, limit: int = 0) -> Tuple[List[Dict], int]:
    """
    Get all video objects for a particular channel that have a video file.  Also get the total videos that match this
    criteria.
    """
    Channel, Video = db['channel'], db['video']
    channel = Channel.get_one(link=link)
    if not channel:
        raise UnknownChannel('Unknown Channel')

    videos = Video.get_where(channel_id=channel['id']).refine(
        Video['video_path'].IsNotNull())
    total = len(videos)

    videos = videos.order_by(
        'upload_date DESC, LOWER(title) ASC, LOWER(video_path) ASC').limit(limit).offset(offset)

    return videos, total


def get_matching_directories(path: Union[str, Path]) -> List[str]:
    """
    Return a list of directory strings that start with the provided path.  If the path is a directory, return it's
    subdirectories, if the directory contains no subdirectories, return the directory.
    """
    path = str(path)

    if os.path.isdir(path):
        # The provided path is a directory, return it's subdirectories, or itself if no subdirectories exist
        paths = [os.path.join(path, i) for i in os.listdir(path)]
        paths = sorted(i for i in paths if os.path.isdir(i))
        if len(paths) == 0:
            return [path]
        return paths

    head, tail = os.path.split(path)
    paths = os.listdir(head)
    paths = [os.path.join(head, i) for i in paths]
    pattern = path.lower()
    paths = sorted(i for i in paths if os.path.isdir(i) and i.lower().startswith(pattern))

    return paths


def make_media_directory(path: str):
    """
    Make a directory relative within the media directory.
    """
    media_dir = get_media_directory()
    path = media_dir / str(path)
    path.mkdir(parents=True)


def replace_extension(path: pathlib.Path, new_ext) -> pathlib.Path:
    """Swap the extension of a file's path.

    Example:
        >>> foo = pathlib.Path('foo.bar')
        >>> replace_extension(foo, 'baz')
        'foo.baz'
    """
    parent = path.parent
    existing_ext = path.suffix
    path = str(path)
    name, _, _ = path.rpartition(existing_ext)
    path = pathlib.Path(str(parent / name) + new_ext)
    return path


def generate_video_thumbnail(video_path: Path):
    """
    Create a thumbnail next to the provided video_path.
    """
    poster_path = replace_extension(video_path, '.jpg')
    cmd = ['/usr/bin/ffmpeg', '-n', '-i', str(video_path), '-f', 'mjpeg', '-vframes', '1', '-ss', '00:00:05.000',
           str(poster_path)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f'Generated thumbnail at {poster_path}')
    except subprocess.CalledProcessError as e:
        logger.warning(f'FFMPEG thumbnail generation failed with stdout: {e.stdout.decode()}')
        logger.warning(f'FFMPEG thumbnail generation failed with stdout: {e.stderr.decode()}')
        raise


async def generate_bulk_thumbnails(video_ids: List[int]):
    """
    Generate all thumbnails for the provided videos.  Update the video object with the new jpg file location.  Do not
    clobber existing jpg files.
    """
    with get_db_context(commit=True) as (db_conn, db):
        logger.info(f'Generating {len(video_ids)} video thumbnails')
        Video = db['video']
        for idx, video_id in enumerate(video_ids):
            video = Video.get_one(id=video_id)
            channel = video['channel']
            video_path = get_absolute_video_path(video)

            poster_path = replace_extension(video_path, '.jpg')
            if not poster_path.exists():
                generate_video_thumbnail(video_path)
            channel_dir = get_absolute_media_path(channel['directory'])
            poster_path = poster_path.relative_to(channel_dir)
            video['poster_path'] = str(poster_path)

            video.flush()
            db_conn.commit()


def get_video_duration(video_path: Path) -> int:
    """
    Get the duration of a video in seconds.  Do this using ffprobe.
    """
    cmd = ['/usr/bin/ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
           'default=noprint_wrappers=1:nokey=1', str(video_path)]

    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.warning(f'FFPROBE failed to get duration with stdout: {e.stdout.decode()}')
        logger.warning(f'FFPROBE failed to get duration with stderr: {e.stderr.decode()}')
        raise
    stdout = proc.stdout.decode()
    duration = int(float(stdout.strip()))
    return duration


async def get_bulk_video_duration(video_ids: List[int]):
    """
    Get and save the duration for each video provided.
    """
    with get_db_context(commit=True) as (db_conn, db):
        logger.info(f'Getting {len(video_ids)} video durations.')
        Video = db['video']
        for video_id in video_ids:
            video = Video.get_one(id=video_id)
            logger.debug(f'Getting video duration: {video["id"]} {video["title"]}')
            video_path = get_absolute_video_path(video)

            try:
                info_json = get_absolute_video_info_json(video)
                with open(str(info_json), 'rt') as fh:
                    contents = json.load(fh)
                    duration = contents['duration']
            except UnknownFile:
                duration = get_video_duration(video_path)

            video['duration'] = duration
            video.flush()
            db_conn.commit()


async def get_bulk_video_size(video_ids: List[int]):
    """
    Get and save the size for each video provided.
    """
    with get_db_context(commit=True) as (db_conn, db):
        logger.info(f'Getting {len(video_ids)} video sizes.')
        Video = db['video']
        for video_id in video_ids:
            video = Video.get_one(id=video_id)
            logger.debug(f'Getting video size: {video["id"]} {video["video_path "]}')
            video_path = get_absolute_video_path(video)

            size = video_path.stat().st_size
            video['size'] = size
            video.flush()


def toggle_video_favorite(video_id: int, favorite: bool) -> Optional[datetime]:
    """
    Toggle the timestamp on Video.favorite on a video.
    """
    with get_db_context(commit=True) as (db_conn, db):
        Video = db['video']
        video = Video.get_one(id=video_id)
        _favorite = video['favorite'] = datetime.now() if favorite else None
        video.flush()

    return _favorite


def minimize_dict(d: dict, keys: Union[Set, List]) -> dict:
    """
    Return a new dictionary that contains only the keys provided.
    """
    return {k: d[k] for k in d if k in keys}


def minimize_channel(channel: dict) -> dict:
    """
    Return a Channel dictionary that contains only the key/values typically used.
    """
    minimal_keys = {'id', 'name', 'directory', 'url', 'video_count', 'link'}
    channel = minimize_dict(channel, minimal_keys)
    return channel


def minimize_video_info_json(info_json: dict) -> dict:
    minimal_keys = {'description'}
    info_json = minimize_dict(info_json, minimal_keys)
    return info_json


def minimize_video(video: dict) -> dict:
    """
    Return a Video dictionary that contains only the key/values typically used.  Minimize the Channel and info_json,
    if they are present.
    """
    minimal_keys = {'id', 'title', 'upload_date', 'duration', 'channel', 'channel_id', 'favorite', 'size',
                    'poster_path', 'caption_path', 'video_path', 'info_json', 'channel', 'viewed'}
    video = minimize_dict(video, minimal_keys)

    if video.get('channel'):
        video['channel'] = minimize_channel(video['channel'])
    if video.get('info_json'):
        video['info_json'] = minimize_video_info_json(video['info_json'])

    return video


def add_video_to_skip_list(channel: Dict, video: Dict):
    try:
        channel['skip_download_videos'].append(video['source_id'])
        channel.flush()
    except AttributeError:
        channel['skip_download_videos'] = [video['source_id'], ]
        channel.flush()


def delete_video(video: Dict):
    """
    Delete any and all video files for a particular video.  If deletion succeeds, mark it as "do-not-download".
    """
    video_files = get_absolute_video_files(video)
    for path in video_files:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    if not video_files:
        raise UnknownFile('No video files were deleted')

    with get_db_context(commit=True) as (db_conn, db):
        Video = db['video']
        video = Video.get_one(id=video['id'])

        video['video_path'] = None
        video['poster_path'] = None
        video['caption_path'] = None
        video['description_path'] = None
        video['info_json_path'] = None
        video.flush()

        channel = video['channel']
        add_video_to_skip_list(channel, video)
