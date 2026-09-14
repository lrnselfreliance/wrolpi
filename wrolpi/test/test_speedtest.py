import time
from http import HTTPStatus

import pytest

from wrolpi import speedtest
from wrolpi.api_utils import api_app


def _active() -> int:
    return api_app.shared_ctx.speedtest_active.value


def test_clamp_seconds():
    assert speedtest.clamp_seconds(None) == speedtest.DEFAULT_DOWNLOAD_SECONDS
    assert speedtest.clamp_seconds('') == speedtest.DEFAULT_DOWNLOAD_SECONDS
    assert speedtest.clamp_seconds('2.5') == 2.5
    # Too long is clamped to the ceiling, too short to the floor.
    assert speedtest.clamp_seconds('999') == speedtest.MAX_DOWNLOAD_SECONDS
    assert speedtest.clamp_seconds('0') == speedtest.MIN_DOWNLOAD_SECONDS
    with pytest.raises(speedtest.ValidationError):
        speedtest.clamp_seconds('abc')
    with pytest.raises(speedtest.ValidationError):
        speedtest.clamp_seconds('-1')


def test_chunks_never_empty():
    """The chunk generator wraps around the random buffer without ever yielding a short chunk."""
    chunks = speedtest.iter_chunks()
    seen = [next(chunks) for _ in range(len(speedtest._RANDOM) // speedtest.CHUNK_SIZE + 3)]
    assert all(len(i) == speedtest.CHUNK_SIZE for i in seen)
    # Wrapped around to the start.
    assert seen[0] == seen[len(speedtest._RANDOM) // speedtest.CHUNK_SIZE]


@pytest.mark.asyncio
async def test_ping(async_client):
    request, response = await async_client.get('/api/speedtest/ping')
    assert response.status_code == HTTPStatus.OK
    assert isinstance(response.json['now'], (int, float))
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.asyncio
async def test_download_streams_for_requested_seconds(async_client):
    assert _active() == 0
    start = time.monotonic()
    request, response = await async_client.get('/api/speedtest/download?seconds=0.3')
    elapsed = time.monotonic() - start
    assert response.status_code == HTTPStatus.OK
    assert response.headers['Content-Type'] == 'application/octet-stream'
    assert response.headers['Cache-Control'] == 'no-store'
    assert len(response.body) >= speedtest.CHUNK_SIZE
    assert len(response.body) % speedtest.CHUNK_SIZE == 0
    # Ran for about the requested duration.  Loose upper bound for slow CI.
    assert 0.25 <= elapsed < 5
    # Counter is released when the stream finishes.
    assert _active() == 0


@pytest.mark.asyncio
async def test_download_clamps_seconds(async_client):
    """A client cannot hold a worker longer than MAX_DOWNLOAD_SECONDS."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(speedtest, 'MAX_DOWNLOAD_SECONDS', 0.2)
        start = time.monotonic()
        request, response = await async_client.get('/api/speedtest/download?seconds=999')
        elapsed = time.monotonic() - start
    assert response.status_code == HTTPStatus.OK
    assert elapsed < 3
    assert _active() == 0


@pytest.mark.asyncio
async def test_download_invalid_seconds(async_client):
    request, response = await async_client.get('/api/speedtest/download?seconds=abc')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    request, response = await async_client.get('/api/speedtest/download?seconds=-1')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert _active() == 0


@pytest.mark.asyncio
async def test_download_client_disconnect_releases_counter(async_client):
    """The active-test counter is released even when the stream dies part way through."""

    def broken_chunks():
        yield speedtest._RANDOM[:speedtest.CHUNK_SIZE]
        raise ConnectionResetError('client went away')

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(speedtest, 'iter_chunks', broken_chunks)
        try:
            await async_client.get('/api/speedtest/download?seconds=0.5')
        except Exception:
            # The test client may surface the broken stream; the counter is what matters.
            pass
    assert _active() == 0


@pytest.mark.asyncio
async def test_upload_counts_and_discards(async_client):
    body = b'x' * (1024 * 1024)
    request, response = await async_client.post('/api/speedtest/upload', content=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['bytes'] == len(body)
    assert response.json['seconds'] >= 0
    assert _active() == 0


@pytest.mark.asyncio
async def test_upload_too_large(async_client):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(speedtest, 'MAX_UPLOAD_CHUNK', 1024)
        body = b'x' * 2048
        request, response = await async_client.post('/api/speedtest/upload', content=body)
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert _active() == 0


@pytest.mark.asyncio
async def test_info(async_client):
    request, response = await async_client.get('/api/speedtest/info')
    assert response.status_code == HTTPStatus.OK
    assert response.json['client_ip']
    assert response.json['active_tests'] == 0
    assert response.json['max_download_seconds'] == speedtest.MAX_DOWNLOAD_SECONDS
    assert response.json['max_upload_chunk'] == speedtest.MAX_UPLOAD_CHUNK

    # Caddy forwards the real client address; Sanic is configured to trust one proxy hop.
    request, response = await async_client.get('/api/speedtest/info',
                                               headers={'X-Forwarded-For': '10.42.0.7'})
    assert response.json['client_ip'] == '10.42.0.7'


def test_speedtest_counter_in_shared_context():
    """The counter must be created pre-fork so all Sanic workers share it."""
    from sanic import Sanic
    from wrolpi.contexts import attach_shared_contexts, reset_shared_contexts

    test_app = Sanic(f'test_context_{id(test_speedtest_counter_in_shared_context)}')
    attach_shared_contexts(test_app)
    assert test_app.shared_ctx.speedtest_active.value == 0
    test_app.shared_ctx.speedtest_active.value = 3
    reset_shared_contexts(test_app)
    assert test_app.shared_ctx.speedtest_active.value == 0
