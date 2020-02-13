import asyncio
from http import HTTPStatus

from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, sanitize_link, logger, save_settings_config
from api.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from api.videos.common import check_for_channel_conflicts, \
    get_channel_videos, get_relative_to_media_directory, make_media_directory
from api.videos.schema import ChannelsResponse, ChannelResponse, JSONErrorResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest, SuccessResponse, ChannelVideosResponse

channel_bp = Blueprint('Channel')

logger = logger.getChild('channel')


@channel_bp.get('/channels')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsResponse,
)
def get_channels(request: Request):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channels = Channel.get_where().order_by('LOWER(name) ASC')
    # Minimize the data returned when getting all channels
    keys = {'id', 'name', 'link', 'directory', 'match_regex', 'url'}
    new_channels = [{k: c[k] for k in keys} for c in channels]

    # Add video count to each channel
    for idx, channel in enumerate(new_channels):
        channel['video_count'] = len(channels[idx]['videos'])

    return response.json({'channels': new_channels})


@channel_bp.route('/channels/<link:string>', methods=['GET', 'OPTIONS'])
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
    if not channel:
        raise UnknownChannel()
    # Remove the info_json stuff
    channel = dict(channel)
    channel.pop('info_json')
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
        data['directory'] = get_relative_to_media_directory(data['directory'])
    except UnknownDirectory:
        if data['mkdir']:
            make_media_directory(data['directory'])
            data['directory'] = get_relative_to_media_directory(data['directory'])
        else:
            raise

    db: DictDB = request.ctx.get_db()
    Channel = db['channel']

    # Verify that the URL/Name/Link aren't taken
    try:
        check_for_channel_conflicts(
            db,
            url=data.get('url'),
            name=data['name'],
            link=sanitize_link(data['name']),
            directory=str(data['directory']),
        )
    except APIError as e:
        raise ValidationError from e

    with db.transaction(commit=True):
        channel = Channel(
            name=data['name'],
            url=data.get('url'),
            match=data.get('match_regex'),
            link=sanitize_link(data['name']),
            directory=str(data['directory']),
        )
        channel.flush()

    # Save these changes to the local.yaml as well
    save_settings_config()

    # Refresh the videos asynchronously
    from api.videos.api import async_refresh_videos_with_db
    coro = async_refresh_videos_with_db([data['name']])
    asyncio.ensure_future(coro)

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
            raise UnknownChannel()

        # Only update directory if it was empty
        if data.get('directory') and not channel['directory']:
            try:
                data['directory'] = get_relative_to_media_directory(data['directory'])
            except UnknownDirectory:
                if data['mkdir']:
                    make_media_directory(data['directory'])
                    data['directory'] = get_relative_to_media_directory(data['directory'])
                else:
                    raise

        if 'directory' in data:
            data['directory'] = str(data['directory'])

        # Verify that the URL/Name/Link aren't taken
        check_for_channel_conflicts(
            db=db,
            id=channel.get('id'),
            url=data.get('url'),
            name=data.get('name'),
            link=data.get('link'),
            directory=data.get('directory'),
        )

        # Apply the changes now that we've OK'd them
        channel.update(data)
        channel.flush()

    # Save these changes to the local.yaml as well
    save_settings_config()

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
        raise UnknownChannel()
    with db.transaction(commit=True):
        channel.delete()

    # Save these changes to the local.yaml as well
    save_settings_config()

    return response.raw('', HTTPStatus.NO_CONTENT)


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
        raise

    return response.json({'videos': list(videos), 'total': total})


@channel_bp.post('/channels/conflict')
@validate_doc(
    summary='Get any channels that conflict with the properties provided.',
    consumes=ChannelPutRequest,
    produces=ChannelsResponse,
)
def channel_conflict(request, data: dict):
    db: DictDB = request.ctx.get_db()
    check_for_channel_conflicts(db, url=data.get('url'), name=data.get('name'),
                                directory=data.get('directory'))

    return response.raw('', HTTPStatus.NO_CONTENT)
