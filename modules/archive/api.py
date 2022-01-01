import asyncio
from http import HTTPStatus

from requests import Request
from sanic import response

from wrolpi.common import logger, wrol_mode_check
from wrolpi.errors import ValidationError
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.schema import validate_doc, JSONErrorResponse
from . import lib
from .schema import RetrieveURLsRequest, RetrieveURLsResponse, PostArchiveRequest, ArchiveSearchRequest, \
    ArchiveSearchResponse

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


@bp.post('/')
@validate_doc(
    'Archive a website',
    PostArchiveRequest,
)
@wrol_mode_check
async def post_archive(_: Request, data: dict):
    # Remove whitespace from URL.
    url = data['url'].strip()
    lib.new_archive(url)
    return response.empty()


@bp.delete('/<archive_id:int>')
@validate_doc(
    'Delete a website record',
    responses=[
        (HTTPStatus.NOT_FOUND, JSONErrorResponse),
    ]
)
@wrol_mode_check
async def delete_archive(_: Request, archive_id: int):
    lib.delete_archive(archive_id)
    return response.empty()


@bp.post('/urls')
@validate_doc(
    'Get a list of URLs',
    RetrieveURLsRequest,
    RetrieveURLsResponse,
)
async def get_urls(_: Request, data: dict):
    try:
        limit = abs(int(data.get('limit', 20)))
        offset = abs(int(data.get('offset', 0)))
        domain = data.get('domain')
    except Exception as e:
        logger.error(f'Bad request', exc_info=e)
        return response.json(dict(error='bad request'), HTTPStatus.BAD_REQUEST)

    urls = lib.get_urls(limit, offset, domain)
    count = lib.get_url_count(domain)
    ret = dict(urls=urls, totals=dict(urls=count))
    return json_response(ret)


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
