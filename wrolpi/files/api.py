from http import HTTPStatus

from sanic import response, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import get_media_directory, wrol_mode_check, get_relative_to_media_directory
from wrolpi.errors import InvalidFile
from wrolpi.root_api import get_blueprint, json_response
from . import lib, schema
from ..schema import JSONErrorResponse

bp = get_blueprint('Files', '/api/files')


@bp.post('/')
@openapi.definition(
    summary='List files in a directory',
    body=schema.FilesRequest,
)
@validate(schema.FilesRequest)
async def get_files(_: Request, body: schema.FilesRequest):
    directories = body.directories or []

    files = lib.list_directories_contents(directories)
    return json_response({'files': files})


@bp.post('/file')
@openapi.definition(
    summary='Get the dict of one file',
    body=schema.FileRequest,
)
@validate(schema.FileRequest)
async def get_file(_: Request, body: schema.FileRequest):
    file = lib.get_file_dict(body.file)
    return json_response({'file': file})


@bp.post('/delete')
@openapi.definition(
    summary='Delete a single file.  Returns an error if WROL Mode is enabled.',
    body=schema.DeleteRequest,
)
@validate(schema.DeleteRequest)
async def delete_file(_: Request, body: schema.DeleteRequest):
    if not body.file:
        raise InvalidFile('file cannot be empty')
    lib.delete_file(body.file)
    return response.empty()


@bp.post('/refresh')
@openapi.definition(
    summary='Refresh and index all paths (files/directories) in the provided list.  Refresh all files if not provided.',
    body=schema.FilesRefreshRequest,
)
@wrol_mode_check
async def refresh(request: Request):
    paths = None
    if request.body:
        media_directory = get_media_directory()
        if not isinstance(request.json['paths'], list):
            raise ValueError('Can only refresh a list')

        paths = [media_directory / i for i in request.json['paths']]
    await lib.refresh_files(paths)
    return response.empty()


@bp.get('/refresh_progress')
@openapi.definition(
    summary='Get the progress of the file refresh'
)
async def refresh_progress(request: Request):
    progress = lib.get_refresh_progress()
    return json_response(dict(
        progress=progress,
    ))


@bp.post('/search')
@openapi.definition(
    summary='Search Files',
    body=schema.FilesSearchRequest,
)
@validate(schema.FilesSearchRequest)
async def post_search_files(_: Request, body: schema.FilesSearchRequest):
    file_groups, total = lib.search_files(body.search_str, body.limit, body.offset, body.mimetypes, body.model,
                                          body.tag_names)
    return json_response(dict(file_groups=file_groups, totals=dict(file_groups=total)))


@bp.post('/directories')
@openapi.definition(
    summary='Get all directories that match the search_str, prefixed by the media directory.',
    body=schema.DirectoriesRequest,
)
@openapi.response(HTTPStatus.OK, schema.DirectoriesResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.DirectoriesRequest)
def post_directories(_, body: schema.DirectoriesRequest):
    path = get_media_directory() / (body.search_str or '')
    search_str = str(path)
    dirs = lib.get_matching_directories(search_str)
    dirs = [str(get_relative_to_media_directory(i)) for i in dirs]

    body = {'directories': dirs, 'exists': path.exists(), 'is_dir': path.is_dir(), 'is_file': path.is_file()}
    return response.json(body)


@bp.post('/tag')
@validate(schema.TagFileGroupPost)
async def post_tag_file_group(_, body: schema.TagFileGroupPost):
    if not body.tag_id and not body.tag_name:
        return json_response(
            dict(error='tag_id and tag_name cannot both be empty'),
            HTTPStatus.BAD_REQUEST,
        )
    if not body.file_group_id and not body.file_group_primary_path:
        return json_response(
            dict(error='file_group_primary_path and file_group_id cannot both be empty'),
            HTTPStatus.BAD_REQUEST,
        )

    await lib.add_file_group_tag(body.file_group_id, body.file_group_primary_path, body.tag_name, body.tag_id)
    return response.empty(HTTPStatus.CREATED)


@bp.post('/untag')
@validate(schema.TagFileGroupPost)
async def post_untag_file_group(_, body: schema.TagFileGroupPost):
    await lib.remove_file_group_tag(body.file_group_id, body.file_group_primary_path, body.tag_name, body.tag_id)
    return response.empty(HTTPStatus.NO_CONTENT)
