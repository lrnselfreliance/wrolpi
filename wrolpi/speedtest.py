"""Speed test endpoints: ping, a bounded download stream, a bounded upload sink, and context.

Nothing is stored.  Several clients may test at once; the server only counts tests in flight.
"""
import os
import time
from http import HTTPStatus
from typing import Iterator, Optional

from sanic import Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response, api_app
from wrolpi.common import logger
from wrolpi.errors import ValidationError, APIError

logger = logger.getChild(__name__)

speedtest_bp = Blueprint('SpeedTest', url_prefix='/api/speedtest')

# Bounds on how long a download stream may hold a worker.
MIN_DOWNLOAD_SECONDS = 0.1
DEFAULT_DOWNLOAD_SECONDS = 10.0
MAX_DOWNLOAD_SECONDS = 15.0
# Bytes sent per `await response.send()`.  Large enough that Python overhead does not cap a fast
# LAN, small enough that the loop yields often.
CHUNK_SIZE = 256 * 1024
# The browser uploads in sequential POSTs of a few MiB.  Both caps exist so a request cannot hold a
# worker: size alone does not, a slow or paused body could trickle in for minutes.
MAX_UPLOAD_CHUNK = 8 * 1024 * 1024
MAX_UPLOAD_SECONDS = 15.0

# One random buffer built at import; chunks are slices of it so no bytes are generated per
# request.  Random so no proxy or compression can flatter the result.  A whole multiple of
# CHUNK_SIZE so every slice is a full chunk.
_RANDOM = os.urandom(CHUNK_SIZE * 16)

NO_STORE_HEADERS = {
    'Cache-Control': 'no-store',
    # Ask proxies not to buffer the stream.
    'X-Accel-Buffering': 'no',
}


class UploadTooLarge(APIError):
    code = 'UPLOAD_TOO_LARGE'
    summary = f'Speed test upload requests are limited to {MAX_UPLOAD_CHUNK} bytes'
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class UploadTooSlow(APIError):
    code = 'UPLOAD_TOO_SLOW'
    summary = f'Speed test upload requests must finish within {MAX_UPLOAD_SECONDS} seconds'
    status_code = HTTPStatus.REQUEST_TIMEOUT


def clamp_seconds(value: Optional[str]) -> float:
    """Parse the requested download duration and keep it within the server's bounds."""
    if value is None or value == '':
        return DEFAULT_DOWNLOAD_SECONDS
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f'seconds must be a number, got {value!r}')
    if seconds != seconds:  # NaN
        raise ValidationError('seconds must be a number, got NaN')
    if seconds < 0:
        raise ValidationError('seconds must not be negative')
    return max(MIN_DOWNLOAD_SECONDS, min(seconds, MAX_DOWNLOAD_SECONDS))


def iter_chunks() -> Iterator[bytes]:
    """Yield full CHUNK_SIZE slices of the random buffer forever, wrapping around."""
    offset = 0
    while True:
        yield _RANDOM[offset:offset + CHUNK_SIZE]
        offset = (offset + CHUNK_SIZE) % len(_RANDOM)


def _counter():
    """The cross-worker count of speed tests in flight (created pre-fork in wrolpi.contexts)."""
    return api_app.shared_ctx.speedtest_active


def _adjust_active(delta: int):
    counter = _counter()
    with counter.get_lock():
        counter.value = max(0, counter.value + delta)


def get_client_ip(request: Request) -> str:
    """The address Caddy forwarded, falling back to the socket peer for direct requests."""
    return request.remote_addr or request.ip


@speedtest_bp.get('/ping')
@openapi.definition(
    summary='Tiny response the browser times to measure round trip latency.',
)
async def ping(_: Request):
    return json_response(dict(now=time.monotonic() * 1000), headers=NO_STORE_HEADERS)


@speedtest_bp.get('/info')
@openapi.definition(
    summary='Context for a speed test: the client address the server saw and how many tests are running.',
)
async def info(request: Request):
    return json_response(dict(
        client_ip=get_client_ip(request),
        active_tests=_counter().value,
        max_download_seconds=MAX_DOWNLOAD_SECONDS,
        max_upload_chunk=MAX_UPLOAD_CHUNK,
        max_upload_seconds=MAX_UPLOAD_SECONDS,
    ), headers=NO_STORE_HEADERS)


@speedtest_bp.get('/download')
@openapi.definition(
    summary='Stream random bytes for `seconds` (clamped) so the browser can measure download throughput.',
)
async def download(request: Request):
    seconds = clamp_seconds(request.args.get('seconds'))
    response = await request.respond(content_type='application/octet-stream', headers=NO_STORE_HEADERS)
    _adjust_active(1)
    try:
        deadline = time.monotonic() + seconds
        for chunk in iter_chunks():
            if time.monotonic() >= deadline:
                break
            await response.send(chunk)
        await response.eof()
    except Exception as e:
        # The browser aborts the fetch when its own timer ends; that is normal.
        logger.debug(f'speed test download ended early: {e!r}')
    finally:
        _adjust_active(-1)


async def drain_upload(request: Request) -> int:
    """Read and discard the request body, enforcing both the size and the time cap."""
    deadline = time.monotonic() + MAX_UPLOAD_SECONDS
    total = 0
    while True:
        body = await request.stream.read()
        if body is None:
            return total
        total += len(body)
        if total > MAX_UPLOAD_CHUNK:
            raise UploadTooLarge()
        if time.monotonic() > deadline:
            raise UploadTooSlow()


@speedtest_bp.post('/upload', stream=True)
@openapi.definition(
    summary='Read and discard the request body, reporting how many bytes arrived and how long it took.',
)
async def upload(request: Request):
    declared = request.headers.get('content-length')
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_CHUNK:
        raise UploadTooLarge()

    _adjust_active(1)
    try:
        start = time.monotonic()
        total = await drain_upload(request)
        seconds = time.monotonic() - start
    finally:
        _adjust_active(-1)

    return json_response(dict(bytes=total, seconds=seconds), headers=NO_STORE_HEADERS)
