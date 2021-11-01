import asyncio
import random
from functools import wraps
from http import HTTPStatus
from multiprocessing import Event

import requests
from sanic import Blueprint, response
from sanic.request import Request

from wrolpi import before_startup
from wrolpi.common import create_websocket_feed, get_sanic_url, \
    wrol_mode_check, ProgressReporter, get_config
from wrolpi.common import logger
from wrolpi.root_api import add_blueprint, json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from .channel.api import channel_bp
from .downloader import update_channels, download_all_missing_videos
from .lib import process_video_meta_data, _refresh_videos, get_statistics, get_download_history
from .schema import StreamResponse, \
    FavoriteRequest, FavoriteResponse, VideosStatisticsResponse, DownloadHistoryResponse
from .video.api import video_bp
from .video.lib import set_video_favorite

content_bp = Blueprint('Video Content', '/api/videos')
bp = Blueprint('Videos', '/api/videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
)
add_blueprint(bp)

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
            refresh_queue.put({'error': 'Refresh failed.  See server logs.', 'message': str(e)})
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
    if refresh_event.is_set():
        return response.json({'error': 'Refresh is running.  Cannot download.'})

    download_event.set()

    async def do_download():
        reporter = ProgressReporter(download_queue, 2)
        reporter.set_progress_total(0, 1)
        reporter.send_progress(0, 1, 'Download started')

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
            reporter.error(0, 'Download failed.  See server logs.')
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


@content_bp.get('/download_history')
@validate_doc(
    summary='Retrieve video download history',
    produces=DownloadHistoryResponse,
)
async def download_history(_: Request):
    history = await get_download_history()
    ret = dict(history=history)
    return json_response(ret, HTTPStatus.OK)


MIN_DOWNLOAD_FREQUENCY = 60 * 60 * 4  # 4 hours
MAX_DOWNLOAD_FREQUENCY = 60 * 60 * 12  # 12 hours
PERIODIC_DOWNLOAD_EVENT = Event()


async def _periodic_download(min_download_frequency: int, max_download_frequency: int):
    """
    Wait some amount of time, download, then schedule the next download.
    """
    sleep_seconds = random.randint(min_download_frequency, max_download_frequency)
    logger.debug(f'Waiting {sleep_seconds} seconds before next periodic download')
    await asyncio.sleep(sleep_seconds)

    url = get_sanic_url(path='/api/videos:download')
    resp = requests.post(url)
    if resp.status_code != HTTPStatus.OK and resp.status_code != HTTPStatus.CONFLICT:
        # Download failed and wasn't already running.
        logger.warning(f'Periodic download failed with status_code={resp.status_code}')
        logger.warning(f'Periodic download response={resp}')

    # Schedule the next download
    asyncio.ensure_future(_periodic_download(min_download_frequency, max_download_frequency))


@before_startup
def start_periodic_download():
    """
    Periodically download the videos.
    """
    if not PERIODIC_DOWNLOAD_EVENT.is_set():
        PERIODIC_DOWNLOAD_EVENT.set()
        logger.info(f'Starting periodic download')

        config = get_config()
        try:
            min_download_frequency = int(config.get('min_download_frequency', MIN_DOWNLOAD_FREQUENCY))
            max_download_frequency = int(config.get('max_download_frequency', MAX_DOWNLOAD_FREQUENCY))
        except Exception:
            logger.fatal(f'Failed to get min/max download frequencies from config!', exc_info=True)
            raise

        asyncio.ensure_future(_periodic_download(min_download_frequency, max_download_frequency))
