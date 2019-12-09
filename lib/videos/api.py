"""
This module contains the Sanic routes, as well as functions necessary to retrieve video files.  This module also
contains functions that will search the file structure for video files, as well as cleanup the DB video records.

All paths in the DB are relative.  A Channel's directory is relative to the video_root_directory.  A Video's path (as
well as its meta files) is relative to its Channel's directory.

    Example:
        Real Paths:
            video_root_directory = '/media/something'
            channel['directory'] = '/media/something/the channel'
            video['video_path'] = '/media/something/the channel/foo.mp4'
            video['poster_path'] = '/media/something/the channel/foo.jpg'
            video['video_path'] = '/media/something/the channel/subdir/bar.mp4'

        The same paths in the DB:
            channel['directory'] = 'the channel'
            video['video_path'] = 'foo.mp4'
            video['poster_path'] = 'foo.jpg'
            video['video_path'] = 'subdir/bar.mp4'

Relative DB paths allow files to be moved without having to rebuild the entire collection.  It also ensures that when
a file is moved, it will not be duplicated in the DB.
"""
import asyncio
import pathlib
from functools import wraps
from http import HTTPStatus
from uuid import uuid1

from dictorm import DictDB
from sanic import Blueprint, response
from sanic.exceptions import abort
from sanic.request import Request

from lib.common import sanitize_link, boolean_arg, load_schema, attach_websocket_with_queue, get_sanic_url, \
    make_progress_calculator, validate_doc
from lib.db import get_db_context
from .captions import process_captions
from .common import generate_video_paths, save_settings_config, get_downloader_config, \
    get_absolute_channel_directory, UnknownDirectory
from .common import get_conflicting_channels, get_absolute_video_path, UnknownFile
from .common import logger
from .downloader import insert_video, update_channels, download_all_missing_videos
from .schema import DownloaderConfig, ChannelRequest, ChannelsModel, SettingsResponse, StreamResponse, \
    JSONErrorResponse, \
    ChannelResponse, ChannelPostResponse

api_bp = Blueprint('api_video', url_prefix='/videos')


@api_bp.put('/settings')
@validate_doc(
    summary='Update video settings config',
    consumes=DownloaderConfig,
    produces=SettingsResponse,
)
def settings(request: Request, data: dict):
    downloader_config = get_downloader_config()
    downloader_config['video_root_directory'] = data['video_root_directory']
    downloader_config['file_name_format'] = data['file_name_format']
    save_settings_config(downloader_config)
    return response.json({'success': 'Settings saved'})


@api_bp.get('/channels')
@validate_doc(
    summary='Get a list of all Channels',
    produces=ChannelsModel,
)
def get_channels(request: Request):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channels = Channel.get_where().order_by('name DESC')
    channels = list(channels)
    return response.json({'channels': channels})


refresh_queue, refresh_event = attach_websocket_with_queue('/feeds/refresh', api_bp)


@api_bp.post('/settings/refresh')
@validate_doc(
    summary='Search for videos that have previously been downloaded and stored.',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ],
)
async def refresh(_):
    refresh_logger = logger.getChild('refresh')

    # Only one refresh can run at a time
    if refresh_event.is_set():
        return response.json({'error': 'Refresh already running'}, HTTPStatus.BAD_REQUEST)

    refresh_event.set()
    refresh_queue.put('refresh-started')

    async def do_refresh():
        try:
            refresh_logger.info('refresh started')

            with get_db_context(commit=True) as (db_conn, db):
                for msg in _refresh_videos(db):
                    refresh_queue.put(msg)

            refresh_logger.info('refresh complete')
        except Exception as e:
            refresh_queue.put({'error': 'Refresh failed.  See server logs.'})
            raise
        finally:
            refresh_event.clear()

    coro = do_refresh()
    asyncio.ensure_future(coro)
    refresh_logger.debug('do_refresh scheduled')
    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/refresh')
    return response.json({'success': 'stream-started', 'stream_url': stream_url})


download_queue, download_event = attach_websocket_with_queue('/feeds/download', api_bp)


@api_bp.post('/settings/download')
@validate_doc(
    summary='Update channel catalogs, download any missing videos',
    produces=StreamResponse,
    responses=[
        (HTTPStatus.BAD_REQUEST, JSONErrorResponse)
    ],
)
async def download(_):
    download_logger = logger.getChild('download')

    # Only one download can run at a time
    if download_event.is_set():
        return response.json({'error': 'download already running'}, HTTPStatus.BAD_REQUEST)

    download_event.set()
    download_queue.put('download-started')

    async def do_download():
        try:
            download_logger.info('download started')

            with get_db_context(commit=True) as (db_conn, db):
                for msg in update_channels(db_conn, db):
                    download_queue.put(msg)
                for msg in download_all_missing_videos(db_conn, db):
                    download_queue.put(msg)

            download_logger.info('download complete')
        except Exception as e:
            download_queue.put({'error': 'Download failed.  See server logs.'})
            raise
        finally:
            download_event.clear()

    coro = do_download()
    asyncio.ensure_future(coro)
    download_logger.debug('do_download scheduled')
    stream_url = get_sanic_url(scheme='ws', path='/api/videos/feeds/download')
    return response.json({'success': 'stream-started', 'stream_url': stream_url})


@api_bp.get('/channel/<link:string>')
@validate_doc(
    summary='Get a Channel',
    produces=ChannelResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    )
)
def channel_get(request: Request, link: str):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channel = Channel.get_one(link=link)
    if not channel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)
    return response.json({'channel': channel})


@api_bp.post('/channel')
@validate_doc(
    summary='Insert a Channel',
    responses=(
            (HTTPStatus.CREATED, ChannelPostResponse),
            (HTTPStatus.BAD_REQUEST, JSONErrorResponse),
    )
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
        url=data['url'],
        name_=data['name'],
        link=sanitize_link(data['name']),
    )
    if conflicting_channels:
        return response.json({'error': 'Channel Name or URL already taken'}, HTTPStatus.BAD_REQUEST)

    with db.transaction(commit=True):
        channel = Channel(
            name=data['name'],
            url=data['url'],
            match=data['match_regex'],
            link=sanitize_link(data['name']),
        )
        channel.flush()

    return response.json({'success': 'Channel created successfully'}, HTTPStatus.CREATED,
                         {'Location': f'/api/videos/channel/{channel["link"]}'})


@api_bp.put('/channel/<link:string>')
@load_schema(ChannelRequest)
def channel_put(request: Request, link: str, data: dict):
    """Update an existing channel"""
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']

    with db.transaction(commit=True):
        existing_channel = Channel.get_one(link=link)

        if not existing_channel:
            return response.json({'error': 'Unknown channel'}, 404)

        # Only update directory if it was empty
        if data['directory'] and not existing_channel['directory']:
            try:
                data['directory'] = get_absolute_channel_directory(data['directory'])
            except UnknownDirectory:
                return response.json({'error': 'Unknown directory'}, 404)
        else:
            data['directory'] = existing_channel['directory']
        data['directory'] = str(data['directory'])

        # Verify that the URL/Name/Link aren't taken
        conflicting_channels = get_conflicting_channels(
            db=db,
            id=existing_channel['id'],
            url=data['url'],
            name_=data['name'],
            link=data['link'],
            directory=data['directory'],
        )
        if list(conflicting_channels):
            return response.json({'error': 'Channel Name or URL already taken'}, 400)

        existing_channel['url'] = data['url']
        existing_channel['name'] = data['name']
        existing_channel['directory'] = data['directory']
        existing_channel['match_regex'] = data['match_regex']
        existing_channel.flush()

    return response.json({'success': 'The channel was updated successfully.'})


@api_bp.delete('/channel/<link:string>')
def channel_delete(request, link: str):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channel = Channel.get_one(link=link)
    if not channel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)
    with db.transaction(commit=True):
        channel.delete()
    return response.json({'success': 'Channel deleted'})


@api_bp.get('/channel/<link:string>/videos')
def channel_videos(request, link: str):
    db: DictDB = request.ctx.get_db()
    Channel = db['channel']
    channel = Channel.get_one(link=link)
    if not channel:
        return response.json({'error': 'Unknown channel'}, HTTPStatus.NOT_FOUND)
    return response.json({'videos': list(channel['videos'])})


@api_bp.route('/video/<hash:string>')
@api_bp.route('/poster/<hash:string>')
@api_bp.route('/caption/<hash:string>')
async def media_file(request: Request, hash: str):
    db: DictDB = request.ctx.get_db()
    download = boolean_arg(request, 'download')
    Video = db['video']
    kind = str(request.path).split('/')[3]

    try:
        video = Video.get_one(video_path_hash=hash)
        path = get_absolute_video_path(video, kind=kind)
        if download:
            return await response.file_stream(str(path), filename=path.name)
        else:
            return await response.file_stream(str(path))
    except TypeError or KeyError or UnknownFile:
        abort(404, f"Can't find {kind} by that ID.")


def get_channel_form(form_data: dict):
    channel = dict(
        url=form_data.get('url'),
        name=form_data['name'],
        match_regex=form_data.get('match_regex'),
        link=sanitize_link(form_data['name']),
        directory=form_data.get('directory'),
    )
    return channel


def refresh_channel_videos(db, channel):
    """
    Find all video files in a channel's directory.  Add any videos not in the DB to the DB.
    """
    # Set the idempotency key so we can remove any videos not touched during this search
    curs = db.get_cursor()
    curs.execute('UPDATE video SET idempotency=NULL WHERE channel_id=%s', (channel['id'],))
    idempotency = str(uuid1())

    directory = get_absolute_channel_directory(channel['directory'])

    # A set of absolute paths that exist in the file system
    possible_new_paths = set(generate_video_paths(directory))

    # Update all videos that match the current video paths
    query = 'UPDATE video SET idempotency = %s WHERE channel_id = %s AND video_path = ANY(%s) RETURNING video_path'
    relative_new_paths = [str(i.relative_to(directory)) for i in possible_new_paths]
    curs.execute(query, (idempotency, channel['id'], relative_new_paths))
    existing_paths = {i for (i,) in curs.fetchall()}

    # Get the paths for any video not yet in the DB
    # (paths in DB are relative, but we need to pass an absolute path)
    new_videos = {p for p in possible_new_paths if str(p.relative_to(directory)) not in existing_paths}

    for video_path in new_videos:
        logger.debug(f'{channel["name"]}: Added {video_path}')
        insert_video(db, pathlib.Path(video_path), channel, idempotency=idempotency)

    curs.execute('DELETE FROM video WHERE channel_id=%s AND idempotency IS NULL RETURNING id', (channel['id'],))
    deleted_count = curs.fetchall()
    if deleted_count:
        deleted_count = len(deleted_count)
        deleted_status = f'Deleted {deleted_count} video records from channel {channel["name"]}'
        logger.info(deleted_status)
        yield deleted_status

    status = f'{channel["name"]}: {len(new_videos)} new videos, {len(existing_paths)} already existed. '
    logger.info(status)
    yield status

    # Fill in any missing captions
    query = 'SELECT id FROM video WHERE channel_id=%s AND caption IS NULL AND caption_path IS NOT NULL'
    curs.execute(query, (channel['id'],))
    missing_captions = [i for (i,) in curs.fetchall()]
    Video = db['video']
    for video_id in missing_captions:
        video = Video.get_one(id=video_id)
        process_captions(video)
        yield f'Processed captions for video {video_id}'

    status = f'Processed {len(missing_captions)} missing captions.'
    logger.info(status)
    yield status


def _refresh_videos(db: DictDB):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :param db:
    :return:
    """
    logger.info('Refreshing video files')
    Channel = db['channel']

    calc_progress = make_progress_calculator(Channel.count())
    for idx, channel in enumerate(Channel.get_where()):
        yield {'progress': calc_progress(idx), 'message': f'Checking {channel["name"]} directory for new videos'}
        with db.transaction(commit=True):
            for msg in refresh_channel_videos(db, channel):
                yield {'message': msg}
    yield {'progress': 100, 'message': 'All videos refreshed.'}


@wraps(_refresh_videos)
def refresh_videos(db: DictDB):
    return list(_refresh_videos(db))


@wraps(_refresh_videos)
def refresh_videos_with_db():
    with get_db_context(commit=True) as (db_conn, db):
        return refresh_videos(db)


def video_search(db: DictDB, search_str, offset, link):
    db_conn = db.conn
    curs = db_conn.cursor()

    # Get the match count per channel
    query = 'SELECT channel_id, COUNT(*) FROM video WHERE textsearch @@ to_tsquery(%s) GROUP BY channel_id'
    curs.execute(query, (search_str,))
    channel_totals = {i: j for (i, j) in curs.fetchall()}

    # Get the names of each channel, add the counts respectively
    query = 'SELECT id, name, link FROM channel ORDER BY LOWER(name)'
    curs.execute(query)
    channels = []
    for (id_, name, link_) in curs.fetchall():
        channel_total = channel_totals[id_] if id_ in channel_totals else 0
        d = {
            'id': id_,
            'name': f'{name} ({channel_total})',
            'link': link_,
            'search_link': f'/videos/search?link={link_}&search={search_str}',
        }
        channels.append(d)

    # Get the search results
    if link:
        # The results are restricted to a single channel
        curs.execute('SELECT id FROM channel WHERE link = %s', (link,))
        (channel_id,) = curs.fetchone()
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) AND channel_id=%s ORDER BY 2 OFFSET %s LIMIT 20'
        curs.execute(query, (search_str, search_str, channel_id, offset))
        total = channel_totals[channel_id]
    else:
        # The results are for all channels
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) ORDER BY 2 OFFSET %s LIMIT 20'
        curs.execute(query, (search_str, search_str, offset))
        # Sum up all the matches for paging
        total = sum(channel_totals.values())

    results = list(curs.fetchall())

    videos = []
    Video = db['video']
    if results:
        videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]

    results = {
        'videos': videos,
        'total': total,
        'channels': channels,
    }
    return results
