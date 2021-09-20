from requests import Request
from sanic import Blueprint
from sanic_openapi import doc

from wrolpi.schema import validate_doc
from .lib import new_archive

NAME = 'archive'

api_bp = Blueprint('Archive', url_prefix='/archive')


class PostArchiveRequest:
    url = doc.String(required=True)


@api_bp.post('/')
@validate_doc(
    'Archive a website',
    PostArchiveRequest,
)
def post_archive(request: Request, data: dict):
    url = data['url']
    new_archive(url)
