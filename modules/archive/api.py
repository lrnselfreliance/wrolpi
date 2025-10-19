import multiprocessing
import queue
from http import HTTPStatus

from sanic import response, Request, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi
from sqlalchemy.orm import Session

from wrolpi.api_utils import json_response, api_app
from wrolpi.common import logger, wrol_mode_check, api_param_limiter, TRACE_LEVEL
from wrolpi.db import get_db_session
from wrolpi.errors import ValidationError
from wrolpi.events import Events
from wrolpi.files.lib import upsert_file
from wrolpi.schema import JSONErrorResponse
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from . import lib, schema

NAME = 'archive'

archive_bp = Blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


@archive_bp.get('/<archive_id:int>')
@openapi.description('Get an archive')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_archive(_: Request, archive_id: int):
    archive = lib.get_archive(archive_id=archive_id)
    archive_file_group = archive.file_group.__json__()
    history = [i.file_group.__json__() for i in archive.history]
    return json_response({'file_group': archive_file_group, 'history': history})


@archive_bp.delete('/<archive_ids:int>', name='archive_delete_one')
@archive_bp.delete('/<archive_ids:[0-9,]+>', name='archive_delete_many')
@openapi.description('Delete Archives')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
async def delete_archive(_: Request, archive_ids: str):
    try:
        archive_ids = [int(i) for i in str(archive_ids).split(',')]
    except ValueError:
        raise ValidationError('Could not parse archive ids')
    lib.delete_archives(*archive_ids)
    return response.empty()


@archive_bp.get('/domains')
@openapi.summary('Get a list of all Domains and their Archive statistics')
@openapi.response(200, schema.GetDomainsResponse, "The list of domains")
async def get_domains(_: Request):
    domains = lib.get_domains()
    return json_response({'domains': domains, 'totals': {'domains': len(domains)}})


archive_limit_limiter = api_param_limiter(100)


@archive_bp.post('/search')
@openapi.definition(
    summary='A File search with more filtering related to Archives',
    body=schema.ArchiveSearchRequest,
)
@openapi.response(HTTPStatus.OK, schema.ArchiveSearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.ArchiveSearchRequest)
async def search_archives(_: Request, body: schema.ArchiveSearchRequest):
    search_str = body.search_str
    domain = body.domain
    limit = archive_limit_limiter(body.limit)
    offset = body.offset or 0

    file_groups, total = lib.search_archives(search_str, domain, limit, offset, body.order_by, body.tag_names,
                                             body.headline)
    ret = dict(file_groups=file_groups, totals=dict(file_groups=total))
    return json_response(ret)


@archive_bp.get('/upload')
@openapi.definition(
    summary='A message to confirm to the user that they have the correct upload URL.'
)
async def get_upload_singlefile(request: Request):
    return response.text('This is the URL to upload files using the SingleFile browser extension.'
                         ' This requires a POST request.')


@register_switch_handler('singlefile_upload_switch_handler')
async def singlefile_upload_switch_handler(url=None):
    """Used by `post_upload_singlefile` to upload a single file"""
    from wrolpi.downloader import Download
    from . import ArchiveDownloader

    q: multiprocessing.Queue = api_app.shared_ctx.archive_singlefiles

    trace_enabled = logger.isEnabledFor(TRACE_LEVEL)
    if trace_enabled:
        logger.trace(f'singlefile_upload_switch_handler called for {url}')
    try:
        singlefile = q.get_nowait()
    except queue.Empty:
        if trace_enabled:
            logger.trace(f'singlefile_upload_switch_handler called on empty queue')
        return

    try:
        q_size = q.qsize()
    except NotImplementedError:
        # qsize() is not implemented on macOS
        q_size = '?'
    logger.info(f'singlefile_upload_switch_handler queue size: {q_size}')

    try:
        archive = await lib.singlefile_to_archive(singlefile)
    except Exception as e:
        logger.error(f'singlefile_upload_switch_handler failed', exc_info=e)
        Events.send_upload_archive_failed(f'Failed to convert singlefile to archive: {e}')
        raise

    name = archive.file_group.title or archive.file_group.url
    logger.info(f'Created Archive from upload ({q_size}): {archive}')
    Events.send_archive_uploaded(f'Created Archive from upload: {name}', url=archive.location)
    url = archive.file_group.url
    if url and (download := Download.get_by_url(url)):
        if (download.is_failed or download.is_deferred) and download.downloader == ArchiveDownloader.name:
            # Download was attempted and failed, user manually archived the URL.
            download.complete()
            download.location = archive.location
            Session.object_session(download).commit()

    # Call this function again so any new singlefiles can be archived.
    singlefile_upload_switch_handler.activate_switch()


singlefile_upload_switch_handler: ActivateSwitchMethod


@register_switch_handler('generate_screenshot_switch_handler')
async def generate_screenshot_switch_handler(archive_id=None):
    """Used by `post_generate_screenshot` to generate screenshots in the background"""
    q: multiprocessing.Queue = api_app.shared_ctx.archive_screenshots

    trace_enabled = logger.isEnabledFor(TRACE_LEVEL)
    if trace_enabled:
        logger.trace(f'generate_screenshot_switch_handler called for archive_id={archive_id}')
    try:
        archive_id = q.get_nowait()
    except queue.Empty:
        if trace_enabled:
            logger.trace(f'generate_screenshot_switch_handler called on empty queue')
        return

    try:
        q_size = q.qsize()
    except NotImplementedError:
        # qsize() is not implemented on macOS
        q_size = '?'
    logger.info(f'generate_screenshot_switch_handler queue size: {q_size}')

    try:
        await lib.generate_archive_screenshot(archive_id)
        # Always send success event since exceptions are raised on failure
        from modules.archive import Archive
        archive = lib.get_archive(archive_id=archive_id)
        location = archive.location
        name = archive.file_group.title or archive.file_group.url
        logger.info(f'Generated screenshot for Archive ({q_size}): {archive_id}')
        Events.send_screenshot_generated(f'Generated screenshot for: {name}', url=location)
    except Exception as e:
        logger.error(f'generate_screenshot_switch_handler failed for Archive {archive_id}', exc_info=e)
        Events.send_screenshot_generation_failed(f'Failed to generate screenshot: {e}')
        raise

    # Call this function again so any new screenshot requests can be processed.
    generate_screenshot_switch_handler.activate_switch()


generate_screenshot_switch_handler: ActivateSwitchMethod


@archive_bp.post('/upload')
@openapi.definition(
    summary='Upload SingleFile from SingleFile browser extension and convert it to an Archive.'
)
async def post_upload_singlefile(request: Request):
    url = request.form['url'][0]
    singlefile = request.files['singlefile_contents'][0].body
    logger.info(f'Got Archive upload of {len(singlefile)} bytes for URL: {url}')

    # Extract the URL to ensure that the singlefile is valid.
    lib.get_url_from_singlefile(singlefile)

    # Send processing to background task so the extension can continue.
    api_app.shared_ctx.archive_singlefiles.put(singlefile)
    singlefile_upload_switch_handler.activate_switch(context=dict(url=url))
    # Return empty json response because SingleFile extension expects a JSON response.
    return json_response(dict(), status=HTTPStatus.OK)


@archive_bp.post('/<archive_id:int>/generate_screenshot')
@openapi.description('Generate a screenshot for an Archive that does not have one')
@openapi.response(HTTPStatus.OK, description='Screenshot generation queued')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@wrol_mode_check
async def post_generate_screenshot(_: Request, archive_id: int):
    """Queue a screenshot generation request for an Archive."""
    # Verify archive exists
    try:
        archive = lib.get_archive(archive_id=archive_id)
    except Exception:
        return json_response({'error': f'Archive {archive_id} not found'}, status=HTTPStatus.NOT_FOUND)

    if not archive.singlefile_path:
        return json_response({'error': 'Archive has no singlefile'}, status=HTTPStatus.BAD_REQUEST)

    # Queue the screenshot generation request
    logger.info(f'Queueing screenshot generation for Archive {archive_id}')
    api_app.shared_ctx.archive_screenshots.put(archive_id)
    generate_screenshot_switch_handler.activate_switch(context=dict(archive_id=archive_id))

    return json_response({'message': 'Screenshot generation queued'}, status=HTTPStatus.OK)
