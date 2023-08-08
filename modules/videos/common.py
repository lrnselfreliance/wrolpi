import asyncio
import json
import os
import pathlib
import re
import shlex
import subprocess
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple, Union

import PIL
from PIL import Image
from sqlalchemy.orm import Session

from wrolpi.captions import FFMPEG_BIN
from wrolpi.cmd import FFPROBE_BIN
from wrolpi.common import logger, get_media_directory
from wrolpi.dates import seconds_to_timestamp
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.vars import DEFAULT_FILE_PERMISSIONS
from .errors import ChannelNameConflict, ChannelURLConflict, ChannelDirectoryConflict, ChannelSourceIdConflict
from .models import Channel

logger = logger.getChild(__name__)

REQUIRED_OPTIONS = ['name', 'directory']


class ConfigError(Exception):
    pass


def get_videos_directory() -> pathlib.Path:
    """Get the "videos" directory in the media directory.  Make it if it does not exist."""
    directory = get_media_directory() / 'videos'
    if not directory.is_dir():
        directory.mkdir(parents=True)
    return directory


def get_no_channel_directory() -> pathlib.Path:
    """Get the "NO CHANNEL" directory in the videos directory.  Make it if it does not exist."""  # noqa
    directory = get_videos_directory() / 'NO CHANNEL'
    if not directory.is_dir():
        directory.mkdir(parents=True)
    return directory


def check_for_channel_conflicts(session: Session, id_=None, url=None, name=None, directory=None,
                                source_id=None):
    """
    Search for any channels that conflict with the provided args, raise a relevant exception if any conflicts are found.
    """
    if not any([id_, url, name, directory]):
        raise Exception('Cannot search for channel with no arguments')

    logger.debug(f'Checking for channel conflicts: id={id_} url={url} name={name} directory={directory}')

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
    if directory:
        conflicts = base_where.filter(Channel.directory == directory)
        if list(conflicts):
            raise ChannelDirectoryConflict()
    if source_id:
        conflicts = base_where.filter(Channel.source_id == source_id)
        if list(conflicts):
            raise ChannelSourceIdConflict()

    # Assure that this Channel's directory is not in another Channel's directory.
    directory = f'{directory}/'
    for channel in session.query(Channel).filter(Channel.id != id_):
        channel_directory = f'{channel.directory}/'
        if directory.startswith(channel_directory) or channel_directory.startswith(directory):
            raise ChannelDirectoryConflict()


def duration_to_seconds(duration: str) -> int:
    """Convert ffmpeg duration to seconds"""
    hours, minutes, seconds = duration.split(':')
    seconds, microseconds = seconds.split('.')
    return int(timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        microseconds=int(microseconds),
    ).total_seconds())


def seconds_to_duration(seconds: int) -> str:
    """Convert integer seconds to ffmpeg duration"""
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}.000'


DURATION_REGEX = re.compile(r'Duration: ([\d:.]+),')


def get_duration_from_ffmpeg(stderr: str) -> int:
    """Extract the duration from FFPEG's stderr, return this duration as integer seconds."""
    duration = DURATION_REGEX.findall(stderr)
    duration = duration_to_seconds(duration[0]) if duration else None
    return duration


def ffmpeg_poster(video_path: Path, poster_path: Path, seconds: int):
    """Use ffmpeg to create a poster file from a video file at a particular time of the video.

    Returns stderr so data about the command can be extracted."""
    timestamp = seconds_to_timestamp(seconds)
    cmd = (FFMPEG_BIN, '-ss', timestamp, '-n', '-i', video_path, '-f', 'mjpeg', '-vframes', '1', poster_path)
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stderr = proc.stderr.decode()
    except subprocess.CalledProcessError as e:
        logger.error(f'Failed to create video poster', exc_info=e)
        raise

    return stderr


def ffmpeg_video_complete(video_path: Path, seconds: int = None) -> bool:
    """Checks if video file is complete by taking screenshot from the end of the video."""
    seconds = seconds or get_video_duration(video_path) - 5
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as fh:
        path = Path(fh.name)
        path.unlink()
        try:
            ffmpeg_poster(video_path, path, seconds)
            return True
        except Exception:
            return False
        finally:
            path.unlink()


def generate_video_poster(video_path: Path, seconds: int = 5) -> Tuple[Path, Optional[int]]:
    """Create a poster (aka thumbnail) next to the provided video_path.  Also returns the video duration."""
    poster_path = video_path.with_suffix('.jpg')
    if poster_path.exists():
        # Poster already exists.
        return poster_path, None

    stderr = ffmpeg_poster(video_path, poster_path, seconds)

    duration = get_duration_from_ffmpeg(stderr)
    return poster_path, duration


def convert_image(existing_path: Path, destination_path: Path, ext: str = 'jpeg'):
    """Convert an image from one format to another.  Remove the existing image file.  This will safely overwrite an
    image if the destination file already exists.
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


async def ffprobe_json(video_path: Union[Path, str]) -> dict:
    """Extract video file metadata using ffprobe.

    >>> ffprobe_json('video')
    {
        'chapters': [],
        'format': {},
        'streams': [
            {},
        ],
    }
    """
    cmd = f'{FFPROBE_BIN}' \
          f' -print_format json' \
          f' -loglevel quiet' \
          f' -show_streams' \
          f' -show_format' \
          f' -show_chapters' \
          f' {shlex.quote(str(video_path.absolute()))}'

    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await proc.communicate()
    except Exception as e:
        logger.error(f'Failed to run ffprobe json', exc_info=e)
        raise

    if proc.returncode != 0:
        raise RuntimeError(f'Got non-zero exit code: {proc.returncode}')

    try:
        content = json.loads(stdout.decode().strip())
    except Exception as e:
        logger.debug(stdout.decode())
        logger.error(f'Failed to load ffprobe json', exc_info=e)
        raise

    if content == dict():
        # Data is empty, video may be corrupt.
        raise RuntimeError('ffprobe data was empty')

    return content


def get_video_duration(video_path: Path) -> int:
    """Get the duration of a video in seconds.  Do this using ffprobe."""
    if not isinstance(video_path, Path):
        video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f'{video_path} does not exist!')
    if not FFPROBE_BIN:
        raise SystemError('ffprobe is not installed!')

    cmd = [FFPROBE_BIN, '-v', 'error', '-show_entries', 'format=duration', '-of',
           'default=noprint_wrappers=1:nokey=1', str(video_path)]

    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.warning(f'FFPROBE failed to get duration with stdout: {e.stdout.decode()}')
        logger.warning(f'FFPROBE failed to get duration with stderr: {e.stderr.decode()}')
        raise
    stdout = proc.stdout.decode()
    duration = int(Decimal(stdout.strip()))
    return duration


def check_for_video_corruption(video_path: Path) -> bool:
    """Uses ffprobe to check for specific ways a video file can be corrupt.

    Also attempts to screenshot the video near the end of it's duration, this check if the video is corrupted somewhere
    in the middle."""
    video_path = Path(video_path) if not isinstance(video_path, Path) else video_path

    if not video_path.is_file():
        raise FileNotFoundError(f'{video_path} does not exist!')
    if not FFPROBE_BIN:
        raise SystemError('ffprobe is not installed!')

    # Just read the video using FFMPEG, this prints out useful information about the video.
    cmd = (FFPROBE_BIN, str(video_path))
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.warning(f'FFPROBE failed to check for corruption with stderr: {e.stderr.decode()}')
        return True  # video is corrupt.

    messages = (
        b'Invalid NAL unit size',
        b'Error splitting the input into NAL units',
        b'Invalid data found when processing input',
    )
    corrupt = False
    for error in messages:
        if error in proc.stderr:
            logger.warning(f'Possible video corruption ({error.decode()}): {video_path}')
            corrupt = True
    return corrupt


async def update_view_counts(channel_id: int):
    """Update view_count for all Videos in a channel using its info_json file."""
    with get_db_session() as session:
        channel: Channel = session.query(Channel).filter_by(id=channel_id).one()
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
