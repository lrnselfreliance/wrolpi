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
    discover_running_wrolpi_services,
    get_discovered_service_status,
    _get_systemd_name,
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
        with mock.patch("controller.lib.systemd.discover_running_wrolpi_services", return_value=[]):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
                result = get_all_services_status()
                assert isinstance(result, list)

    def test_returns_status_for_each_visible_service(self):
        """Should return status for each visible managed service."""
        with mock.patch("controller.lib.systemd.discover_running_wrolpi_services", return_value=[]):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
                result = get_all_services_status()
                managed = get_managed_services()
                # All services should be returned when they're all "running" (active)
                assert len(result) == len(managed)

    def test_filters_show_only_when_running_services_when_stopped(self):
        """Should exclude show_only_when_running services when they're not running."""
        with mock.patch("controller.lib.systemd.discover_running_wrolpi_services", return_value=[]):
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
        with mock.patch("controller.lib.systemd.discover_running_wrolpi_services", return_value=[]):
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


class TestControllerSelfRestart:
    """Tests for controller self-restart behavior."""

    def test_controller_restart_uses_popen(self):
        """Controller restart should use Popen to avoid blocking on self-termination."""
        with mock.patch("subprocess.Popen") as mock_popen:
            result = restart_service("wrolpi-controller")
            mock_popen.assert_called_once_with(["systemctl", "restart", "wrolpi-controller"])
            assert result["success"] is True
            assert result["pending"] is True
            assert result["action"] == "restart"

    def test_controller_restart_handles_exception(self):
        """Controller restart should handle exceptions gracefully."""
        with mock.patch("subprocess.Popen", side_effect=Exception("popen failed")):
            result = restart_service("wrolpi-controller")
            assert result["success"] is False
            assert "popen failed" in result["error"]


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


class TestDiscoverRunningWrolpiServices:
    """Tests for discover_running_wrolpi_services function."""

    def test_discovers_unknown_services(self):
        """Should discover wrolpi-* services not in managed config."""
        systemctl_output = (
            "wrolpi-api.service                        loaded active running WROLPi API\n"
            "wrolpi-fix-media-permissions.service       loaded active running Fix permissions\n"
            "wrolpi-repair.service                      loaded active running WROLPi Repair\n"
        )
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=systemctl_output, stderr="")
            result = discover_running_wrolpi_services()
            # wrolpi-api is managed, so only the other two should be discovered
            assert "wrolpi-api" not in result
            assert "wrolpi-fix-media-permissions" in result
            assert "wrolpi-repair" in result

    def test_returns_empty_on_failure(self):
        """Should return empty list when systemctl fails."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="error")
            result = discover_running_wrolpi_services()
            assert result == []

    def test_returns_empty_on_no_systemctl(self):
        """Should return empty list when systemctl is not found."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            result = discover_running_wrolpi_services()
            assert result == []

    def test_returns_empty_when_no_extra_services(self):
        """Should return empty list when all wrolpi-* services are managed."""
        systemctl_output = "wrolpi-api.service loaded active running WROLPi API\n"
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=systemctl_output, stderr="")
            result = discover_running_wrolpi_services()
            assert result == []


class TestGetDiscoveredServiceStatus:
    """Tests for get_discovered_service_status function."""

    def test_returns_running_status(self):
        """Should return status for a discovered service."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_discovered_service_status("wrolpi-fix-media-permissions")
            assert result["name"] == "wrolpi-fix-media-permissions"
            assert result["status"] == "running"
            assert result["port"] is None
            assert result["viewable"] is False

    def test_handles_no_systemctl(self):
        """Should handle missing systemctl."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            result = get_discovered_service_status("wrolpi-fix-media-permissions")
            assert result["status"] == "unknown"
            assert "error" in result


class TestGetSystemdName:
    """Tests for _get_systemd_name helper."""

    def test_returns_systemd_name_for_managed_service(self):
        """Should return systemd_name from config for managed services."""
        result = _get_systemd_name("wrolpi-api")
        assert result == "wrolpi-api"

    def test_returns_name_for_discovered_wrolpi_service(self):
        """Should return the name itself for discovered wrolpi-* services."""
        result = _get_systemd_name("wrolpi-fix-media-permissions")
        assert result == "wrolpi-fix-media-permissions"

    def test_returns_none_for_unknown_non_wrolpi_service(self):
        """Should return None for unknown non-wrolpi services."""
        result = _get_systemd_name("some-random-service")
        assert result is None


class TestGetAllServicesStatusWithDiscovery:
    """Tests for get_all_services_status including dynamic discovery."""

    def test_includes_discovered_running_services(self):
        """Should include dynamically discovered running wrolpi-* services."""
        systemctl_list_output = (
            "wrolpi-fix-media-permissions.service loaded active running Fix permissions\n"
        )

        def mock_run_side_effect(cmd, **kwargs):
            if cmd[0] == "systemctl" and cmd[1] == "list-units":
                return mock.Mock(returncode=0, stdout=systemctl_list_output, stderr="")
            # For is-active / is-enabled calls
            return mock.Mock(returncode=0, stdout="active", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run_side_effect):
            result = get_all_services_status()
            service_names = [s["name"] for s in result]
            assert "wrolpi-fix-media-permissions" in service_names

    def test_does_not_duplicate_managed_services(self):
        """Discovered services should not duplicate managed services."""
        systemctl_list_output = (
            "wrolpi-api.service loaded active running WROLPi API\n"
        )

        def mock_run_side_effect(cmd, **kwargs):
            if cmd[0] == "systemctl" and cmd[1] == "list-units":
                return mock.Mock(returncode=0, stdout=systemctl_list_output, stderr="")
            return mock.Mock(returncode=0, stdout="active", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run_side_effect):
            result = get_all_services_status()
            api_count = sum(1 for s in result if s["name"] == "wrolpi-api")
            assert api_count == 1


class TestActionsOnDiscoveredServices:
    """Tests that service actions work on discovered wrolpi-* services."""

    @pytest.mark.parametrize("func,expected_action", [
        (start_service, "start"),
        (stop_service, "stop"),
        (restart_service, "restart"),
        (enable_service, "enable"),
        (disable_service, "disable"),
    ])
    def test_actions_work_on_discovered_services(self, func, expected_action):
        """Should allow actions on discovered wrolpi-* services."""
        with mock.patch("controller.lib.systemd._run_systemctl") as mock_ctl:
            mock_ctl.return_value = {"success": True, "output": "", "error": None}
            result = func("wrolpi-fix-media-permissions")
            assert result["success"] is True
            assert result["action"] == expected_action

    def test_logs_work_on_discovered_services(self):
        """Should return logs for discovered wrolpi-* services."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="log output", stderr="")
            result = get_service_logs("wrolpi-fix-media-permissions", lines=10)
            assert result["service"] == "wrolpi-fix-media-permissions"
            assert "logs" in result

    def test_get_service_status_for_discovered_service(self):
        """get_service_status should work for discovered wrolpi-* services."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="active", stderr="")
            result = get_service_status("wrolpi-fix-media-permissions")
            assert result["name"] == "wrolpi-fix-media-permissions"
            assert result["status"] == "running"
