from http import HTTPStatus

from sanic import Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger
from . import lib, schema
from .channel.api import channel_bp
from .video.api import video_bp

content_bp = Blueprint('VideoContent', '/api/videos')
videos_bp = Blueprint('Videos', '/api/videos').group(
    content_bp,  # view and manage video content and settings
    channel_bp,  # view and manage channels
    video_bp,  # view videos
)

logger = logger.getChild(__name__)


@content_bp.get('/statistics')
@openapi.response(HTTPStatus.OK, schema.VideosStatisticsResponse)
async def statistics(_: Request):
    ret = await lib.get_statistics()
    return json_response(ret, HTTPStatus.OK)
