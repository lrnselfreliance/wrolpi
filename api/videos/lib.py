import asyncio
import pathlib
from multiprocessing.queues import Queue
from typing import List
from uuid import uuid1

from dictorm import Dict

from api.common import FeedReporter, save_settings_config, sanitize_link
from api.db import get_db_curs, get_db_context
from api.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from api.videos.captions import insert_bulk_captions
from api.videos.common import generate_bulk_posters, get_bulk_video_duration, get_bulk_video_size, \
    get_absolute_media_path, generate_video_paths, remove_duplicate_video_paths, get_relative_to_media_directory, \
    make_media_directory, check_for_channel_conflicts
from api.videos.downloader import upsert_video
from ..common import logger

logger = logger.getChild(__name__)


def refresh_channel_video_captions() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE caption IS NULL AND caption_path IS NOT NULL'
        curs.execute(query)
        missing_captions = [i for (i,) in curs.fetchall()]

    if missing_captions:
        coro = insert_bulk_captions(missing_captions)
        asyncio.ensure_future(coro)
        return True
    else:
        logger.debug('No missing captions to process.')
        return False


def refresh_channel_generate_posters() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE video_path IS NOT NULL AND poster_path IS NULL'
        curs.execute(query)
        missing_posters = [i for (i,) in curs.fetchall()]

    if missing_posters:
        coro = generate_bulk_posters(missing_posters)
        asyncio.ensure_future(coro)
        return True
    else:
        logger.debug('No missing posters to generate.')
        return False


def refresh_channel_calculate_duration() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE video_path IS NOT NULL AND duration IS NULL'
        curs.execute(query)
        missing_duration = [i for (i,) in curs.fetchall()]

    if missing_duration:
        coro = get_bulk_video_duration(missing_duration)
        asyncio.ensure_future(coro)
        return True
    else:
        logger.debug('No videos missing duration.')
        return False


def refresh_channel_calculate_size() -> bool:
    with get_db_curs() as curs:
        query = 'SELECT id FROM video WHERE video_path IS NOT NULL AND size IS NULL'
        curs.execute(query)
        missing_size = [i for (i,) in curs.fetchall()]

    if missing_size:
        coro = get_bulk_video_size(missing_size)
        asyncio.ensure_future(coro)
        return True
    else:
        logger.debug('No videos missing size.')
        return False


def process_video_meta_data():
    """
    Search for any videos missing meta data, fill in that data.
    """
    refresh_channel_video_captions()
    refresh_channel_generate_posters()
    refresh_channel_calculate_duration()
    refresh_channel_calculate_size()


def refresh_channel_videos(channel: Dict, reporter: FeedReporter):
    """
    Find all video files in a channel's directory.  Add any videos not in the DB to the DB.
    """
    reporter.set_progress(1, 0)

    # Set the idempotency key so we can remove any videos not touched during this search
    with get_db_curs(commit=True) as curs:
        curs.execute('UPDATE video SET idempotency=NULL WHERE channel_id=%s', (channel['id'],))

    idempotency = str(uuid1())
    directory = get_absolute_media_path(channel['directory'])

    # A set of absolute paths that exist in the file system
    possible_new_paths = generate_video_paths(directory)
    possible_new_paths = remove_duplicate_video_paths(possible_new_paths)
    reporter.message('Found all possible video files')

    # Update all videos that match the current video paths
    relative_new_paths = [str(i.relative_to(directory)) for i in possible_new_paths]
    with get_db_curs(commit=True) as curs:
        query = 'UPDATE video SET idempotency = %s WHERE channel_id = %s AND video_path = ANY(%s) RETURNING video_path'
        curs.execute(query, (idempotency, channel['id'], relative_new_paths))
        existing_paths = {i for (i,) in curs.fetchall()}

    # Get the paths for any video not yet in the DB
    # (paths in DB are relative, but we need to pass an absolute path)
    new_videos = {p for p in possible_new_paths if str(p.relative_to(directory)) not in existing_paths}

    for video_path in new_videos:
        with get_db_context(commit=True) as (db_conn, db):
            upsert_video(db, pathlib.Path(video_path), channel, idempotency=idempotency)
            logger.debug(f'{channel["name"]}: Added {video_path}')

    reporter.message('Matched all existing video files')

    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM video WHERE channel_id=%s AND idempotency IS NULL RETURNING id', (channel['id'],))
        deleted_count = len(curs.fetchall())

    if deleted_count:
        deleted_status = f'Deleted {deleted_count} video records from channel {channel["name"]}'
        logger.info(deleted_status)
        reporter.message(deleted_status)

    status = f'{channel["name"]}: {len(new_videos)} new videos, {len(existing_paths)} already existed. '
    logger.info(status)
    reporter.message(status)


def _refresh_videos(q: Queue, channel_links: list = None):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :return:
    """
    logger.info('Refreshing video files')
    with get_db_context() as (db_conn, db):
        Channel = db['channel']

        reporter = FeedReporter(q, 2)
        reporter.code('refresh-started')
        reporter.set_progress_total(0, Channel.count())

        if channel_links:
            channels = Channel.get_where(Channel['link'].In(channel_links))
        else:
            channels = Channel.get_where()

        channels = list(channels)

    if not channels and channel_links:
        raise Exception(f'No channels match links(s): {channel_links}')
    elif not channels:
        raise Exception(f'No channels in DB.  Have you created any?')

    for idx, channel in enumerate(channels):
        reporter.set_progress(0, idx, f'Checking {channel["name"]} directory for new videos')
        refresh_channel_videos(channel, reporter)

    # Fill in any missing data for all videos.
    process_video_meta_data()

    reporter.set_progress(0, 100, 'All videos refreshed.')
    reporter.code('refresh-complete')


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


async def get_minimal_channels() -> List[dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_context() as (db_conn, db):
        curs = db.get_cursor()

        # Get all channels, even if they don't have videos.
        query = '''
            SELECT
                c.id, name, link, directory, url
            FROM
                channel AS c
            ORDER BY LOWER(name)
        '''
        curs.execute(query)
        channels = list(map(dict, curs.fetchall()))

        # Add video counts to all channels
        query = '''
            SELECT
                c.id, COUNT(v.id) AS video_count
            FROM
                channel AS c
                LEFT JOIN video AS v ON v.channel_id = c.id
            WHERE
                v.video_path IS NOT NULL
            GROUP BY 1
        '''
        curs.execute(query)
        video_counts = {i['id']: i['video_count'] for i in curs.fetchall()}

        for channel in channels:
            channel_id = channel['id']
            try:
                channel['video_count'] = video_counts[channel_id]
            except KeyError:
                # No videos for this channel
                channel['video_count'] = 0

    return channels


def delete_channel(link):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            raise UnknownChannel()
        with db.transaction(commit=True):
            # Delete all videos in this channel
            curs = db.get_cursor()
            query = 'DELETE FROM video WHERE channel_id = %s'
            curs.execute(query, (channel['id'],))

            # Finally, delete the channel
            channel.delete()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)


def update_channel(data, link):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        with db.transaction(commit=True):
            channel = Channel.get_one(link=link)

            if not channel:
                raise UnknownChannel()

            # Only update directory if it was empty
            if data.get('directory') and not channel['directory']:
                try:
                    data['directory'] = get_relative_to_media_directory(data['directory'])
                except UnknownDirectory:
                    if data['mkdir']:
                        make_media_directory(data['directory'])
                        data['directory'] = get_relative_to_media_directory(data['directory'])
                    else:
                        raise

            if 'directory' in data:
                data['directory'] = str(data['directory'])

            # Verify that the URL/Name/Link aren't taken
            check_for_channel_conflicts(
                db=db,
                id=channel.get('id'),
                url=data.get('url'),
                name=data.get('name'),
                link=data.get('link'),
                directory=data.get('directory'),
            )

            # Apply the changes now that we've OK'd them
            channel.update(data)
            channel.flush()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)

    return channel


def get_channels_config(db) -> dict:
    """
    Create a dictionary that contains all the Channels from the DB.
    """
    Channel = db['channel']
    channels = {
        i['link']:
            dict(
                directory=i['directory'],
                match_regex=i.get('match_regex', ''),
                name=i['name'],
                url=i.get('url', ''),
                generate_posters=i['generate_posters'],
                calculate_duration=i['calculate_duration'],
                skip_download_videos=[j for j in i['skip_download_videos'] if j] if i['skip_download_videos'] else [],
            )
        for i in Channel.get_where().order_by('link')
    }
    return dict(channels=channels)


def get_channel(link) -> dict:
    with get_db_context() as (db_conn, db):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            raise UnknownChannel()
        return dict(channel)


def create_channel(data):
    with get_db_context() as (db_conn, db):
        Channel = db['channel']

        # Verify that the URL/Name/Link aren't taken
        try:
            check_for_channel_conflicts(
                db,
                url=data.get('url'),
                name=data['name'],
                link=sanitize_link(data['name']),
                directory=str(data['directory']),
            )
        except APIError as e:
            raise ValidationError from e

        with db.transaction(commit=True):
            channel = Channel(
                name=data['name'],
                url=data.get('url'),
                match=data.get('match_regex'),
                link=sanitize_link(data['name']),
                directory=str(data['directory']),
            )
            channel.flush()

        # Save these changes to the local.yaml as well
        channels = get_channels_config(db)
        save_settings_config(channels)

        return dict(channel)
