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

from dictorm import DictDB, Dict
from sanic import Blueprint, response

from api.common import create_websocket_feed, get_sanic_url, \
    validate_doc, FeedReporter
from api.db import get_db_context
from api.videos.channel import channel_bp
from api.videos.video import video_bp
from .captions import insert_bulk_captions
from .common import logger, generate_video_paths, get_absolute_media_path, generate_bulk_thumbnails, \
    get_bulk_video_duration
from .downloader import update_channels, download_all_missing_videos, upsert_video, update_channel
from .schema import StreamResponse, \
    JSONErrorResponse

content_bp = Blueprint('Video Content')
api_bp = Blueprint('Videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
    url_prefix='/videos')

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
            refresh_videos_with_db(channel_links)

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

            if link:
                with get_db_context(commit=True) as (db_conn, db):
                    update_channel(db_conn, db, link=link)
            else:
                with get_db_context(commit=True) as (db_conn, db):
                    for msg in update_channels(db_conn, db):
                        download_queue.put(msg)
                    download_logger.info('Updated all channel catalogs')
                    for msg in download_all_missing_videos(db_conn, db):
                        download_queue.put(msg)

            download_logger.info('download complete')
        except Exception as e:
            download_queue.put({'error': 'Download failed.  See server logs.'})
            raise
        finally:
            download_event.clear()

    coro = do_download()
    asyncio.ensure_future(coro)
    download_logger.debug('do_download scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


def refresh_channel_videos(db: DictDB, channel: Dict, reporter: FeedReporter):
    """
    Find all video files in a channel's directory.  Add any videos not in the DB to the DB.
    """
    reporter.set_progress(1, 0)

    # Set the idempotency key so we can remove any videos not touched during this search
    curs = db.get_cursor()
    curs.execute('UPDATE video SET idempotency=NULL WHERE channel_id=%s', (channel['id'],))
    idempotency = str(uuid1())
    directory = get_absolute_media_path(channel['directory'])

    # A set of absolute paths that exist in the file system
    possible_new_paths = set(generate_video_paths(directory))
    reporter.message('Found all possible video files')

    # Update all videos that match the current video paths
    query = 'UPDATE video SET idempotency = %s WHERE channel_id = %s AND video_path = ANY(%s) RETURNING video_path'
    relative_new_paths = [str(i.relative_to(directory)) for i in possible_new_paths]
    curs.execute(query, (idempotency, channel['id'], relative_new_paths))
    existing_paths = {i for (i,) in curs.fetchall()}

    # Get the paths for any video not yet in the DB
    # (paths in DB are relative, but we need to pass an absolute path)
    new_videos = {p for p in possible_new_paths if str(p.relative_to(directory)) not in existing_paths}

    for video_path in new_videos:
        upsert_video(db, pathlib.Path(video_path), channel, idempotency=idempotency)
        logger.debug(f'{channel["name"]}: Added {video_path}')

    reporter.message('Matched all existing video files')

    curs.execute('DELETE FROM video WHERE channel_id=%s AND idempotency IS NULL RETURNING id', (channel['id'],))
    deleted_count = curs.fetchall()
    if deleted_count:
        deleted_count = len(deleted_count)
        deleted_status = f'Deleted {deleted_count} video records from channel {channel["name"]}'
        logger.info(deleted_status)
        reporter.message(deleted_status)

    status = f'{channel["name"]}: {len(new_videos)} new videos, {len(existing_paths)} already existed. '
    logger.info(status)
    reporter.message(status)

    # Commit all insertions and deletions
    db.conn.commit()

    # Fill in any missing captions
    query = 'SELECT id FROM video WHERE channel_id=%s AND caption IS NULL AND caption_path IS NOT NULL'
    curs.execute(query, (channel['id'],))
    missing_captions = [i for (i,) in curs.fetchall()]

    if missing_captions:
        coro = insert_bulk_captions(missing_captions)
        asyncio.ensure_future(coro)
    else:
        logger.debug('No missing captions to process.')

    # Generate any missing posters
    query = 'SELECT id FROM video WHERE channel_id=%s AND poster_path IS NULL'
    curs.execute(query, (channel['id'],))
    missing_posters = [i for (i,) in curs.fetchall()]

    if missing_posters:
        coro = generate_bulk_thumbnails(missing_posters)
        asyncio.ensure_future(coro)
    else:
        logger.debug('No missing posters to generate.')

    # Get the duration of any video that is missing it's duration
    query = 'SELECT id FROM video WHERE channel_id=%s AND duration IS NULL'
    curs.execute(query, (channel['id'],))
    missing_duration = [i for (i,) in curs.fetchall()]

    if missing_duration:
        coro = get_bulk_video_duration(missing_duration)
        asyncio.ensure_future(coro)
    else:
        logger.debug('No videos missing duration')


def _refresh_videos(db: DictDB, q: Queue, channel_links: list = None):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :param db:
    :return:
    """
    logger.info('Refreshing video files')
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
        with db.transaction(commit=True):
            refresh_channel_videos(db, channel, reporter)
    reporter.set_progress(0, 100, 'All videos refreshed.')
    reporter.code('refresh-complete')


@wraps(_refresh_videos)
def refresh_videos(db: DictDB, channel_links: list = None):
    return _refresh_videos(db, refresh_queue, channel_links=channel_links)


@wraps(_refresh_videos)
def refresh_videos_with_db(channel_links: list = None):
    with get_db_context(commit=True) as (db_conn, db):
        return refresh_videos(db, channel_links=channel_links)


@wraps(refresh_videos_with_db)
async def async_refresh_videos_with_db(channel_links: list = None):
    return refresh_videos_with_db(channel_links)
