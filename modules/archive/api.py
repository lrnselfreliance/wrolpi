import asyncio
from http import HTTPStatus

from requests import Request
from sanic import response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, api_param_limiter
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.schema import JSONErrorResponse
from . import lib
from .schema import ArchiveSearchRequest, ArchiveSearchResponse

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


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
archive_offset_limiter = api_param_limiter(100, 0)


@bp.post('/search')
@openapi.definition(
    summary='Search archive contents and titles',
    body=ArchiveSearchRequest,
)
@openapi.response(HTTPStatus.OK, ArchiveSearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(ArchiveSearchRequest)
async def search_archives(_: Request, body: ArchiveSearchRequest):
    search_str = body.search_str
    domain = body.domain
    limit = archive_limit_limiter(body.limit)
    offset = archive_offset_limiter(body.offset)

    archives, total = lib.search(search_str, domain, limit, offset)
    ret = dict(archives=archives, totals=dict(archives=total))
    return json_response(ret)
