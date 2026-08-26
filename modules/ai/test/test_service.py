"""Tests for the llama-server lifecycle: on-demand start and idle unload."""
import time
from unittest import mock

import pytest

from modules.ai import service


@pytest.mark.asyncio
async def test_ensure_llama_running_already_healthy(async_client):
    """A healthy llama-server is used as-is and activity is recorded."""
    with mock.patch('modules.ai.service.llama_healthy', return_value=True), \
            mock.patch('modules.ai.service.start_llm_service') as start:
        assert await service.ensure_llama_running() is True
    start.assert_not_called()
    assert service.get_last_llm_activity() > 0


@pytest.mark.asyncio
async def test_ensure_llama_running_cold_start(async_client):
    """An unhealthy llama-server is started via the Controller and polled until healthy."""
    health = iter([False, False, True])

    async def fake_healthy():
        return next(health)

    with mock.patch('modules.ai.service.llama_healthy', side_effect=fake_healthy), \
            mock.patch('modules.ai.service.start_llm_service', return_value=True) as start, \
            mock.patch('modules.ai.service.asyncio.sleep'):
        assert await service.ensure_llama_running(timeout=10) is True
    start.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_llama_running_start_fails(async_client):
    """A Controller start failure is reported as False, not an exception."""
    with mock.patch('modules.ai.service.llama_healthy', return_value=False), \
            mock.patch('modules.ai.service.start_llm_service', return_value=False):
        assert await service.ensure_llama_running(timeout=1) is False


@pytest.mark.asyncio
async def test_idle_unload(async_client, test_ai_config):
    """llama-server is stopped only after the configured idle minutes."""
    from wrolpi.api_utils import api_app
    from modules.ai.config import get_ai_config

    get_ai_config().idle_unload_minutes = 10

    # Never used: nothing happens.
    api_app.shared_ctx.ai_llm_last_request.value = 0.0
    with mock.patch('modules.ai.service.stop_llm_service') as stop:
        await service.perpetual_llm_idle_unload()
    stop.assert_not_called()

    # Recently used: not stopped.
    api_app.shared_ctx.ai_llm_last_request.value = time.time()
    with mock.patch('modules.ai.service.stop_llm_service') as stop, \
            mock.patch('modules.ai.service.llama_healthy', return_value=True):
        await service.perpetual_llm_idle_unload()
    stop.assert_not_called()

    # Idle past the threshold: stopped, and the activity marker resets.
    api_app.shared_ctx.ai_llm_last_request.value = time.time() - 11 * 60
    with mock.patch('modules.ai.service.stop_llm_service', return_value=True) as stop, \
            mock.patch('modules.ai.service.llama_healthy', return_value=True):
        await service.perpetual_llm_idle_unload()
    stop.assert_called_once()
    assert api_app.shared_ctx.ai_llm_last_request.value == 0.0

    # Idle but already stopped: the marker resets without a stop call.
    api_app.shared_ctx.ai_llm_last_request.value = time.time() - 11 * 60
    with mock.patch('modules.ai.service.stop_llm_service') as stop, \
            mock.patch('modules.ai.service.llama_healthy', return_value=False):
        await service.perpetual_llm_idle_unload()
    stop.assert_not_called()
    assert api_app.shared_ctx.ai_llm_last_request.value == 0.0
