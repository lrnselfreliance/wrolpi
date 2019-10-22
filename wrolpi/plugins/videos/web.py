import cherrypy
from cherrypy.lib.static import serve_file
from dictorm import DictDB

from wrolpi.common import env
from wrolpi.plugins.videos.common import get_downloader_config, get_absolute_video_path, \
    get_video_description, get_video_info_json, UnknownFile

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
            path = get_absolute_video_path(video, kind=kind)
        except TypeError or KeyError or UnknownFile:
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


def get_pagination(results_gen, offset, limit=20):
    results_gen = results_gen.offset(offset)
    results = [i for (i, _) in zip(results_gen, range(limit))]
    try:
        next(results_gen)
        more = True
    except StopIteration:
        more = False

    pagination = dict(
        offset=offset,
        more=more,
        limit=limit,
    )
    return results, pagination


@cherrypy.popargs('link')
class ChannelHandler(object):

    def __init__(self):
        self.video = VideoHandler()

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, link: str = None, db: DictDB = None, offset: int = None, limit: int = None):
        if not link:
            # Link was not passed, probably a malformed url
            raise cherrypy.HTTPRedirect(f'/{PLUGIN_ROOT}')

        offset = int(offset) if offset else 0
        limit = int(limit) if limit else 20

        Channel = db['channel']
        channel = Channel.get_one(link=link)
        videos, pagination = get_pagination(channel['videos'], offset, limit)

        template = env.get_template('wrolpi/plugins/videos/templates/channel_videos.html')
        kwargs = _get_render_kwargs(db, link=link, linked_channel=channel, videos=videos,
                                    pagination=pagination)
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
        description = get_video_description(video)
        info_json = get_video_info_json(video)
        description = description or info_json.get('description', '')

        template = env.get_template('wrolpi/plugins/videos/templates/video.html')
        items = _get_render_kwargs(db, link=link, hash=hash, video=video, description=description,
                                   info_json=info_json)
        html = template.render(**items)
        return html
