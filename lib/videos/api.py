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
from multiprocessing import Queue
from uuid import uuid1

from dictorm import DictDB, Dict
from sanic import Blueprint, response
from sanic.request import Request

from lib.common import create_websocket_feed, get_sanic_url, \
    validate_doc, FeedReporter
from lib.db import get_db_context
from lib.videos.channel import channel_bp
from lib.videos.video import video_bp
from .captions import process_captions
from .common import generate_video_paths, save_settings_config, get_downloader_config, \
    get_absolute_channel_directory
from .common import logger
from .downloader import insert_video, update_channels, download_all_missing_videos
from .schema import DownloaderConfig, SuccessResponse, StreamResponse, \
    JSONErrorResponse

content_bp = Blueprint('Video Content')
api_bp = Blueprint('Videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
    url_prefix='/videos')


@content_bp.put('/settings')
@validate_doc(
    summary='Update video settings config',
    consumes=DownloaderConfig,
    produces=SuccessResponse,
)
def settings(request: Request, data: dict):
    downloader_config = get_downloader_config()
    downloader_config['video_root_directory'] = data['video_root_directory']
    downloader_config['file_name_format'] = data['file_name_format']
    save_settings_config(downloader_config)
    return response.json({'success': 'Settings saved'})


refresh_queue, refresh_event = create_websocket_feed('/feeds/refresh', content_bp)


@content_bp.post('/settings:refresh')
@validate_doc(
    summary='Search for videos that have previously been downloaded and stored.',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ],
)
async def refresh(_):
    refresh_logger = logger.getChild('refresh')
    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/refresh')

    # Only one refresh can run at a time
    if refresh_event.is_set():
        return response.json({'error': 'Refresh already running', 'stream_url': stream_url}, HTTPStatus.CONFLICT)

    refresh_event.set()

    async def do_refresh():
        try:
            refresh_logger.info('refresh started')

            with get_db_context(commit=True) as (db_conn, db):
                _refresh_videos(db, refresh_queue)

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


download_queue, download_event = create_websocket_feed('/feeds/download', content_bp)


@content_bp.post('/settings:download')
@validate_doc(
    summary='Update channel catalogs, download any missing videos',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ],
)
async def download(_):
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
    directory = get_absolute_channel_directory(channel['directory'])

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
        logger.debug(f'{channel["name"]}: Added {video_path}')
        insert_video(db, pathlib.Path(video_path), channel, idempotency=idempotency)

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

    # Fill in any missing captions
    query = 'SELECT id FROM video WHERE channel_id=%s AND caption IS NULL AND caption_path IS NOT NULL'
    curs.execute(query, (channel['id'],))
    missing_captions = [i for (i,) in curs.fetchall()]
    reporter.set_progress_total(1, len(missing_captions))
    Video = db['video']
    for idx, video_id in enumerate(missing_captions):
        video = Video.get_one(id=video_id)
        process_captions(video)
        reporter.set_progress(1, idx, f'Processed captions for video {video_id}')

    status = f'Processed {len(missing_captions)} missing captions.'
    logger.info(status)
    reporter.set_progress(1, len(missing_captions), status)


def _refresh_videos(db: DictDB, q: Queue):
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

    for idx, channel in enumerate(Channel.get_where()):
        reporter.set_progress(0, idx, f'Checking {channel["name"]} directory for new videos')
        with db.transaction(commit=True):
            refresh_channel_videos(db, channel, reporter)
    reporter.set_progress(0, 100, 'All videos refreshed.')
    reporter.code('refresh-complete')


@wraps(_refresh_videos)
def refresh_videos(db: DictDB):
    return _refresh_videos(db, refresh_queue)


@wraps(_refresh_videos)
def refresh_videos_with_db():
    with get_db_context(commit=True) as (db_conn, db):
        return refresh_videos(db)
