import json
import pathlib

import cherrypy
from cherrypy.lib.static import serve_file
from dictorm import DictDB

from wrolpi.common import env
from wrolpi.plugins.videos.common import get_downloader_config, get_absolute_channel_directory

PLUGIN_ROOT = 'videos'

# This will be set once all plugins are loaded
PLUGINS = None


def set_plugins(plugins):
    global PLUGINS
    PLUGINS = plugins


def _get_render_kwargs(db, **kwargs):
    """
    Always pass at least these kwargs to the template.render
    """
    d = dict()
    d['PLUGINS'] = PLUGINS
    d['PLUGIN_ROOT'] = PLUGIN_ROOT
    d['channels'] = db['channel'].get_where().order_by('LOWER(name) ASC')
    d.update(kwargs)
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
        kwargs = _get_render_kwargs(db)
        html = template.render(**kwargs)
        return html

    @cherrypy.expose
    @cherrypy.tools.db()
    def settings(self, db):
        """Page to list and edit channels"""
        downloader_config = get_downloader_config()
        video_root_directory = downloader_config['video_root_directory']

        template = env.get_template('wrolpi/plugins/videos/templates/channels_settings.html')
        kwargs = _get_render_kwargs(db,
                                    video_root_directory=video_root_directory,
                                    file_name_format=downloader_config['file_name_format'],
                                    )
        html = template.render(**kwargs)
        return html

    @staticmethod
    def serve_file(kind, hash: str, db: DictDB, download: bool = False):
        Video = db['video']

        try:
            video = Video.get_one(video_path_hash=hash)
            path = video[kind + '_path']
            path = pathlib.Path(path)
            downloader_config = get_downloader_config()
            video_root_directory = downloader_config['video_root_directory']
            path = pathlib.Path(video_root_directory) / video['channel']['directory'] / path
        except TypeError or KeyError:
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
            raise cherrypy.HTTPRedirect(f'/{PLUGIN_ROOT}')

        Channel = db['channel']
        channel = Channel.get_one(link=link)

        template = env.get_template('wrolpi/plugins/videos/templates/channel_videos.html')
        kwargs = _get_render_kwargs(db, link=link, linked_channel=channel)
        html = template.render(**kwargs)
        return html


@cherrypy.popargs('hash')
class VideoHandler(object):

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, link: str = None, hash: str = None, db: DictDB = None):
        Video = db['video']

        video = Video.get_one(video_path_hash=hash)
        if not video:
            raise cherrypy.HTTPError(404, f'No video with id {hash}')

        # Get the description from it's file, or from the video's info_json file.
        directory = get_absolute_channel_directory(video['channel']['directory'])
        description = ''
        description_path = video['description_path']
        if description_path:
            description_path = directory / description_path
            with open(description_path, 'rb') as fh:
                description = fh.read()

        info_json = {}
        info_json_path = video['info_json_path']
        if info_json_path:
            info_json_path = directory / info_json_path
            with open(info_json_path, 'rb') as fh:
                info_json = json.load(fh)
            if not description:
                description = info_json.get('description')

        template = env.get_template('wrolpi/plugins/videos/templates/video.html')
        items = _get_render_kwargs(db, link=link, hash=hash, video=video, description=description,
                                   info_json=info_json)
        html = template.render(**items)
        return html
