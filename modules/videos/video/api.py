from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request

from wrolpi.common import logger, wrol_mode_check, run_after, get_media_directory, \
    get_relative_to_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import ValidationError, InvalidOrderBy
from wrolpi.root_api import json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from .lib import get_video, VIDEO_ORDERS, DEFAULT_VIDEO_ORDER, video_search, get_video_for_app
from ..common import get_matching_directories, get_allowed_limit
from ..lib import save_channels_config
from ..schema import VideoResponse, VideoSearchRequest, VideoSearchResponse, \
    DirectoriesResponse, DirectoriesRequest

video_bp = Blueprint('Video', '/api/videos')

logger = logger.getChild(__name__)


@video_bp.get('/video/<video_id:int>')
@validate_doc(
    summary='Get Video information',
    produces=VideoResponse,
    responses=(
            (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ),
)
def video_get(_: Request, video_id: int):
    video, previous_video, next_video = get_video_for_app(video_id)
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
        filters = data.get('filters', None)
    except Exception as e:
        raise ValidationError('Unable to validate search queries') from e

    if order_by not in VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    videos, videos_total = video_search(search_str, offset, limit, channel_link, order_by, filters)

    ret = {'videos': list(videos), 'totals': {'videos': videos_total}}
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
@run_after(save_channels_config)
def video_delete(_: Request, video_id: int):
    with get_db_session(commit=True) as session:
        video = get_video(session, video_id)
        video.delete()
    return response.raw('', HTTPStatus.NO_CONTENT)
