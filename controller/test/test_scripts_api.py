"""
Integration tests for Controller scripts API endpoints.
"""

from unittest import mock


class TestScriptsListEndpoint:
    """Tests for /api/scripts endpoint."""

    def test_scripts_list_returns_200(self, test_client):
        """Scripts list endpoint should return 200 OK."""
        response = test_client.get("/api/scripts")
        assert response.status_code == 200

    def test_scripts_list_returns_list(self, test_client):
        """Scripts list should return a list."""
        response = test_client.get("/api/scripts")
        data = response.json()
        assert isinstance(data, list)

    def test_scripts_list_includes_repair(self, test_client):
        """Scripts list should include repair script."""
        response = test_client.get("/api/scripts")
        data = response.json()
        names = [s["name"] for s in data]
        assert "repair" in names

    def test_scripts_list_has_required_fields(self, test_client):
        """Each script should have required fields."""
        response = test_client.get("/api/scripts")
        data = response.json()
        for script in data:
            assert "name" in script
            assert "display_name" in script
            assert "description" in script
            assert "warnings" in script
            assert "available" in script

    def test_scripts_unavailable_in_docker_mode(self, test_client_docker_mode):
        """Scripts should be marked unavailable in Docker mode."""
        response = test_client_docker_mode.get("/api/scripts")
        data = response.json()
        for script in data:
            assert script["available"] is False


class TestScriptsStatusEndpoint:
    """Tests for /api/scripts/status endpoint."""

    def test_scripts_status_returns_200(self, test_client):
        """Scripts status endpoint should return 200 OK."""
        response = test_client.get("/api/scripts/status")
        assert response.status_code == 200

    def test_scripts_status_has_running_field(self, test_client):
        """Scripts status should have running field."""
        response = test_client.get("/api/scripts/status")
        data = response.json()
        assert "running" in data

    def test_scripts_status_not_running_in_docker(self, test_client_docker_mode):
        """Scripts should not be running in Docker mode."""
        response = test_client_docker_mode.get("/api/scripts/status")
        data = response.json()
        assert data["running"] is False


class TestScriptsStartEndpoint:
    """Tests for /api/scripts/{name}/start endpoint."""

    def test_scripts_start_returns_501_in_docker(self, test_client_docker_mode):
        """Scripts start should return 501 in Docker mode."""
        response = test_client_docker_mode.post("/api/scripts/repair/start")
        assert response.status_code == 501
        assert "Docker" in response.json()["detail"]

    def test_scripts_start_returns_400_for_unknown_script(self, test_client):
        """Scripts start should return 400 for unknown script."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            response = test_client.post("/api/scripts/nonexistent/start")
            assert response.status_code == 400

    def test_scripts_start_returns_400_if_already_running(self, test_client):
        """Scripts start should return 400 if script already running."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={
                "running": True,
                "script_name": "repair",
            }):
                response = test_client.post("/api/scripts/repair/start")
                assert response.status_code == 400
                assert "already running" in response.json()["detail"].lower()


class TestScriptsOutputEndpoint:
    """Tests for /api/scripts/{name}/output endpoint."""

    def test_scripts_output_returns_501_in_docker(self, test_client_docker_mode):
        """Scripts output should return 501 in Docker mode."""
        response = test_client_docker_mode.get("/api/scripts/repair/output")
        assert response.status_code == 501
        assert "Docker" in response.json()["detail"]

    def test_scripts_output_returns_200(self, test_client):
        """Scripts output should return 200 when not in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log output"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result):
                response = test_client.get("/api/scripts/repair/output")
                assert response.status_code == 200

    def test_scripts_output_has_expected_fields(self, test_client):
        """Scripts output should have expected fields."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log output"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result):
                response = test_client.get("/api/scripts/repair/output")
                data = response.json()
                assert "output" in data
                assert "lines" in data
                assert "script_name" in data

    def test_scripts_output_respects_lines_param(self, test_client):
        """Scripts output should respect lines parameter."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log output"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                response = test_client.get("/api/scripts/repair/output?lines=500")
                assert response.status_code == 200
                # Verify journalctl was called with -n 500
                call_args = mock_run.call_args[0][0]
                assert "500" in call_args

    def test_scripts_output_limits_lines(self, test_client):
        """Scripts output should limit lines to 5000."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log output"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                response = test_client.get("/api/scripts/repair/output?lines=10000")
                assert response.status_code == 200
                # Verify journalctl was called with -n 5000 (max)
                call_args = mock_run.call_args[0][0]
                assert "5000" in call_args


class TestOpenAPIIncludesScriptsEndpoints:
    """Tests that OpenAPI documentation includes scripts endpoints."""

    def test_openapi_has_scripts_paths(self, test_client):
        """OpenAPI schema should include scripts paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/scripts" in data["paths"]
        assert "/api/scripts/status" in data["paths"]
        assert "/api/scripts/{name}/start" in data["paths"]
        assert "/api/scripts/{name}/output" in data["paths"]
