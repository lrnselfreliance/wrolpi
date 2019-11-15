from pathlib import Path

from dictorm import DictDB
from sanic import Blueprint, response
from sanic.exceptions import abort
from sanic.request import Request

from wrolpi.common import env, get_pagination_with_generator, create_pagination_dict
from wrolpi.plugins.videos.common import get_downloader_config, get_video_description, get_video_info_json

PLUGIN_ROOT = 'videos'

# This will be set once all plugins are loaded
PLUGINS = None


def set_plugins(plugins):
    global PLUGINS
    PLUGINS = plugins


CWD = Path(__file__).parent
TEMPLATES = CWD / 'templates'


def _get_render_kwargs(db, channels=None, **kwargs):
    """
    Always pass at least these kwargs to the template.render
    """
    d = dict()
    d['PLUGINS'] = PLUGINS
    d['PLUGIN_ROOT'] = PLUGIN_ROOT
    d['channels'] = channels or db['channel'].get_where().order_by('LOWER(name) ASC')
    d.update(kwargs)
    return d


client_bp = Blueprint('content_video', url_prefix='/videos')


@client_bp.route('/')
async def index(request):
    """
    This page displays a list of channels.
    """
    db: DictDB = request.ctx.get_db()
    template = env.get_template('wrolpi/plugins/videos/templates/channels.html')
    kwargs = _get_render_kwargs(db)
    html = template.render(**kwargs)
    return response.html(html)


@client_bp.route('/settings')
async def settings(request):
    """Page to list and edit channels"""
    db: DictDB = request.ctx.get_db()
    downloader_config = get_downloader_config()
    video_root_directory = downloader_config['video_root_directory']

    template = env.get_template('wrolpi/plugins/videos/templates/channels_settings.html')
    kwargs = _get_render_kwargs(db,
                                video_root_directory=video_root_directory,
                                file_name_format=downloader_config['file_name_format'],
                                )
    html = template.render(**kwargs)
    return response.html(html)


@client_bp.route('/search')
def search(request: Request):
    query_args = request.args
    search = query_args.get('search')
    offset = query_args.get('offset')
    offset = int(offset) if offset else 0
    link = query_args.get('link')

    db: DictDB = request.ctx.get_db()

    results = video_search(db, search, offset, link)
    template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
    pagination = create_pagination_dict(offset, 20, total=results['total'])
    kwargs = _get_render_kwargs(db, results=results, pagination=pagination, channels=results['channels'], SEARCH=search)
    # Overwrite the channels with their respective counts
    html = template.render(**kwargs, link=link)
    return response.html(html)


@client_bp.route('/channel/<link:string>')
def channel_index(request, link: str = None, offset: int = None, limit: int = None):
    db: DictDB = request.ctx.get_db()
    if not link:
        # Link was not passed, probably a malformed url
        raise response.redirect(f'/{PLUGIN_ROOT}')

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
    return response.html(html)


@client_bp.route('/channel/<link:string>/video/<hash:string>')
def video_index(request, link: str, hash: str):
    db: DictDB = request.ctx.get_db()
    Video = db['video']

    video = Video.get_one(video_path_hash=hash)
    if not video:
        abort(404, f'No video with id {hash}')

    # Get the description from it's file, or from the video's info_json file.
    description = get_video_description(video)
    info_json = get_video_info_json(video)
    description = description or info_json.get('description', '')

    template = env.get_template('wrolpi/plugins/videos/templates/video.html')
    items = _get_render_kwargs(db, link=link, hash=hash, video=video, description=description,
                               info_json=info_json)
    html = template.render(**items)
    return response.html(html)


def video_search(db: DictDB, search_str, offset, link):
    db_conn = db.conn
    template = env.get_template('wrolpi/plugins/videos/templates/search_video.html')
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
            'search_link': f'/{PLUGIN_ROOT}/search?link={link_}&search={search_str}',
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
        'template': template,
        'videos': videos,
        'total': total,
        'channels': channels,
    }
    return results
