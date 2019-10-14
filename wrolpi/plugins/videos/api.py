import json
import pathlib

import cherrypy
from dictorm import DictDB

from wrolpi.common import sanitize_link, get_db_context
from wrolpi.plugins.videos.common import get_conflicting_channels
from wrolpi.plugins.videos.downloader import insert_video, update_channels, download_all_missing_videos
from wrolpi.plugins.videos.main import logger
from .common import generate_video_paths, save_settings_config, get_downloader_config, \
    resolve_project_path, \
    UnknownDirectory


class APIRoot(object):

    def __init__(self):
        self.settings = SettingsAPI()
        self.channel = ChannelAPI()


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


def newline_streamer(func):
    def add_newlines(*a, **kw):
        yield from (f'{i}\n' for i in func(*a, **kw))
    return add_newlines


@cherrypy.expose
class Refresh(object):

    def POST(self):
        cherrypy.response.headers['Content-Type'] = 'text/event-stream'

        @newline_streamer
        def streamer():
            with get_db_context(commit=True) as (db_conn, db):
                yield from refresh_videos(db)
            yield 'stream-complete'

        return streamer()

    POST._cp_config = {'response.stream': True}


@cherrypy.expose
class Download(object):

    def POST(self):
        cherrypy.response.headers['Content-Type'] = 'text/event-stream'

        @newline_streamer
        def streamer():
            with get_db_context(commit=True) as (db_conn, db):
                yield from update_channels(db_conn, db)
                yield from download_all_missing_videos(db_conn, db)
            yield 'stream-complete'

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
            new_channel['directory'] = resolve_project_path(new_channel['directory'])
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
                    new_channel['directory'] = resolve_project_path(new_channel['directory'])
                except UnknownDirectory:
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
    existing_paths = {i['video_path'] for i in channel['videos']}
    directory = resolve_project_path(channel['directory'])
    if not pathlib.Path(directory).is_dir():
        logger.warn(f'Channel {channel["name"]} directory "{directory}" does not exist, skipping...')
        logger.warn(f'Have you downloaded any videos for channel {channel["name"]}?')
        return

    possible_new_paths = {str(i) for i in generate_video_paths(directory)}
    new_videos = possible_new_paths.difference(existing_paths)

    for video_path in new_videos:
        logger.debug(f'{channel["name"]}: Added {video_path}')
        insert_video(db, pathlib.Path(video_path), channel)

    final_status = f'{channel["name"]}: Added {len(new_videos)} new videos, {len(existing_paths)} already existed.'
    logger.info(final_status)
    yield final_status


def refresh_videos(db: DictDB):
    """
    Find any videos in the channel directories and add them to the DB.  Delete DB records of any videos not in the
    file system.

    Yields status updates to be passed to the UI.

    :param db:
    :return:
    """
    logger.info('Refreshing video list')
    Channel = db['channel']

    # Remove any videos that don't exist
    yield 'Verifying videos in DB exist in file system'
    curs = db.get_cursor()
    curs.execute('SELECT id, video_path FROM video')
    existing_videos = curs.fetchall()
    to_delete = []
    for video in existing_videos:
        if not pathlib.Path(video['video_path']).is_file():
            to_delete.append(video['id'])
    if to_delete:
        yield 'Deleting video files no longer in file system'
        curs.execute('DELETE FROM video WHERE id = ANY(%s)', (to_delete,))

    for channel in Channel.get_where():
        yield f'Checking {channel["name"]} directory for new videos'
        with db.transaction(commit=True):
            yield from refresh_channel_videos(db, channel)
