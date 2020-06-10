from http import HTTPStatus
from typing import List, Dict, Tuple

import psycopg2
from dictorm import DictDB
from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, logger, json_response, string_to_boolean
from api.db import get_db_context
from api.errors import UnknownVideo, ValidationError, InvalidOrderBy
from api.videos.common import get_video_info_json, get_matching_directories, get_media_directory, \
    get_relative_to_media_directory, get_allowed_limit
from api.videos.schema import VideoResponse, JSONErrorResponse, VideoSearchRequest, VideoSearchResponse, \
    DirectoriesResponse, DirectoriesRequest

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

    return json_response({'video': video})


VIDEO_ORDERS = {
    'upload_date': 'upload_date ASC, LOWER(video_path) ASC',
    '-upload_date': 'upload_date DESC NULLS LAST, LOWER(video_path) DESC',
    'rank': '2 DESC, LOWER(video_path) DESC',
    '-rank': '2 ASC, LOWER(video_path) ASC',
}
DEFAULT_VIDEO_ORDER = 'rank'
VIDEO_QUERY_LIMIT = 20


def video_search(
        db_conn: psycopg2.connect,
        db: DictDB,
        search_str: str = None,
        offset: int = None,
        limit: int = VIDEO_QUERY_LIMIT,
        channel_link: str = None,
        order_by: str = None,
        favorites: bool = None,
) -> Tuple[List[Dict], int]:
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

    # Filter for/against favorites, if it was provided
    favorites_where = ''
    if favorites is not None:
        favorites_where = f'AND favorite IS {"NOT" if favorites else ""} NULL'

    where = ''
    if search_str:
        # A search_str was provided by the user, modify the query to filter by it.
        select = 'id, ts_rank_cd(textsearch, websearch_to_tsquery(%(search_str)s)), COUNT(*) OVER() AS total'
        where = 'AND textsearch @@ websearch_to_tsquery(%(search_str)s)'
        args['search_str'] = search_str
    else:
        # No search_str provided.  Get id and total only.
        select = 'id, COUNT(*) OVER() AS total'

    query = f'''
        SELECT
            {select}
        FROM video
        WHERE
            video_path IS NOT NULL
            {where}
            {channel_where}
            {favorites_where}
        ORDER BY {order}
        OFFSET %(offset)s LIMIT {limit}
    '''

    curs.execute(query, args)
    results = list(curs.fetchall())
    total = results[0][1] if results else 0
    ranked_ids = [i[0] for i in results]

    results = []
    if ranked_ids:
        Video = db['video']
        results = Video.get_where(Video['id'].In(ranked_ids))
        results = sorted(results, key=lambda r: ranked_ids.index(r['id']))
    return results, total


@video_bp.post('/search')
@validate_doc(
    summary='Search Video titles and captions',
    consumes=VideoSearchRequest,
    produces=VideoSearchResponse,
)
def search(_: Request, data: dict):
    try:
        search_str = data.get('search_str')
        channel_link = data.get('channel_link')
        order_by = data.get('order_by', DEFAULT_VIDEO_ORDER)
        offset = int(data.get('offset', 0))
        limit = get_allowed_limit(data.get('limit'))
        favorites = string_to_boolean(data['favorites']) if 'favorites' in data else None
    except Exception as e:
        raise ValidationError('Unable to validate search queries') from e

    if order_by not in VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    with get_db_context() as (db_conn, db):
        videos, videos_total = video_search(db_conn, db, search_str, offset, limit, channel_link, order_by, favorites)

        # Get each Channel for each Video, this will be converted to a dict by the response
        # TODO these are huge, and must be simplified.
        _ = [i['channel'] for i in videos]

    ret = {'videos': videos, 'totals': {'videos': videos_total}}
    return json_response(ret)


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
