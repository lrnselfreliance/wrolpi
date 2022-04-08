import asyncio
from functools import wraps
from http import HTTPStatus
from typing import List

from sanic import Blueprint, response
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import create_websocket_feed, get_sanic_url, \
    wrol_mode_check
from wrolpi.common import logger
from wrolpi.root_api import add_blueprint, json_response
from wrolpi.schema import JSONErrorResponse
from . import lib, schema
from .channel import lib as channel_lib
from .channel.api import channel_bp
from .video import lib as video_lib
from .video.api import video_bp

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
@content_bp.post('/refresh/<channel_id:str>')
@openapi.description('Search for videos that have previously been downloaded and stored.')
@openapi.response(HTTPStatus.OK, schema.StreamResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def refresh(_, channel_id: int = None):
    refresh_logger = logger.getChild('refresh')
    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/refresh')

    # Only one refresh can run at a time
    if refresh_event.is_set():
        return response.json({'error': 'Refresh already running', 'stream_url': stream_url}, HTTPStatus.CONFLICT)

    refresh_event.set()

    async def do_refresh():
        try:
            refresh_logger.info('refresh started')

            channel_ids = [channel_id] if channel_id else None
            await refresh_videos(channel_ids)

            refresh_logger.info('refresh complete')
        except Exception:
            raise
        finally:
            refresh_event.clear()

    coro = do_refresh()
    asyncio.ensure_future(coro)
    refresh_logger.debug('do_refresh scheduled')
    return response.json({'code': 'stream-started', 'stream_url': stream_url})


@content_bp.post('/download/<channel_id:int>')
@openapi.description('Update a channel catalog, download any missing videos')
@openapi.response(HTTPStatus.OK, schema.StreamResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
def download(_, channel_id: int = None):
    channel_lib.download_channel(channel_id)
    return response.empty()


@wraps(lib.refresh_videos)
async def refresh_videos(channel_ids: List[int] = None):
    return lib.refresh_videos(channel_ids=channel_ids)


@content_bp.post('/favorite')
@openapi.definition(
    description='Toggle the favorite flag on a video',
    body=schema.FavoriteRequest,
)
@validate(schema.FavoriteRequest)
@openapi.response(HTTPStatus.OK, schema.FavoriteResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
async def favorite(_: Request, body: schema.FavoriteRequest):
    _favorite = video_lib.set_video_favorite(body.video_id, body.favorite)
    ret = {'video_id': body.video_id, 'favorite': _favorite}
    return json_response(ret, HTTPStatus.OK)


@content_bp.get('/statistics')
@openapi.response(HTTPStatus.OK, schema.VideosStatisticsResponse)
async def statistics(_: Request):
    ret = await lib.get_statistics()
    return json_response(ret, HTTPStatus.OK)
