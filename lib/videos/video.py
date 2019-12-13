import asyncio
from http import HTTPStatus

from dictorm import DictDB
from sanic import response, Blueprint
from sanic.exceptions import abort
from sanic.request import Request

from lib.common import validate_doc, boolean_arg
from lib.db import get_db_context
from lib.videos.common import get_absolute_video_path, UnknownFile, VIDEO_QUERY_LIMIT
from lib.videos.schema import ChannelVideoResponse, JSONErrorResponse, VideoSearchRequest, VideoSearchResponse

video_bp = Blueprint('Video')


@video_bp.get('/video/<video_hash:string>')
@validate_doc(
    summary='Get Video information',
    produces=ChannelVideoResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def video(request, video_hash: str):
    db: DictDB = request.ctx.get_db()
    Video = db['video']
    video = Video.get_one(video_path_hash=video_hash)
    if not video:
        return response.json({'error': 'Unknown video'}, HTTPStatus.NOT_FOUND)
    return response.json({'video': video})


@video_bp.route('/static/video/<hash:string>')
@video_bp.route('/static/poster/<hash:string>')
@video_bp.route('/static/caption/<hash:string>')
@validate_doc(
    summary='Get a video/poster/caption file',
)
async def media_file(request: Request, hash: str):
    db: DictDB = request.ctx.get_db()
    download = boolean_arg(request, 'download')
    Video = db['video']
    # kind is enforced by the Sanic routes defined for this function
    kind = str(request.path).split('/')[4]

    try:
        video = Video.get_one(video_path_hash=hash)
        path = get_absolute_video_path(video, kind=kind)
        if download:
            return await response.file_stream(str(path), filename=path.name)
        else:
            return await response.file_stream(str(path))
    except TypeError or KeyError or UnknownFile:
        abort(404, f"Can't find {kind} by that ID.")


async def video_search(db_conn, db: DictDB, search_str: str, offset: int):
    curs = db_conn.cursor()

    query = 'SELECT id, ts_rank_cd(textsearch, to_tsquery(%s)), COUNT(*) OVER() AS total ' \
            f'FROM video WHERE textsearch @@ to_tsquery(%s) ORDER BY 2 DESC OFFSET %s LIMIT {VIDEO_QUERY_LIMIT}'
    curs.execute(query, (search_str, search_str, offset))
    results = list(curs.fetchall())
    total = results[0][2] if results else 0
    ranked_ids = [i[0] for i in results]

    results = []
    if ranked_ids:
        Video = db['video']
        results = Video.get_where(Video['id'].In(ranked_ids))
        results = sorted(results, key=lambda r: ranked_ids.index(r['id']))
    return results, total


async def channel_search(db_conn, db: DictDB, search_str: str, offset: int):
    curs = db_conn.cursor()

    query = 'SELECT id, COUNT(*) OVER() as total ' \
            f'FROM channel WHERE name ILIKE %s ORDER BY LOWER(name) DESC OFFSET %s LIMIT {VIDEO_QUERY_LIMIT}'
    curs.execute(query, (f'%{search_str}%', offset))
    results = list(curs.fetchall())
    total = results[0][1] if results else 0
    ids = [i[0] for i in results]

    results = []
    if ids:
        Channel = db['channel']
        results = Channel.get_where(Channel['id'].In(ids))
        results = list(results)
    return results, total


@video_bp.post('/search')
@validate_doc(
    summary='Search Video titles and captions, search Channel names.',
    consumes=VideoSearchRequest,
    produces=VideoSearchResponse,
)
async def search(request: Request, data: dict):
    search_str = data['search_str']
    offset = int(data.get('offset', 0))

    if not search_str:
        return response.json({'error': 'search_str must have contents'})

    # ts_query accepts a pipe & as an "and" between keywords, we'll just assume any spaces mean "and"
    tsquery = ' & '.join(search_str.split(' '))

    with get_db_context() as (db_conn, db):
        videos_coro = video_search(db_conn, db, tsquery, offset)
        channels_coro = channel_search(db_conn, db, tsquery, offset)
        (videos, videos_total), (channels, channels_total) = await asyncio.gather(videos_coro, channels_coro)

    ret = {'videos': videos, 'channels': channels, 'tsquery': tsquery,
           'totals': {'videos': videos_total, 'channels': channels_total}}
    return response.json(ret)
