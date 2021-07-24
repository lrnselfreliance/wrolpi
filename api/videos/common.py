import json
import os
import pathlib
import subprocess
import tempfile
from functools import partial, lru_cache
from pathlib import Path
from typing import Union, Tuple, List, Set, Iterable

import PIL
from PIL import Image
from sqlalchemy.orm import Session

from api.common import sanitize_link, logger, CONFIG_PATH, get_config, iterify
from api.db import get_db_context
from api.errors import UnknownFile, UnknownDirectory, ChannelNameConflict, ChannelURLConflict, \
    ChannelLinkConflict, ChannelDirectoryConflict
from api.vars import DOCKERIZED, PROJECT_DIR, VIDEO_EXTENSIONS, MINIMUM_CHANNEL_KEYS, MINIMUM_INFO_JSON_KEYS, \
    MINIMUM_VIDEO_KEYS, DEFAULT_FILE_PERMISSIONS
from .models import Channel, Video

logger = logger.getChild(__name__)

REQUIRED_OPTIONS = ['name', 'directory']

VIDEO_QUERY_LIMIT = 20
VIDEO_QUERY_MAX_LIMIT = 100


def load_downloader_config() -> dict:
    config = get_config()
    downloader = config['downloader']
    return downloader


def load_channels_config() -> dict:
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
    config = load_channels_config()

    with get_db_context(commit=True) as (engine, session):
        for section in config:
            for option in (i for i in REQUIRED_OPTIONS if i not in config[section]):
                raise ConfigError(f'Channel "{section}" is required to have "{option}"')

            name, directory = config[section]['name'], config[section]['directory']

            link = sanitize_link(name)
            matches = session.query(Channel).filter(Channel.link == link)
            if not matches.count():
                # Channel not yet in the DB, add it
                channel = Channel(link=link)
            else:
                channel = matches.one()

            # Only name and directory are required
            channel.name = name
            channel.directory = directory

            channel.calculate_duration = config[section].get('calculate_duration')
            channel.download_frequency = config[section].get('download_frequency')
            channel.generate_posters = config[section].get('generate_posters')
            channel.match_regex = config[section].get('match_regex')
            channel.skip_download_videos = list(set(config[section].get('skip_download_videos', {})))
            channel.url = config[section].get('url')

            session.add(channel)
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


def get_absolute_video_path(video: Video, kind: str = 'video') -> Path:
    if kind not in VALID_VIDEO_KINDS:
        raise Exception(f'Unknown video path kind {kind}')
    directory = get_absolute_media_path(video.channel.directory)
    path = getattr(video, f'{kind}_path')
    if directory and path:
        return directory / path
    raise UnknownFile()


get_absolute_video_caption = partial(get_absolute_video_path, kind='caption')
get_absolute_video_poster = partial(get_absolute_video_path, kind='poster')
get_absolute_video_description = partial(get_absolute_video_path, kind='description')
get_absolute_video_info_json = partial(get_absolute_video_path, kind='info_json')


def get_absolute_video_files(video: Video) -> List[Path]:
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


def get_video_info_json(video) -> Union[dict, None]:
    """Get the info_json object from a video's meta-file.  Return an empty dict if not possible."""
    if not video.channel or not video.channel.directory:
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
                yield sorted(paths)[0]


def check_for_channel_conflicts(session: Session, id=None, url=None, name=None, link=None, directory=None):
    """
    Search for any channels that conflict with the provided args, raise a relevant exception if any conflicts are found.
    """
    if not any([id, url, name, link, directory]):
        raise Exception('Cannot search for channel with no arguments')

    logger.debug(f'Checking for channel conflicts: id={id} url={url} name={name} link={link} directory={directory}')

    # A channel can't conflict with itself
    if id:
        base_where = session.query(Channel).filter(Channel.id != id)
    else:
        base_where = session.query(Channel)

    if url:
        conflicts = base_where.filter(Channel.url == url)
        if list(conflicts):
            raise ChannelURLConflict()
    if name:
        conflicts = base_where.filter(Channel.name == name)
        if list(conflicts):
            raise ChannelNameConflict()
    if link:
        conflicts = base_where.filter(Channel.link == link)
        if list(conflicts):
            raise ChannelLinkConflict()
    if directory:
        conflicts = base_where.filter(Channel.directory == directory)
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


def generate_video_poster(video_path: Path):
    """
    Create a poster (aka thumbnail) next to the provided video_path.
    """
    poster_path = replace_extension(video_path, '.jpg')
    cmd = ['/usr/bin/ffmpeg', '-n', '-i', str(video_path), '-f', 'mjpeg', '-vframes', '1', '-ss', '00:00:05.000',
           str(poster_path)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f'Generated poster at {poster_path}')
    except subprocess.CalledProcessError as e:
        logger.warning(f'FFMPEG poster generation failed with stdout: {e.stdout.decode()}')
        logger.warning(f'FFMPEG poster generation failed with stdout: {e.stderr.decode()}')
        raise


async def generate_bulk_posters(video_ids: List[int]):
    """
    Generate all posters for the provided videos.  Update the video object with the new jpg file location.  Do not
    clobber existing jpg files.
    """
    with get_db_context(commit=True) as (engine, session):
        logger.info(f'Generating {len(video_ids)} video posters')
        videos = session.query(Video).filter(Video.id.in_(video_ids))
        for video in videos:
            video_path = get_absolute_video_path(video)

            poster_path = replace_extension(video_path, '.jpg')
            if not poster_path.exists():
                generate_video_poster(video_path)
            channel_dir = get_absolute_media_path(video.channel.directory)
            poster_path = poster_path.relative_to(channel_dir)
            video.poster_path = str(poster_path)


def convert_image(existing_path: Path, destination_path: Path, ext: str = 'jpeg'):
    """
    Convert an image from one format to another.  Remove the existing image file.  This will safely overwrite an image
    if the existing path is the same as the destination path.
    """
    with tempfile.NamedTemporaryFile(dir=destination_path.parent, delete=False) as fh:
        img = Image.open(existing_path).convert('RGB')
        img.save(fh.name, ext)

        existing_path.unlink()
        os.rename(fh.name, destination_path)
        os.chmod(destination_path, DEFAULT_FILE_PERMISSIONS)


def is_valid_poster(poster_path: Path) -> bool:
    """Return True only if poster file exists, and is of a JPEG format."""
    if poster_path.is_file():
        try:
            img = Image.open(poster_path)
            return img.format == 'JPEG'
        except PIL.UnidentifiedImageError:
            logger.error(f'Failed to identify poster: {poster_path}', exc_info=True)
            pass

    return False


def bulk_validate_posters(video_ids: List[int]):
    """
    Replace all posters for the provided videos if a video's poster is not a JPEG format.
    """
    logger.info(f'Validating {len(video_ids)} video posters')
    for video_id in video_ids:
        with get_db_context(commit=True) as (engine, session):
            video = session.query(Video).filter_by(id=video_id).one()
            channel = video.channel

            poster_path: Path = get_absolute_video_poster(video)
            new_poster_path = poster_path.with_suffix('.jpg')

            if poster_path != new_poster_path and new_poster_path.exists():
                # Destination JPEG already exists (it may have the wrong format), lets overwrite it with a valid JPEG.
                poster_path.unlink()
                poster_path = new_poster_path

            if not is_valid_poster(poster_path):
                # Poster is not valid, convert it and place it in the new location.
                try:
                    convert_image(poster_path, new_poster_path)
                    logger.info(f'Converted invalid poster {poster_path} to {new_poster_path}')
                except Exception:
                    logger.error(f'Failed to convert invalid poster {poster_path} to {new_poster_path}', exc_info=True)
            else:
                logger.debug(f'Poster was already valid: {new_poster_path}')

            channel_dir = get_absolute_media_path(channel.directory)

            # Update the video with the new poster path.  Mark it as validated.
            video.poster_path = str(new_poster_path.relative_to(channel_dir))
            video.validated_poster = True


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
    with get_db_context(commit=True) as (engine, session):
        logger.info(f'Getting {len(video_ids)} video durations.')
        for video_id in video_ids:
            video = session.query(Video).filter_by(id=video_id).one()
            logger.debug(f'Getting video duration: {video.id} {video.title}')
            video_path = get_absolute_video_path(video)

            try:
                info_json = get_absolute_video_info_json(video)
                with open(str(info_json), 'rt') as fh:
                    contents = json.load(fh)
                    duration = contents['duration']
            except UnknownFile:
                duration = get_video_duration(video_path)

            video.duration = duration


async def get_bulk_video_size(video_ids: List[int]):
    """
    Get and save the size for each video provided.
    """
    with get_db_context(commit=True) as (engine, session):
        logger.info(f'Getting {len(video_ids)} video sizes.')
        for video_id in video_ids:
            video = session.query(Video).filter_by(id=video_id).one()
            logger.debug(f'Getting video size: {video.id} {video.video_path}')
            video_path = get_absolute_video_path(video)

            size = video_path.stat().st_size
            video.size = size


def minimize_dict(d: dict, keys: Iterable) -> dict:
    """
    Return a new dictionary that contains only the keys provided.
    """
    return {k: d[k] for k in d if k in keys}


minimize_channel = partial(minimize_dict, keys=MINIMUM_CHANNEL_KEYS)
minimize_video_info_json = partial(minimize_dict, keys=MINIMUM_INFO_JSON_KEYS)
_minimize_video = partial(minimize_dict, keys=MINIMUM_VIDEO_KEYS)


def minimize_video(video: dict) -> dict:
    """
    Return a Video dictionary that contains only the key/values typically used.  Minimize the Channel and info_json,
    if they are present.
    """
    video = _minimize_video(video)

    if video.get('channel'):
        video['channel'] = minimize_channel(video['channel'])
    if video.get('info_json'):
        video['info_json'] = minimize_video_info_json(video['info_json'])

    return video


def add_video_to_skip_list(channel, video):
    try:
        channel.skip_download_videos.append(video.source_id)
    except AttributeError:
        channel.skip_download_videos = [video.source_id, ]
