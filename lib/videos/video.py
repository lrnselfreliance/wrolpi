from http import HTTPStatus

from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from lib.common import validate_doc, boolean_arg, logger, get_last_modified_headers, \
    FileNotModified
from lib.db import get_db_context
from lib.errors import UnknownVideo, UnknownFile, SearchEmpty, ValidationError
from lib.videos.common import get_absolute_video_path, VIDEO_QUERY_LIMIT, get_absolute_video_info_json
from lib.videos.schema import VideoResponse, JSONErrorResponse, VideoSearchRequest, VideoSearchResponse

video_bp = Blueprint('Video')

logger = logger.getChild('video')


@video_bp.get('/video/<video_hash:string>')
@validate_doc(
    summary='Get Video information',
    produces=VideoResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def video(request, video_hash: str):
    db: DictDB = request.ctx.get_db()
    Video = db['video']
    video = Video.get_one(video_path_hash=video_hash)
    if not video:
        raise UnknownVideo()

    try:
        path = get_absolute_video_info_json(video)
        video = dict(video)
        with open(str(path), 'rt') as fh:
            video['info_json'] = fh.read()
    except UnknownFile:
        video = dict(video)
        video['info_json'] = None

    return response.json({'video': video})


@video_bp.route('/static/video/<hash:string>')
@video_bp.route('/static/poster/<hash:string>')
@video_bp.route('/static/caption/<hash:string>')
@validate_doc(
    summary='Get a video/poster/caption file',
)
async def media_file(request: Request, hash: str):
    download = boolean_arg(request, 'download')

    db: DictDB = request.ctx.get_db()
    Video = db['video']
    # kind is enforced by the Sanic routes defined for this function
    kind = str(request.path).split('/')[4]

    try:
        video = Video.get_one(video_path_hash=hash)
        path = get_absolute_video_path(video, kind=kind)

        try:
            headers = get_last_modified_headers(request.headers, path)
        except FileNotModified:
            return response.raw('', status=HTTPStatus.NOT_MODIFIED)

        if download:
            return await response.file_stream(str(path), filename=path.name, headers=headers)
        else:
            return await response.file_stream(str(path), headers=headers)
    except TypeError or KeyError or UnknownFile:
        raise UnknownFile()


def video_search(db_conn, db: DictDB, search_str: str, offset: int):
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


def channel_search(db_conn, db: DictDB, search_str: str, offset: int):
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
def search(_: Request, data: dict):
    search_str = data['search_str']
    offset = int(data.get('offset', 0))

    if not search_str:
        raise ValidationError() from SearchEmpty()

    # ts_query accepts a & as an "and" between keywords, we'll just assume any spaces mean "and"
    tsquery = ' & '.join(search_str.split(' '))

    with get_db_context() as (db_conn, db):
        videos, videos_total = video_search(db_conn, db, tsquery, offset)
        channels, channels_total = channel_search(db_conn, db, tsquery, offset)

    ret = {'videos': videos, 'channels': channels, 'tsquery': tsquery,
           'totals': {'videos': videos_total, 'channels': channels_total}}
    return response.json(ret)
