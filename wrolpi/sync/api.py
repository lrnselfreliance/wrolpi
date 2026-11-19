import asyncio
import os
import re
from http import HTTPStatus

from sanic import Request, Blueprint, response
from sanic_ext.extensions.openapi import openapi

from wrolpi import flags
from wrolpi.api_utils import json_response, perpetual_signal
from wrolpi.common import logger, is_secondary, wrol_mode_check, wrol_mode_enabled, \
    CONTROLLER_URL, aiohttp_post
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidConfig, SecondaryRole, WROLModeEnabled
from wrolpi.sync import backup, lib, schema, snapshot
from wrolpi.sync.config import get_sync_config
from wrolpi.sync.status import get_backup_status, get_snapshot_status
from wrolpi.vars import DOCKERIZED

sync_bp = Blueprint('Sync', '/api/sync')

logger = logger.getChild(__name__)

@perpetual_signal(sleep=5)
async def perpetual_sync_worker():
    # A secondary's sync is the Controller's (controller/lib/sync.py), which stops this API while it runs.
    await backup.backup_tick()
    await snapshot.snapshot_tick()


@sync_bp.get('/info')
@openapi.definition(summary='This WROLPi, as a primary that secondaries sync from')
async def get_info(_: Request):
    def info():
        with get_db_session() as session:
            return lib.get_sync_info(session)

    return json_response(await asyncio.to_thread(info))


@sync_bp.get('/status')
@openapi.definition(summary="The progress of this secondary's sync")
async def get_status(_: Request):
    # A secondary's sync is the Controller's: /controller/api/sync/status.
    return json_response(dict(backup=get_backup_status(), backup_running=bool(flags.backup_running.is_set()),
                              snapshot=get_snapshot_status()))


@sync_bp.post('/snapshot')
@openapi.definition(summary="Make a snapshot of this WROLPi's database for a secondary to copy")
async def post_snapshot(_: Request):
    if reason := snapshot.snapshot_skip_reason():
        raise InvalidConfig(reason)
    # Made by the perpetual process; `/api/sync/status` says when it is done.
    snapshot.request_snapshot()
    return response.empty(HTTPStatus.ACCEPTED)


def controller_url() -> str:
    return 'http://controller' if DOCKERIZED else CONTROLLER_URL


async def _ask_controller(path: str):
    """A secondary's sync runs in the Controller, because this API is stopped while the library is replaced."""
    try:
        async with aiohttp_post(f'{controller_url()}/api/sync/{path}', json_={}, timeout=15) as controller_response:
            if controller_response.status < 300:
                return response.empty(HTTPStatus.ACCEPTED)
            body = await controller_response.json(content_type=None)
    except Exception as e:
        logger.error(f'Could not reach the Controller to {path} the sync', exc_info=e)
        raise InvalidConfig('The Controller did not answer')
    raise InvalidConfig((body or {}).get('detail') or f'The Controller answered {controller_response.status}')


@sync_bp.post('/run')
@openapi.definition(summary='Sync from the primary now (the Controller runs it)')
@wrol_mode_check
async def post_run(_: Request):
    if not is_secondary():
        raise SecondaryRole('Only a secondary WROLPi syncs from a primary')
    if not get_sync_config().primary_url:
        raise InvalidConfig('No primary is configured')
    return await _ask_controller('run')


@sync_bp.post('/cancel')
@openapi.definition(summary='Stop the running sync (the Controller runs it)')
async def post_cancel(_: Request):
    return await _ask_controller('cancel')


@sync_bp.get('/test')
@openapi.definition(summary='Check that the configured primary answers')
async def get_test(_: Request):
    url = get_sync_config().primary_url
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


@sync_bp.post('/directories')
@openapi.definition(summary='List the folders inside a folder, to choose which are not copied',
                    body=schema.SyncDirectoriesRequest, validate=True)
async def post_directories(_: Request, body: schema.SyncDirectoriesRequest):
    if body.source == 'local':
        return json_response(dict(directories=lib.list_local_directories(body.path)))
    if not is_secondary() or not get_sync_config().primary_url:
        raise InvalidConfig('Only a secondary with a primary can list its primary\'s folders')
    try:
        directories = await asyncio.wait_for(lib.list_primary_directories(body.path), timeout=15)
    except InvalidConfig:
        raise
    except Exception as e:
        logger.warning(f'Could not list the primary\'s folder {body.path!r}', exc_info=e)
        return json_response(dict(error=str(e) or type(e).__name__), status=HTTPStatus.BAD_GATEWAY)
    return json_response(dict(directories=directories))


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
            changes['primary_url'] = lib.normalize_primary_url(body.sync_primary_url) \
                if body.sync_primary_url else None
        except ValueError as e:
            raise InvalidConfig(str(e))
    for request_key, config_key in (('sync_window_start', 'window_start'), ('sync_window_end', 'window_end'),
                                    ('backup_window_start', 'backup_window_start'),
                                    ('backup_window_end', 'backup_window_end')):
        value = getattr(body, request_key)
        if value is None:
            continue
        if value and not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', value):
            raise InvalidConfig(f'{request_key} must be in HH:MM format')
        changes[config_key] = value or None
    if body.sync_delete_after_days is not None:
        days = int(body.sync_delete_after_days)
        changes['delete_after_days'] = None if days < 0 else days
    for key in ('sync_excluded_directories', 'backup_excluded_directories'):
        if (value := getattr(body, key)) is not None:
            changes[key] = lib.normalize_excluded_directories(value)
    if body.backup_directory is not None or body.backup_device_uuid is not None:
        changes.update(_backup_drive_changes(body.backup_directory, body.backup_device_uuid))
    if not changes:
        raise InvalidConfig('No settings to change')

    get_sync_config().update(changes)
    if changes.get('role') == 'secondary':
        # A secondary's library comes from its primary.
        from wrolpi.downloader import download_manager
        download_manager.disable()
    return response.empty()


def _backup_drive_changes(directory: str, uuid: str) -> dict:
    if not directory and not uuid:
        # No backup drive.
        return dict(backup_directory=None, backup_device_uuid=None)
    if DOCKERIZED:
        raise InvalidConfig('Backup drives are not supported in Docker')
    if reason := backup.check_backup_target(directory, uuid):
        raise InvalidConfig(reason)
    return dict(backup_directory=os.path.normpath(directory), backup_device_uuid=uuid)


@sync_bp.post('/backup/run')
@openapi.definition(summary='Copy the media directory to the backup drive now')
@wrol_mode_check
async def post_backup_run(_: Request):
    if not get_sync_config().backup_directory:
        raise InvalidConfig('No backup drive is configured')
    if flags.backup_running.is_set():
        raise InvalidConfig('A backup is already running')
    backup.request_backup()
    return response.empty(HTTPStatus.ACCEPTED)


@sync_bp.post('/backup/cancel')
@openapi.definition(summary='Stop the running backup')
async def post_backup_cancel(_: Request):
    backup.request_backup_cancel()
    return response.empty(HTTPStatus.ACCEPTED)
