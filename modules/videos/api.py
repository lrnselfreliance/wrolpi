from http import HTTPStatus

from sanic import Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger
from . import lib, schema
from . import cookies
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
async def channel_tag_info(request: Request, body: schema.ChannelTagInfoRequest):
    from wrolpi.tags import Tag
    session = request.ctx.session
    channel = Channel.find_by_id(session, body.channel_id) if body.channel_id else None
    channel_name = channel.name if channel else None
    channel_url = channel.url if channel else None
    tag_name = Tag.find_by_name(session, body.tag_name).name if body.tag_name else None
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


@content_bp.post('/cookies')
@openapi.definition(
    description='Upload and encrypt cookies for yt-dlp',
    body=schema.CookiesUploadRequest,
)
@validate(schema.CookiesUploadRequest)
async def upload_cookies(_: Request, body: schema.CookiesUploadRequest):
    """Upload cookies content, encrypt with password, and save."""
    try:
        cookies.save_encrypted_cookies(body.cookies_content, body.password)
        return json_response({'success': True}, HTTPStatus.CREATED)
    except ValueError as e:
        return json_response({'error': str(e)}, HTTPStatus.BAD_REQUEST)


@content_bp.get('/cookies/status')
@openapi.response(HTTPStatus.OK, schema.CookiesStatusResponse)
async def get_cookies_status(_: Request):
    """Get cookies status (exist? unlocked?)."""
    status = cookies.get_cookies_status()
    return json_response(status)


@content_bp.delete('/cookies')
async def delete_cookies(_: Request):
    """Delete stored encrypted cookies."""
    deleted = cookies.delete_cookies()
    if deleted:
        return json_response({'success': True}, HTTPStatus.NO_CONTENT)
    else:
        return json_response({'error': 'No cookies file found'}, HTTPStatus.NOT_FOUND)


@content_bp.post('/cookies/unlock')
@openapi.definition(
    description='Decrypt cookies to memory for session use',
    body=schema.CookiesUnlockRequest,
)
@validate(schema.CookiesUnlockRequest)
async def unlock_cookies(_: Request, body: schema.CookiesUnlockRequest):
    """Unlock cookies by decrypting to memory."""
    try:
        cookies.unlock_cookies(body.password)
        return json_response({'success': True})
    except FileNotFoundError:
        return json_response({'error': 'No cookies file found'}, HTTPStatus.NOT_FOUND)
    except ValueError as e:
        return json_response({'error': str(e)}, HTTPStatus.BAD_REQUEST)


@content_bp.post('/cookies/lock')
async def lock_cookies(_: Request):
    """Lock cookies by clearing from memory."""
    cookies.lock_cookies()
    return json_response({'success': True})


@content_bp.get('/suggested-user-agent')
async def get_suggested_user_agent(request: Request):
    """Return the user-agent of the browser making this request.

    This is useful for pre-filling the user_agent field in Video Settings
    with the browser's user-agent, which should match the browser used to
    export cookies."""
    user_agent = request.headers.get('User-Agent', '')
    return json_response({'user_agent': user_agent})
