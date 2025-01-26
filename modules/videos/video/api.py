from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger, wrol_mode_check
from wrolpi.errors import InvalidOrderBy, ValidationError
from wrolpi.events import Events
from wrolpi.schema import JSONErrorResponse
from . import lib
from .. import schema
from ..lib import save_channels_config

video_bp = Blueprint('Video', '/api/videos')

logger = logger.getChild(__name__)


@video_bp.get('/video/<video_id:int>')
@openapi.description('Get Video information')
@openapi.response(HTTPStatus.OK, schema.VideoResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get(_: Request, video_id: int):
    video, previous_video, next_video = lib.get_video_for_app(video_id)
    return json_response({'file_group': video, 'prev': previous_video, 'next': next_video})


@video_bp.get('/video/<video_id:int>/comments')
@openapi.description('Get Video comments')
@openapi.response(HTTPStatus.OK, schema.VideoCommentsResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get_comments(_: Request, video_id: int):
    video = lib.get_video(video_id)
    return json_response({'comments': video.get_comments()})


@video_bp.get('/video/<video_id:int>/captions')
@openapi.description('Get Video captions')
@openapi.response(HTTPStatus.OK, schema.VideoCaptionsResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get_captions(_: Request, video_id: int):
    video = lib.get_video(video_id)
    return json_response({'captions': video.file_group.d_text})


@video_bp.post('/search')
@openapi.definition(
    summary='Search Video titles and captions',
    body=schema.VideoSearchRequest,
)
@openapi.response(HTTPStatus.OK, schema.VideoSearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.VideoSearchRequest)
async def search_videos(_: Request, body: schema.VideoSearchRequest):
    if body.order_by not in lib.VIDEO_ORDERS:
        raise InvalidOrderBy('Invalid order by')

    file_groups, videos_total = lib.search_videos(
        body.search_str,
        body.offset,
        body.limit,
        body.channel_id,
        body.order_by,
        body.tag_names,
        body.headline,
    )

    ret = {'file_groups': list(file_groups), 'totals': {'file_groups': videos_total}}
    return json_response(ret)


@video_bp.delete('/video/<video_ids:[0-9,]+>', name='Video Delete Many')
@video_bp.delete('/video/<video_ids:int>', name='Video Delete One')
@openapi.description('Delete videos.')
@openapi.response(HTTPStatus.NO_CONTENT)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
async def video_delete(_: Request, video_ids: str):
    try:
        video_ids = [int(i) for i in str(video_ids).split(',')]
    except Exception:
        raise ValidationError('Unable to parse video ids')

    lib.delete_videos(*video_ids)

    save_channels_config.activate_switch()
    Events.send_deleted(f'Deleted {len(video_ids)} videos')
    return response.empty()
