from http import HTTPStatus

from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from lib.common import validate_doc, sanitize_link
from lib.videos.common import logger, get_absolute_channel_directory, UnknownDirectory, get_conflicting_channels, \
    get_channel_videos, UnknownChannel
from lib.videos.schema import ChannelsResponse, ChannelResponse, JSONErrorResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest, SuccessResponse, ChannelVideosResponse

channel_bp = Blueprint('Channel')


@channel_bp.get('/channels')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsResponse,
)
def get_channels(request: Request):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channels = Channel.get_where().order_by('LOWER(name) ASC')
    channels = list(channels)
    return response.json({'channels': channels})


@channel_bp.get('/channels/<link:string>')
@validate_doc(
    summary='Get a Channel',
    produces=ChannelResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def channel_get(request: Request, link: str):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channel = Channel.get_one(link=link)
    logger.debug(f'channel_get.channel: {channel}')
    if not channel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)
    return response.json({'channel': channel})


@channel_bp.post('/channels')
@validate_doc(
    summary='Insert a Channel',
    consumes=ChannelPostRequest,
    responses=(
            (HTTPStatus.CREATED, ChannelPostResponse),
            (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ),
)
def channel_post(request: Request, data: dict):
    """Create a new channel"""
    try:
        data['directory'] = get_absolute_channel_directory(data['directory'])
    except UnknownDirectory:
        return response.json({'error': 'Unknown directory'}, HTTPStatus.BAD_REQUEST)

    db: DictDB = request.ctx.get_db()
    Channel = db['channel']

    # Verify that the URL/Name/Link aren't taken
    conflicting_channels = get_conflicting_channels(
        db,
        url=data.get('url'),
        name_=data['name'],
        link=sanitize_link(data['name']),
    )
    if conflicting_channels:
        return response.json({'error': 'Channel Name or URL already taken'}, HTTPStatus.BAD_REQUEST)

    with db.transaction(commit=True):
        channel = Channel(
            name=data['name'],
            url=data.get('url'),
            match=data.get('match_regex'),
            link=sanitize_link(data['name']),
        )
        channel.flush()

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.put('/channels/<link:string>')
@channel_bp.patch('/channels/<link:string>')
@validate_doc(
    summary='Update a Channel',
    consumes=ChannelPutRequest,
    produces=SuccessResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
            (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    ),
)
def channel_update(request: Request, link: str, data: dict):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']

    with db.transaction(commit=True):
        channel = Channel.get_one(link=link)

        if not channel:
            return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)

        # Only update directory if it was empty
        if data.get('directory') and not channel['directory']:
            try:
                data['directory'] = get_absolute_channel_directory(data['directory'])
            except UnknownDirectory:
                return response.json({'error': 'Unknown directory'}, HTTPStatus.NOT_FOUND)

        if 'directory' in data:
            data['directory'] = str(data['directory'])

        # Verify that the URL/Name/Link aren't taken
        conflicting_channels = get_conflicting_channels(
            db=db,
            id=channel.get('id'),
            url=data.get('url'),
            name_=data.get('name'),
            link=data.get('link'),
            directory=data.get('directory'),
        )
        if conflicting_channels:
            return response.json({'error': 'Channel Name or URL already taken'}, HTTPStatus.BAD_REQUEST)

        # Apply the changes now that we've OK'd them
        channel.update(data)
        channel.flush()

    return response.raw('', HTTPStatus.NO_CONTENT,
                        headers={'Location': f'/api/videos/channels/{channel["link"]}'})


@channel_bp.delete('/channels/<link:string>')
@validate_doc(
    summary='Delete a Channel',
    produces=SuccessResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def channel_delete(request, link: str):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channel = Channel.get_one(link=link)
    if not channel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)
    with db.transaction(commit=True):
        channel.delete()
    return response.raw(None, HTTPStatus.NO_CONTENT)


@channel_bp.get('/channels/<link:string>/videos')
@validate_doc(
    summary='Get Channel Videos',
    produces=ChannelVideosResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def channel_videos(request, link: str):
    offset = int(request.args.get('offset', 0))
    db: DictDB = request.ctx.get_db()
    try:
        videos, total = get_channel_videos(db, link, offset)
    except UnknownChannel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)

    return response.json({'videos': list(videos), 'total': total})
