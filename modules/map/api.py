import asyncio
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from sanic import Blueprint, response
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.map.schema import PBFPostRequest, PBFPostResponse
from wrolpi.common import create_websocket_feed

NAME = 'map'

api_bp = Blueprint('Map', url_prefix='/map')

download_queue, download_event = create_websocket_feed('pbf_progress', '/feeds/pbf_progress', api_bp)


@api_bp.route('/pbf', methods=['POST'])
@openapi.description('Queue a PBF file for download and processing')
@openapi.response(HTTPStatus.OK, PBFPostResponse)
@validate(PBFPostRequest)
def pbf_post(request, data: dict):
    pbf_url = data.get('pbf_url')
    parsed = urlparse(pbf_url)
    if not parsed.scheme or not parsed.netloc or not parsed.path:
        return response.json({'error': 'Invalid PBF url'}, HTTPStatus.BAD_REQUEST)

    # Get the size of the PBF file.  Also, check that it is accessible.
    try:
        size, filename = get_http_file_info(pbf_url)
    except LookupError:
        # Couldn't get the size of the file, probably doesn't exist
        return response.json({'error': 'Failed to get file size.  Does it exists?', 'url': pbf_url},
                             HTTPStatus.NOT_FOUND)

    destination = Path('/tmp') / filename
    coro = download_file(pbf_url, size, destination)
    asyncio.ensure_future(coro)
    return response.json({'success': 'File download started'})
