import asyncio
from functools import wraps
from http import HTTPStatus

from sanic import Blueprint, response
from sanic.request import Request

from wrolpi import before_startup
from wrolpi.common import create_websocket_feed, get_sanic_url, \
    wrol_mode_check
from wrolpi.common import logger
from wrolpi.root_api import add_blueprint, json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from .channel.api import channel_bp
from .channel.lib import download_channel, spread_channel_downloads
from .lib import _refresh_videos, get_statistics
from .schema import StreamResponse, \
    FavoriteRequest, FavoriteResponse, VideosStatisticsResponse
from .video.api import video_bp
from .video.lib import set_video_favorite, censored_videos

content_bp = Blueprint('VideoContent', '/api/videos')
bp = Blueprint('Videos', '/api/videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
)
add_blueprint(bp)

logger = logger.getChild(__name__)

refresh_queue, refresh_event = create_websocket_feed('refresh', '/feeds/refresh', content_bp)


@content_bp.post('/refresh')
@content_bp.post('/refresh/<link:str>')
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
        except Exception:
            raise
        finally:
            refresh_event.clear()

    coro = do_refresh()
    asyncio.ensure_future(coro)
    refresh_logger.debug('do_refresh scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


download_queue, download_event = create_websocket_feed('download', '/feeds/download', content_bp)


@content_bp.post('/download')
@content_bp.post('/download/<link:str>')
@validate_doc(
    summary='Update channel catalogs, download any missing videos',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ],
)
@wrol_mode_check
def download(_, link: str = None):
    download_logger = logger.getChild('download')

    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/download')
    # Only one download can run at a time
    if download_event.is_set():
        return response.json({'error': 'download already running', 'stream_url': stream_url}, HTTPStatus.CONFLICT)
    if refresh_event.is_set():
        return response.json({'error': 'Refresh is running.  Cannot download.'})

    download_channel(link)

    download_logger.debug('do_download scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


@wraps(_refresh_videos)
async def refresh_videos(channel_links: list = None):
    return _refresh_videos(channel_links=channel_links)


@content_bp.post('/favorite')
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


@before_startup
def startup_spread_channel_downloads():
    spread_channel_downloads()


@content_bp.get('/censored')
@content_bp.get('/censored/<link:str>')
@validate_doc(
    summary='Get all videos that were deleted on their source website',
)
async def get_censored_videos(_: Request, link: str = None):
    videos = censored_videos(link=link)
    ret = {'videos': videos}
    return json_response(ret)
