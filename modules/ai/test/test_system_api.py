"""Tests for the /api/ai system endpoints (System mode)."""
from http import HTTPStatus
from unittest import mock

import pytest

CONTROLLER_STATS = dict(
    cpu=dict(percent=12.5),
    memory=dict(total=8_000_000_000, used=2_000_000_000),
    load=dict(minute_1=0.5),
    drives=[dict(mount='/media/wrolpi', percent=41)],
    # Keys the lean status must NOT forward (too big for small contexts).
    processes=[dict(pid=1, name='huge')],
    iostat=dict(huge=True),
)

CONTROLLER_SERVICES = [
    dict(name='wrolpi-api', status='running', enabled=True, port=8081, description='API', viewable=True),
    dict(name='wrolpi-kiwix', status='failed', enabled=True, port=9085, description='', view_path='/'),
]


def _mock_controller(responses: dict):
    """Patch controller_get to answer from {path: (status, body)}."""

    async def fake_controller_get(path, params=None, timeout=10):
        if path not in responses:
            raise ConnectionError(f'no controller response for {path}')
        return responses[path]

    return mock.patch('modules.ai.api.controller_get', side_effect=fake_controller_get)


@pytest.mark.asyncio
async def test_ai_system_status(async_client, test_session):
    """The aggregate status contains API state, lean Controller stats, and services."""
    responses = {
        '/api/stats': (200, CONTROLLER_STATS),
        '/api/services': (200, CONTROLLER_SERVICES),
    }
    with _mock_controller(responses):
        request, response = await async_client.get('/api/ai/status')
    assert response.status_code == HTTPStatus.OK
    assert response.json['version']
    assert response.json['wrol_mode'] is False
    assert isinstance(response.json['flags'], dict)
    # Only the lean subset of Controller stats is forwarded.
    assert response.json['system']['cpu'] == dict(percent=12.5)
    assert 'processes' not in response.json['system']
    assert 'iostat' not in response.json['system']
    # Services are lean: no view_path/viewable noise, empty description omitted.
    services = {i['name']: i for i in response.json['services']}
    assert services['wrolpi-kiwix']['status'] == 'failed'
    assert 'viewable' not in services['wrolpi-api']
    assert 'description' not in services['wrolpi-kiwix']
    assert response.json['errors'] == []


@pytest.mark.asyncio
async def test_ai_system_status_controller_down(async_client, test_session):
    """A Controller outage degrades to errors entries, never a 500."""
    with _mock_controller({}):
        request, response = await async_client.get('/api/ai/status')
    assert response.status_code == HTTPStatus.OK
    assert response.json['version']
    assert any('system stats' in i for i in response.json['errors'])
    assert any('service statuses' in i for i in response.json['errors'])
    assert 'system' not in response.json
    assert 'services' not in response.json


@pytest.mark.asyncio
async def test_ai_list_services(async_client, test_session):
    """Services are listed lean; a Controller failure is a clear 502."""
    with _mock_controller({'/api/services': (200, CONTROLLER_SERVICES)}):
        request, response = await async_client.get('/api/ai/services')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 2
    assert response.json['results'][0]['name'] == 'wrolpi-api'

    with _mock_controller({'/api/services': (500, dict(error='boom'))}):
        request, response = await async_client.get('/api/ai/services')
    assert response.status_code == HTTPStatus.BAD_GATEWAY


@pytest.mark.asyncio
async def test_ai_get_service_logs(async_client, test_session):
    """Logs are proxied with the lines param clamped."""
    captured = {}

    async def fake_controller_get(path, params=None, timeout=10):
        captured['path'] = path
        captured['params'] = params
        return 200, dict(service='wrolpi-kiwix', lines=params['lines'], logs='line1\nline2')

    with mock.patch('modules.ai.api.controller_get', side_effect=fake_controller_get):
        request, response = await async_client.get('/api/ai/services/wrolpi-kiwix/logs?lines=999999')
    assert response.status_code == HTTPStatus.OK
    assert captured['path'] == '/api/services/wrolpi-kiwix/logs'
    assert captured['params']['lines'] == 1_000  # clamped
    assert response.json['logs'] == 'line1\nline2'

    # Unknown service: the Controller's error becomes a 502 with its detail.
    with _mock_controller({'/api/services/nope/logs': (404, dict(detail='Service not found'))}):
        request, response = await async_client.get('/api/ai/services/nope/logs')
    assert response.status_code == HTTPStatus.BAD_GATEWAY


@pytest.mark.asyncio
async def test_ai_list_disks(async_client, test_session):
    """Disks and SMART are aggregated; partial failures land in errors."""
    disks = [dict(name='sda1', path='/dev/sda1', size='500G', fstype='ext4', mountpoint='/media/wrolpi')]
    responses = {
        '/api/disks': (200, disks),
        '/api/disks/smart': (200, dict(available=True, drives=[dict(name='sda', assessment='PASS')])),
    }
    with _mock_controller(responses):
        request, response = await async_client.get('/api/ai/disks')
    assert response.status_code == HTTPStatus.OK
    assert response.json['disks'] == disks
    assert response.json['smart']['available'] is True
    assert response.json['errors'] == []

    # SMART unavailable (e.g. docker) is an error entry, not a failure.
    with _mock_controller({'/api/disks': (200, disks)}):
        request, response = await async_client.get('/api/ai/disks')
    assert response.status_code == HTTPStatus.OK
    assert response.json['disks'] == disks
    assert 'smart' not in response.json
    assert len(response.json['errors']) == 1
