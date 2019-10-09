import json
import pathlib

import cherrypy
from cherrypy.lib.static import serve_file
from dictorm import DictDB

from wrolpi.common import env
from wrolpi.plugins.videos.common import get_downloader_config

LINK = 'videos'

# This will be set once all plugins are loaded
PLUGINS = None


def set_plugins(plugins):
    global PLUGINS
    PLUGINS = plugins


class UnknownVideo(Exception):
    pass


class UnknownFile(Exception):
    pass


class UnknownChannel(Exception):
    pass


def _get_render_items(db, **kw):
    d = dict()
    default_plugin_render_items = {
        'active_page': LINK,
        'plugins': PLUGINS,
    }
    d.update(default_plugin_render_items)
    d.update(kw)
    d['channels'] = db['channel'].get_where().order_by('LOWER(name) ASC')
    return d


class ClientRoot(object):

    def __init__(self):
        self.channel = ChannelHandler()

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, db):
        """
        This page displays a list of channels.
        """
        template = env.get_template('wrolpi/plugins/videos/templates/channels.html')
        items = _get_render_items(db)
        html = template.render(**items)
        return html

    @cherrypy.expose
    @cherrypy.tools.db()
    def settings(self, db):
        """Page to list and edit channels"""
        Channel = db['channel']

        downloader_config = get_downloader_config()
        video_root_directory = downloader_config['video_root_directory']

        channels = Channel.get_where().order_by('LOWER(name) ASC')
        for channel in channels:
            if channel['directory'].startswith(video_root_directory):
                channel['directory'] = channel['directory'][len(video_root_directory):]
        template = env.get_template('wrolpi/plugins/videos/templates/channels_settings.html')
        items = _get_render_items(db,
                                  video_root_directory=video_root_directory,
                                  file_name_format=downloader_config['file_name_format'],
                                  )
        html = template.render(**items)
        return html

    @staticmethod
    def serve_file(kind, hash: str, db: DictDB, download: bool = False):
        Video = db['video']

        video = Video.get_one(video_path_hash=hash)
        if not video:
            raise cherrypy.HTTPError(404, f"Can't find {kind} by that ID.")

        path = video[kind + '_path']
        try:
            path = pathlib.Path(path)
        except TypeError:
            raise cherrypy.HTTPError(404, f"Can't find {kind} by that ID.")

        if download:
            return serve_file(str(path), 'application/x-download', 'attachment')
        else:
            return serve_file(str(path))

    @cherrypy.expose
    @cherrypy.tools.db()
    def video(self, hash: str, db: DictDB, **kwargs):
        return self.serve_file('video', hash, db, **kwargs)

    @cherrypy.expose
    @cherrypy.tools.db()
    def poster(self, hash: str, db: DictDB, **kwargs):
        return self.serve_file('poster', hash, db, **kwargs)

    @cherrypy.expose
    @cherrypy.tools.db()
    def caption(self, hash: str, db: DictDB, **kwargs):
        return self.serve_file('caption', hash, db, **kwargs)


@cherrypy.popargs('link')
class ChannelHandler(object):

    def __init__(self):
        self.video = VideoHandler()

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, link: str = None, db: DictDB = None):
        if not link:
            # Link was not passed, probably a malformed url
            raise cherrypy.HTTPRedirect('/videos')

        Channel = db['channel']
        channel = Channel.get_one(link=link)

        template = env.get_template('wrolpi/plugins/videos/templates/channel_videos.html')
        items = _get_render_items(db, link=link, linked_channel=channel)
        html = template.render(**items)
        return html


@cherrypy.popargs('hash')
class VideoHandler(object):

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, link: str = None, hash: str = None, db: DictDB = None):
        Video = db['video']

        video = Video.get_one(video_path_hash=hash)
        if not video:
            raise UnknownVideo(f'No video with id {hash}')

        # Get the description from it's file, or from the video's info_json file.
        description_path = video['description_path']
        info_json_path = video['info_json_path']
        description = ''
        info_json = {}
        if description_path:
            with open(description_path, 'rb') as fh:
                description = fh.read()
        elif info_json_path:
            with open(info_json_path, 'rb') as fh:
                info_json = json.load(fh)
            description = info_json.get('description')

        template = env.get_template('wrolpi/plugins/videos/templates/video.html')
        items = _get_render_items(db, link=link, hash=hash, video=video, description=description,
                                  info_json=info_json)
        html = template.render(**items)
        return html
