"""HTTP client for the WROLPi API."""
import httpx

from wrolpi_mcp.config import API_BASE_URL, VERIFY_TLS


async def api_get(path: str, params: dict | None = None) -> dict:
    """GET request to the WROLPi API.  Returns parsed JSON."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, verify=VERIFY_TLS, timeout=30.0) as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


async def api_post(path: str, json: dict | None = None) -> dict:
    """POST request to the WROLPi API.  Returns parsed JSON."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, verify=VERIFY_TLS, timeout=30.0) as client:
        resp = await client.post(path, json=json or {})
        resp.raise_for_status()
        return resp.json()


async def api_get_text(path: str) -> str:
    """GET request that returns raw text/HTML."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, verify=VERIFY_TLS, timeout=30.0) as client:
        resp = await client.get(path)
        resp.raise_for_status()
        return resp.text
