import asyncio
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from sanic import Blueprint, response

from lib.common import get_http_file_info, download_file, validate_doc
from lib.map.schema import PBFPostRequest, PBFPostResponse

NAME = 'map'

api_bp = Blueprint('api_map', url_prefix='/map')


@api_bp.route('/pbf', methods=['POST'])
@validate_doc(
    summary='Queue a PBF file for download and processing',
    consumes=PBFPostRequest,
    produces=PBFPostResponse,
)
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


@api_bp.websocket('/pbf_progress')
def pbf_progress(request, ws):
    pass
