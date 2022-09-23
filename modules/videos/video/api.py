from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, run_after, get_media_directory, \
    get_relative_to_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidOrderBy, ValidationError
from wrolpi.root_api import json_response
from wrolpi.schema import JSONErrorResponse
from . import lib
from .. import common, schema

video_bp = Blueprint('Video', '/api/videos')

logger = logger.getChild(__name__)


@video_bp.get('/video/<video_id:int>')
@openapi.description('Get Video information')
@openapi.response(HTTPStatus.OK, schema.VideoResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get(_: Request, video_id: int):
    video, previous_video, next_video = lib.get_video_for_app(video_id)
    return json_response({'file': video, 'prev': previous_video, 'next': next_video})


@video_bp.post('/search')
@openapi.definition(
    summary='Search Video titles and captions',
    body=schema.VideoSearchRequest,
)
@openapi.response(HTTPStatus.OK, schema.VideoSearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.VideoSearchRequest)
async def search(_: Request, body: schema.VideoSearchRequest):
    if body.order_by not in lib.VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    files, videos_total = lib.video_search(
        body.search_str,
        body.offset,
        body.limit,
        body.channel_id,
        body.order_by,
        body.filters,
    )

    ret = {'files': list(files), 'totals': {'files': videos_total}}
    return json_response(ret)


@video_bp.post('/directories')
@openapi.definition(
    summary='Get all directories that match the search_str, prefixed by the media directory.',
    body=schema.DirectoriesRequest,
)
@openapi.response(HTTPStatus.OK, schema.DirectoriesResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.DirectoriesRequest)
def directories(_, body: schema.DirectoriesRequest):
    search_str = str(get_media_directory() / (body.search_str or ''))
    dirs = common.get_matching_directories(search_str)
    dirs = [str(get_relative_to_media_directory(i)) for i in dirs]
    return response.json({'directories': dirs})


@video_bp.delete('/video/<video_ids:[0-9,]+>')
@video_bp.delete('/video/<video_ids:int>')
@openapi.description('Delete videos.')
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
@run_after(lib.save_channels_config)
def video_delete(_: Request, video_ids: str):
    try:
        video_ids = [int(i) for i in str(video_ids).split(',')]
    except Exception:
        return ValidationError('Unable to parse video ids')

    lib.delete_videos(*video_ids)
    return response.raw('', HTTPStatus.NO_CONTENT)
