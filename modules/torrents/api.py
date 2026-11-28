from sanic import Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from modules.torrents import lib
from wrolpi.api_utils import json_response

torrents_bp = Blueprint('Torrents', '/api/torrents')


@torrents_bp.get('/')
@openapi.description("Every torrent, qBittorrent's state, and the VPN's (torrents reach the Internet only through it)")
async def get_torrents(_: Request):
    return json_response(await lib.get_torrents_status())
