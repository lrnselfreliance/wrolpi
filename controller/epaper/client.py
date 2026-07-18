"""HTTP client for Controller APIs used by the e-paper UI."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ControllerClient:
    def __init__(self, base_url: str = "http://127.0.0.1", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
        except Exception as e:
            raise RuntimeError(f"Controller unreachable: {e}") from e

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: Optional[dict] = None) -> Any:
        return self._request("POST", path, body if body is not None else {})

    def health(self) -> dict:
        return self.get("/api/health")

    def stats(self) -> dict:
        return self.get("/api/stats")

    def network_info(self) -> dict:
        return self.get("/api/network/info")

    def feature_status(self, name: str) -> dict:
        paths = {
            "hotspot": "/api/hotspot/status",
            "bluetooth": "/api/bluetooth/status",
            "throttle": "/api/throttle/status",
            "ssh": "/api/ssh/status",
            "desktop": "/api/desktop/status",
            "wrol_mode": "/api/wrol-mode",
        }
        return self.get(paths[name])

    def hotspot_settings(self) -> dict:
        """SSID/password for WiFi QR (only use password when hotspot is on)."""
        return self.get("/api/hotspot/settings")

    def feature_set(self, name: str, enable: bool) -> dict:
        action = "enable" if enable else "disable"
        paths = {
            "hotspot": f"/api/hotspot/{action}",
            "bluetooth": f"/api/bluetooth/{action}",
            "throttle": f"/api/throttle/{action}",
            "ssh": f"/api/ssh/{action}",
            "desktop": f"/api/desktop/{action}",
            "wrol_mode": f"/api/wrol-mode/{action}",
        }
        return self.post(paths[name])

    def reboot(self) -> dict:
        return self.post("/api/reboot")

    def shutdown(self) -> dict:
        return self.post("/api/shutdown")
