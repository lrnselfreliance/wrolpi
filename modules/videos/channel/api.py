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
    ChannelPostResponse, ChannelPutRequest, SuccessResponse

channel_bp = Blueprint('Channel', url_prefix='/api/videos/channels')

logger = logger.getChild(__name__)


@channel_bp.get('/')
@openapi.description('Get a list of all Channels')
@openapi.response(HTTPStatus.OK, ChannelsResponse)
async def get_channels(_: Request):
    channels = await get_minimal_channels()
    return json_response({'channels': channels})


@channel_bp.route('/<link:str>', methods=['GET', 'OPTIONS'])
@openapi.description('Get a Channel')
@openapi.response(HTTPStatus.OK, ChannelResponse)
def channel_get(_: Request, link: str):
    channel = get_channel(link=link)
    channel.pop('info_json')
    return json_response({'channel': channel})


@channel_bp.post('/')
@openapi.description('Insert a Channel')
@openapi.response(HTTPStatus.OK, ChannelPostResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(ChannelPostRequest)
@wrol_mode_check
def channel_post(_: Request, data: dict):
    try:
        # Channel directory is relative to the media directory.  Channel directory may not be in "videos" directory!
        data['directory'] = get_media_directory() / data['directory']
    except UnknownDirectory:
        if data['mkdir']:
            make_media_directory(data['directory'])
            data['directory'] = get_relative_to_media_directory(data['directory'])
        else:
            raise
    # Channel directory is relative to the media directory.  Channel directory may not be in "videos" directory!
    data['directory'] = get_media_directory() / data['directory']
    if data.get('mkdir') is True:
        make_media_directory(data['directory'])

    if download_frequency := data.get('download_frequency'):
        try:
            download_frequency = int(download_frequency)
        except ValueError:
            if download_frequency in ('null', 'None'):
                download_frequency = None

    data['download_frequency'] = download_frequency

    channel = create_channel(data)

    # Refresh the videos asynchronously
    from ..api import refresh_videos
    coro = refresh_videos([channel['link']])
    asyncio.ensure_future(coro)

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.put('/<link:str>')
@channel_bp.patch('/<link:str>')
@openapi.description('Update a Channel')
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@validate(ChannelPutRequest)
@wrol_mode_check
def channel_update(_: Request, link: str, data: dict):
    channel = update_channel(data, link)
    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel.link}'})


@channel_bp.delete('/<link:str>')
@openapi.description('Delete a Channel')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(SuccessResponse)
@wrol_mode_check
def channel_delete(_: Request, link: str):
    delete_channel(link)
    return response.raw('', HTTPStatus.NO_CONTENT)
