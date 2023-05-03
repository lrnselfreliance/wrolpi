import pathlib
from http import HTTPStatus
from multiprocessing import Manager
from typing import List

import sanic.request
from sanic import response, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import get_media_directory, wrol_mode_check, get_relative_to_media_directory, logger, background_task
from wrolpi.errors import InvalidFile, UnknownDirectory, FileUploadFailed
from wrolpi.root_api import get_blueprint, json_response
from . import lib, schema
from ..schema import JSONErrorResponse

bp = get_blueprint('Files', '/api/files')

logger = logger.getChild(__name__)


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
                                          body.tag_names, body.headline)
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


@bp.post('/search_directories')
@openapi.definition(
    summary='Get all directories whose name matches the provided name.',
    body=schema.DirectoriesSearchRequest,
)
@validate(schema.DirectoriesSearchRequest)
async def post_search_directories(_, body: schema.DirectoriesSearchRequest):
    if len(body.name) <= 1:
        return response.empty()

    from modules.videos.channel import lib as channels_lib
    channels = channels_lib.search_channels_by_name(name=body.name)
    channel_directories = [dict(path=i.directory, name=i.name) for i in channels]
    channel_paths = [i['path'] for i in channel_directories]

    from modules.archive import lib as archives_lib
    domains = archives_lib.search_domains_by_name(name=body.name)
    domain_directories = [dict(path=i.directory, domain=i.domain) for i in domains]
    domain_paths = [i['path'] for i in domain_directories]

    # Get all directories that match but do not contain the above directories.
    from wrolpi.files.models import Directory
    directories: List[Directory] = await lib.search_directories_by_name(
        name=body.name,
        excluded=list(map(str, channel_paths + domain_paths)))

    body = {
        'directories': directories,
        'channel_directories': channel_directories,
        'domain_directories': domain_directories
    }
    return json_response(body)


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


# {
#   '/media/directory/sub-dir/the-file-name.suffix': 2,  # The chunk number we will receive next.
# }
UPLOADED_FILES = Manager().dict()


@bp.post('/upload')
async def post_upload(request: Request):
    """Accepts a multipart/form-data request to upload a single file.

    Tracks the number of chunks and will request the correct chunk of the chunks come out of order.

    Will not overwrite an existing file, unless a previous upload did not complete."""
    try:
        destination = request.form['destination'][0]
    except Exception as e:
        logger.error(f'Failed to get upload destination', exc_info=e)
        raise UnknownDirectory('Must provide destination') from e

    destination = get_media_directory() / destination
    if not destination.is_dir():
        raise UnknownDirectory('Destination must be a relative directory that is already in the media directory!')

    try:
        filename = str(request.form['filename'][0])
    except Exception:
        raise FileUploadFailed('filename string is required')

    try:
        chunk_num = int(request.form['chunkNumber'][0])
    except Exception:
        raise FileUploadFailed('chunkNumber integer is required')

    try:
        total_chunks = int(request.form['totalChunks'][0])
    except Exception:
        raise FileUploadFailed('totalChunks integer is required')

    filename = pathlib.Path(filename.lstrip('/'))
    output = destination / filename
    output_str = str(output)

    # Chunks start at 0.
    expected_chunk_num = UPLOADED_FILES.get(output_str, 0)
    logger.debug(f'last_chunk_num is {expected_chunk_num} for {repr(output_str)} received {chunk_num=}')

    chunk_size = int(request.form['chunkSize'][0])
    # The bytes of the uploading file.
    chunk: sanic.request.File = request.files['chunk'][0]
    if (body_size := len(chunk.body)) != chunk_size:
        raise FileUploadFailed(f'Chunk size does not match the size of the chunk! {chunk_size} != {body_size=}')

    if chunk_num == 0 and output.is_file() and output_str in UPLOADED_FILES:
        # User attempted to upload this same file, but it did not finish.  User has started over again.
        logger.info(f'Restarting upload of {repr(output_str)}')
        output.unlink()
        expected_chunk_num = 0

    if expected_chunk_num != chunk_num:
        # Respond with a request for the correct chunk number.
        return json_response({'expected_chunk': expected_chunk_num}, HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)

    if chunk_num == 0 and output.is_file():
        # Do not overwrite files that already exist.
        raise FileUploadFailed('File already exists!')
    if output.is_dir():
        raise FileUploadFailed('File already exists as a directory!')

    if chunk_num == 0:
        try:
            output.touch()
        except FileNotFoundError:
            # Uploading a file in a directory.  Use mkdir to create all parents, but remove final directory that is
            # created because it will be the file.
            output.mkdir(parents=True)
            output.rmdir()
        with output.open('wb') as fh:
            fh.write(chunk.body)
    else:
        with output.open('ab') as fh:
            # Finally append the chunk to the file.
            fh.write(chunk.body)

    # Store what we expect to receive next.
    expected_chunk_num += 1
    UPLOADED_FILES[output_str] = expected_chunk_num

    # Chunks start at 0.
    if chunk_num == total_chunks:
        # File upload is complete.
        del UPLOADED_FILES[output_str]
        background_task(lib.refresh_files([output]))
        return response.empty(HTTPStatus.CREATED)

    # Request the next chunk.
    return json_response({'expected_chunk': expected_chunk_num}, HTTPStatus.OK)
