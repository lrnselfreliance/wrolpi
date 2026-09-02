"""Tests for the ai.yaml config, the model catalog, and the GGUF downloader."""
import json
from http import HTTPStatus
from unittest import mock

import pytest
import yaml

from modules.ai import catalog
from modules.ai.config import get_ai_config
from modules.ai.downloader import ai_model_downloader
from wrolpi.downloader import Download


def test_ai_config_defaults_and_update(test_ai_config):
    """The config has safe defaults (AI off) and round-trips values."""
    config = get_ai_config()
    assert config.enabled is False
    assert config.active_model == ''
    assert config.idle_unload_minutes == 15
    assert config.context_size is None
    assert config.max_tool_calls == 6
    assert config.temperature == 0.3

    config.enabled = True
    config.active_model = 'Qwen3-1.7B-Q4_K_M.gguf'
    config.context_size = 8_192
    assert get_ai_config().enabled is True
    assert get_ai_config().active_model == 'Qwen3-1.7B-Q4_K_M.gguf'
    assert get_ai_config().context_size == 8_192


@pytest.mark.asyncio
async def test_ai_config_import(test_ai_config):
    """A hand-edited ai.yaml is the source of truth on import."""
    test_ai_config.write_text(yaml.dump(dict(
        version=1, enabled=True, active_model='custom.gguf', idle_unload_minutes=5,
        context_size=None, max_tool_calls=4,
    )))
    config = get_ai_config()
    config.import_config(test_ai_config)
    assert config.enabled is True
    assert config.active_model == 'custom.gguf'
    assert config.idle_unload_minutes == 5
    assert config.max_tool_calls == 4
    assert config.successful_import is True


@pytest.mark.asyncio
async def test_models_catalog_fallback(async_client):
    """The bundled catalog is served when the CDN is unreachable."""
    with mock.patch('modules.ai.catalog.fetch_models_manifest', side_effect=RuntimeError('offline')):
        models, source = await catalog.get_models_catalog()
    assert source == 'bundled'
    assert models == catalog.AI_MODELS

    manifest = dict(version=1, models=[dict(name='new.gguf', tier='small')])
    with mock.patch('modules.ai.catalog.fetch_models_manifest', return_value=manifest):
        models, source = await catalog.get_models_catalog()
    assert source == 'cdn'
    assert models[0]['name'] == 'new.gguf'


def test_recommend_tier():
    gb = 1024 ** 3
    assert catalog.recommend_tier(4 * gb) == 'small'
    assert catalog.recommend_tier(8 * gb) == 'medium'
    assert catalog.recommend_tier(32 * gb) == 'large'


@pytest.mark.asyncio
async def test_model_downloader(test_session, test_directory, test_download_manager):
    """The model downloader verifies the meta4 signature, stages, and lands in <media>/ai/models."""
    url = 'https://example.com/ai/Test-Model-Q4_K_M.gguf'
    download = Download(url=url, downloader='ai_model')

    prepared = ai_model_downloader.prepare_download(test_session, download)
    assert prepared.error is None
    assert prepared.output_path == test_directory / 'ai/models/Test-Model-Q4_K_M.gguf'
    assert prepared.models_directory.is_dir()

    meta4 = b'<metalink>fake</metalink>'

    async def fake_download_file(download_, url_, directory, **kwargs):
        assert kwargs['meta4_xml'] == meta4
        path = directory / 'Test-Model-Q4_K_M.gguf'
        path.write_bytes(b'GGUF fake weights')
        return path

    with mock.patch.object(ai_model_downloader, 'get_meta4_contents', return_value=meta4), \
            mock.patch('modules.ai.downloader.verify_meta4_signature', return_value=True), \
            mock.patch.object(ai_model_downloader, 'download_file', side_effect=fake_download_file):
        executed = await ai_model_downloader.execute_download(prepared, ctx=None, download=download)
    assert executed.error is None
    assert prepared.output_path.is_file()

    result = ai_model_downloader.finalize_download(test_session, download, executed)
    assert result.success is True

    # A second download of the same model is skipped.
    prepared = ai_model_downloader.prepare_download(test_session, download)
    assert prepared.already_done is True
    executed = await ai_model_downloader.execute_download(prepared, ctx=None, download=download)
    assert executed.skipped is True


@pytest.mark.asyncio
async def test_model_downloader_refuses_unverified(test_session, test_directory, test_download_manager):
    """No meta4, or a bad signature, refuses the download."""
    url = 'https://example.com/ai/Test-Model.gguf'
    download = Download(url=url, downloader='ai_model')
    prepared = ai_model_downloader.prepare_download(test_session, download)

    with mock.patch.object(ai_model_downloader, 'get_meta4_contents', return_value=None):
        executed = await ai_model_downloader.execute_download(prepared, ctx=None, download=download)
    assert 'refusing an unverified download' in executed.error

    with mock.patch.object(ai_model_downloader, 'get_meta4_contents', return_value=b'<m/>'), \
            mock.patch('modules.ai.downloader.verify_meta4_signature', return_value=False):
        executed = await ai_model_downloader.execute_download(prepared, ctx=None, download=download)
    assert 'signature verification failed' in executed.error
    assert not prepared.output_path.exists()

    # Not a GGUF URL is refused in prepare.
    bad = ai_model_downloader.prepare_download(test_session, Download(url='https://example.com/x.zip'))
    assert 'Not a GGUF model URL' in bad.error


@pytest.mark.asyncio
async def test_ai_manage_endpoints(async_client, test_directory, test_ai_config):
    """The Manage tab's catalog and settings endpoints."""
    with mock.patch('modules.ai.catalog.fetch_models_manifest', side_effect=RuntimeError('offline')):
        request, response = await async_client.get('/api/ai/manage/catalog')
    assert response.status_code == HTTPStatus.OK
    assert response.json['catalog_source'] == 'bundled'
    assert response.json['enabled'] is False
    assert response.json['recommended_tier'] in ('small', 'medium', 'large')
    assert all(i['downloaded'] is False for i in response.json['models'])

    # Selecting a model that is not downloaded is refused.
    content = dict(active_model='Qwen3-1.7B-Q4_K_M.gguf')
    request, response = await async_client.post('/api/ai/manage/settings', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Once the file exists it can be selected, and shows downloaded/active in the catalog.
    models_dir = test_directory / 'ai/models'
    models_dir.mkdir(parents=True)
    (models_dir / 'Qwen3-1.7B-Q4_K_M.gguf').write_bytes(b'GGUF')
    content = dict(active_model='Qwen3-1.7B-Q4_K_M.gguf', enabled=True, idle_unload_minutes=5)
    request, response = await async_client.post('/api/ai/manage/settings', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['active_model'] == 'Qwen3-1.7B-Q4_K_M.gguf'
    assert response.json['enabled'] is True

    with mock.patch('modules.ai.catalog.fetch_models_manifest', side_effect=RuntimeError('offline')):
        request, response = await async_client.get('/api/ai/manage/catalog')
    model = next(i for i in response.json['models'] if i['name'] == 'Qwen3-1.7B-Q4_K_M.gguf')
    assert model['downloaded'] is True and model['active'] is True
    assert response.json['disk_usage'] > 0

    # Bad idle minutes.
    request, response = await async_client.post('/api/ai/manage/settings',
                                                content=json.dumps(dict(idle_unload_minutes=0)))
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_effective_context_size(test_ai_config):
    """Explicit ai.yaml value wins; else the active model's catalog default; else the small default."""
    config = get_ai_config()
    assert catalog.get_effective_context_size() == 8_192  # no model, no override

    config.active_model = 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
    assert catalog.get_effective_context_size() == 16_384  # the 4B's catalog default

    config.context_size = 4_096
    assert catalog.get_effective_context_size() == 4_096  # explicit override wins


@pytest.mark.asyncio
async def test_manage_settings_adopts_model_context(async_client, test_directory, test_ai_config):
    """Selecting a model writes its catalog context default unless the request sets one."""
    models_dir = test_directory / 'ai/models'
    models_dir.mkdir(parents=True)
    (models_dir / 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf').write_bytes(b'GGUF')

    content = dict(active_model='Qwen3-4B-Instruct-2507-Q4_K_M.gguf')
    request, response = await async_client.post('/api/ai/manage/settings', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['context_size'] == 16_384

    # An explicit context_size in the same request is respected.
    content = dict(active_model='Qwen3-4B-Instruct-2507-Q4_K_M.gguf', context_size=4_096)
    request, response = await async_client.post('/api/ai/manage/settings', content=json.dumps(content))
    assert response.json['context_size'] == 4_096
