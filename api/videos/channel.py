import asyncio
from http import HTTPStatus
from typing import List, Dict

from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, sanitize_link, logger, save_settings_config, json_response
from api.db import get_db_context
from api.errors import UnknownChannel, UnknownDirectory, APIError, ValidationError
from api.videos.common import check_for_channel_conflicts, \
    get_relative_to_media_directory, make_media_directory
from api.videos.schema import ChannelsResponse, ChannelResponse, JSONErrorResponse, ChannelPostRequest, \
    ChannelPostResponse, ChannelPutRequest, SuccessResponse

channel_bp = Blueprint('Channel', url_prefix='/channels')

logger = logger.getChild('channel')


async def get_minimal_channels() -> List[Dict]:
    """
    Get the minimum amount of information necessary about all channels.
    """
    with get_db_context() as (db_conn, db):
        curs = db.get_cursor()

        # Get all channels, even if they don't have videos.
        query = '''
            SELECT
                c.id, name, link, directory, url
            FROM
                channel AS c
            ORDER BY LOWER(name)
        '''
        curs.execute(query)
        channels = list(map(dict, curs.fetchall()))

        # Add video counts to all channels
        query = '''
            SELECT
                c.id, COUNT(v.id) AS video_count
            FROM
                channel AS c
                LEFT JOIN video AS v ON v.channel_id = c.id
            WHERE
                v.video_path IS NOT NULL
            GROUP BY 1
        '''
        curs.execute(query)
        video_counts = [dict(i) for i in curs.fetchall()]
        video_counts = {i['id']: i['video_count'] for i in video_counts}

        for channel in channels:
            channel_id = channel['id']
            try:
                channel['video_count'] = video_counts[channel_id]
            except KeyError:
                # No videos for this channel
                channel['video_count'] = 0

    return channels


@channel_bp.get('/')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsResponse,
)
async def get_channels(_: Request):
    channels = await get_minimal_channels()
    return response.json({'channels': channels})


@channel_bp.route('/<link:string>', methods=['GET', 'OPTIONS'])
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
    coro = async_refresh_videos_with_db([channel['link']])
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


@channel_bp.delete('/<link:string>')
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


@channel_bp.post('/conflict')
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
