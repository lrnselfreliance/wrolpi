"""One helper for API -> Controller requests.

Existing call sites disagree on the base URL (wrolpi/common.py uses http://127.0.0.1, the zim
module uses the docker service name); this module resolves it once: the docker service name when
DOCKERIZED, else localhost, overridable with the CONTROLLER_URL environment variable.
"""
import os
from typing import Tuple
from urllib.parse import urlencode

from wrolpi.common import aiohttp_get, aiohttp_post, logger
from wrolpi.vars import DOCKERIZED

logger = logger.getChild(__name__)

CONTROLLER_URL = os.environ.get('CONTROLLER_URL') or ('http://controller' if DOCKERIZED else 'http://127.0.0.1')


async def controller_get(path: str, params: dict = None, timeout: int = 10) -> Tuple[int, dict]:
    """GET a Controller endpoint, returning (status, JSON body).  Raises on connection errors."""
    url = f'{CONTROLLER_URL}{path}'
    if params:
        params = {k: v for k, v in params.items() if v is not None}
        if params:
            url = f'{url}?{urlencode(params)}'
    async with aiohttp_get(url, timeout=timeout) as response:
        return response.status, await response.json()


async def controller_post(path: str, json_: dict = None, timeout: int = 30) -> Tuple[int, dict]:
    """POST a Controller endpoint, returning (status, JSON body).  Raises on connection errors."""
    async with aiohttp_post(f'{CONTROLLER_URL}{path}', json_=json_ or {}, timeout=timeout) as response:
        try:
            body = await response.json()
        except Exception:
            body = {}
        return response.status, body
