from http import HTTPStatus

from requests import Request
from sanic import response
from sanic_openapi import doc

from wrolpi.common import logger
from wrolpi.root_api import get_blueprint
from wrolpi.schema import validate_doc
from .lib import new_archive

NAME = 'archive'

bp = get_blueprint('Archive', '/api/archive')

logger = logger.getChild(__name__)


class PostArchiveRequest:
    url = doc.String(required=True)


@bp.post('/')
@validate_doc(
    'Archive a website',
    PostArchiveRequest,
)
async def post_archive(request: Request, data: dict):
    url = data['url']
    try:
        new_archive(url)
    except Exception:
        logger.error(f'Failed to create new archive', exc_info=True)
        return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)
    return response.empty()
