import asyncio
import json
import pathlib
import re
from typing import Tuple
from uuid import uuid1

from sqlalchemy.orm import Session

from wrolpi.common import logger, chunks
from wrolpi.common import save_settings_config
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.vars import PYTEST
from .captions import insert_bulk_captions, process_captions
from .common import generate_bulk_posters, get_bulk_video_info_json, get_bulk_video_size, \
    generate_video_paths, remove_duplicate_video_paths, bulk_validate_posters, \
    apply_info_json
from .models import Channel, Video

logger = logger.getChild(__name__)

DEFAULT_DOWNLOAD_FREQUENCY = 60 * 60 * 24 * 7  # weekly


def refresh_channel_video_captions() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE caption IS NULL AND caption_path IS NOT NULL'
        curs.execute(query)
        missing_captions = [i for (i,) in curs.fetchall()]

    if missing_captions:
        coro = insert_bulk_captions(missing_captions)
        asyncio.ensure_future(coro)
        logger.info('Scheduled insert_bulk_captions()')
        return True
    else:
        logger.info('No missing captions to process.')
        return False


def refresh_channel_generate_posters() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE video_path IS NOT NULL AND poster_path IS NULL'
        curs.execute(query)
        missing_posters = [i for (i,) in curs.fetchall()]

    if missing_posters:
        coro = generate_bulk_posters(missing_posters)
        asyncio.ensure_future(coro)
        logger.info('Scheduled generate_bulk_posters()')
        return True
    else:
        logger.info('No missing posters to generate.')
        return False


def convert_invalid_posters() -> bool:
    """
    Searches the DB for all videos with an invalid poster type (i.e. webp) and converts them to JPEGs.  A video with a
    valid poster will be marked as such in it's column "validated_poster".
    """
    with get_db_curs() as curs:
        query = "SELECT id FROM video WHERE poster_path IS NOT NULL AND validated_poster = FALSE"
        curs.execute(query)
        invalid_posters = [i for (i,) in curs.fetchall()]

    if invalid_posters:
        async def _():
            return bulk_validate_posters(invalid_posters)

        coro = _()
        asyncio.ensure_future(coro)
        logger.info('Scheduled bulk_replace_invalid_posters()')
        return True
    else:
        logger.info('No invalid posters to replace.')
        return False


def refresh_channel_info_json() -> bool:
    """
    Fill in Video columns that are extracted from the info_json.
    """
    with get_db_curs() as curs:
        query = '''
            SELECT v.id
            FROM video v
            WHERE
                v.video_path IS NOT NULL
                AND v.info_json_path IS NOT NULL
                AND v.info_json_path != ''
                AND (v.duration IS NULL OR v.view_count IS NULL)
        '''
        curs.execute(query)
        missing_duration = [i for (i,) in curs.fetchall()]

    if missing_duration:
        coro = get_bulk_video_info_json(missing_duration)
        asyncio.ensure_future(coro)
        logger.info('Scheduled get_bulk_video_duration()')
        return True
    else:
        logger.info('No videos missing duration.')
        return False


def refresh_channel_calculate_size() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE video_path IS NOT NULL AND size IS NULL'
        curs.execute(query)
        missing_size = [i for (i,) in curs.fetchall()]

    if missing_size:
        coro = get_bulk_video_size(missing_size)
        asyncio.ensure_future(coro)
        logger.info('Scheduled get_bulk_video_size()')
        return True
    else:
        logger.info('No videos missing size.')
        return False


def process_video_meta_data():
    """
    Search for any videos missing meta data, fill in that data.
    """
    refresh_channel_video_captions()
    refresh_channel_generate_posters()
    convert_invalid_posters()
    refresh_channel_info_json()
    refresh_channel_calculate_size()


def refresh_channel_videos(channel: Channel):
    """
    Find all video files in a channel's directory.  Add any videos not in the DB to the DB.
    """
    # Set the idempotency key so we can remove any videos not touched during this search
    with get_db_curs(commit=True) as curs:
        curs.execute('UPDATE video SET idempotency=NULL WHERE channel_id=%s', (channel.id,))

    idempotency = str(uuid1())
    directory = channel.directory.path

    # A set of absolute paths that exist in the file system
    possible_new_paths = generate_video_paths(directory)
    possible_new_paths = remove_duplicate_video_paths(possible_new_paths)

    # Update all videos that match the current video paths
    new_paths = [str(i) for i in possible_new_paths]
    with get_db_curs(commit=True) as curs:
        query = 'UPDATE video SET idempotency = %s WHERE channel_id = %s AND video_path = ANY(%s) RETURNING video_path'
        curs.execute(query, (idempotency, channel.id, new_paths))
        existing_paths = {i for (i,) in curs.fetchall()}

    # Get the paths for any video not yet in the DB
    # (paths in DB are relative, but we need to pass an absolute path)
    new_videos = {i for i in possible_new_paths if str(i) not in existing_paths}

    for chunk in chunks(new_videos, 20):
        with get_db_session(commit=True) as session:
            for video_path in chunk:
                video_path = pathlib.Path(video_path)
                upsert_video(session, video_path, channel, idempotency=idempotency)
                logger.debug(f'{channel.name}: Added {video_path.name}')

    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM video WHERE channel_id=%s AND idempotency IS NULL RETURNING id', (channel.id,))
        deleted_count = len(curs.fetchall())

    if deleted_count:
        deleted_status = f'Deleted {deleted_count} video records from channel {channel.name}'
        logger.info(deleted_status)

    logger.info(f'{channel.name}: {len(new_videos)} new videos, {len(existing_paths)} already existed. ')

    apply_info_json(channel.id)


def refresh_no_channel_videos():
    """
    Refresh the Videos in the NO CHANNEL directory.
    """
    from modules.videos.downloader import get_no_channel_directory
    directory = get_no_channel_directory()
    if not directory.is_dir():
        return

    logger.info('Refreshing NO CHANNEL videos')

    idempotency = str(uuid1())

    # Get all WROLPi compatible videos, remove any duplicates (different formats).
    possible_new_paths = generate_video_paths(directory)
    possible_new_paths = remove_duplicate_video_paths(possible_new_paths)

    new_paths = [str(i) for i in possible_new_paths]
    with get_db_curs(commit=True) as curs:
        query = 'UPDATE video SET idempotency = %s WHERE video_path = ANY(%s) RETURNING video_path'
        curs.execute(query, (idempotency, new_paths))
        existing_paths = {i for (i,) in curs.fetchall()}

    new_videos = {i for i in possible_new_paths if str(i) not in existing_paths}

    for chunk in chunks(new_videos, 20):
        with get_db_session(commit=True) as session:
            for video_path in chunk:
                upsert_video(session, pathlib.Path(video_path), idempotency=idempotency)
                logger.debug(f'Added NO CHANNEL video {video_path}')

    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM video WHERE channel_id IS NULL AND idempotency IS NULL RETURNING id')
        deleted_count = len(curs.fetchall())

    if deleted_count:
        deleted_status = f'Deleted {deleted_count} video records in NO CHANNEL.'
        logger.info(deleted_status)


def _refresh_videos(channel_links: list = None):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :return:
    """
    logger.info('Refreshing video files')
    with get_db_session() as session:
        if channel_links:
            channels = session.query(Channel).filter(Channel.link.in_(channel_links))
        else:
            channels = session.query(Channel).all()

        channels = list(channels)

    if not channels and channel_links:
        raise Exception(f'No channels match links(s): {channel_links}')
    elif not channels:
        raise Exception(f'No channels in DB.  Have you created any?')

    for idx, channel in enumerate(channels):
        refresh_channel_videos(channel)

    if not channel_links:
        # Refresh NO CHANNEL videos when not refreshing a specific channel.
        refresh_no_channel_videos()

    # Fill in any missing data for all videos.
    if not PYTEST:
        process_video_meta_data()


def get_channels_config(session: Session) -> dict:
    """
    Create a dictionary that contains all the Channels from the DB.
    """
    channels = session.query(Channel).order_by(Channel.link).all()
    channels = {i.link: i.config_view() for i in channels}
    return dict(channels=channels)


def save_channels_config(session=None):
    """
    Pull the Channel information from the DB, save it to the config.
    """
    if session:
        config = get_channels_config(session)
    else:
        with get_db_session() as session:
            config = get_channels_config(session)
    save_settings_config(config)


async def get_statistics():
    with get_db_curs() as curs:
        curs.execute('''
        SELECT
            -- total videos
            COUNT(id) AS "videos",
            -- total videos that are marked as favorite
            COUNT(id) FILTER (WHERE favorite IS NOT NULL) AS "favorites",
            -- total videos downloaded over the past week/month/year
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 week') AS "week",
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 month') AS "month",
            COUNT(id) FILTER (WHERE upload_date >= current_date - interval '1 year') AS "year",
            -- sum of all video lengths in seconds
            COALESCE(SUM(duration), 0) AS "sum_duration",
            -- sum of all video file sizes
            COALESCE(SUM(size), 0)::BIGINT AS "sum_size",
            -- largest video
            COALESCE(MAX(size), 0) AS "max_size"
        FROM
            video
        WHERE
            video_path IS NOT NULL
        ''')
        video_stats = dict(curs.fetchone())

        # Get the total videos downloaded every month for the past two years.
        curs.execute('''
        SELECT
            DATE_TRUNC('month', months.a),
            COUNT(id)::BIGINT,
            SUM(size)::BIGINT AS "size"
        FROM
            generate_series(
                date_trunc('month', current_date) - interval '2 years',
                date_trunc('month', current_date) - interval '1 month',
                '1 month'::interval) AS months(a),
            video
        WHERE
            video.upload_date >= date_trunc('month', months.a)
            AND video.upload_date < date_trunc('month', months.a) + interval '1 month'
            AND video.upload_date IS NOT NULL
            AND video.video_path IS NOT NULL
        GROUP BY
            1
        ORDER BY
            1
        ''')
        monthly_videos = [dict(i) for i in curs.fetchall()]

        historical_stats = dict(monthly_videos=monthly_videos)
        historical_stats['average_count'] = (sum(i['count'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0
        historical_stats['average_size'] = (sum(i['size'] for i in monthly_videos) // len(monthly_videos)) \
            if monthly_videos else 0

        curs.execute('''
        SELECT
            COUNT(id) AS "channels"
        FROM
            channel
        ''')
        channel_stats = dict(curs.fetchone())
    ret = dict(statistics=dict(
        videos=video_stats,
        channels=channel_stats,
        historical=historical_stats,
    ))
    return ret


NAME_PARSER = re.compile(r'(.*?)_((?:\d+?)|(?:NA))_(?:(.{11})_)?(.*)\.'
                         r'(jpg|webp|flv|mp4|part|info\.json|description|webm|..\.srt|..\.vtt)')


def upsert_video(session: Session, video_path: pathlib.Path, channel: Channel = None, idempotency: str = None,
                 skip_captions=False, id_: str = None) -> Video:
    """
    Insert a video into the DB.  Also, find any meta-files near the video file and store them on the video row.

    If id_ is provided, update that entry.
    """
    if not video_path.is_absolute():
        raise ValueError(f'Video path is not absolute: {video_path}')
    poster_path, description_path, caption_path, info_json_path = find_meta_files(video_path)

    name_match = NAME_PARSER.match(video_path.name)
    _ = upload_date = source_id = title = ext = None
    if name_match:
        _, upload_date, source_id, title, ext = name_match.groups()

    # Make sure the date is a valid date format, if not, leave it blank.  Youtube-DL sometimes puts an NA in the date.
    # We may even get videos that weren't downloaded by WROLPi.
    if not upload_date or not upload_date.isdigit() or len(upload_date) != 8:
        logger.debug(f'Could not parse date from filename: {video_path}')
        upload_date = None

    duration = None
    url = None
    if info_json_path:
        try:
            with info_json_path.open('rt') as fh:
                json_contents = json.load(fh)
                duration = json_contents.get('duration')
                url = json_contents.get('webpage_url')
        except json.decoder.JSONDecodeError:
            logger.warning(f'Failed to load JSON file to get duration: {info_json_path}')

    size = video_path.stat().st_size

    video_dict = dict(
        caption_path=str(caption_path) if caption_path else None,
        channel_id=channel.id if channel else None,
        description_path=str(description_path) if description_path else None,
        duration=duration,
        ext=ext,
        idempotency=idempotency,
        info_json_path=str(info_json_path) if info_json_path else None,
        poster_path=str(poster_path) if poster_path else None,
        size=size,
        source_id=source_id,
        title=title,
        upload_date=upload_date,
        url=url,
        video_path=str(video_path),
    )

    if id_:
        video = session.query(Video).filter_by(id=id_).one()
        for key, value in video_dict.items():
            setattr(video, key, value)
    else:
        video = Video(**video_dict)

    session.add(video)
    session.flush()

    if skip_captions is False and caption_path:
        # Process captions only when requested
        process_captions(video)

    return video


def find_meta_files(path: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    """
    Find all files that share a file's full path, except their extensions.  It is assumed that file with the
    same name, but different extension is related to that file.  A None will be yielded if the meta file doesn't exist.

    Example:
        >>> foo = pathlib.Path('foo.bar')
        >>> find_meta_files(foo)
        (pathlib.Path('foo.jpg'), pathlib.Path('foo.description'),
        pathlib.Path('foo.en.vtt'), pathlib.Path('foo.info.json'))
    """
    suffix = path.suffix
    name, suffix, _ = str(path.name).rpartition(suffix)
    meta_file_exts = (('.jpg', '.webp', '.png'), ('.description',), ('.en.vtt', '.en.srt'), ('.info.json',))
    for meta_exts in meta_file_exts:
        for meta_ext in meta_exts:
            meta_path = path.with_suffix(meta_ext)
            if meta_path.exists():
                yield meta_path
                break
        else:
            yield None
