import asyncio
from http import HTTPStatus

from sanic import Blueprint, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.flasher import lib, schema
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
