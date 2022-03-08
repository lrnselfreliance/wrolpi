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
    summary='Import PBF map files',
    body=schema.ImportPost,
)
@validate(schema.ImportPost)
@wrol_mode_check
async def import_pbfs(request: Request, body: schema.ImportPost):
    if lib.IMPORT_EVENT.is_set():
        return response.json({'error': 'Map import already running'}, HTTPStatus.CONFLICT)

    pbfs = [i for i in body.pbfs if i]
    if not pbfs:
        raise ValidationError('No PBF files were provided')

    if PYTEST:
        await lib.import_pbfs(pbfs)
    else:
        asyncio.create_task(lib.import_pbfs(pbfs))
    return response.empty()


@bp.get('/pbf')
@openapi.description('Find any PBF map files, get their import status')
def pbf(request: Request):
    pbfs = lib.get_pbf_import_status()
    pbfs = sorted(pbfs, key=lambda i: str(i.path))
    importing = lib.IMPORTING.get('pbf')
    if importing:
        importing = Path(importing).relative_to(get_media_directory())
    body = dict(
        pbfs=pbfs,
        importing=importing,
        import_running=lib.IMPORT_EVENT.is_set(),
        dockerized=DOCKERIZED,
    )
    return json_response(body, HTTPStatus.OK)
