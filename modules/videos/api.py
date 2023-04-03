from http import HTTPStatus

from sanic import Blueprint, response
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger
from wrolpi.root_api import add_blueprint, json_response
from wrolpi.schema import JSONErrorResponse
from . import lib, schema
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


@content_bp.post('/tag')
@openapi.definition(
    description='Associate a Video with a Tag',
    body=schema.TagRequest,
)
@validate(schema.TagRequest)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
async def tag(_: Request, body: schema.TagRequest):
    video_lib.tag_video(body.video_id, body.tag_name)
    return response.empty()


@content_bp.get('/statistics')
@openapi.response(HTTPStatus.OK, schema.VideosStatisticsResponse)
async def statistics(_: Request):
    ret = await lib.get_statistics()
    return json_response(ret, HTTPStatus.OK)
