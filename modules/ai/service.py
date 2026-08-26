"""llama-server lifecycle: on-demand start and idle unload.

The API owns the policy (this module); the Controller executes the mechanism through its
existing service start/stop endpoints — it runs as root natively and manages the `llm`
container in docker, so no sudoers changes are needed.

Idle unload is mandatory on small devices: a swapped-to-death Pi is worse than a slow first
token.  The chat handler records activity; the perpetual worker stops llama-server after the
configured idle minutes."""
import asyncio
import os
import time

from modules.ai.config import get_ai_config
from modules.ai.controller_client import controller_post
from wrolpi.api_utils import api_app, perpetual_signal
from wrolpi.common import aiohttp_get, logger
from wrolpi.vars import DOCKERIZED

logger = logger.getChild(__name__)

LLAMA_URL = os.environ.get('LLAMA_URL', 'http://127.0.0.1:11435')
# The Controller's name for the service: the systemd unit natively, the compose service in docker.
LLM_SERVICE_NAME = 'llm' if DOCKERIZED else 'wrolpi-llm'

# How long to wait for llama-server to answer /health after a cold start (model load included).
STARTUP_TIMEOUT_SECONDS = 90


def record_llm_activity():
    """Note that the LLM was just used; postpones the idle unload."""
    try:
        api_app.shared_ctx.ai_llm_last_request.value = time.time()
    except AttributeError:
        # Shared contexts are absent in some unit tests.
        pass


def get_last_llm_activity() -> float:
    try:
        return api_app.shared_ctx.ai_llm_last_request.value
    except AttributeError:
        return 0.0


async def llama_healthy() -> bool:
    try:
        async with aiohttp_get(f'{LLAMA_URL}/health', timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


async def start_llm_service() -> bool:
    status, body = await controller_post(f'/api/services/{LLM_SERVICE_NAME}/start')
    if status != 200:
        logger.error(f'Controller failed to start {LLM_SERVICE_NAME}: HTTP {status} {body}')
        return False
    return True


async def stop_llm_service() -> bool:
    status, body = await controller_post(f'/api/services/{LLM_SERVICE_NAME}/stop')
    if status != 200:
        logger.error(f'Controller failed to stop {LLM_SERVICE_NAME}: HTTP {status} {body}')
        return False
    return True


async def ensure_llama_running(timeout: int = STARTUP_TIMEOUT_SECONDS) -> bool:
    """Start llama-server on demand and wait for it to answer /health.

    Returns True when llama-server is up.  Cold-start latency (service start + model load) is
    expected and acceptable."""
    if await llama_healthy():
        record_llm_activity()
        return True

    logger.info(f'Asking the Controller to start {LLM_SERVICE_NAME}')
    if not await start_llm_service():
        return False

    started = time.time()
    while time.time() - started < timeout:
        if await llama_healthy():
            record_llm_activity()
            return True
        await asyncio.sleep(1)
    logger.error(f'llama-server did not become healthy within {timeout}s')
    return False


@perpetual_signal(sleep=60)
async def perpetual_llm_idle_unload():
    """Stop llama-server after the configured idle minutes.  Only acts after it was used."""
    try:
        last_activity = get_last_llm_activity()
        if not last_activity:
            return
        config = get_ai_config()
        idle_seconds = config.idle_unload_minutes * 60
        if time.time() - last_activity < idle_seconds:
            return
        if not await llama_healthy():
            # Already stopped (or crashed); nothing to unload.
            api_app.shared_ctx.ai_llm_last_request.value = 0.0
            return
        logger.info(f'Stopping {LLM_SERVICE_NAME} after {config.idle_unload_minutes} idle minutes')
        if await stop_llm_service():
            api_app.shared_ctx.ai_llm_last_request.value = 0.0
    except Exception as e:
        logger.error('LLM idle unload worker failed', exc_info=e)
