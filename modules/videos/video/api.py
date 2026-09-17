import asyncio
from http import HTTPStatus

from sanic import Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger, wrol_mode_check
from wrolpi.errors import InvalidOrderBy, InvalidJob
from wrolpi.schema import JSONErrorResponse
from . import lib
from .. import schema
from ..transcode import transcode_video_job, validate_transcode_request, REMOVE_VIDEO

video_bp = Blueprint('Video', '/api/videos')

logger = logger.getChild(__name__)


@video_bp.get('/<file_group_id:int>')
@openapi.description('Get Video information')
@openapi.response(HTTPStatus.OK, schema.VideoResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get(request: Request, file_group_id: int):
    skip_viewed = request.args.get('skip_viewed', '').lower() == 'true'
    video, previous_video, next_video = lib.get_video_for_app(file_group_id, skip_viewed=skip_viewed)
    return json_response({'file_group': video, 'prev': previous_video, 'next': next_video})


@video_bp.put('/<file_group_id:int>')
@openapi.description('Edit a Video\'s details.  Written to its info json; the Video is validated again.')
@openapi.body({'application/json': schema.VideoUpdateRequest})
@openapi.response(HTTPStatus.OK, schema.VideoResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.VideoUpdateRequest)
@wrol_mode_check
async def video_update(_: Request, file_group_id: int, body: schema.VideoUpdateRequest):
    lib.update_video(file_group_id, title=body.title, description=body.description)
    video, previous_video, next_video = lib.get_video_for_app(file_group_id)
    return json_response({'file_group': video, 'prev': previous_video, 'next': next_video})


@video_bp.get('/<file_group_id:int>/comments')
@openapi.description('Get Video comments')
@openapi.response(HTTPStatus.OK, schema.VideoCommentsResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get_comments(_: Request, file_group_id: int):
    video = lib.get_video(file_group_id)
    return json_response({'comments': video.get_comments()})


@video_bp.get('/<file_group_id:int>/description')
@openapi.description('Get Video description')
@openapi.response(HTTPStatus.OK, schema.VideoDescriptionResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get_description(_: Request, file_group_id: int):
    video = lib.get_video(file_group_id)
    return json_response({'description': video.get_description()})


@video_bp.get('/<file_group_id:int>/captions')
@openapi.description('Get Video captions')
@openapi.response(HTTPStatus.OK, schema.VideoCaptionsResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
def video_get_captions(_: Request, file_group_id: int):
    video = lib.get_video(file_group_id)
    return json_response({'captions': video.get_caption_chunks()})


@video_bp.post('/<file_group_id:int>/transcode')
@openapi.description('Queue a Job which transcodes the Video to the requested codecs/container.')
@openapi.body({'application/json': schema.VideoTranscodeRequest})
@openapi.response(HTTPStatus.OK, schema.VideoTranscodeResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.VideoTranscodeRequest)
@wrol_mode_check
async def video_transcode(_: Request, file_group_id: int, body: schema.VideoTranscodeRequest):
    try:
        validate_transcode_request(body.video_codec, body.audio_codec, body.container, body.fragmented)
    except ValueError as e:
        raise InvalidJob(str(e))
    # Raises UnknownVideo (404) before anything is queued.
    video = lib.get_video(file_group_id)
    is_audio = (video.file_group.mimetype or '').startswith('audio/')
    if is_audio and body.video_codec and body.video_codec != REMOVE_VIDEO:
        raise InvalidJob(f'This is an audio file; it has no video stream to transcode to {body.video_codec}')
    if body.video_codec == REMOVE_VIDEO and not is_audio:
        action = 'Extract audio from'
    elif not body.video_codec and not body.audio_codec:
        action = 'Remux'
    else:
        action = 'Transcode'
    job_id = transcode_video_job.enqueue(
        description=f'{action} {video.video_path.name}',
        file_group_id=file_group_id,
        video_codec=body.video_codec,
        audio_codec=body.audio_codec,
        container=body.container,
        fragmented=body.fragmented,
    )
    return json_response({'job_id': job_id})


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

    # Synchronous SQLite query; keep it off the event loop.
    file_groups, videos_total = await asyncio.to_thread(
        lib.search_videos,
        body.search_str,
        body.offset,
        body.limit,
        body.channel_id,
        body.order_by,
        body.tag_names,
        body.headline,
        body.censored,
        body.deep,
    )

    ret = {'file_groups': list(file_groups), 'totals': {'file_groups': videos_total}}
    return json_response(ret)


