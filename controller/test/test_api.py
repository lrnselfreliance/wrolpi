"""
Integration tests for Controller API endpoints.
"""
import re
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from controller import __version__


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_returns_200(self, test_client):
        """Health endpoint should return 200 OK."""
        response = test_client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_expected_fields(self, test_client):
        """Health endpoint should return expected fields."""
        response = test_client.get("/api/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == __version__
        assert data["docker_mode"] is False
        assert "drive_mounted" in data
        assert isinstance(data["drive_mounted"], bool)

    def test_health_returns_docker_mode_true(self, test_client_docker_mode):
        """Health endpoint should return docker_mode=true when in Docker."""
        response = test_client_docker_mode.get("/api/health")
        data = response.json()
        assert data["docker_mode"] is True


class TestDashboardEndpoint:
    """Tests for / dashboard endpoint (UI)."""

    def test_dashboard_basic_response(self, test_client):
        """Dashboard should return 200 with HTML content-type and a recognisable body."""
        response = test_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert b"Controller" in response.content
        assert b"WROLPi" in response.content

    @pytest.mark.parametrize("needle", [
        # Status cards.
        "CPU", "Memory", "Load", "Storage",
        # Sections / structural ids.
        "Disks", 'id="disks"', "Services", 'id="services"',
        # System actions.
        "System Actions", "Restart All Services",
        # Mount modal.
        'id="mount-modal"', 'id="mount-point-input"', 'id="mount-persist-checkbox"',
        "Persistent (survive reboots)",
        # Disks JS table.
        "<th>Persist</th>", "function togglePersist", "api/disks/fstab",
    ])
    def test_dashboard_contains(self, test_client, needle):
        """Dashboard body should contain each expected fragment (native mode)."""
        response = test_client.get("/")
        assert needle in response.text

    def test_dashboard_native_mode_shows_boot_column_and_hides_docker_banner(self, test_client):
        """Native (non-Docker) mode: Boot column visible, no Docker banner."""
        response = test_client.get("/")
        content = response.text
        assert "<th>Boot</th>" in content
        assert 'class="toggle"' in content
        assert "Running in Docker mode" not in content

    def test_dashboard_docker_mode_shows_banner_and_hides_boot_column(self, test_client_docker_mode):
        """Docker mode: Docker banner visible, no Boot toggles in rendered tbody."""
        response = test_client_docker_mode.get("/")
        content = response.text
        assert "Running in Docker mode" in content
        assert "<th>Boot</th>" not in content
        # JS template literals may mention 'id="boot-' but the server-rendered tbody must not.
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', content, re.DOTALL)
        if tbody_match:
            assert 'id="boot-' not in tbody_match.group(1)


class TestOpenAPI:
    """Tests for the OpenAPI schema and its expected endpoint coverage."""

    @pytest.fixture
    def openapi(self, test_client):
        """Fetch the OpenAPI schema once per parametrized test."""
        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        return response.json()

    def test_openapi_metadata(self, openapi):
        """Schema title and version should match the package metadata."""
        assert openapi["info"]["title"] == "WROLPi Controller"
        assert openapi["info"]["version"] == __version__

    @pytest.mark.parametrize("path", [
        # Health.
        "/api/health",
        # Stats (per-resource + aggregated).
        "/api/stats/cpu", "/api/stats/memory", "/api/stats/load",
        "/api/stats/drives/primary", "/api/stats/network", "/api/stats/power",
        # Admin: hotspot, bluetooth, throttle, timezone, power.
        "/api/hotspot/status", "/api/hotspot/enable", "/api/hotspot/disable",
        "/api/bluetooth/status", "/api/bluetooth/enable", "/api/bluetooth/disable",
        "/api/throttle/status", "/api/throttle/enable", "/api/throttle/disable",
        "/api/timezone/status", "/api/timezone/set",
        "/api/network/info",
        "/api/ssh/status", "/api/ssh/enable", "/api/ssh/disable",
        "/api/desktop/status", "/api/desktop/enable", "/api/desktop/disable",
        "/api/wrol-mode", "/api/wrol-mode/enable", "/api/wrol-mode/disable",
        "/api/shutdown", "/api/reboot", "/api/restart",
        # Disks.
        "/api/disks", "/api/disks/mounts", "/api/disks/mount", "/api/disks/unmount",
        "/api/disks/fstab", "/api/disks/smart",
        # Services.
        "/api/services", "/api/services/{name}",
        "/api/services/{name}/start", "/api/services/{name}/stop",
        "/api/services/{name}/restart", "/api/services/{name}/enable",
        "/api/services/{name}/disable", "/api/services/{name}/logs",
        # Scripts.
        "/api/scripts", "/api/scripts/status",
        "/api/scripts/{name}/start", "/api/scripts/{name}/output",
    ])
    def test_openapi_has_path(self, openapi, path):
        """Every documented API path should be present in the OpenAPI schema."""
        assert path in openapi["paths"], f"OpenAPI schema is missing {path}"

    def test_openapi_has_aggregated_stats(self, openapi):
        """Aggregated /api/stats endpoint (may register with or without trailing slash)."""
        paths = openapi["paths"]
        assert "/api/stats" in paths or "/api/stats/" in paths


class TestDocsEndpoint:
    """Tests for Swagger UI documentation endpoint."""

    def test_docs_returns_200(self, test_client):
        """Docs endpoint should return 200 OK."""
        response = test_client.get("/docs")
        assert response.status_code == 200

    def test_docs_returns_html(self, test_client):
        """Docs endpoint should return HTML."""
        response = test_client.get("/docs")
        assert "text/html" in response.headers["content-type"]


class TestDriveMountedStatus:
    """Tests for drive mounted status in responses."""

    @pytest.mark.parametrize("endpoint,mounted,expected", [
        ("/api/health", True, True),
        ("/api/health", False, False),
    ])
    def test_drive_mounted_status(self, reset_runtime_config, mock_docker_mode, endpoint, mounted, expected):
        """Endpoints should return correct drive_mounted status."""
        from controller.main import app

        with mock.patch(
                "controller.main.is_primary_drive_mounted", return_value=mounted
        ):
            with TestClient(app) as client:
                response = client.get(endpoint)
                data = response.json()
                assert data["drive_mounted"] is expected

    def test_dashboard_shows_onboarding_when_drive_not_mounted(self, reset_runtime_config, mock_docker_mode):
        """Dashboard should show onboarding banner in native mode when drive is not mounted."""
        from controller.main import app

        with mock.patch(
                "controller.main.is_primary_drive_mounted", return_value=False
        ):
            with TestClient(app) as client:
                response = client.get("/")
                assert "Welcome to WROLPi" in response.text

    def test_dashboard_shows_drive_not_mounted_banner_in_docker(self, reset_runtime_config, mock_docker_mode_enabled):
        """Dashboard should show info banner in Docker mode when drive is not mounted."""
        from controller.main import app

        with mock.patch(
                "controller.main.is_primary_drive_mounted", return_value=False
        ):
            with TestClient(app) as client:
                response = client.get("/")
                assert "Primary drive not mounted" in response.text
