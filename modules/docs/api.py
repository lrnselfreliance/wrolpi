from http import HTTPStatus

from sanic import Request, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger, api_param_limiter
from wrolpi.schema import JSONErrorResponse
from . import schema
from .lib import get_statistics, _doc_response, _get_doc, _search_docs

NAME = 'docs'

docs_bp = Blueprint('Docs', '/api/docs')

logger = logger.getChild(__name__)


@docs_bp.get('/statistics')
@openapi.response(HTTPStatus.OK, schema.DocStatisticsResponse)
async def statistics(_: Request):
    ret = get_statistics()
    return json_response(ret, HTTPStatus.OK)


@docs_bp.get('/<file_group_id:int>')
@openapi.description('Get a doc by FileGroup ID')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_doc(request: Request, file_group_id: int):
    session = request.ctx.session
    doc = _get_doc(session, file_group_id)
    return json_response(_doc_response(doc))


doc_limit_limiter = api_param_limiter(100)


@docs_bp.post('/search')
@openapi.definition(
    summary='Search docs with filtering',
    body=schema.DocSearchRequest,
)
@openapi.response(HTTPStatus.OK, schema.DocSearchResponse)
@validate(schema.DocSearchRequest)
async def search_docs(_: Request, body: schema.DocSearchRequest):
    limit = doc_limit_limiter(body.limit)
    offset = body.offset or 0
    file_groups, total = _search_docs(
        search_str=body.search_str,
        author=body.author,
        subject=body.subject,
        language=body.language,
        mimetype=body.mimetype,
        limit=limit,
        offset=offset,
        order_by=body.order_by,
        tag_names=body.tag_names,
        deep=body.deep,
    )
    ret = dict(file_groups=file_groups, totals=dict(file_groups=total))
    return json_response(ret)
