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


# OpenAPI endpoint-presence tests are consolidated in test_api.py::TestOpenAPI.
