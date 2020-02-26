from http import HTTPStatus
from typing import List, Dict, Tuple

import psycopg2
from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, logger
from api.db import get_db_context
from api.errors import UnknownVideo, SearchEmpty, ValidationError
from api.videos.common import get_video_info_json, get_matching_directories, get_media_directory, \
    get_relative_to_media_directory
from api.videos.schema import VideoResponse, JSONErrorResponse, VideoSearchRequest, VideoSearchResponse, \
    ChannelVideosResponse, DirectoriesResponse, DirectoriesRequest

video_bp = Blueprint('Video')

logger = logger.getChild('video')


@video_bp.get('/video/<video_id:string>')
@validate_doc(
    summary='Get Video information',
    produces=VideoResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def video(request, video_id: str):
    db: DictDB = request.ctx.get_db()
    Video = db['video']
    video = Video.get_one(id=video_id)
    if not video:
        raise UnknownVideo()

    info_json = get_video_info_json(video)
    video = dict(video)
    video['info_json'] = info_json

    return response.json({'video': video})


VIDEO_ORDERS = {
    'upload_date': 'upload_date ASC',
    '-upload_date': 'upload_date DESC',
    'rank': '2 DESC',
    '-rank': '2 ASC',
}
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 20


def video_search(
        db_conn: psycopg2.connect,
        db: DictDB,
        search_str: str = None,
        offset: int = None,
        channel_link: str = None,
        order_by: str = None,
) -> Tuple[List[Dict], int]:
    # TODO handle when there is no search_str
    curs = db_conn.cursor()

    args = dict(search_str=search_str, offset=offset)
    channel_where = ''
    if channel_link:
        channel_where = 'AND channel_id = (select id from channel where link=%(channel_link)s)'
        args['channel_link'] = channel_link

    # Convert the user-friendly order by into a real order by, restrict what can be interpolated by using the whitelist.
    order = VIDEO_ORDERS[DEFAULT_VIDEO_ORDER]
    if order_by:
        try:
            order = VIDEO_ORDERS[order_by]
        except KeyError:
            raise

    query = f'''
        SELECT
            id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total
        FROM video
        WHERE
            textsearch @@ websearch_to_tsquery(%(search_str)s)
            {channel_where}
        ORDER BY {order}
        OFFSET %(offset)s LIMIT {VIDEO_QUERY_LIMIT}
    '''

    curs.execute(query, args)
    results = list(curs.fetchall())
    total = results[0][2] if results else 0
    ranked_ids = [i[0] for i in results]

    results = []
    if ranked_ids:
        Video = db['video']
        results = Video.get_where(Video['id'].In(ranked_ids))
        results = sorted(results, key=lambda r: ranked_ids.index(r['id']))
    return results, total


@video_bp.post('/search')
@validate_doc(
    summary='Search Video titles and captions, search Channel names.',
    consumes=VideoSearchRequest,
    produces=VideoSearchResponse,
)
def search(_: Request, data: dict):
    search_str = data['search_str']
    channel_link = data.get('channel_link')
    order_by = data.get('channe_link', DEFAULT_VIDEO_ORDER)
    offset = int(data.get('offset', 0))

    if not search_str:
        raise ValidationError() from SearchEmpty()

    with get_db_context() as (db_conn, db):
        videos, videos_total = video_search(db_conn, db, search_str, offset, channel_link, order_by)

        # Get each Channel for each Video, this will be converted to a dict by the response
        _ = [i['channel'] for i in videos]

    ret = {'videos': videos,
           'totals': {'videos': videos_total}}
    return response.json(ret)


def get_recent_videos(db_conn, db: DictDB, offset: int = 0) -> Tuple[List[Dict], int]:
    curs = db_conn.cursor()
    query = '''
        SELECT
        id, COUNT(*) OVER() as total
        FROM video
        WHERE
            upload_date IS NOT NULL
            AND (video_path IS NOT NULL AND video_path != '')
        ORDER BY upload_date DESC
        OFFSET %s LIMIT 20
        '''
    curs.execute(query, (offset,))
    results = list(curs.fetchall())
    total = results[0][1] if results else 0
    ids = [i[0] for i in results]

    results = []
    if ids:
        Video = db['video']
        results = Video.get_where(Video['id'].In(ids))
        results = sorted(results, key=lambda r: ids.index(r['id']))
        results = list(results)
    return results, total


@video_bp.get('/recent')
@validate_doc(
    summary='Get Channel Videos',
    produces=ChannelVideosResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def recent_videos(request, channel_link: str = None):
    offset = int(request.args.get('offset', 0))

    with get_db_context() as (db_conn, db):
        videos, total = get_recent_videos(db_conn, db, offset)

        # Get each Channel for each Video, this will be converted to a dict by the response
        _ = [i['channel'] for i in videos]

    return response.json({'videos': list(videos), 'total': total})


@video_bp.post('/directories')
@validate_doc(
    summary='Get all directories that match the search_str, prefixed by the media directory.',
    consumes=DirectoriesRequest,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
            (HTTPStatus.OK, DirectoriesResponse),
    ),
)
def directories(_, data):
    search_str = str(get_media_directory() / data['search_str'])
    logger.debug(f'Searching for: {search_str}')
    dirs = get_matching_directories(search_str)
    dirs = [str(get_relative_to_media_directory(i)) for i in dirs]
    return response.json({'directories': dirs})
