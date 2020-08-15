from datetime import datetime
from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request

from api.common import validate_doc, logger, json_response, wrol_mode_check
from api.db import get_db_context
from api.errors import ValidationError, InvalidOrderBy
from api.videos.common import get_video_info_json, get_matching_directories, get_media_directory, \
    get_relative_to_media_directory, get_allowed_limit, minimize_video
from api.videos.schema import VideoResponse, JSONErrorResponse, VideoSearchRequest, VideoSearchResponse, \
    DirectoriesResponse, DirectoriesRequest
from api.videos.video.lib import get_video, get_surrounding_videos, VIDEO_ORDERS, DEFAULT_VIDEO_ORDER, video_search, \
    delete_video

video_bp = Blueprint('Video')

logger = logger.getChild(__name__)


@video_bp.get('/video/<video_id:int>')
@validate_doc(
    summary='Get Video information',
    produces=VideoResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def video_get(request, video_id: int):
    with get_db_context(commit=True) as (db_conn, db):
        video = get_video(db, video_id)
        video['viewed'] = datetime.now()
        video.flush()

        info_json = get_video_info_json(video)
        video = dict(video)
        video['info_json'] = info_json
        video = minimize_video(video)

        previous_video, next_video = get_surrounding_videos(db, video_id, video['channel_id'])
        previous_video = minimize_video(previous_video) if previous_video else None
        next_video = minimize_video(next_video) if next_video else None

    return json_response({'video': video, 'prev': previous_video, 'next': next_video})


@video_bp.post('/search')
@validate_doc(
    summary='Search Video titles and captions',
    consumes=VideoSearchRequest,
    produces=VideoSearchResponse,
)
async def search(_: Request, data: dict):
    try:
        search_str = data.get('search_str')
        channel_link = data.get('channel_link')
        order_by = data.get('order_by', DEFAULT_VIDEO_ORDER)
        offset = int(data.get('offset', 0))
        limit = get_allowed_limit(data.get('limit'))
        favorites = data.get('favorites', None)
    except Exception as e:
        raise ValidationError('Unable to validate search queries') from e

    if order_by not in VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    with get_db_context() as (db_conn, db):
        videos, videos_total = video_search(db, search_str, offset, limit, channel_link, order_by, favorites)

        # Get each Channel for each Video, this will be converted to a dict by the response
        videos = [minimize_video(i) for i in videos]

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


@video_bp.delete('/video/<video_id:int>')
@validate_doc(
    summary='Delete a video',
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
@wrol_mode_check
def video_delete(request: Request, video_id: int):
    with get_db_context(commit=True) as (db_conn, db):
        video = get_video(db, video_id)
    delete_video(video)
    return response.raw('', HTTPStatus.NO_CONTENT)
