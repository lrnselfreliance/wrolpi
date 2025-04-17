from http import HTTPStatus

from sanic import Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger
from . import lib, schema
from .channel.api import channel_bp
from .downloader import preview_filename
from .lib import format_videos_destination
from .models import Channel
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


@content_bp.post('/tag_info')
@openapi.definition(
    description='Get data about tagging a Channel',
    body=schema.ChannelTagInfoRequest,
)
@validate(schema.ChannelTagInfoRequest)
async def channel_tag_info(_: Request, body: schema.ChannelTagInfoRequest):
    from wrolpi.tags import Tag
    channel = Channel.find_by_id(body.channel_id) if body.channel_id else None
    channel_name = channel.name if channel else None
    channel_url = channel.url if channel else None
    tag_name = Tag.find_by_name(body.tag_name).name if body.tag_name else None
    videos_destination = format_videos_destination(channel_name, tag_name, channel_url)
    ret = dict(videos_destination=videos_destination)
    return json_response(ret)


@content_bp.post('/file_format')
@openapi.definition(
    description='Preview the video file format',
    body=schema.VideoFileFormatRequest,
)
@validate(schema.VideoFileFormatRequest)
async def post_file_format(_: Request, body: schema.VideoFileFormatRequest):
    try:
        preview = preview_filename(body.video_file_format)
        return json_response(dict(
            video_file_format=body.video_file_format,
            preview=preview,
        ))
    except RuntimeError as e:
        return json_response(dict(
            error=str(e),
            video_file_format=body.video_file_format,
        ), status=HTTPStatus.BAD_REQUEST)


@content_bp.get('/browser-profiles')
async def get_browser_profiles(_: Request):
    browser_profiles = lib.get_browser_profiles()
    return json_response(browser_profiles)
