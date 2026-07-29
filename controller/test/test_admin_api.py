"""
Integration tests for Controller admin API endpoints.
"""

import pytest


class TestStatusEndpoints:
    """Status endpoints (hotspot/bluetooth/desktop/throttle/timezone) — shape + docker behaviour."""

    @pytest.mark.parametrize("endpoint,required_fields", [
        ("/api/hotspot/status", ["enabled", "available"]),
        ("/api/bluetooth/status", ["enabled", "available"]),
        ("/api/desktop/status", ["running", "available"]),
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
        "/api/desktop/status",
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


class TestHotspotProtocolsEndpoint:
    """GET /api/hotspot/protocols lists the protocols a device can host."""

    def test_protocols_endpoint_shape(self, test_client):
        """Should probe the requested device."""
        from unittest import mock
        with mock.patch("controller.api.admin.get_device_hotspot_protocols",
                        return_value=["wpa2", "wpa3"]) as mock_protocols:
            response = test_client.get("/api/hotspot/protocols?device=wlp2s0")
        assert response.status_code == 200
        assert response.json() == {"device": "wlp2s0", "protocols": ["wpa2", "wpa3"]}
        mock_protocols.assert_called_once_with("wlp2s0")

    def test_protocols_defaults_to_configured_device(self, test_client):
        """Should probe the configured hotspot device when none is given."""
        from unittest import mock
        with mock.patch("controller.api.admin.get_device_hotspot_protocols", return_value=["wpa2"]):
            response = test_client.get("/api/hotspot/protocols")
        assert response.status_code == 200
        assert response.json() == {"device": "wlan0", "protocols": ["wpa2"]}

    def test_protocols_empty_in_docker(self, test_client_docker_mode):
        """Docker mode cannot host a hotspot."""
        response = test_client_docker_mode.get("/api/hotspot/protocols?device=wlan0")
        assert response.status_code == 200
        assert response.json() == {"device": "wlan0", "protocols": []}


class TestHotspotSettingsEndpoint:
    """GET/POST /api/hotspot/settings manage hotspot settings in controller.yaml."""

    def test_get_settings(self, test_client):
        """Should return the current hotspot settings."""
        response = test_client.get("/api/hotspot/settings")
        assert response.status_code == 200
        assert response.json() == {"device": "wlan0", "ssid": "WROLPi", "password": "wrolpi hotspot",
                                   "protocol": "wpa2"}

    def test_post_settings(self, test_client, mock_config_path):
        """Should update settings and persist them to controller.yaml."""
        response = test_client.post(
            "/api/hotspot/settings",
            json={"device": "wlp2s0", "ssid": "RafaelPi", "password": "password123", "protocol": "wpa3"},
        )
        assert response.status_code == 200
        assert response.json() == {"device": "wlp2s0", "ssid": "RafaelPi", "password": "password123",
                                   "protocol": "wpa3"}
        assert "wlp2s0" in mock_config_path.read_text()
        assert "wpa3" in mock_config_path.read_text()

    def test_post_rejects_short_password(self, test_client, mock_config_path):
        """Should reject a password shorter than 8 characters."""
        response = test_client.post("/api/hotspot/settings", json={"password": "short"})
        assert response.status_code == 400

    def test_post_rejects_invalid_protocol(self, test_client, mock_config_path):
        """Should reject protocols other than wpa2/wpa3."""
        response = test_client.post("/api/hotspot/settings", json={"protocol": "wep"})
        assert response.status_code == 400

    def test_post_rejected_in_docker(self, test_client_docker_mode):
        """Should reject settings changes in Docker mode."""
        response = test_client_docker_mode.post("/api/hotspot/settings", json={"device": "wlp2s0"})
        assert response.status_code == 500


class TestDockerModeRejectsAdminActions:
    """Admin action endpoints should reject requests when running in Docker."""

    @pytest.mark.parametrize("method,endpoint,expected_status,payload", [
        # Subsystem actions — return 500 with a Docker-flavoured error.
        ("post", "/api/hotspot/start", 500, None),
        ("post", "/api/hotspot/stop", 500, None),
        ("post", "/api/bluetooth/unblock", 500, None),
        ("post", "/api/bluetooth/block", 500, None),
        ("post", "/api/desktop/start", 500, None),
        ("post", "/api/desktop/stop", 500, None),
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


class TestDesktopEndpoints:
    """Desktop start/stop endpoints drive the display-manager.service unit."""

    @pytest.mark.parametrize("endpoint,systemctl_action", [
        ("/api/desktop/start", "start"),
        ("/api/desktop/stop", "stop"),
    ])
    def test_action_runs_systemctl(self, test_client, endpoint, systemctl_action):
        """Each action endpoint should run systemctl with the matching action."""
        from unittest import mock

        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            response = test_client.post(endpoint)
        assert response.status_code == 200
        assert response.json()["success"] is True
        # Stopping also switches the display to a console VT, so assert the first call.
        assert mock_exec.call_args_list[0] == mock.call(
            "systemctl", systemctl_action, "display-manager.service",
            stdout=mock.ANY,
            stderr=mock.ANY,
        )

    @pytest.mark.parametrize("endpoint", ["/api/desktop/start", "/api/desktop/stop"])
    def test_action_reports_failure(self, test_client, endpoint):
        """A failed systemctl action should return a 500 with the error detail."""
        from unittest import mock

        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Failed to connect to bus")
        mock_proc.returncode = 1

        with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            response = test_client.post(endpoint)
        assert response.status_code == 500
        assert "Failed to connect to bus" in response.json()["detail"]
