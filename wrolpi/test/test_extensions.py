"""Tests for the /api/extensions endpoints that distribute the WROLPi browser extension binaries."""
import json
from http import HTTPStatus

import pytest

from wrolpi import root_api


@pytest.fixture
def extension_dir(tmp_path, monkeypatch):
    """Point root_api.EXTENSION_DIR at a temp directory for the test."""
    monkeypatch.setattr(root_api, 'EXTENSION_DIR', tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_extensions_metadata_no_files(test_session, async_client, extension_dir):
    """Metadata endpoint reports unavailable when no binaries are installed."""
    request, response = await async_client.get('/api/extensions')
    assert response.status_code == HTTPStatus.OK
    body = response.json
    assert body['files']['wrolpi-chrome.zip']['available'] is False
    assert body['files']['wrolpi-firefox.xpi']['available'] is False
    assert body['files']['wrolpi-chrome.zip']['size_bytes'] is None
    assert body['versions'] == {}


@pytest.mark.asyncio
async def test_extensions_metadata_with_files(test_session, async_client, extension_dir):
    """Metadata endpoint reports each file's size and parses versions.json."""
    (extension_dir / 'wrolpi-chrome.zip').write_bytes(b'PK\x03\x04' + b'fake-chrome' * 100)
    (extension_dir / 'wrolpi-firefox.xpi').write_bytes(b'PK\x03\x04' + b'fake-xpi' * 100)
    (extension_dir / 'versions.json').write_text(json.dumps({'chrome': '0.1.0', 'firefox': '0.1.0'}))

    request, response = await async_client.get('/api/extensions')
    assert response.status_code == HTTPStatus.OK
    body = response.json
    assert body['files']['wrolpi-chrome.zip']['available'] is True
    assert body['files']['wrolpi-chrome.zip']['size_bytes'] > 0
    assert body['files']['wrolpi-firefox.xpi']['available'] is True
    assert body['versions'] == {'chrome': '0.1.0', 'firefox': '0.1.0'}


@pytest.mark.asyncio
async def test_extensions_download_chrome_zip(test_session, async_client, extension_dir):
    """Chrome zip is served with application/zip and an attachment Content-Disposition."""
    payload = b'PK\x03\x04' + b'\x00' * 1024
    (extension_dir / 'wrolpi-chrome.zip').write_bytes(payload)

    request, response = await async_client.get('/api/extensions/wrolpi-chrome.zip')
    assert response.status_code == HTTPStatus.OK
    assert response.headers.get('content-type') == 'application/zip'
    assert 'attachment' in response.headers.get('content-disposition', '')
    assert 'wrolpi-chrome.zip' in response.headers.get('content-disposition', '')
    assert response.body == payload


@pytest.mark.asyncio
async def test_extensions_download_firefox_xpi_content_type(test_session, async_client, extension_dir):
    """Firefox .xpi must be served as application/x-xpinstall for click-to-install to work."""
    payload = b'PK\x03\x04' + b'\x00' * 1024
    (extension_dir / 'wrolpi-firefox.xpi').write_bytes(payload)

    request, response = await async_client.get('/api/extensions/wrolpi-firefox.xpi')
    assert response.status_code == HTTPStatus.OK
    assert response.headers.get('content-type') == 'application/x-xpinstall'
    # Firefox click-to-install requires the response NOT carry an
    # `attachment` Content-Disposition; otherwise the browser saves the file
    # instead of invoking the add-on install handler.
    assert 'attachment' not in response.headers.get('content-disposition', '').lower()


@pytest.mark.asyncio
async def test_extensions_download_missing_file(test_session, async_client, extension_dir):
    """Whitelisted-but-not-installed file returns 404 with a clear message."""
    request, response = await async_client.get('/api/extensions/wrolpi-chrome.zip')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'not installed' in response.json['error']


@pytest.mark.asyncio
async def test_extensions_download_unknown_file(test_session, async_client, extension_dir):
    """Non-whitelisted filename returns 404 (path-traversal protection)."""
    # Even though the file might exist on disk via traversal, the whitelist blocks it.
    request, response = await async_client.get('/api/extensions/something-else.zip')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_extensions_download_path_traversal(test_session, async_client, extension_dir):
    """Path-traversal attempts are rejected by the whitelist."""
    request, response = await async_client.get('/api/extensions/..%2F..%2Fetc%2Fpasswd')
    assert response.status_code == HTTPStatus.NOT_FOUND
