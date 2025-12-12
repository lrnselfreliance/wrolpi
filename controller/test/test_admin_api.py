"""
Integration tests for Controller admin API endpoints.
"""


class TestHotspotStatusEndpoint:
    """Tests for /api/hotspot/status endpoint."""

    def test_hotspot_status_returns_200(self, test_client):
        """Hotspot status endpoint should return 200 OK."""
        response = test_client.get("/api/hotspot/status")
        assert response.status_code == 200

    def test_hotspot_status_returns_expected_fields(self, test_client):
        """Hotspot status should return enabled and available fields."""
        response = test_client.get("/api/hotspot/status")
        data = response.json()
        assert "enabled" in data
        assert "available" in data

    def test_hotspot_status_shows_unavailable_in_docker(self, test_client_docker_mode):
        """Hotspot should be unavailable in Docker mode."""
        response = test_client_docker_mode.get("/api/hotspot/status")
        data = response.json()
        assert data["available"] is False


class TestHotspotEnableEndpoint:
    """Tests for /api/hotspot/enable endpoint."""

    def test_hotspot_enable_fails_in_docker(self, test_client_docker_mode):
        """Hotspot enable should fail in Docker mode."""
        response = test_client_docker_mode.post("/api/hotspot/enable")
        assert response.status_code == 500
        assert "Docker" in response.json()["detail"]


class TestHotspotDisableEndpoint:
    """Tests for /api/hotspot/disable endpoint."""

    def test_hotspot_disable_fails_in_docker(self, test_client_docker_mode):
        """Hotspot disable should fail in Docker mode."""
        response = test_client_docker_mode.post("/api/hotspot/disable")
        assert response.status_code == 500
        assert "Docker" in response.json()["detail"]


class TestThrottleStatusEndpoint:
    """Tests for /api/throttle/status endpoint."""

    def test_throttle_status_returns_200(self, test_client):
        """Throttle status endpoint should return 200 OK."""
        response = test_client.get("/api/throttle/status")
        assert response.status_code == 200

    def test_throttle_status_returns_expected_fields(self, test_client):
        """Throttle status should return enabled and available fields."""
        response = test_client.get("/api/throttle/status")
        data = response.json()
        assert "enabled" in data
        assert "available" in data

    def test_throttle_status_shows_unavailable_in_docker(self, test_client_docker_mode):
        """Throttle should be unavailable in Docker mode."""
        response = test_client_docker_mode.get("/api/throttle/status")
        data = response.json()
        assert data["available"] is False


class TestThrottleEnableEndpoint:
    """Tests for /api/throttle/enable endpoint."""

    def test_throttle_enable_fails_in_docker(self, test_client_docker_mode):
        """Throttle enable should fail in Docker mode."""
        response = test_client_docker_mode.post("/api/throttle/enable")
        assert response.status_code == 500
        assert "Docker" in response.json()["detail"]


class TestThrottleDisableEndpoint:
    """Tests for /api/throttle/disable endpoint."""

    def test_throttle_disable_fails_in_docker(self, test_client_docker_mode):
        """Throttle disable should fail in Docker mode."""
        response = test_client_docker_mode.post("/api/throttle/disable")
        assert response.status_code == 500
        assert "Docker" in response.json()["detail"]


class TestShutdownEndpoint:
    """Tests for /api/shutdown endpoint."""

    def test_shutdown_returns_501_in_docker(self, test_client_docker_mode):
        """Shutdown should return 501 in Docker mode."""
        response = test_client_docker_mode.post("/api/shutdown")
        assert response.status_code == 501
        assert "Docker" in response.json()["detail"]


class TestRebootEndpoint:
    """Tests for /api/reboot endpoint."""

    def test_reboot_returns_501_in_docker(self, test_client_docker_mode):
        """Reboot should return 501 in Docker mode."""
        response = test_client_docker_mode.post("/api/reboot")
        assert response.status_code == 501
        assert "Docker" in response.json()["detail"]


class TestRestartEndpoint:
    """Tests for /api/restart endpoint."""

    def test_restart_returns_501_in_docker(self, test_client_docker_mode):
        """Restart should return 501 in Docker mode."""
        response = test_client_docker_mode.post("/api/restart")
        assert response.status_code == 501
        assert "Docker" in response.json()["detail"]


class TestOpenAPIIncludesAdminEndpoints:
    """Tests that OpenAPI documentation includes admin endpoints."""

    def test_openapi_has_hotspot_paths(self, test_client):
        """OpenAPI schema should include hotspot paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/hotspot/status" in data["paths"]
        assert "/api/hotspot/enable" in data["paths"]
        assert "/api/hotspot/disable" in data["paths"]

    def test_openapi_has_throttle_paths(self, test_client):
        """OpenAPI schema should include throttle paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/throttle/status" in data["paths"]
        assert "/api/throttle/enable" in data["paths"]
        assert "/api/throttle/disable" in data["paths"]

    def test_openapi_has_system_control_paths(self, test_client):
        """OpenAPI schema should include system control paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/shutdown" in data["paths"]
        assert "/api/reboot" in data["paths"]
        assert "/api/restart" in data["paths"]
