import cherrypy
from cherrypy.lib.static import serve_file
from dictorm import DictDB

from wrolpi.common import env, get_pagination_with_generator, create_pagination_dict
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

    @cherrypy.expose
    @cherrypy.tools.db()
    def search(self, search: str, db: DictDB, offset: int = None, link: str = None):
        offset = int(offset) if offset else 0
        results = video_search(db, search, offset, link)
        template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
        pagination = create_pagination_dict(offset, 20, total=results['total'])
        kwargs = _get_render_kwargs(db, results=results, pagination=pagination)
        # Overwrite the channels with their respective counts
        kwargs['channels'] = results['channels']
        html = template.render(**kwargs, link=link)
        return html


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
        videos = channel['videos'].order_by('upload_date DESC, name ASC')
        videos, pagination = get_pagination_with_generator(videos, offset, limit, total=len(channel['videos']))

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


def video_search(db: DictDB, search_str, offset, link):
    db_conn = db.conn
    template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
    curs = db_conn.cursor()

    # Get the match count per channel
    query = 'SELECT channel_id, COUNT(*) FROM video WHERE textsearch @@ to_tsquery(%s) GROUP BY channel_id'
    curs.execute(query, (search_str,))
    channel_totals = {i: j for (i, j) in curs.fetchall()}
    # Sum up all the matches for paging
    total = sum(channel_totals.values())

    # Get the names of each channel, add the counts respectively
    query = 'SELECT id, name, link FROM channel ORDER BY LOWER(name)'
    curs.execute(query)
    channels = []
    for (id_, name, link) in curs.fetchall():
        channel_total = channel_totals[id_] if id_ in channel_totals else 0
        d = {
            'id': id_,
            'name': f'{name} ({channel_total})',
            'link': link,
            'search_link': f'/{PLUGIN_ROOT}/search?link={link}&search={search_str}',
        }
        channels.append(d)

    # Get the search results
    if link:
        curs.execute('SELECT id FROM channel WHERE link = %s', (link,))
        (channel_id,) = curs.fetchone()
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) AND channel_id=%s ORDER BY 2 OFFSET %s'
        curs.execute(query, (search_str, search_str, channel_id, offset))
    else:
        query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)) FROM video WHERE ' \
                'textsearch @@ to_tsquery(%s) ORDER BY 2 OFFSET %s'
        curs.execute(query, (search_str, search_str, offset))
    results = list(curs.fetchall())

    videos = []
    Video = db['video']
    if results:
        videos = [dict(i) for i in Video.get_where(Video['id'].In([i[0] for i in results]))]

    results = {
        'template': template,
        'items': videos,
        'total': total,
        'channels': channels,
    }
    return results
