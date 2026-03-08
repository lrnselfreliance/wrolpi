"""
Readiness checks for WROLPi services.

Makes server-side HTTP requests to the API and React app to determine
if they are responding. Used by the controller UI during fallback and upgrade
modes to avoid cross-origin browser issues (CORS, self-signed certificates).
"""

import aiohttp

from controller.lib.config import is_docker_mode

# Timeout for individual readiness checks (seconds).
CHECK_TIMEOUT = 3


def _get_api_url() -> str:
    """Get the internal URL for the WROLPi API health check."""
    if is_docker_mode():
        return "http://api:8081/api/echo"
    return "http://127.0.0.1:8081/api/echo"


def _get_app_url() -> str:
    """Get the internal URL for the React app health check."""
    if is_docker_mode():
        return "http://app:3000"
    return "http://127.0.0.1:3000"


async def check_api_ready() -> bool:
    """Check if the main WROLPi API is responding."""
    try:
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_get_api_url()) as resp:
                return resp.status == 200
    except Exception:
        return False


async def check_app_ready() -> bool:
    """Check if the React app is responding."""
    try:
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_get_app_url()) as resp:
                return 200 <= resp.status < 400
    except Exception:
        return False
