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
