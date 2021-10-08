import json
import os
import pathlib
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from typing import Union, Tuple, List, Set, Iterable

import PIL
from PIL import Image
from sqlalchemy.orm import Session

from wrolpi import before_startup
from wrolpi.common import sanitize_link, logger, CONFIG_PATH, get_config, iterify, chunks, get_media_directory, \
    get_absolute_media_path, minimize_dict
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import UnknownFile, UnknownDirectory, ChannelNameConflict, ChannelURLConflict, \
    ChannelLinkConflict, ChannelDirectoryConflict
from wrolpi.vars import DOCKERIZED, DEFAULT_FILE_PERMISSIONS
from .models import Channel, Video

logger = logger.getChild(__name__)

REQUIRED_OPTIONS = ['name', 'directory']
MINIMUM_CHANNEL_KEYS = {'id', 'name', 'directory', 'url', 'video_count', 'link'}
MINIMUM_INFO_JSON_KEYS = {'description', 'view_count'}
MINIMUM_VIDEO_KEYS = {'id', 'title', 'upload_date', 'duration', 'channel', 'channel_id', 'favorite', 'size',
                      'poster_path', 'caption_path', 'video_path', 'info_json', 'channel', 'viewed', 'source_id'}
VIDEO_QUERY_LIMIT = 20
VIDEO_QUERY_MAX_LIMIT = 100
# These are the supported video formats.  These are in order of their preference.
VIDEO_EXTENSIONS = ('mp4', 'ogg', 'webm', 'flv')


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


@before_startup
def import_videos_config():
    """Import channel settings to the DB.  Existing channels will be updated."""
    try:
        config = load_channels_config()

        with get_db_session(commit=True) as session:
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
                channel.directory = str(directory)

                channel.calculate_duration = config[section].get('calculate_duration')
                channel.download_frequency = config[section].get('download_frequency')
                channel.generate_posters = config[section].get('generate_posters')
                channel.match_regex = config[section].get('match_regex')
                channel.skip_download_videos = list(set(config[section].get('skip_download_videos', {})))
                channel.url = config[section].get('url')

                session.add(channel)

                # Set favorite Videos of this Channel.
                favorites = config[section].get('favorites', {})
                if favorites:
                    videos = session.query(Video).filter(Video.source_id.in_(favorites.keys()))
                    for video in videos:
                        video.favorite = favorites[video.source_id]['favorite']
    except Exception:
        logger.warning('Failed to load channels config!', exc_info=True)


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


def check_for_channel_conflicts(session: Session, id_=None, url=None, name=None, link=None, directory=None):
    """
    Search for any channels that conflict with the provided args, raise a relevant exception if any conflicts are found.
    """
    if not any([id_, url, name, link, directory]):
        raise Exception('Cannot search for channel with no arguments')

    logger.debug(f'Checking for channel conflicts: id={id_} url={url} name={name} link={link} directory={directory}')

    # A channel can't conflict with itself
    if id_:
        base_where = session.query(Channel).filter(Channel.id != id_)
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
    logger.info(f'Generating {len(video_ids)} video posters')
    for video_ids in chunks(video_ids, 10):
        with get_db_session(commit=True) as session:
            videos = session.query(Video).filter(Video.id.in_(video_ids))
            for video in videos:
                video_path = get_absolute_video_path(video)

                poster_path = replace_extension(video_path, '.jpg')
                if not poster_path.exists():
                    generate_video_poster(video_path)
                channel_dir = get_absolute_media_path(video.channel.directory)
                poster_path = poster_path.relative_to(channel_dir)
                video.poster_path = str(poster_path)
    logger.info('Done generating video posters')


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
    for video_ids in chunks(video_ids, 10):
        for video_id in video_ids:
            with get_db_session(commit=True) as session:
                video = session.query(Video).filter_by(id=video_id).one()
                channel = video.channel

                poster_path: Path = get_absolute_video_poster(video)
                new_poster_path = poster_path.with_suffix('.jpg')

                if poster_path != new_poster_path and new_poster_path.exists():
                    # Destination JPEG already exists (it may have the wrong format), lets overwrite it with a valid
                    # JPEG.
                    poster_path.unlink()
                    poster_path = new_poster_path

                if not is_valid_poster(poster_path):
                    # Poster is not valid, convert it and place it in the new location.
                    try:
                        convert_image(poster_path, new_poster_path)
                        logger.info(f'Converted invalid poster {poster_path} to {new_poster_path}')
                    except Exception:
                        logger.error(f'Failed to convert invalid poster {poster_path} to {new_poster_path}',
                                     exc_info=True)
                else:
                    logger.debug(f'Poster was already valid: {new_poster_path}')

                channel_dir = get_absolute_media_path(channel.directory)

                # Update the video with the new poster path.  Mark it as validated.
                video.poster_path = str(new_poster_path.relative_to(channel_dir))
                video.validated_poster = True
    logger.info('Done validating video posters.')


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


async def get_bulk_video_info_json(video_ids: List[int]):
    """
    Get and save the info_json data for each video provided.
    """
    logger.info(f'Getting {len(video_ids)} video info_json meta data.')
    for video_ids in chunks(video_ids, 10):
        with get_db_session(commit=True) as session:
            for video_id in video_ids:
                video = session.query(Video).filter_by(id=video_id).one()
                logger.debug(f'Getting video info_json data: {video}')
                video_path = get_absolute_video_path(video)

                try:
                    info_json = video.get_info_json()
                    video.view_count = info_json.get('view_count') if info_json else None
                    video.duration = info_json.get('duration') if info_json else get_video_duration(video_path)
                except Exception:
                    logger.warning(f'Unable to get meta data of {video}', exc_info=True)
    logger.info('Done getting video info_json meta data.')


async def get_bulk_video_size(video_ids: List[int]):
    """
    Get and save the size for each video provided.
    """
    logger.info(f'Getting {len(video_ids)} video sizes.')
    for video_ids in chunks(video_ids, 10):
        with get_db_session(commit=True) as session:
            for video_id in video_ids:
                video = session.query(Video).filter_by(id=video_id).one()
                logger.debug(f'Getting video size: {video.id} {video.video_path}')
                video_path = get_absolute_video_path(video)

                size = video_path.stat().st_size
                video.size = size
    logger.info('Done getting video sizes')


def update_view_count(channel_id: int):
    """
    Update view_count for all Videos in a channel.
    """
    with get_db_session() as session:
        channel = session.query(Channel).filter_by(id=channel_id).one()
        info = channel.info_json

    if not info:
        logger.info(f'No info_json for channel {channel.name}')
        return

    view_counts = [{'id': i['id'], 'view_count': i['view_count']} for i in info['entries']]
    logger.info(f'Updating {len(view_counts)} view counts for channel {channel.name}')
    view_counts_str = json.dumps(view_counts)

    with get_db_curs(commit=True) as curs:
        stmt = '''
            WITH source AS (select * from json_to_recordset(%s::json) as (id text, view_count int))
            UPDATE video
            SET view_count = s.view_count
            FROM source as s
            WHERE source_id=s.id AND channel_id=%s
        '''
        curs.execute(stmt, (view_counts_str, channel_id))


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
