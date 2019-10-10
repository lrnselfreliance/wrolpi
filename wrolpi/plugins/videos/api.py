import json
import pathlib

import cherrypy
from dictorm import DictDB

from wrolpi.common import sanitize_link
from wrolpi.plugins.videos.common import get_conflicting_channels
from wrolpi.plugins.videos.downloader import insert_video
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

    def PUT(self, **form_data):
        downloader_config = get_downloader_config()
        downloader_config['video_root_directory'] = form_data['video_root_directory']
        downloader_config['file_name_format'] = form_data['file_name_format']
        save_settings_config(downloader_config)
        return json.dumps({'success': 'Settings saved'})


@cherrypy.expose
class Refresh(object):

    @cherrypy.tools.db()
    def GET(self, db: DictDB):
        refresh_videos(db)
        return json.dumps({'success': 'Videos refreshed'})


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

    logger.info(f'{channel["name"]}: Added {len(new_videos)} new videos, {len(existing_paths)} already existed.')


def refresh_videos(db: DictDB):
    logger.info('Refreshing video list')
    Channel = db['channel']

    for channel in Channel.get_where():
        with db.transaction(commit=True):
            refresh_channel_videos(db, channel)
