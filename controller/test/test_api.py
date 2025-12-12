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


class TestRootEndpoint:
    """Tests for / root endpoint."""

    def test_root_returns_200(self, test_client):
        """Root endpoint should return 200 OK."""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_root_returns_expected_fields(self, test_client):
        """Root endpoint should return expected fields."""
        response = test_client.get("/")
        data = response.json()
        assert data["message"] == "WROLPi Controller"
        assert data["version"] == __version__
        assert "endpoints" in data
        assert data["endpoints"]["health"] == "/api/health"
        assert data["endpoints"]["info"] == "/api/info"


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

    def test_openapi_has_paths(self, test_client):
        """OpenAPI schema should have paths defined."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/health" in data["paths"]
        assert "/api/info" in data["paths"]
        assert "/" in data["paths"]


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
