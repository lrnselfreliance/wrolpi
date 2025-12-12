"""
Unit tests for controller.lib.systemd module.
"""

from unittest import mock

import pytest

from controller.lib.systemd import (
    get_managed_services,
    get_service_config,
    get_service_status,
    get_all_services_status,
    start_service,
    stop_service,
    restart_service,
    enable_service,
    disable_service,
    get_service_logs,
    _run_systemctl,
)


class TestGetManagedServices:
    """Tests for get_managed_services function."""

    def test_returns_list(self):
        """Should return a list."""
        result = get_managed_services()
        assert isinstance(result, list)

    def test_returns_services_from_config(self):
        """Should return services from config."""
        result = get_managed_services()
        # Default config has managed_services
        assert len(result) > 0

    def test_each_service_has_name(self):
        """Each service should have a name."""
        result = get_managed_services()
        for service in result:
            assert "name" in service


class TestGetServiceConfig:
    """Tests for get_service_config function."""

    def test_returns_config_for_known_service(self):
        """Should return config for a known service."""
        # wrolpi-api is in default config
        result = get_service_config("wrolpi-api")
        assert result is not None
        assert result["name"] == "wrolpi-api"

    def test_returns_none_for_unknown_service(self):
        """Should return None for unknown service."""
        result = get_service_config("nonexistent-service")
        assert result is None


class TestRunSystemctl:
    """Tests for _run_systemctl function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = _run_systemctl("is-active", "test.service")
            assert isinstance(result, dict)

    def test_success_on_zero_returncode(self):
        """Should return success=True when returncode is 0."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="done", stderr="")
            result = _run_systemctl("start", "test.service")
            assert result["success"] is True

    def test_failure_on_nonzero_returncode(self):
        """Should return success=False when returncode is non-zero."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="failed")
            result = _run_systemctl("start", "test.service")
            assert result["success"] is False
            assert result["error"] == "failed"

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        import subprocess
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 30)):
            result = _run_systemctl("start", "test.service")
            assert result["success"] is False
            assert "timed out" in result["error"].lower()

    def test_handles_file_not_found(self):
        """Should handle systemctl not found."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            result = _run_systemctl("start", "test.service")
            assert result["success"] is False
            assert "not found" in result["error"].lower()


class TestGetServiceStatus:
    """Tests for get_service_status function."""

    def test_returns_error_for_unknown_service(self):
        """Should return error for unknown service."""
        result = get_service_status("nonexistent-service")
        assert "error" in result

    def test_returns_status_dict(self):
        """Should return a status dictionary."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_service_status("wrolpi-api")
            assert "name" in result
            assert "status" in result

    @pytest.mark.parametrize("systemd_state,expected_status", [
        ("active", "running"),
        ("activating", "running"),  # oneshot services during execution
        ("inactive", "stopped"),
        ("failed", "failed"),
    ])
    def test_maps_systemd_state_to_status(self, systemd_state, expected_status):
        """Should map systemd states to simple status values."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=systemd_state, stderr="")
            result = get_service_status("wrolpi-api")
            assert result["status"] == expected_status

    @pytest.mark.parametrize("service_name,expected_https", [
        ("wrolpi-help", True),
        ("wrolpi-kiwix", True),
        ("apache2", True),
        ("wrolpi-api", False),
    ])
    def test_returns_use_https_field(self, service_name, expected_https):
        """Should return use_https field from service config."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_service_status(service_name)
            assert result.get("use_https", False) == expected_https


class TestGetAllServicesStatus:
    """Tests for get_all_services_status function."""

    def test_returns_list(self):
        """Should return a list."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_all_services_status()
            assert isinstance(result, list)

    def test_returns_status_for_each_visible_service(self):
        """Should return status for each visible managed service."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_all_services_status()
            managed = get_managed_services()
            # All services should be returned when they're all "running" (active)
            assert len(result) == len(managed)

    def test_filters_show_only_when_running_services_when_stopped(self):
        """Should exclude show_only_when_running services when they're not running."""
        with mock.patch("subprocess.run") as mock_run:
            # Simulate all services as "inactive" (stopped)
            mock_run.return_value = mock.Mock(returncode=0, stdout="inactive", stderr="")
            result = get_all_services_status()
            managed = get_managed_services()
            # Count services without show_only_when_running flag
            always_visible = [s for s in managed if not s.get("show_only_when_running")]
            assert len(result) == len(always_visible)

    def test_includes_show_only_when_running_services_when_running(self):
        """Should include show_only_when_running services when they're running."""
        with mock.patch("subprocess.run") as mock_run:
            # Simulate all services as "active" (running)
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_all_services_status()
            managed = get_managed_services()
            # All services should be visible when running
            assert len(result) == len(managed)
            # Verify wrolpi-upgrade is in the result
            service_names = [s["name"] for s in result]
            assert "wrolpi-upgrade" in service_names


class TestServiceActions:
    """Tests for service action functions (start, stop, restart, enable, disable)."""

    @pytest.mark.parametrize("func", [
        start_service,
        stop_service,
        restart_service,
        enable_service,
        disable_service,
    ])
    def test_returns_error_for_unknown_service(self, func):
        """Should return error for unknown service."""
        result = func("nonexistent-service")
        assert result["success"] is False

    @pytest.mark.parametrize("func,expected_action", [
        (start_service, "start"),
        (stop_service, "stop"),
        (restart_service, "restart"),
        (enable_service, "enable"),
        (disable_service, "disable"),
    ])
    def test_calls_correct_systemctl_action(self, func, expected_action):
        """Should call systemctl with correct action."""
        with mock.patch("controller.lib.systemd._run_systemctl") as mock_ctl:
            mock_ctl.return_value = {"success": True, "output": "", "error": None}
            result = func("wrolpi-api")
            mock_ctl.assert_called_once()
            assert mock_ctl.call_args[0][0] == expected_action
            assert result["success"] is True
            assert result["action"] == expected_action


class TestGetServiceLogs:
    """Tests for get_service_logs function."""

    def test_returns_error_for_unknown_service(self):
        """Should return error for unknown service."""
        result = get_service_logs("nonexistent-service")
        assert "error" in result

    def test_returns_logs(self):
        """Should return logs."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="log line 1\nlog line 2", stderr="")
            result = get_service_logs("wrolpi-api", lines=10)
            assert "logs" in result
            assert result["service"] == "wrolpi-api"
            assert result["lines"] == 10

    def test_handles_since_parameter(self):
        """Should include since parameter in journalctl command."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="logs", stderr="")
            result = get_service_logs("wrolpi-api", lines=50, since="1h")
            assert result["since"] == "1h"
            # Verify journalctl was called with --since
            call_args = mock_run.call_args[0][0]
            assert "--since" in call_args
            assert "1h" in call_args
