"""
This module contains the CherryPy classes, as well as functions necessary to retrieve video files.  This module also
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
import json
import pathlib
from functools import wraps
from uuid import uuid1

import cherrypy
from dictorm import DictDB

from wrolpi.common import sanitize_link
from wrolpi.plugins.videos.common import get_conflicting_channels, verify_config
from wrolpi.plugins.videos.downloader import insert_video, update_channels, download_all_missing_videos
from wrolpi.plugins.videos.main import logger
from wrolpi.tools import get_db_context
from .common import generate_video_paths, save_settings_config, get_downloader_config, \
    get_absolute_channel_directory, UnknownDirectory


class APIRoot(object):

    def __init__(self):
        self.settings = SettingsAPI()
        self.channel = ChannelAPI()
        verify_config()


@cherrypy.expose
class SettingsAPI(object):

    def __init__(self):
        self.refresh = Refresh()
        self.download = Download()

    def PUT(self, **form_data):
        downloader_config = get_downloader_config()
        downloader_config['video_root_directory'] = form_data['video_root_directory']
        downloader_config['file_name_format'] = form_data['file_name_format']
        save_settings_config(downloader_config)
        return json.dumps({'success': 'Settings saved'})


def json_statuses_streamer(func):
    """Wraps status lines in JSON objects.  Adds a new line after each JSON string.

    Example:
        >>> func = json_statuses_streamer(lambda : ['foo', 'bar'])
        >>> func()
        '{"status": "foo"}\n'
        '{"status": "bar"}\n'
        '{"success": "stream-complete"}\n'
    """

    @wraps(func)
    def wrap(*a, **kw):
        yield from (json.dumps({'status': i}) + '\n' for i in func(*a, **kw))
        yield json.dumps({'success': 'stream-complete'}) + '\n'

    return wrap


@cherrypy.expose
class Refresh(object):

    def POST(self):
        cherrypy.response.headers['Content-Type'] = 'text/event-stream'

        @json_statuses_streamer
        def streamer():
            with get_db_context(commit=True) as (db_conn, db):
                yield from _refresh_videos(db)

        return streamer()

    POST._cp_config = {'response.stream': True}


@cherrypy.expose
class Download(object):

    def POST(self):
        cherrypy.response.headers['Content-Type'] = 'text/event-stream'

        @json_statuses_streamer
        def streamer():
            with get_db_context(commit=True) as (db_conn, db):
                yield from update_channels(db_conn, db)
                yield from download_all_missing_videos(db_conn, db)

        return streamer()

    POST._cp_config = {'response.stream': True}


@cherrypy.expose
class ChannelAPI(object):

    @cherrypy.tools.db()
    def GET(self, link, db: DictDB):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            return json.dumps({'error': 'Unknown channel'})
        return json.dumps({'channel': channel})

    @cherrypy.tools.db()
    def POST(self, db: DictDB, **form_data):
        """Create a new channel"""
        Channel = db['channel']

        new_channel = get_channel_form(form_data)

        try:
            new_channel['directory'] = get_absolute_channel_directory(new_channel['directory'])
        except UnknownDirectory:
            return json.dumps({'error': 'Unknown directory'})

        # Verify that the URL/Name/Link aren't taken
        conflicting_channels = get_conflicting_channels(
            db,
            url=new_channel['url'],
            name_=new_channel['name'],
            link=new_channel['link'],
        )
        if conflicting_channels:
            cherrypy.response.status = 400
            return json.dumps({'error': 'Channel Name or URL already taken'})

        if not new_channel['name'] or not new_channel['url']:
            cherrypy.response.status = 400
            return json.dumps({'error': 'Channels require a URL and Name'})

        with db.transaction(commit=True):
            channel = Channel(
                name=new_channel['name'],
                url=new_channel['url'],
                match=new_channel['match_regex'],
                link=new_channel['link'],
            )
            channel.flush()

        return json.dumps({'success': 'Channel created successfully'})

    @cherrypy.tools.db()
    def PUT(self, link, db: DictDB, **form_data):
        """Update an existing channel"""
        Channel = db['channel']

        new_channel = get_channel_form(form_data)

        with db.transaction(commit=True):
            existing_channel = Channel.get_one(link=link)

            if not existing_channel:
                cherrypy.response.status = 400
                return json.dumps({'error': 'Unknown channel'})

            # Only update directory if it was empty
            if new_channel['directory'] and not existing_channel['directory']:
                try:
                    new_channel['directory'] = get_absolute_channel_directory(new_channel['directory'])
                except Exception:
                    cherrypy.response.status = 400
                    return json.dumps({'error': 'Unknown directory'})
            else:
                new_channel['directory'] = existing_channel['directory']
            new_channel['directory'] = str(new_channel['directory'])

            # Verify that the URL/Name/Link aren't taken
            conflicting_channels = get_conflicting_channels(
                db=db,
                id=existing_channel['id'],
                url=new_channel['url'],
                name_=new_channel['name'],
                link=new_channel['link'],
                directory=new_channel['directory'],
            )
            if list(conflicting_channels):
                return json.dumps({'error': 'Channel Name or URL already taken'})

            existing_channel['url'] = new_channel['url']
            existing_channel['name'] = new_channel['name']
            existing_channel['directory'] = new_channel['directory']
            existing_channel['match_regex'] = new_channel['match_regex']
            existing_channel.flush()

        return json.dumps({'success': 'The channel was updated successfully.'})

    @cherrypy.tools.db()
    def DELETE(self, link, db: DictDB):
        Channel = db['channel']
        channel = Channel.get_one(link=link)
        if not channel:
            return json.dumps({'error': 'Unknown channel'})
        with db.transaction(commit=True):
            channel.delete()
        return json.dumps({'success': 'Channel deleted'})


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
    final_status = f'{channel["name"]}: {len(new_videos)} new videos, {len(existing_paths)} already existed.'
    logger.info(final_status)
    yield final_status


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

    for channel in Channel.get_where():
        yield f'Checking {channel["name"]} directory for new videos'
        with db.transaction(commit=True):
            yield from refresh_channel_videos(db, channel)


@wraps(_refresh_videos)
def refresh_videos(db: DictDB):
    return list(_refresh_videos(db))


@wraps(_refresh_videos)
def refresh_videos_with_db():
    with get_db_context(commit=True) as (db_conn, db):
        return refresh_videos(db)
