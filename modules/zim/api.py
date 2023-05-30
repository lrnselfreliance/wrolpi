import urllib.parse
from http import HTTPStatus

from sanic import Request, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi import lang
from wrolpi.common import logger
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager
from wrolpi.events import Events
from wrolpi.root_api import get_blueprint, json_response
from . import lib, schema

bp = get_blueprint('Zim', '/api/zim')

logger = logger.getChild(__name__)


@bp.get('/')
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


@bp.delete('/<zim_ids:[0-9,]+>')
@openapi.definition(
    summary='Delete all Zim files',
)
async def delete_zims(_: Request, zim_ids: str):
    zim_ids = [int(i) for i in zim_ids.split(',')]
    lib.delete_zims(zim_ids)
    return response.empty()


@bp.post('/search/<zim_id:[0-9]+>')
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


@bp.get('/<zim_id:[0-9]+>/entry/<zim_path:[ -~/]*>')
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


@bp.post('/tag')
@openapi.definition(
    summary='Tag a Zim entry',
    body=schema.TagZimEntry,
)
@validate(schema.TagZimEntry)
async def post_zim_tag(_: Request, body: schema.TagZimEntry):
    await lib.add_tag(body.tag_name, body.zim_id, body.zim_entry)
    return response.empty(HTTPStatus.CREATED)


@bp.post('/untag')
@openapi.definition(
    summary='Untag a Zim entry',
    body=schema.TagZimEntry,
)
@validate(schema.TagZimEntry)
async def post_zim_untag(_: Request, body: schema.TagZimEntry):
    await lib.untag(body.tag_name, body.zim_id, body.zim_entry)
    return response.empty(HTTPStatus.NO_CONTENT)


@bp.get('/subscribe')
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


@bp.post('/subscribe')
@openapi.definition(
    summary='Subscribe to a particular Kiwix Zim',
    body=schema.TagZimSubscribe,
)
@validate(schema.TagZimSubscribe)
async def post_zim_subscribe(_: Request, body: schema.TagZimSubscribe):
    await lib.subscribe(body.name, body.language)
    if download_manager.disabled.is_set() or download_manager.stopped.is_set():
        # Downloads are disabled, warn the user.
        Events.send_downloads_disabled('Download created. But, downloads are disabled.')
    return response.empty(HTTPStatus.CREATED)


@bp.delete('/subscribe/<subscription_id:[0-9]+>')
@openapi.definition(
    summary='Unsubscribe to a particular Kiwix Zim',
)
async def delete_zim_subscription(_: Request, subscription_id: int):
    await lib.unsubscribe(subscription_id)
    return response.empty(HTTPStatus.NO_CONTENT)


@bp.get('/outdated')
@openapi.definition(
    summary='Returns the outdated and current Zim files',
    response=schema.OutdatedZims,
)
async def get_outdated_zims(_: Request):
    outdated, current = lib.find_outdated_zim_files()
    d = dict(outdated=outdated, current=current)
    return json_response(d)


@bp.delete('/outdated')
@openapi.definition(
    summary='Remove all outdated Zims, if any.'
)
async def delete_outdated_zims(_: Request):
    await lib.remove_outdated_zim_files()
    lib.flag_outdated_zim_files()
    return response.empty(HTTPStatus.NO_CONTENT)
