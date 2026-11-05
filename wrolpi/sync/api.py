import asyncio
import re
from http import HTTPStatus

from sanic import Request, Blueprint, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi import flags
from wrolpi.api_utils import api_app, json_response, perpetual_signal
from wrolpi.common import logger, get_wrolpi_config, is_secondary, wrol_mode_check, wrol_mode_enabled
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidConfig, SecondaryRole, SyncInProgress, WROLModeEnabled
from wrolpi.sync import lib, schema
from wrolpi.sync.status import get_sync_status

sync_bp = Blueprint('Sync', '/api/sync')

logger = logger.getChild(__name__)

# Requests a secondary answers while it syncs: enough for the UI to show the sync's progress, and to cancel it.
SYNC_ALLOWED_REQUESTS = frozenset({
    ('GET', '/api/echo'),
    ('GET', '/api/events/feed'),
    ('GET', '/api/settings'),
    ('GET', '/api/status'),
    ('GET', '/api/sync/info'),
    ('GET', '/api/sync/status'),
    ('POST', '/api/sync/cancel'),
})


@api_app.middleware('request')
async def check_sync_api_lock(request: Request):
    """A secondary refuses requests while it replaces its library with its primary's (see wrolpi.sync)."""
    # The Event costs nothing to check; the Flag confirms it (the Event survives a perpetual process that died).
    if not api_app.shared_ctx.sync_api_locked.is_set() or not flags.sync_running.is_set():
        return
    if request.method == 'OPTIONS' or (request.method, request.path.rstrip('/')) in SYNC_ALLOWED_REQUESTS:
        return
    raise SyncInProgress()


@perpetual_signal(sleep=5)
async def perpetual_sync_worker():
    await lib.sync_tick()


@sync_bp.get('/info')
@openapi.definition(summary='This WROLPi, as a primary that secondaries sync from')
async def get_info(_: Request):
    def info():
        with get_db_session() as session:
            return lib.get_sync_info(session)

    return json_response(await asyncio.to_thread(info))


@sync_bp.get('/manifest')
@openapi.definition(summary="One page of this WROLPi's files, for a secondary to compare with its own")
@validate(query=schema.ManifestRequest)
async def get_manifest(_: Request, query: schema.ManifestRequest):
    def page():
        with get_db_session() as session:
            return lib.build_manifest_page(session, query.after_id, query.limit)

    return json_response(await asyncio.to_thread(page))


@sync_bp.get('/status')
@openapi.definition(summary="The progress of this secondary's sync")
async def get_status(_: Request):
    return json_response(dict(sync=get_sync_status(), sync_running=bool(flags.sync_running.is_set())))


@sync_bp.post('/run')
@openapi.definition(summary='Sync from the primary now', body=schema.SyncRunRequest, validate=True)
@wrol_mode_check
async def post_run(_: Request, body: schema.SyncRunRequest):
    if not is_secondary():
        raise SecondaryRole('Only a secondary WROLPi syncs from a primary')
    if flags.sync_running.is_set():
        raise SyncInProgress()
    if not get_wrolpi_config().sync_primary_url:
        raise InvalidConfig('No primary is configured')
    lib.request_sync(force=body.force)
    return response.empty(HTTPStatus.ACCEPTED)


@sync_bp.post('/cancel')
@openapi.definition(summary='Stop the running sync')
async def post_cancel(_: Request):
    lib.request_sync_cancel()
    return response.empty(HTTPStatus.ACCEPTED)


@sync_bp.get('/test')
@openapi.definition(summary='Check that the configured primary answers')
async def get_test(_: Request):
    url = get_wrolpi_config().sync_primary_url
    if not url:
        raise InvalidConfig('No primary is configured')
    try:
        async with lib.PrimaryClient(url) as client:
            info = await asyncio.wait_for(client.get_info(), timeout=15)
    except Exception as e:
        logger.warning(f'Primary {url} did not answer', exc_info=e)
        return json_response(dict(ok=False, error=str(e) or type(e).__name__))
    ok = info.get('role') == 'primary'
    return json_response(dict(ok=ok, info=info, error=None if ok else f'{url} is not a primary WROLPi'))


@sync_bp.put('/settings')
@openapi.definition(summary="Set this WROLPi's role and its primary", body=schema.SyncSettingsRequest, validate=True)
async def put_settings(_: Request, body: schema.SyncSettingsRequest):
    if wrol_mode_enabled():
        raise WROLModeEnabled()
    changes = dict()
    if body.role is not None:
        changes['role'] = body.role
    if body.sync_primary_url is not None:
        try:
            changes['sync_primary_url'] = lib.normalize_primary_url(body.sync_primary_url) \
                if body.sync_primary_url else None
        except ValueError as e:
            raise InvalidConfig(str(e))
    for key in ('sync_window_start', 'sync_window_end'):
        value = getattr(body, key)
        if value is None:
            continue
        if value and not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', value):
            raise InvalidConfig(f'{key} must be in HH:MM format')
        changes[key] = value or None
    if not changes:
        raise InvalidConfig('No settings to change')

    get_wrolpi_config().update(changes)
    if changes.get('role') == 'secondary':
        # A secondary's library comes from its primary.
        from wrolpi.downloader import download_manager
        download_manager.disable()
    return response.empty()
