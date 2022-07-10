import asyncio
from http import HTTPStatus

from sanic import response, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, api_param_limiter
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.schema import JSONErrorResponse
from . import lib, schema

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


@bp.get('/<archive_id:int>')
@openapi.description('Get an archive')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_archive(_: Request, archive_id: int):
    archive = lib.get_archive(archive_id=archive_id)
    alternatives = archive.alternatives
    return json_response({'archive': archive, 'alternatives': alternatives})


@bp.delete('/<archive_id:int>')
@openapi.description('Delete an individual archive')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@wrol_mode_check
async def delete_archive(_: Request, archive_id: int):
    lib.delete_archive(archive_id)
    return response.empty()


@bp.post('/refresh')
@wrol_mode_check
async def refresh_archives(_: Request):
    asyncio.ensure_future(lib.refresh_archives())
    return response.empty()


@bp.get('/domains')
async def fetch_domains(_: Request):
    domains = lib.get_domains()
    return json_response({'domains': domains, 'totals': {'domains': len(domains)}})


archive_limit_limiter = api_param_limiter(100)


@bp.post('/search')
@openapi.definition(
    summary='Search archive contents and titles',
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

    archives, total = lib.search(search_str, domain, limit, offset)
    ret = dict(archives=archives, totals=dict(archives=total))
    return json_response(ret)
