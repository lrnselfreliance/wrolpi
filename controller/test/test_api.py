"""
Integration tests for Controller API endpoints.
"""
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

    def test_dashboard_returns_200(self, test_client):
        """Dashboard endpoint should return 200 OK."""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_dashboard_returns_html(self, test_client):
        """Dashboard endpoint should return HTML."""
        response = test_client.get("/")
        assert "text/html" in response.headers["content-type"]

    def test_dashboard_contains_title(self, test_client):
        """Dashboard should contain title."""
        response = test_client.get("/")
        # Title format is "Controller - {hostname} WROLPi"
        assert b"Controller" in response.content
        assert b"WROLPi" in response.content

    def test_dashboard_contains_version(self, test_client):
        """Dashboard should contain version."""
        response = test_client.get("/")
        assert __version__.encode() in response.content

    def test_dashboard_contains_status_cards(self, test_client):
        """Dashboard should contain status cards."""
        response = test_client.get("/")
        content = response.text
        assert "CPU" in content
        assert "Memory" in content
        assert "Load" in content
        assert "Storage" in content

    def test_dashboard_contains_disks_section(self, test_client):
        """Dashboard should contain disks section."""
        response = test_client.get("/")
        content = response.text
        assert "Disks" in content
        assert 'id="disks"' in content

    def test_dashboard_contains_services_section(self, test_client):
        """Dashboard should contain services section."""
        response = test_client.get("/")
        content = response.text
        assert "Services" in content
        assert 'id="services"' in content

    def test_dashboard_contains_system_actions(self, test_client):
        """Dashboard should contain system actions section."""
        response = test_client.get("/")
        content = response.text
        assert "System Actions" in content
        assert "Restart All Services" in content

    def test_dashboard_shows_docker_banner_when_dockerized(self, test_client_docker_mode):
        """Dashboard should show Docker mode banner when in Docker."""
        response = test_client_docker_mode.get("/")
        content = response.text
        assert "Running in Docker mode" in content

    def test_dashboard_no_docker_banner_when_not_dockerized(self, test_client):
        """Dashboard should not show Docker mode banner when not in Docker."""
        response = test_client.get("/")
        content = response.text
        assert "Running in Docker mode" not in content

    def test_dashboard_shows_boot_column_when_not_dockerized(self, test_client):
        """Dashboard should show Boot column in services table when not in Docker."""
        response = test_client.get("/")
        content = response.text
        assert "<th>Boot</th>" in content
        # Should have toggle switches
        assert 'class="toggle"' in content

    def test_dashboard_no_boot_column_when_dockerized(self, test_client_docker_mode):
        """Dashboard should not show Boot column in services table when in Docker."""
        response = test_client_docker_mode.get("/")
        content = response.text
        assert "<th>Boot</th>" not in content
        # The table body (rendered server-side) should not have boot toggles
        # Note: JavaScript template literals may contain 'id="boot-' for dynamic updates,
        # but the actual rendered <tbody> should not have boot toggles in Docker mode
        import re
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', content, re.DOTALL)
        if tbody_match:
            tbody_content = tbody_match.group(1)
            assert 'id="boot-' not in tbody_content

    def test_dashboard_has_upgrade_banner_element(self, test_client):
        """Dashboard should have upgrade banner element for upgrade mode."""
        response = test_client.get("/")
        content = response.text
        assert 'id="upgrade-banner"' in content
        assert "Upgrade in Progress" in content
        assert "Do not power off" in content

    def test_dashboard_has_mount_modal(self, test_client):
        """Dashboard should have mount modal for disk mounting."""
        response = test_client.get("/")
        content = response.text
        assert 'id="mount-modal"' in content
        assert 'id="mount-point-input"' in content
        assert 'id="mount-persist-checkbox"' in content
        assert "Persistent (survive reboots)" in content

    def test_dashboard_has_persist_column_in_disks_js(self, test_client):
        """Dashboard JavaScript should include Persist column in disk table."""
        response = test_client.get("/")
        content = response.text
        # The loadDisks() function should create a table with Persist column
        assert "<th>Persist</th>" in content
        # Should have togglePersist function
        assert "function togglePersist" in content
        # Should fetch fstab entries
        assert "api/disks/fstab" in content


class TestOpenAPIEndpoint:
    """Tests for OpenAPI documentation endpoint."""

    def test_openapi_returns_200(self, test_client):
        """OpenAPI endpoint should return 200 OK."""
        response = test_client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_has_title(self, test_client):
        """OpenAPI schema should have correct title."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert data["info"]["title"] == "WROLPi Controller"

    def test_openapi_has_version(self, test_client):
        """OpenAPI schema should have version."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert data["info"]["version"] == __version__

    def test_openapi_has_api_paths(self, test_client):
        """OpenAPI schema should have API paths defined."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/health" in data["paths"]


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

    def test_dashboard_shows_drive_not_mounted_banner(self, reset_runtime_config, mock_docker_mode):
        """Dashboard should show banner when drive is not mounted."""
        from controller.main import app

        with mock.patch(
                "controller.main.is_primary_drive_mounted", return_value=False
        ):
            with TestClient(app) as client:
                response = client.get("/")
                assert "Primary drive not mounted" in response.text
