import json
import json
import os
import pathlib
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from typing import Union, Tuple, List, Set, Iterable, Optional

import PIL
from PIL import Image
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from wrolpi import before_startup
from wrolpi.common import logger, get_config, iterify, get_media_directory, \
    minimize_dict, api_param_limiter
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import UnknownFile, UnknownDirectory, ChannelNameConflict, ChannelURLConflict, \
    ChannelLinkConflict, ChannelDirectoryConflict, ChannelSourceIdConflict
from wrolpi.media_path import MediaPath
from wrolpi.vars import DEFAULT_FILE_PERMISSIONS
from .models import Channel, Video

logger = logger.getChild(__name__)

REQUIRED_OPTIONS = ['name', 'directory']
MINIMUM_CHANNEL_KEYS = {'id', 'name', 'directory', 'url', 'video_count', 'link'}
MINIMUM_INFO_JSON_KEYS = {'description', 'view_count', 'webpage_url'}
MINIMUM_VIDEO_KEYS = {'id', 'title', 'upload_date', 'duration', 'channel', 'channel_id', 'favorite', 'size',
                      'poster_path', 'caption_path', 'video_path', 'info_json', 'channel', 'viewed', 'source_id',
                      'view_count'}
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


video_limiter = api_param_limiter(100)


class ConfigError(Exception):
    pass


@before_startup
def import_videos_config():
    """Import channel settings to the DB.  Existing channels will be updated."""
    logger.info('Importing videos config')
    try:
        config = get_config()
        config, favorites = config['channels'], config.get('favorites', {})

        with get_db_session(commit=True) as session:
            for link in config:
                for option in (i for i in REQUIRED_OPTIONS if i not in config[link]):
                    raise ConfigError(f'Channel "{link}" is required to have "{option}"')

                name, directory = config[link]['name'], config[link]['directory']

                channel = session.query(Channel).filter(Channel.link == link).one_or_none()
                if not channel:
                    # Channel not yet in the DB, add it.
                    channel = Channel(link=link)

                # Only name and directory are required
                channel.name = name
                channel.directory = str(directory)

                channel.calculate_duration = config[link].get('calculate_duration') or channel.calculate_duration
                channel.download_frequency = config[link].get('download_frequency') or channel.download_frequency
                channel.generate_posters = config[link].get('generate_posters') or channel.generate_posters
                channel.match_regex = config[link].get('match_regex') or channel.match_regex
                channel.skip_download_videos = list(set(config[link].get('skip_download_videos', {})))
                channel.source_id = config[link].get('source_id') or channel.source_id
                channel.url = config[link].get('url') or channel.url

                if not channel.source_id and channel.url:
                    # If we can download from a channel, we must have its source_id.
                    channel.source_id = get_channel_source_id(channel.url)

                session.add(channel)

        with get_db_session(commit=True) as session:
            for link, favorites in favorites.items():
                if link != 'NO CHANNEL':
                    channel: Channel = session.query(Channel).filter_by(link=link).one_or_none()
                    if not channel:
                        logger.warning(f'Cannot find channel {link=} for favorites!')
                        continue
                    channel_dir = channel.directory.path
                else:
                    from .downloader import get_no_channel_directory
                    channel_dir = get_no_channel_directory()

                # Set favorite Videos of this Channel.
                for video_path, data in favorites.items():
                    # Favorite in the config is the name of the video_path.  Add the channel directory onto this
                    # video_path, so we can match the complete path for the Video.
                    video_path = channel_dir / video_path
                    video = session.query(Video).filter_by(video_path=video_path).one_or_none()
                    # If no Video is found, it may be that we need to refresh.
                    if video:
                        video.favorite = data['favorite']
                    else:
                        logger.warning(f'Cannot find video to favorite: {video_path}')
    except Exception as e:
        logger.warning('Failed to load channels config!', exc_info=e)


VALID_VIDEO_KINDS = {'video', 'caption', 'poster', 'description', 'info_json'}


def get_absolute_video_path(video: Video, kind: str = 'video') -> MediaPath:
    if kind not in VALID_VIDEO_KINDS:
        raise Exception(f'Unknown video path kind {kind}')
    path = getattr(video, f'{kind}_path')
    if path:
        return path
    raise UnknownFile()


get_absolute_video_caption = partial(get_absolute_video_path, kind='caption')
get_absolute_video_poster = partial(get_absolute_video_path, kind='poster')
get_absolute_video_description = partial(get_absolute_video_path, kind='description')
get_absolute_video_info_json = partial(get_absolute_video_path, kind='info_json')


def get_absolute_video_files(video: Video) -> List[MediaPath]:
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


def get_video_info_json(video) -> Optional[dict]:
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


def generate_video_paths(directory: Union[str, pathlib.Path]) -> Tuple[str, pathlib.Path]:
    """
    Generate a list of video paths in the provided directory.
    """
    directory = pathlib.Path(directory)

    for child in directory.iterdir():
        if child.is_file() and match_video_extensions(child.name):
            child = child.absolute()
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


def check_for_channel_conflicts(session: Session, id_=None, url=None, name=None, link=None, directory=None,
                                source_id=None):
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
    if source_id:
        conflicts = base_where.filter(Channel.source_id == source_id)
        if list(conflicts):
            raise ChannelSourceIdConflict()


def get_matching_directories(path: Union[str, Path]) -> List[str]:
    """
    Return a list of directory strings that start with the provided path.  If the path is a directory, return it's
    subdirectories, if the directory contains no subdirectories, return the directory.
    """
    path = str(path)

    ignored_directories = {
        str(get_media_directory() / 'videos/NO CHANNEL'),
    }

    if os.path.isdir(path):
        # The provided path is a directory, return its subdirectories, or itself if no subdirectories exist
        paths = [os.path.join(path, i) for i in os.listdir(path)]
        paths = sorted(i for i in paths if os.path.isdir(i) and i not in ignored_directories)
        if len(paths) == 0:
            return [path]
        return paths

    head, tail = os.path.split(path)
    paths = os.listdir(head)
    paths = [os.path.join(head, i) for i in paths]
    pattern = path.lower()
    paths = sorted(
        i for i in paths if os.path.isdir(i) and i.lower().startswith(pattern) and i not in ignored_directories)

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


def generate_video_poster(video_path: Path) -> Path:
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
    return poster_path


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
    """Return True only if poster file exists, and is a JPEG format."""
    if poster_path.is_file():
        try:
            img = Image.open(poster_path)
            return img.format == 'JPEG'
        except PIL.UnidentifiedImageError:
            logger.error(f'Failed to identify poster: {poster_path}', exc_info=True)
            pass

    return False


def get_video_duration(video_path: Path) -> int:
    """
    Get the duration of a video in seconds.  Do this using ffprobe.
    """
    if not isinstance(video_path, Path):
        video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f'{video_path} does not exist!')

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


def apply_info_json(channel_id: int):
    """
    Update view_count for all Videos in a channel using its info_json file.  Mark any videos not in the info_json as
    "censored".
    """
    with get_db_session() as session:
        channel = session.query(Channel).filter_by(id=channel_id).one()
        channel_name = channel.name
        info = channel.info_json

    if not info:
        logger.info(f'No info_json for channel {channel.name}')
        return

    view_counts = [{'id': i['id'], 'view_count': i['view_count']} for i in info['entries']]
    view_counts_str = json.dumps(view_counts)

    with get_db_curs(commit=True) as curs:
        # Update the view_count for each video.
        stmt = '''
            WITH source AS (select * from json_to_recordset(%s::json) as (id text, view_count int))
            UPDATE video
            SET view_count = s.view_count
            FROM source as s
            WHERE source_id=s.id AND channel_id=%s
            RETURNING video.id AS updated_ids
        '''
        curs.execute(stmt, (view_counts_str, channel_id))
        count = len(curs.fetchall())
        logger.debug(f'Updated {count} view counts in DB for {channel_name}.')

        # Mark any video not in the info_json entries as censored.
        source_ids = [i['id'] for i in info['entries']]
        stmt = '''
            UPDATE video SET censored=(source_id != ALL(%s))
            WHERE channel_id=%s
        '''
        curs.execute(stmt, (source_ids, channel_id))


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


YDL = YoutubeDL()
YDL.params['logger'] = logger.getChild('youtube-dl')
YDL.add_default_info_extractors()


def get_channel_source_id(url: str) -> str:
    channel_info = YDL.extract_info(url, download=False, process=False)
    return channel_info.get('uploader_id') or channel_info['id']
