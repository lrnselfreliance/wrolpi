"""
Integration tests for Controller API endpoints.
"""
import pytest
from unittest import mock

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


class TestInfoEndpoint:
    """Tests for /api/info endpoint."""

    def test_info_returns_200(self, test_client):
        """Info endpoint should return 200 OK."""
        response = test_client.get("/api/info")
        assert response.status_code == 200

    def test_info_returns_expected_fields(self, test_client):
        """Info endpoint should return expected fields."""
        response = test_client.get("/api/info")
        data = response.json()
        assert data["version"] == __version__
        assert "docker_mode" in data
        assert "config" in data
        config = data["config"]
        assert config["port"] == 8087
        assert config["media_directory"] == "/media/wrolpi"
        assert config["managed_services_count"] == 8


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
        assert b"WROLPi Controller" in response.content

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

    def test_dashboard_contains_navigation(self, test_client):
        """Dashboard should contain navigation links."""
        response = test_client.get("/")
        content = response.text
        assert 'href="/"' in content
        assert 'href="/services"' in content
        assert 'href="/disks"' in content

    def test_dashboard_contains_quick_links(self, test_client):
        """Dashboard should contain quick links section."""
        response = test_client.get("/")
        content = response.text
        assert "Quick Links" in content
        assert "WROLPi" in content
        assert "API Docs" in content
        assert "Map" in content
        assert "Kiwix" in content
        assert "Help" in content

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


class TestServicesPageEndpoint:
    """Tests for /services page endpoint."""

    def test_services_page_returns_200(self, test_client):
        """Services page should return 200 OK."""
        response = test_client.get("/services")
        assert response.status_code == 200

    def test_services_page_returns_html(self, test_client):
        """Services page should return HTML."""
        response = test_client.get("/services")
        assert "text/html" in response.headers["content-type"]


class TestDisksPageEndpoint:
    """Tests for /disks page endpoint."""

    def test_disks_page_returns_200(self, test_client):
        """Disks page should return 200 OK."""
        response = test_client.get("/disks")
        assert response.status_code == 200

    def test_disks_page_returns_html(self, test_client):
        """Disks page should return HTML."""
        response = test_client.get("/disks")
        assert "text/html" in response.headers["content-type"]


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
        assert "/api/info" in data["paths"]


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
        ("/api/info", True, True),
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
