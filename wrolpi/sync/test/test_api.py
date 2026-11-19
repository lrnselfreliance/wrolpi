import contextlib
import json
from http import HTTPStatus

import pytest
import yaml

from wrolpi.common import get_wrolpi_config, enable_wrol_mode
from wrolpi.downloader import download_manager
from wrolpi.sync import api as sync_api, backup, snapshot
from wrolpi.sync.config import get_sync_config


@pytest.mark.asyncio
async def test_info(async_client, test_session, test_wrolpi_config):
    request, response = await async_client.get('/api/sync/info')
    assert response.status_code == HTTPStatus.OK
    assert set(response.json) == {'version', 'role', 'media_directory', 'database_revision', 'media_mounted'}
    assert response.json['role'] == 'primary'

    # The old engine's manifest is gone; a secondary copies with rsync.
    request, response = await async_client.get('/api/sync/manifest')
    assert response.status_code == HTTPStatus.NOT_FOUND


class FakeControllerResponse:
    def __init__(self, status, body=None):
        self.status, self.body = status, body

    async def json(self, content_type=None):
        return self.body


def fake_controller(monkeypatch, status=None, body=None, error=None):
    """The Controller answers the API's sync requests with `status` and `body`, or not at all (`error`)."""
    calls = []

    @contextlib.asynccontextmanager
    async def aiohttp_post(url, json_, timeout=None, headers=None):
        calls.append(url)
        if error:
            raise error
        yield FakeControllerResponse(status, body)

    monkeypatch.setattr(sync_api, 'aiohttp_post', aiohttp_post)
    return calls


@pytest.mark.asyncio
async def test_run(async_client, test_wrolpi_config, make_secondary, monkeypatch):
    """The Controller runs a secondary's sync, because it stops this API; the API only asks it to."""
    calls = fake_controller(monkeypatch, status=HTTPStatus.ACCEPTED)
    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.FORBIDDEN, 'a primary does not sync'
    assert calls == []

    make_secondary('https://primary.example')
    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.ACCEPTED
    assert calls == ['http://127.0.0.1/api/sync/run']
    request, response = await async_client.post('/api/sync/cancel')
    assert response.status_code == HTTPStatus.ACCEPTED
    assert calls[-1] == 'http://127.0.0.1/api/sync/cancel'

    # The Controller's reason is the API's.
    fake_controller(monkeypatch, status=HTTPStatus.CONFLICT, body=dict(detail='A sync is already running'))
    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['error'] == 'A sync is already running'

    fake_controller(monkeypatch, error=ConnectionRefusedError())
    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['error'] == 'The Controller did not answer'


@pytest.mark.asyncio
async def test_worker_runs_the_backup_and_the_snapshot(async_client, test_wrolpi_config, monkeypatch):
    """The API's loop makes the backup and the primary's database snapshot; a secondary's sync is the Controller's."""
    called = []

    async def tick(name):
        called.append(name)

    monkeypatch.setattr(backup, 'backup_tick', lambda: tick('backup'))
    monkeypatch.setattr(snapshot, 'snapshot_tick', lambda: tick('snapshot'))
    await sync_api.perpetual_sync_worker()
    assert called == ['backup', 'snapshot']


@pytest.mark.asyncio
async def test_settings(async_client, test_directory, test_wrolpi_config, test_download_manager, await_switches):
    body = dict(role='secondary', sync_primary_url=' https://10.0.0.5:8443/ ', sync_window_start='01:00',
                sync_window_end='05:00')
    request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    config = get_sync_config()
    assert config.role == 'secondary'
    assert config.primary_url == 'https://10.0.0.5:8443'
    assert (config.window_start, config.window_end) == ('01:00', '05:00')
    # Saved to sync.yaml, not wrolpi.yaml.
    await await_switches()
    saved = yaml.safe_load((test_directory / 'config/sync.yaml').read_text())
    assert (saved['role'], saved['primary_url']) == ('secondary', 'https://10.0.0.5:8443')
    assert 'role' not in get_wrolpi_config().dict()
    assert download_manager.is_disabled, 'a secondary does not download'

    request, response = await async_client.get('/api/settings')
    assert response.json['role'] == 'secondary'
    assert response.json['sync_primary_url'] == 'https://10.0.0.5:8443'

    request, response = await async_client.post('/api/download/enable')
    assert response.status_code == HTTPStatus.FORBIDDEN

    # The backup drive has its own window.
    body = dict(backup_window_start='02:00', backup_window_end='04:00')
    request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert (config.backup_window_start, config.backup_window_end) == ('02:00', '04:00')
    assert (config.window_start, config.window_end) == ('01:00', '05:00')
    request, response = await async_client.get('/api/settings')
    assert (response.json['backup_window_start'], response.json['backup_window_end']) == ('02:00', '04:00')

    # Clearing the window leaves only "Sync now".
    body = dict(sync_window_start='', sync_window_end='')
    request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert config.window_start is None

    for body in (dict(role='tertiary'), dict(sync_primary_url='ftp://primary'),
                 dict(sync_primary_url='https://user:password@primary'),
                 dict(sync_primary_url='https://primary/media'), dict(sync_window_start='25:00'),
                 dict(backup_window_end='5pm'), dict()):
        request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST, body


@pytest.mark.asyncio
async def test_settings_excluded_directories(async_client, test_directory, test_wrolpi_config, await_switches):
    """Each panel has its own excluded folders, normalized and saved to sync.yaml."""
    body = dict(sync_excluded_directories=['/Movies/', 'Movies/deep'], backup_excluded_directories=['videos/Movies'])
    request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    config = get_sync_config()
    assert config.sync_excluded_directories == ['Movies']
    assert config.backup_excluded_directories == ['videos/Movies']
    await await_switches()
    saved = yaml.safe_load((test_directory / 'config/sync.yaml').read_text())
    assert saved['sync_excluded_directories'] == ['Movies']
    assert saved['backup_excluded_directories'] == ['videos/Movies']

    request, response = await async_client.get('/api/settings')
    assert response.json['sync_excluded_directories'] == ['Movies']
    assert response.json['backup_excluded_directories'] == ['videos/Movies']

    # Changing one list leaves the other alone; [] clears.
    request, response = await async_client.put('/api/sync/settings',
                                               content=json.dumps(dict(backup_excluded_directories=[])))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert config.backup_excluded_directories == []
    assert config.sync_excluded_directories == ['Movies']

    for value in (['../etc'], ['config'], ['.hidden'], [''], 'Movies'):
        body = dict(sync_excluded_directories=value)
        request, response = await async_client.put('/api/sync/settings', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST, value
    assert config.sync_excluded_directories == ['Movies']


@pytest.mark.asyncio
async def test_directories(async_client, test_directory, test_wrolpi_config):
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden', 'lost+found'):
        (test_directory / i).mkdir(parents=True, exist_ok=True)

    request, response = await async_client.post('/api/sync/directories', content=json.dumps(dict(path='')))
    assert response.status_code == HTTPStatus.OK
    assert response.json['directories'] == [dict(name='Movies', path='Movies'), dict(name='videos', path='videos')]

    body = dict(path='videos', source='local')
    request, response = await async_client.post('/api/sync/directories', content=json.dumps(body))
    assert response.json['directories'] == [dict(name='channel', path='videos/channel')]

    for body in (dict(path='../'), dict(path='missing'), dict(source='elsewhere'),
                 dict(source='primary')):  # A primary has no primary.
        request, response = await async_client.post('/api/sync/directories', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST, body


@pytest.mark.asyncio
async def test_directories_primary_unreachable(async_client, test_wrolpi_config, make_secondary):
    """A primary that does not answer is reported, not raised."""
    make_secondary('https://127.0.0.1:1')
    body = dict(path='', source='primary')
    request, response = await async_client.post('/api/sync/directories', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert response.json['error']


@pytest.mark.asyncio
async def test_wrol_mode_refuses_a_sync(async_client, test_wrolpi_config, test_download_manager, make_secondary,
                                        monkeypatch):
    """WROL Mode means the secondary is in use: no sync is asked of the Controller.  (The Controller itself also
    refuses, and stops a sync at its next step, when it finds WROL Mode enabled.)"""
    make_secondary()
    calls = fake_controller(monkeypatch, status=HTTPStatus.ACCEPTED)
    enable_wrol_mode()

    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert calls == []
