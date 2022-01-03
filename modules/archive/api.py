import asyncio
from http import HTTPStatus

from requests import Request
from sanic import response

from wrolpi.common import logger, wrol_mode_check
from wrolpi.errors import ValidationError
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from . import lib
from .schema import ArchiveSearchRequest, ArchiveSearchResponse

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


@bp.delete('/<archive_id:int>')
@validate_doc(
    'Delete an individual archive',
    responses=[
        (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ]
)
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


@bp.post('/search')
@validate_doc(
    'Search archive contents and titles',
    consumes=ArchiveSearchRequest,
    produces=ArchiveSearchResponse,
    optional_body=True,
)
async def search_archives(_: Request, data: dict):
    try:
        search_str = data.get('search_str')
        domain = data.get('domain')
        limit = int(data.get('limit', 20))
        offset = int(data.get('offset', 0))
    except Exception as e:
        raise ValidationError('Unable to validate search queries') from e

    archives, total = lib.search(search_str, domain, limit, offset)
    ret = dict(archives=archives, totals=dict(archives=total))
    return json_response(ret)
