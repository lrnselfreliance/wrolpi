import asyncio
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, logger, json_response, wrol_mode_check
from api.errors import UnknownDirectory
from api.videos.channel.lib import get_minimal_channels, delete_channel, update_channel, get_channel, create_channel
from api.videos.common import get_relative_to_media_directory, make_media_directory
from api.videos.schema import ChannelsResponse, ChannelResponse, JSONErrorResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest, SuccessResponse

channel_bp = Blueprint('Channel', url_prefix='/channels')

logger = logger.getChild(__name__)


@channel_bp.get('/')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsResponse,
)
async def get_channels(_: Request):
    channels = await get_minimal_channels()
    return json_response({'channels': channels})


@channel_bp.route('/<link:string>', methods=['GET', 'OPTIONS'])
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
    channel = channel.dict()

    # Refresh the videos asynchronously
    from api.videos.api import refresh_videos
    coro = refresh_videos([channel['link']])
    asyncio.ensure_future(coro)

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.put('/<link:string>')
@channel_bp.patch('/<link:string>')
@validate_doc(
    summary='Update a Channel',
    consumes=ChannelPutRequest,
    produces=SuccessResponse,
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


@channel_bp.delete('/<link:string>')
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
