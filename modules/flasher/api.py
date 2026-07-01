import asyncio
from http import HTTPStatus
from urllib.parse import unquote

from sanic import Blueprint, Request, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.flasher import lib, schema
from modules.flasher.config import get_flasher_config
from wrolpi.api_utils import json_response

flasher_bp = Blueprint('Flasher', '/api/flasher')


@flasher_bp.post('/search')
@openapi.definition(
    summary='Search .bin firmware and filter to ESP images (optionally for a specific chip)',
    body=schema.FlasherSearchRequest,
)
@validate(schema.FlasherSearchRequest)
async def post_flasher_search(_: Request, body: schema.FlasherSearchRequest):
    # Reading many firmware headers touches the disk; run off the event loop.
    file_groups, total = await asyncio.to_thread(
        lib.search_esp_firmware, body.chip, body.path, body.limit)
    return json_response(dict(file_groups=file_groups, totals=dict(file_groups=total)), HTTPStatus.OK)


@flasher_bp.get('/configs')
@openapi.definition(summary='List saved firmware flashing configurations')
async def get_flasher_configs(_: Request):
    return json_response(dict(configurations=get_flasher_config().configurations), HTTPStatus.OK)


@flasher_bp.post('/configs')
@openapi.definition(
    summary='Save (add or replace by name) a firmware flashing configuration',
    body=schema.FlasherSaveConfigRequest,
)
@validate(schema.FlasherSaveConfigRequest)
async def save_flasher_config(_: Request, body: schema.FlasherSaveConfigRequest):
    try:
        configuration = get_flasher_config().save_configuration(body.name, body.files, body.erase_all)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)
    return json_response(dict(configuration=configuration), HTTPStatus.CREATED)


@flasher_bp.delete('/configs/<name:str>')
@openapi.definition(summary='Delete a saved firmware flashing configuration by name')
async def delete_flasher_config(_: Request, name: str):
    name = unquote(name)
    if get_flasher_config().delete_configuration(name):
        return response.empty()
    return response.json({'error': f'No saved configuration named {name!r}'}, HTTPStatus.NOT_FOUND)
