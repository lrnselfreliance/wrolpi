import asyncio
from http import HTTPStatus
from pathlib import Path

from sanic import Request, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.map import lib, schema
from wrolpi.common import wrol_mode_check, get_media_directory
from wrolpi.errors import ValidationError
from wrolpi.root_api import get_blueprint, json_response
from wrolpi.vars import PYTEST, DOCKERIZED

bp = get_blueprint('Map', '/api/map')


@bp.post('/import')
@openapi.definition(
    summary='Import PBF/dump map files',
    body=schema.ImportPost,
)
@validate(schema.ImportPost)
@wrol_mode_check
async def import_pbfs(_: Request, body: schema.ImportPost):
    if lib.IMPORT_EVENT.is_set():
        return response.json({'error': 'Map import already running'}, HTTPStatus.CONFLICT)

    paths = [i for i in body.files if i]
    if not paths:
        raise ValidationError('No PBF or dump files were provided')

    coro = lib.import_files(paths)
    if PYTEST:
        await coro
    else:
        asyncio.create_task(coro)
    return response.empty()


@bp.get('/files')
@openapi.description('Find any map files, get their import status')
def pbf(_: Request):
    paths = lib.get_import_status()
    paths = sorted(paths, key=lambda i: str(i.path))
    importing = lib.IMPORTING.get('path')
    if importing:
        importing = Path(importing).relative_to(get_media_directory())
    body = dict(
        files=paths,
        importing=importing,
        import_running=lib.IMPORT_EVENT.is_set(),
        dockerized=DOCKERIZED,
    )
    return json_response(body, HTTPStatus.OK)
