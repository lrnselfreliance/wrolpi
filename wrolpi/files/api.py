import pathlib
from http import HTTPStatus
from typing import List
from urllib.request import Request

from sanic import response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import get_media_directory, wrol_mode_check, background_task, get_relative_to_media_directory
from wrolpi.errors import InvalidFile
from wrolpi.root_api import get_blueprint, json_response
from . import lib, schema
from ..schema import JSONErrorResponse
from ..vars import PYTEST

bp = get_blueprint('Files', '/api/files')


def paths_to_files(paths: List[pathlib.Path]):
    """Convert Paths to what the React UI expects."""
    media_directory = get_media_directory()
    new_files = []
    for path in paths:
        stat = path.stat()
        key = path.relative_to(media_directory)
        modified = stat.st_mtime
        if path.is_dir():
            key = f'{key}/'
            new_files.append(dict(
                key=key,
                modified=modified,
                url=key,
                name=path.name,
            ))
        else:
            # A File should know it's size.
            new_files.append(dict(
                key=key,
                modified=modified,
                size=stat.st_size,
                url=key,
                name=path.name,
            ))
    return new_files


@bp.post('/')
@openapi.definition(
    summary='List files in a directory',
    body=schema.FilesRequest,
)
@validate(schema.FilesRequest)
async def get_files(_: Request, body: schema.FilesRequest):
    directories = body.directories or []

    files = lib.list_files(directories)
    files = paths_to_files(files)
    return json_response({'files': files})


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
@openapi.description('Find and index all files in the media directory.')
@wrol_mode_check
async def refresh(_: Request):
    await lib.refresh_files()
    return response.empty()


@bp.post('/refresh/directory')
@openapi.description('Find and index all files in the provided directory.')
@validate(schema.DirectoryRefreshRequest)
@wrol_mode_check
async def refresh_directory(_: Request, body: schema.DirectoryRefreshRequest):
    directory = get_media_directory() / body.directory
    if PYTEST:
        await lib.refresh_directory_files_recursively(directory)
    else:
        background_task(lib.refresh_directory_files_recursively(directory))
    return response.empty()


@bp.post('/refresh/list')
@openapi.definition(
    summary='Refresh and index all files in the provided list',
    body=schema.FilesRefreshListRequest,
)
@validate(schema.FilesRefreshListRequest)
@wrol_mode_check
async def refresh_files_list(_: Request, body: schema.FilesRefreshListRequest):
    if PYTEST:
        await lib.refresh_files_list(body.files, body.include_files_near)
    else:
        background_task(lib.refresh_files_list(body.files, body.include_files_near))
    return response.empty()


@bp.post('/search')
@openapi.definition(
    summary='Search Files',
    body=schema.FilesSearchRequest,
)
@validate(schema.FilesSearchRequest)
async def post_search_files(_: Request, body: schema.FilesSearchRequest):
    files, total = lib.search_files(body.search_str, body.limit, body.offset, body.mimetypes, body.model)
    return json_response(dict(files=files, totals=dict(files=total)))


@bp.post('/directories')
@openapi.definition(
    summary='Get all directories that match the search_str, prefixed by the media directory.',
    body=schema.DirectoriesRequest,
)
@openapi.response(HTTPStatus.OK, schema.DirectoriesResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.DirectoriesRequest)
def directories(_, body: schema.DirectoriesRequest):
    path = get_media_directory() / (body.search_str or '')
    search_str = str(path)
    dirs = lib.get_matching_directories(search_str)
    dirs = [str(get_relative_to_media_directory(i)) for i in dirs]

    body = {'directories': dirs, 'exists': path.exists(), 'is_dir': path.is_dir(), 'is_file': path.is_file()}
    return response.json(body)
