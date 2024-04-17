from http import HTTPStatus

from sanic import response, Request, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import logger, wrol_mode_check, api_param_limiter
from wrolpi.errors import ValidationError
from wrolpi.api_utils import json_response
from wrolpi.schema import JSONErrorResponse
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
@openapi.description('Delete an individual archive')
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
