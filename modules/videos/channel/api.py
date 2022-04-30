import asyncio
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, make_media_directory, \
    get_media_directory, run_after
from wrolpi.root_api import json_response
from wrolpi.schema import JSONErrorResponse
from wrolpi.vars import PYTEST
from . import lib
from .. import schema
from ..lib import save_channels_config

channel_bp = Blueprint('Channel', url_prefix='/api/videos/channels')

logger = logger.getChild(__name__)


@channel_bp.get('/')
@openapi.description('Get a list of all Channels')
@openapi.response(HTTPStatus.OK, schema.ChannelsResponse)
async def get_channels(_: Request):
    channels = await lib.get_minimal_channels()
    return json_response({'channels': channels})


@channel_bp.get('/<channel_id:int>')
@openapi.description('Get a Channel')
@openapi.response(HTTPStatus.OK, schema.ChannelResponse)
def channel_get(_: Request, channel_id: int = None):
    channel = lib.get_channel(channel_id=channel_id)
    channel.pop('info_json')
    return json_response({'channel': channel})


@channel_bp.post('/')
@openapi.definition(
    description='Insert a Channel',
    body=schema.ChannelPostRequest,
)
@openapi.response(HTTPStatus.OK, schema.ChannelPostResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(schema.ChannelPostRequest)
@wrol_mode_check
def channel_post(_: Request, body: schema.ChannelPostRequest):
    body.directory = get_media_directory() / body.directory
    if not body.directory.is_dir() and body.mkdir:
        make_media_directory(body.directory)

    channel = lib.create_channel(data=body, return_dict=False)

    # Refresh the videos asynchronously
    if not PYTEST:
        from ..api import refresh_videos
        coro = refresh_videos([channel.id])
        asyncio.ensure_future(coro)

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel.id}'})


@channel_bp.put('/<channel_id:int>')
@openapi.definition(
    description='Update a Channel',
    body=schema.ChannelPutRequest,
)
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(schema.ChannelPutRequest)
@run_after(save_channels_config)
@wrol_mode_check
def channel_update(_: Request, channel_id: int, body: schema.ChannelPutRequest):
    channel = lib.update_channel(data=body, channel_id=channel_id)
    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel.id}'})


@channel_bp.delete('/<channel_id:int>')
@openapi.description('Delete a Channel')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
def channel_delete(_: Request, channel_id: int):
    lib.delete_channel(channel_id=channel_id)
    return response.raw('', HTTPStatus.NO_CONTENT)
