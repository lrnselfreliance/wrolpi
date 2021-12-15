import asyncio
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request

from wrolpi.common import logger, wrol_mode_check, get_relative_to_media_directory, make_media_directory
from wrolpi.errors import UnknownDirectory
from wrolpi.root_api import json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from .lib import get_minimal_channels, delete_channel, update_channel, get_channel, create_channel
from ..schema import ChannelsResponse, ChannelResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest, SuccessResponse

channel_bp = Blueprint('Channel', url_prefix='/api/videos/channels')

logger = logger.getChild(__name__)


@channel_bp.get('/')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsResponse,
)
async def get_channels(_: Request):
    channels = await get_minimal_channels()
    return json_response({'channels': channels})


@channel_bp.route('/<link:str>', methods=['GET', 'OPTIONS'])
@validate_doc(
    summary='Get a Channel',
    produces=ChannelResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def channel_get(_: Request, link: str):
    channel = get_channel(link)
    channel.pop('info_json')
    return json_response({'channel': channel})


@channel_bp.post('/')
@validate_doc(
    summary='Insert a Channel',
    consumes=ChannelPostRequest,
    responses=(
            (HTTPStatus.CREATED, ChannelPostResponse),
            (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ),
)
@wrol_mode_check
def channel_post(_: Request, data: dict):
    try:
        data['directory'] = get_relative_to_media_directory(data['directory'])
    except UnknownDirectory:
        if data['mkdir']:
            make_media_directory(data['directory'])
            data['directory'] = get_relative_to_media_directory(data['directory'])
        else:
            raise

    channel = create_channel(data)

    # Refresh the videos asynchronously
    from ..api import refresh_videos
    coro = refresh_videos([channel['link']])
    asyncio.ensure_future(coro)

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.put('/<link:str>')
@channel_bp.patch('/<link:str>')
@validate_doc(
    summary='Update a Channel',
    consumes=ChannelPutRequest,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
            (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ),
)
@wrol_mode_check
def channel_update(_: Request, link: str, data: dict):
    channel = update_channel(data, link)
    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel.link}'})


@channel_bp.delete('/<link:str>')
@validate_doc(
    summary='Delete a Channel',
    produces=SuccessResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
@wrol_mode_check
def channel_delete(_: Request, link: str):
    delete_channel(link)
    return response.raw('', HTTPStatus.NO_CONTENT)
