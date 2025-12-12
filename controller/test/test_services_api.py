"""
Integration tests for Controller services API endpoints.
"""

from unittest import mock

import pytest


class TestServicesListEndpoint:
    """Tests for /api/services endpoint."""

    def test_services_list_returns_200(self, test_client):
        """Services list endpoint should return 200 OK."""
        response = test_client.get("/api/services")
        assert response.status_code == 200

    def test_services_list_returns_list_or_error(self, test_client):
        """Services list should return list of services or error object."""
        response = test_client.get("/api/services")
        data = response.json()
        # Should be a list (when docker can manage) or error dict
        assert isinstance(data, (list, dict))


class TestServicesListDockerMode:
    """Tests for /api/services in Docker mode."""

    def test_returns_containers_when_docker_available(self, test_client_docker_mode):
        """Should return container status when Docker is available."""
        mock_containers = [
            {"name": "api", "status": "running", "container_name": "wrolpi-api-1"}
        ]
        with mock.patch(
                "controller.lib.docker_services.can_manage_containers",
                return_value=True
        ):
            with mock.patch(
                    "controller.lib.docker_services.get_all_containers_status",
                    return_value=mock_containers
            ):
                # Also patch in the main module
                with mock.patch(
                        "controller.main.can_manage_containers",
                        return_value=True
                ):
                    with mock.patch(
                            "controller.main.get_all_containers_status",
                            return_value=mock_containers
                    ):
                        with mock.patch(
                                "controller.api.services.can_manage_containers",
                                return_value=True
                        ):
                            with mock.patch(
                                    "controller.api.services.get_all_containers_status",
                                    return_value=mock_containers
                            ):
                                response = test_client_docker_mode.get("/api/services")
                                assert response.status_code == 200


class TestServiceStatusEndpoint:
    """Tests for /api/services/{name} endpoint."""

    def test_service_status_returns_status(self, test_client):
        """Should return service status."""
        with mock.patch(
                "controller.api.services.get_service_status",
                return_value={
                    "name": "wrolpi-api",
                    "status": "running",
                    "systemd_name": "wrolpi-api.service",
                }
        ):
            response = test_client.get("/api/services/wrolpi-api")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "wrolpi-api"

    def test_unknown_service_returns_404(self, test_client):
        """Should return 404 for unknown service."""
        with mock.patch(
                "controller.api.services.get_service_status",
                return_value={"error": "Unknown service: nonexistent"}
        ):
            response = test_client.get("/api/services/nonexistent")
            assert response.status_code == 404


class TestServiceActionEndpoints:
    """Tests for service action endpoints (start, stop, restart, enable, disable)."""

    @pytest.mark.parametrize("action,endpoint,mock_func", [
        ("start", "/api/services/wrolpi-api/start", "start_service"),
        ("stop", "/api/services/wrolpi-api/stop", "stop_service"),
        ("restart", "/api/services/wrolpi-api/restart", "restart_service"),
        ("enable", "/api/services/wrolpi-api/enable", "enable_service"),
        ("disable", "/api/services/wrolpi-api/disable", "disable_service"),
    ])
    def test_action_success(self, test_client, action, endpoint, mock_func):
        """Should perform service action successfully."""
        with mock.patch(
                f"controller.api.services.{mock_func}",
                return_value={"success": True, "service": "wrolpi-api", "action": action}
        ):
            response = test_client.post(endpoint)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["action"] == action

    def test_start_failure_returns_500(self, test_client):
        """Should return 500 on start failure."""
        with mock.patch(
                "controller.api.services.start_service",
                return_value={"success": False, "error": "Failed to start"}
        ):
            response = test_client.post("/api/services/wrolpi-api/start")
            assert response.status_code == 500

    @pytest.mark.parametrize("endpoint", [
        "/api/services/wrolpi-api/enable",
        "/api/services/wrolpi-api/disable",
    ])
    def test_enable_disable_not_available_in_docker(self, test_client_docker_mode, endpoint):
        """Should return 501 in Docker mode for enable/disable."""
        response = test_client_docker_mode.post(endpoint)
        assert response.status_code == 501


class TestServiceLogsEndpoint:
    """Tests for /api/services/{name}/logs endpoint."""

    def test_logs_returns_200(self, test_client):
        """Should return logs successfully."""
        with mock.patch(
                "controller.api.services.get_service_logs",
                return_value={"service": "wrolpi-api", "lines": 100, "logs": "test logs"}
        ):
            response = test_client.get("/api/services/wrolpi-api/logs")
            assert response.status_code == 200
            data = response.json()
            assert "logs" in data

    def test_logs_accepts_lines_parameter(self, test_client):
        """Should accept lines query parameter."""
        with mock.patch(
                "controller.api.services.get_service_logs",
                return_value={"service": "wrolpi-api", "lines": 50, "logs": "logs"}
        ):
            response = test_client.get("/api/services/wrolpi-api/logs?lines=50")
            assert response.status_code == 200

    def test_logs_accepts_since_parameter(self, test_client):
        """Should accept since query parameter."""
        with mock.patch(
                "controller.api.services.get_service_logs",
                return_value={"service": "wrolpi-api", "lines": 100, "since": "1h", "logs": "logs"}
        ):
            response = test_client.get("/api/services/wrolpi-api/logs?since=1h")
            assert response.status_code == 200


class TestOpenAPIIncludesServicesEndpoints:
    """Tests that OpenAPI documentation includes services endpoints."""

    def test_openapi_has_services_paths(self, test_client):
        """OpenAPI schema should include services paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/services" in data["paths"]
        assert "/api/services/{name}" in data["paths"]
        assert "/api/services/{name}/start" in data["paths"]
        assert "/api/services/{name}/stop" in data["paths"]
        assert "/api/services/{name}/restart" in data["paths"]
        assert "/api/services/{name}/enable" in data["paths"]
        assert "/api/services/{name}/disable" in data["paths"]
        assert "/api/services/{name}/logs" in data["paths"]
