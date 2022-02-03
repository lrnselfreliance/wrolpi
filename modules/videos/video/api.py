from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, run_after, get_media_directory, \
    get_relative_to_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidOrderBy
from wrolpi.root_api import json_response
from wrolpi.schema import JSONErrorResponse
from .lib import get_video, VIDEO_ORDERS, video_search, get_video_for_app
from ..common import get_matching_directories
from ..lib import save_channels_config
from ..schema import VideoResponse, VideoSearchRequest, VideoSearchResponse, \
    DirectoriesResponse, DirectoriesRequest

video_bp = Blueprint('Video', '/api/videos')

logger = logger.getChild(__name__)


@video_bp.get('/video/<video_id:int>')
@openapi.description('Get Video information')
@openapi.response(HTTPStatus.OK, VideoResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get(_: Request, video_id: int):
    video, previous_video, next_video = get_video_for_app(video_id)
    return json_response({'video': video, 'prev': previous_video, 'next': next_video})


@video_bp.post('/search')
@openapi.definition(
    summary='Search Video titles and captions',
    body=VideoSearchRequest,
)
@openapi.response(HTTPStatus.OK, VideoSearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(VideoSearchRequest)
async def search(_: Request, body: VideoSearchRequest):
    if body.order_by not in VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    videos, videos_total = video_search(
        body.search_str,
        body.offset,
        body.limit,
        body.channel_link,
        body.order_by,
        body.filters,
    )

    ret = {'videos': list(videos), 'totals': {'videos': videos_total}}
    return json_response(ret)


@video_bp.post('/directories')
@openapi.definition(
    summary='Get all directories that match the search_str, prefixed by the media directory.',
    body=DirectoriesRequest,
)
@openapi.response(HTTPStatus.OK, DirectoriesResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(DirectoriesRequest)
def directories(_, body: DirectoriesRequest):
    search_str = str(get_media_directory() / (body.search_str or ''))
    dirs = get_matching_directories(search_str)
    dirs = [str(get_relative_to_media_directory(i)) for i in dirs]
    return response.json({'directories': dirs})


@video_bp.delete('/video/<video_id:int>')
@openapi.description('Delete a video.')
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
@run_after(save_channels_config)
def video_delete(_: Request, video_id: int):
    with get_db_session(commit=True) as session:
        video = get_video(session, video_id)
        video.delete()
    return response.raw('', HTTPStatus.NO_CONTENT)
