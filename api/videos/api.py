"""
This module contains the Sanic routes, as well as functions necessary to retrieve video files.  This module also
contains functions that will search the file structure for video files, as well as cleanup the DB video records.

All paths in the DB are relative.  A Channel's directory is relative to the video_root_directory.  A Video's path (as
well as its meta files) is relative to its Channel's directory.

    Example:
        Real Paths:
            video_root_directory = '/media/something'
            channel['directory'] = '/media/something/the channel'
            video['video_path'] = '/media/something/the channel/foo.mp4'
            video['poster_path'] = '/media/something/the channel/foo.jpg'
            video['video_path'] = '/media/something/the channel/subdir/bar.mp4'

        The same paths in the DB:
            channel['directory'] = 'the channel'
            video['video_path'] = 'foo.mp4'
            video['poster_path'] = 'foo.jpg'
            video['video_path'] = 'subdir/bar.mp4'

Relative DB paths allow files to be moved without having to rebuild the entire collection.  It also ensures that when
a file is moved, it will not be duplicated in the DB.
"""
import asyncio
import pathlib
from functools import wraps
from http import HTTPStatus
from multiprocessing.queues import Queue
from uuid import uuid1

from dictorm import Dict
from sanic import Blueprint, response
from sanic.request import Request

from api.common import create_websocket_feed, get_sanic_url, \
    validate_doc, FeedReporter, json_response, wrol_mode_check
from api.db import get_db_context, get_db_curs
from api.videos.channel import channel_bp
from api.videos.video import video_bp
from .captions import insert_bulk_captions
from .common import logger, generate_video_paths, get_absolute_media_path, generate_bulk_thumbnails, \
    get_bulk_video_duration, toggle_video_favorite, get_bulk_video_size
from .downloader import update_channels, download_all_missing_videos, upsert_video
from .schema import StreamResponse, \
    JSONErrorResponse, FavoriteRequest, FavoriteResponse, VideosStatisticsResponse

content_bp = Blueprint('Video Content')
api_bp = Blueprint('Videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
    url_prefix='/videos')

logger = logger.getChild(__name__)

refresh_queue, refresh_event = create_websocket_feed('refresh', '/feeds/refresh', content_bp)


@content_bp.post(':refresh')
@content_bp.post(':refresh/<link:string>')
@validate_doc(
    summary='Search for videos that have previously been downloaded and stored.',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ],
)
@wrol_mode_check
async def refresh(_, link: str = None):
    refresh_logger = logger.getChild('refresh')
    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/refresh')

    # Only one refresh can run at a time
    if refresh_event.is_set():
        return response.json({'error': 'Refresh already running', 'stream_url': stream_url}, HTTPStatus.CONFLICT)

    refresh_event.set()

    async def do_refresh():
        try:
            refresh_logger.info('refresh started')

            channel_links = [link] if link else None
            await refresh_videos(channel_links)

            refresh_logger.info('refresh complete')
        except Exception as e:
            refresh_queue.put({'error': 'Refresh failed.  See server logs.'})
            raise
        finally:
            refresh_event.clear()

    coro = do_refresh()
    asyncio.ensure_future(coro)
    refresh_logger.debug('do_refresh scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


download_queue, download_event = create_websocket_feed('download', '/feeds/download', content_bp)


@content_bp.post(':download')
@content_bp.post(':download/<link:string>')
@validate_doc(
    summary='Update channel catalogs, download any missing videos',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ],
)
@wrol_mode_check
async def download(_, link: str = None):
    download_logger = logger.getChild('download')

    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/download')
    # Only one download can run at a time
    if download_event.is_set():
        return response.json({'error': 'download already running', 'stream_url': stream_url}, HTTPStatus.CONFLICT)

    download_event.set()
    download_queue.put('download-started')

    async def do_download():
        try:
            download_logger.info('download started')

            for msg in update_channels(link):
                download_queue.put(msg)
            download_logger.info('Updated all channel catalogs')
            for msg in download_all_missing_videos(link):
                download_queue.put(msg)

            # Fill in any missing data for all videos.
            process_video_meta_data()

            download_logger.info('download complete')
        except Exception as e:
            logger.fatal(f'Download failed: {e}')
            download_queue.put({'error': 'Download failed.  See server logs.'})
            raise
        finally:
            download_event.clear()

    coro = do_download()
    asyncio.ensure_future(coro)
    download_logger.debug('do_download scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


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
        coro = generate_bulk_thumbnails(missing_posters)
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
    possible_new_paths = set(generate_video_paths(directory))
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


@wraps(_refresh_videos)
async def refresh_videos(channel_links: list = None):
    return _refresh_videos(refresh_queue, channel_links=channel_links)


@content_bp.post(':favorite')
@validate_doc(
    summary='Toggle the favorite flag on a video',
    consumes=FavoriteRequest,
    produces=FavoriteResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ]
)
async def favorite(_: Request, data: dict):
    _favorite = toggle_video_favorite(data['video_id'], data['favorite'])
    ret = {'video_id': data['video_id'], 'favorite': _favorite}
    return json_response(ret, HTTPStatus.OK)


@content_bp.get('/statistics')
@validate_doc(
    summary='Retrieve video statistics',
    produces=VideosStatisticsResponse,
)
async def statistics(_: Request):
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
            COALESCE(SUM(size)::BIGINT, 0) AS "sum_size",
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
    return json_response(ret, HTTPStatus.OK)
