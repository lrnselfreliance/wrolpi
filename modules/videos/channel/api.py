import asyncio
import pathlib
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, make_media_directory, \
    get_media_directory, run_after, get_relative_to_media_directory
from wrolpi.downloader import download_manager
from wrolpi.events import Events
from wrolpi.api_utils import json_response
from wrolpi.schema import JSONErrorResponse
from wrolpi.vars import PYTEST
from . import lib
from .. import schema, Channel
from ..errors import UnknownChannel
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
    channel = lib.get_channel(channel_id=channel_id, return_dict=True)
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
        asyncio.ensure_future(channel.refresh_files())

    Events.send_created(f'Created Channel: {channel.name}')

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
    body.directory = pathlib.Path(body.directory) if body.directory else None
    channel = lib.update_channel(data=body, channel_id=channel_id)
    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel.id}'})


@channel_bp.delete('/<channel_id:int>')
@openapi.description('Delete a Channel')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
def channel_delete(_: Request, channel_id: int):
    channel = lib.delete_channel(channel_id=channel_id)
    Events.send_deleted(f'Deleted Channel: {channel["name"]}')
    return response.raw('', HTTPStatus.NO_CONTENT)


@channel_bp.post('/refresh/<channel_id:int>')
@openapi.description('Refresh all files in the Channel directory')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
def channel_refresh(_: Request, channel_id: int):
    channel: Channel = lib.get_channel(channel_id=channel_id, return_dict=False)
    if not channel:
        raise UnknownChannel()

    asyncio.ensure_future(channel.refresh_files())
    directory = get_relative_to_media_directory(channel.directory)
    Events.send_directory_refresh(f'Refreshing: {directory}')
    return response.empty()


@channel_bp.post('/download/<channel_id:int>')
@openapi.description('Download the latest catalog for a Channel, download any missing videos.')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
def channel_download(_: Request, channel_id: int):
    lib.download_channel(channel_id, reset_attempts=True)
    if download_manager.disabled.is_set():
        # Warn the user that downloads are disabled.
        Events.send_downloads_disabled('Channel download created. But downloads are disabled.')
    return response.empty()
