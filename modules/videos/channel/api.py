import asyncio
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, make_media_directory, \
    get_media_directory
from wrolpi.root_api import json_response
from wrolpi.schema import JSONErrorResponse
from .lib import get_minimal_channels, delete_channel, update_channel, get_channel, create_channel
from ..schema import ChannelsResponse, ChannelResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest

channel_bp = Blueprint('Channel', url_prefix='/api/videos/channels')

logger = logger.getChild(__name__)


@channel_bp.get('/')
@openapi.description('Get a list of all Channels')
@openapi.response(HTTPStatus.OK, ChannelsResponse)
async def get_channels(_: Request):
    channels = await get_minimal_channels()
    return json_response({'channels': channels})


@channel_bp.get('/<link:str>')
@openapi.description('Get a Channel')
@openapi.response(HTTPStatus.OK, ChannelResponse)
def channel_get(_: Request, link: str):
    channel = get_channel(link=link)
    channel.pop('info_json')
    return json_response({'channel': channel})


@channel_bp.post('/')
@openapi.definition(
    description='Insert a Channel',
    body=ChannelPostRequest,
)
@openapi.response(HTTPStatus.OK, ChannelPostResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(ChannelPostRequest)
@wrol_mode_check
def channel_post(_: Request, body: ChannelPostRequest):
    body.directory = get_media_directory() / body.directory
    if not body.directory.is_dir() and body.mkdir:
        make_media_directory(body.directory)

    channel = create_channel(body.__dict__)  # TODO don't use the dataclass as a dict.

    # Refresh the videos asynchronously
    from ..api import refresh_videos
    coro = refresh_videos([channel['link']])
    asyncio.ensure_future(coro)

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.put('/<link:str>')
@openapi.definition(
    description='Update a Channel',
    body=ChannelPutRequest,
)
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(ChannelPutRequest)
@wrol_mode_check
def channel_update(_: Request, link: str, body: ChannelPutRequest):
    channel = update_channel(body.__dict__, link)  # TODO don't use the dataclass as a dict.
    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel.link}'})


@channel_bp.delete('/<link:str>')
@openapi.description('Delete a Channel')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
def channel_delete(_: Request, link: str):
    delete_channel(link)
    return response.raw('', HTTPStatus.NO_CONTENT)
