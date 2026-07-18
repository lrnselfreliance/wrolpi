"""
Integration tests for Controller admin API endpoints.
"""

import pytest


class TestStatusEndpoints:
    """Status endpoints (hotspot/bluetooth/throttle/timezone) — shape + docker behaviour."""

    @pytest.mark.parametrize("endpoint,required_fields", [
        ("/api/hotspot/status", ["enabled", "available"]),
        ("/api/bluetooth/status", ["enabled", "available"]),
        ("/api/throttle/status", ["enabled", "available"]),
        ("/api/timezone/status", ["available", "timezone"]),
        ("/api/ssh/status", ["enabled", "available", "enabled_at_boot"]),
        ("/api/desktop/status", ["enabled", "available"]),
        ("/api/wrol-mode", ["enabled", "available", "flag_file"]),
    ])
    def test_status_endpoint_shape(self, test_client, endpoint, required_fields):
        """Each status endpoint should return 200 with the documented fields."""
        response = test_client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        for field in required_fields:
            assert field in data, f"{endpoint} missing field {field!r}"

    @pytest.mark.parametrize("endpoint", [
        "/api/hotspot/status",
        "/api/bluetooth/status",
        "/api/throttle/status",
        "/api/timezone/status",
        "/api/ssh/status",
        "/api/desktop/status",
    ])
    def test_status_endpoint_unavailable_in_docker(self, test_client_docker_mode, endpoint):
        """Status endpoints should report available=False in Docker mode."""
        data = test_client_docker_mode.get(endpoint).json()
        assert data["available"] is False


class TestHotspotDevicesEndpoint:
    """GET /api/hotspot/devices lists WiFi interfaces for the Settings dropdown."""

    def test_devices_endpoint_shape(self, test_client):
        """Should return the WiFi devices found by nmcli."""
        from unittest import mock
        with mock.patch("controller.api.admin.get_wifi_devices", return_value=["wlan0", "wlp2s0"]):
            response = test_client.get("/api/hotspot/devices")
        assert response.status_code == 200
        assert response.json() == {"devices": ["wlan0", "wlp2s0"]}

    def test_devices_empty_in_docker(self, test_client_docker_mode):
        """Should return an empty list in Docker mode."""
        response = test_client_docker_mode.get("/api/hotspot/devices")
        assert response.status_code == 200
        assert response.json() == {"devices": []}


class TestHotspotSettingsEndpoint:
    """GET/POST /api/hotspot/settings manage hotspot settings in controller.yaml."""

    def test_get_settings(self, test_client):
        """Should return the current hotspot settings."""
        response = test_client.get("/api/hotspot/settings")
        assert response.status_code == 200
        assert response.json() == {"device": "wlan0", "ssid": "WROLPi", "password": "wrolpi hotspot"}

    def test_post_settings(self, test_client, mock_config_path):
        """Should update settings and persist them to controller.yaml."""
        response = test_client.post(
            "/api/hotspot/settings",
            json={"device": "wlp2s0", "ssid": "RafaelPi", "password": "password123"},
        )
        assert response.status_code == 200
        assert response.json() == {"device": "wlp2s0", "ssid": "RafaelPi", "password": "password123"}
        assert "wlp2s0" in mock_config_path.read_text()

    def test_post_rejects_short_password(self, test_client, mock_config_path):
        """Should reject a password shorter than 8 characters."""
        response = test_client.post("/api/hotspot/settings", json={"password": "short"})
        assert response.status_code == 400

    def test_post_rejected_in_docker(self, test_client_docker_mode):
        """Should reject settings changes in Docker mode."""
        response = test_client_docker_mode.post("/api/hotspot/settings", json={"device": "wlp2s0"})
        assert response.status_code == 500


class TestDockerModeRejectsAdminActions:
    """Admin action endpoints should reject requests when running in Docker."""

    @pytest.mark.parametrize("method,endpoint,expected_status,payload", [
        # Subsystem enable/disable — return 500 with a Docker-flavoured error.
        ("post", "/api/hotspot/enable", 500, None),
        ("post", "/api/hotspot/disable", 500, None),
        ("post", "/api/bluetooth/enable", 500, None),
        ("post", "/api/bluetooth/disable", 500, None),
        ("post", "/api/throttle/enable", 500, None),
        ("post", "/api/throttle/disable", 500, None),
        ("post", "/api/ssh/enable", 500, None),
        ("post", "/api/ssh/disable", 500, None),
        ("post", "/api/desktop/enable", 500, None),
        ("post", "/api/desktop/disable", 500, None),
        ("post", "/api/timezone/set", 500, {"timezone": "America/Denver"}),
        # System control — return 501 (not implemented under Docker).
        ("post", "/api/shutdown", 501, None),
        ("post", "/api/reboot", 501, None),
        ("post", "/api/restart", 501, None),
    ])
    def test_action_rejected_in_docker(self, test_client_docker_mode, method, endpoint, expected_status, payload):
        """Admin endpoints should reject Docker-mode requests with a Docker-mentioning error."""
        client_call = getattr(test_client_docker_mode, method)
        response = client_call(endpoint, json=payload) if payload else client_call(endpoint)
        assert response.status_code == expected_status
        assert "Docker" in response.json()["detail"]


class TestNetworkInfoEndpoint:
    """GET /api/network/info for hostname + IPv4 display."""

    def test_network_info_shape(self, test_client):
        from unittest import mock
        fake = {
            "hostname": "wrolpi",
            "interfaces": [{"name": "eth0", "ipv4": ["192.168.1.10"], "up": True}],
            "primary_ipv4": "192.168.1.10",
        }
        with mock.patch("controller.api.admin.get_network_info", return_value=fake):
            response = test_client.get("/api/network/info")
        assert response.status_code == 200
        assert response.json() == fake


class TestSshApi:
    """SSH start/stop API (runtime only)."""

    def test_enable_calls_start(self, test_client):
        from unittest import mock
        with mock.patch("controller.api.admin.enable_ssh", return_value={"success": True, "error": None}) as m:
            response = test_client.post("/api/ssh/enable")
        assert response.status_code == 200
        assert response.json()["success"] is True
        m.assert_called_once()

    def test_disable_calls_stop(self, test_client):
        from unittest import mock
        with mock.patch("controller.api.admin.disable_ssh", return_value={"success": True, "error": None}) as m:
            response = test_client.post("/api/ssh/disable")
        assert response.status_code == 200
        m.assert_called_once()


class TestDesktopApi:
    """Desktop start/stop API (runtime only)."""

    def test_enable_calls_start(self, test_client):
        from unittest import mock
        with mock.patch("controller.api.admin.enable_desktop", return_value={"success": True, "error": None}) as m:
            response = test_client.post("/api/desktop/enable")
        assert response.status_code == 200
        m.assert_called_once()

    def test_disable_calls_stop(self, test_client):
        from unittest import mock
        with mock.patch("controller.api.admin.disable_desktop", return_value={"success": True, "error": None}) as m:
            response = test_client.post("/api/desktop/disable")
        assert response.status_code == 200
        m.assert_called_once()


class TestWrolModeApi:
    """WROL Mode status and toggle endpoints."""

    def test_enable_calls_lib(self, test_client):
        from unittest import mock
        result = {
            "success": True,
            "error": None,
            "yaml_updated": True,
            "api_notified": False,
            "api_error": "connection refused",
        }
        with mock.patch("controller.api.admin.enable_wrol_mode", return_value=result) as m:
            response = test_client.post("/api/wrol-mode/enable")
        assert response.status_code == 200
        assert response.json()["success"] is True
        m.assert_called_once()

    def test_disable_calls_lib(self, test_client):
        from unittest import mock
        with mock.patch(
            "controller.api.admin.disable_wrol_mode",
            return_value={"success": True, "error": None, "yaml_updated": True, "api_notified": True, "api_error": None},
        ) as m:
            response = test_client.post("/api/wrol-mode/disable")
        assert response.status_code == 200
        m.assert_called_once()


# OpenAPI endpoint-presence tests are consolidated in test_api.py::TestOpenAPI.
