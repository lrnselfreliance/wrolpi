import json
from http import HTTPStatus

import pytest
import yaml

from wrolpi import flags
from wrolpi.api_utils import api_app
from wrolpi.common import get_wrolpi_config, enable_wrol_mode
from wrolpi.downloader import download_manager
from wrolpi.sync import lib
from wrolpi.sync.config import get_sync_config
from wrolpi.sync.status import get_sync_status, update_sync_status


@pytest.mark.asyncio
async def test_info_and_manifest(async_client, test_session, test_wrolpi_config, make_files_structure,
                                 refresh_files):
    make_files_structure({'docs/a.txt': 'a', 'docs/b.txt': 'b'})
    await refresh_files()

    request, response = await async_client.get('/api/sync/info')
    assert response.status_code == HTTPStatus.OK
    assert response.json['role'] == 'primary'
    assert response.json['max_file_group_id'] > 0

    request, response = await async_client.get('/api/sync/manifest?after_id=0&limit=1')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['groups']) == 1
    after_id = response.json['next_after_id']
    assert after_id

    request, response = await async_client.get(f'/api/sync/manifest?after_id={after_id}&limit=1')
    paths = [p['path'] for g in response.json['groups'] for p in g['paths']]
    assert len(paths) == 1 and paths[0].startswith('docs/')

    request, response = await async_client.get('/api/sync/manifest?limit=0')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_run(async_client, test_wrolpi_config, make_secondary):
    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.FORBIDDEN, 'a primary does not sync'

    make_secondary('https://primary.example')
    request, response = await async_client.post('/api/sync/run', content=json.dumps(dict(force=True)))
    assert response.status_code == HTTPStatus.ACCEPTED
    assert get_sync_status()['requested'] is True
    assert get_sync_status()['force'] is True

    request, response = await async_client.get('/api/sync/status')
    assert response.json['sync']['requested'] is True


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
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden'):
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
async def test_api_locked_while_syncing(async_client, test_wrolpi_config, flags_lock, make_secondary):
    """While a secondary syncs, its API refuses everything but the sync's own progress."""
    make_secondary()
    with lib.lock_api():
        request, response = await async_client.get('/api/files/search?search_str=foo')
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json['code'] == 'SYNCING'
        request, response = await async_client.post('/api/tag', content=json.dumps(dict(name='one')))
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE

        for path in ('/api/status', '/api/sync/status', '/api/settings', '/api/echo'):
            request, response = await async_client.get(path)
            assert response.status_code == HTTPStatus.OK, path
        request, response = await async_client.post('/api/sync/cancel')
        assert response.status_code == HTTPStatus.ACCEPTED
        # Nothing may change the sync while it runs, except stopping it.
        request, response = await async_client.put('/api/sync/settings', content=json.dumps(dict(role='primary')))
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        request, response = await async_client.post('/api/sync/run', content='{}')
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE

        request, response = await async_client.get('/api/status')
        assert response.json['flags']['sync_running'] is True

    request, response = await async_client.get('/api/settings')
    assert response.status_code == HTTPStatus.OK
    assert not api_app.shared_ctx.sync_api_locked.is_set()
    assert not flags.sync_running.is_set()


@pytest.mark.asyncio
async def test_stale_lock_event_does_not_lock(async_client, test_wrolpi_config, flags_lock):
    """The Event outlives a perpetual process that died mid-sync; the cleared Flag unlocks the API."""
    api_app.shared_ctx.sync_api_locked.set()
    try:
        request, response = await async_client.get('/api/settings')
        assert response.status_code == HTTPStatus.OK
    finally:
        api_app.shared_ctx.sync_api_locked.clear()


@pytest.mark.asyncio
async def test_wrol_mode_cancels_sync(async_client, test_wrolpi_config, test_download_manager, make_secondary):
    """WROL Mode means the secondary is in use: a running sync stops, and none start."""
    make_secondary()
    update_sync_status(state='running')
    enable_wrol_mode()
    assert get_sync_status()['cancel_requested'] is True
    assert lib.sync_skip_reason() == 'WROL Mode is enabled'

    request, response = await async_client.post('/api/sync/run', content='{}')
    assert response.status_code == HTTPStatus.FORBIDDEN
