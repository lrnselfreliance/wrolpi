from http import HTTPStatus

from requests import Request
from sanic import response

from wrolpi.common import logger
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.schema import validate_doc
from . import lib
from .schema import RetrieveUrlsRequest, RetrieveURLsResponse, PostArchiveRequest

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


@bp.post('/')
@validate_doc(
    'Archive a website',
    PostArchiveRequest,
)
async def post_archive(_: Request, data: dict):
    url = data['url']
    try:
        lib.new_archive(url)
    except Exception:
        logger.error(f'Failed to create new archive', exc_info=True)
        return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)
    return response.empty()


@bp.post('/search')
@validate_doc(
    'Get a list of URLs',
    RetrieveUrlsRequest,
    RetrieveURLsResponse,
)
async def search_archives(_: Request, data: dict):
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
