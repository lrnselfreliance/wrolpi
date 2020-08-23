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
from functools import wraps
from http import HTTPStatus

from sanic import Blueprint, response
from sanic.request import Request

from api.common import create_websocket_feed, get_sanic_url, \
    validate_doc, json_response, wrol_mode_check, FeedReporter
from api.videos.channel.api import channel_bp
from api.videos.video.api import video_bp
from .common import logger
from .downloader import update_channels, download_all_missing_videos
from .lib import process_video_meta_data, _refresh_videos, get_statistics
from .schema import StreamResponse, \
    JSONErrorResponse, FavoriteRequest, FavoriteResponse, VideosStatisticsResponse
from .video.lib import set_video_favorite

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

    async def do_download():
        reporter = FeedReporter(download_queue, 2)
        reporter.set_progress_total(0, 1)
        reporter.set_progress(0, 1, 'Download started')

        try:
            update_channels(reporter, link)
            download_logger.info('Updated all channel catalogs')
            download_all_missing_videos(reporter, link)
            reporter.finish(1, 'All videos have been downloaded')

            # Fill in any missing data for all videos.
            reporter.message(0, 'Processing and cleaning files')
            process_video_meta_data()
            reporter.finish(0, 'Processing and cleaning complete')

            download_logger.info('download complete')
        except Exception as e:
            logger.fatal(f'Download failed: {e}')
            reporter.error('Download failed.  See server logs.')
            raise
        finally:
            download_event.clear()

    coro = do_download()
    asyncio.ensure_future(coro)
    download_logger.debug('do_download scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


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
    _favorite = set_video_favorite(data['video_id'], data['favorite'])
    ret = {'video_id': data['video_id'], 'favorite': _favorite}
    return json_response(ret, HTTPStatus.OK)


@content_bp.get('/statistics')
@validate_doc(
    summary='Retrieve video statistics',
    produces=VideosStatisticsResponse,
)
async def statistics(_: Request):
    ret = await get_statistics()
    return json_response(ret, HTTPStatus.OK)
