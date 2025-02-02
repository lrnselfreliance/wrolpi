import urllib.parse
from http import HTTPStatus

from sanic import Request, response, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi import lang
from wrolpi.api_utils import json_response
from wrolpi.common import logger
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager
from wrolpi.events import Events
from . import lib, schema
from .models import Zims

zim_bp = Blueprint('Zim', '/api/zim')

logger = logger.getChild(__name__)


@zim_bp.get('/')
@openapi.definition(
    summary='List all known Zim files',
    response=schema.GetZimsResponse,
)
async def get_zims(_: Request):
    with get_db_session() as session:
        zims = lib.get_zims(session=session)
        resp = {
            'zims': [i.__json__() for i in zims],
        }
    return json_response(resp)


@zim_bp.delete('/<zim_ids:[0-9,]+>')
@openapi.definition(
    summary='Delete all Zim files',
)
async def delete_zims(_: Request, zim_ids: str):
    zim_ids = [int(i) for i in zim_ids.split(',')]
    lib.delete_zims(zim_ids)
    return response.empty()


@zim_bp.post('/<zim_id:[0-9]+>/auto_search')
@openapi.definition(
    summary='Change if a Zim file will be searched by default.',
    body=schema.ZimAutoSearchRequest,
)
@validate(schema.ZimAutoSearchRequest)
async def post_set_zim_auto_search(_: Request, zim_id: int, body: schema.ZimAutoSearchRequest):
    zim_id = int(zim_id)
    lib.set_zim_auto_search(zim_id, body.auto_search)
    return response.empty()


@zim_bp.post('/search/<zim_id:[0-9]+>')
@openapi.definition(
    summary='Search all entries of a Zim',
    body=schema.ZimSearchRequest,
    response=schema.ZimSearchResponse,
)
@validate(schema.ZimSearchRequest)
async def search_zim(_: Request, zim_id: int, body: schema.ZimSearchRequest):
    headlines = lib.headline_zim(body.search_str, zim_id, tag_names=body.tag_names, offset=body.offset,
                                 limit=body.limit)
    return json_response({'zim': headlines})


@zim_bp.get('/<zim_id:[0-9]+>/entry/<zim_path:[ -~/]*>')
@openapi.definition(
    summary='Read the entry at `zim_path` from the Zim file',
)
async def get_zim_entry(_: Request, zim_id: int, zim_path: str):
    zim_path = urllib.parse.unquote(zim_path)
    entry = lib.get_entry(zim_path, zim_id=zim_id)
    content = bytes(entry.get_item().content)
    try:
        resp = response.html(content.decode('UTF-8'))
        logger.debug(f'Returning ZIM HTML response {repr(str(zim_path))}')
    except UnicodeDecodeError:
        resp = response.raw(content)
        logger.debug(f'Returning ZIM raw response {repr(str(zim_path))}')

    return resp


@zim_bp.post('/tag')
@openapi.definition(
    summary='Tag a Zim entry',
    body=schema.TagZimEntry,
)
@validate(schema.TagZimEntry)
async def post_zim_tag(_: Request, body: schema.TagZimEntry):
    await lib.add_tag(body.tag_name, body.zim_id, body.zim_entry)
    return response.empty(HTTPStatus.CREATED)


@zim_bp.post('/untag')
@openapi.definition(
    summary='Untag a Zim entry',
    body=schema.TagZimEntry,
)
@validate(schema.TagZimEntry)
async def post_zim_untag(_: Request, body: schema.TagZimEntry):
    await lib.untag(body.tag_name, body.zim_id, body.zim_entry)
    return response.empty(HTTPStatus.NO_CONTENT)


@zim_bp.get('/subscribe')
@openapi.definition(
    summary='Retrieve Zim subscriptions',
    response=schema.ZimSubscriptions,
)
async def get_zim_subscriptions(_: Request):
    catalog = lib.get_kiwix_catalog()
    with get_db_session() as session:
        subscriptions = {i: j.__json__() for i, j in lib.get_kiwix_subscriptions(session).items()}
    resp = dict(
        catalog=catalog,
        iso_639_codes=lang.ISO_639_CODES,
        subscriptions=subscriptions,
    )
    return json_response(resp)


@zim_bp.post('/subscribe')
@openapi.definition(
    summary='Subscribe to a particular Kiwix Zim',
    body=schema.ZimSubscribeRequest,
)
@validate(schema.ZimSubscribeRequest)
async def post_zim_subscribe(_: Request, body: schema.ZimSubscribeRequest):
    await lib.subscribe(body.name, body.language)
    if download_manager.disabled or download_manager.stopped:
        # Downloads are disabled, warn the user.
        Events.send_downloads_disabled('Download created. But, downloads are disabled.')
    Events.send_created(f'Zim subscription created')
    return response.empty(HTTPStatus.CREATED)


@zim_bp.delete('/subscribe/<subscription_id:[0-9]+>')
@openapi.definition(
    summary='Unsubscribe to a particular Kiwix Zim',
)
async def delete_zim_subscription(_: Request, subscription_id: int):
    await lib.unsubscribe(subscription_id)
    Events.send_deleted(f'Zim subscription deleted')
    return response.empty(HTTPStatus.NO_CONTENT)


@zim_bp.get('/outdated')
@openapi.definition(
    summary='Returns the outdated and current Zim files',
    response=schema.OutdatedZims,
)
async def get_outdated_zims(_: Request):
    outdated, current = lib.find_outdated_zim_files()
    d = dict(outdated=outdated, current=current)
    return json_response(d)


@zim_bp.delete('/outdated')
@openapi.definition(
    summary='Remove all outdated Zims, if any.'
)
async def delete_outdated_zims(_: Request):
    deleted_count = await lib.remove_outdated_zim_files()
    if deleted_count:
        lib.flag_outdated_zim_files()
        Events.send_deleted(f'Deleted {deleted_count} outdated Zims')
    return response.empty(HTTPStatus.NO_CONTENT)


@zim_bp.post('/search_estimates')
@validate(json=schema.SearchEstimateRequest)
async def post_search_estimates(_: Request, body: schema.SearchEstimateRequest):
    """Get an estimated count of FileGroups/Zims which may or may not have been tagged."""

    if not body.search_str and not body.tag_names:
        return response.empty(HTTPStatus.BAD_REQUEST)

    if body.tag_names:
        # Get actual count of entries tagged with the tag names.
        zims_estimates = list()
        for zim, count in Zims.entries_with_tags(body.tag_names).items():
            d = dict(
                estimate=count,
                **zim.__json__(),
            )
            zims_estimates.append(d)
    else:
        # Get estimates using libzim.
        zims_estimates = list()
        for zim, estimate in Zims.estimate(body.search_str).items():
            d = dict(
                estimate=estimate,
                **zim.__json__(),
            )
            zims_estimates.append(d)

    ret = dict(
        zims_estimates=zims_estimates
    )
    return json_response(ret)
