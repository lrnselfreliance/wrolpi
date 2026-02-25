"""
Unit tests for controller.lib.scripts module.
"""

import subprocess
from unittest import mock

from controller.lib.scripts import (
    AVAILABLE_SCRIPTS,
    get_script_output,
    get_script_status,
    list_available_scripts,
    start_script,
)


class TestAvailableScripts:
    """Tests for AVAILABLE_SCRIPTS constant."""

    def test_repair_script_exists(self):
        """Should have a repair script defined."""
        assert "repair" in AVAILABLE_SCRIPTS

    def test_repair_script_has_required_fields(self):
        """Repair script should have all required fields."""
        repair = AVAILABLE_SCRIPTS["repair"]
        assert "name" in repair
        assert "display_name" in repair
        assert "description" in repair
        assert "service_name" in repair
        assert "warnings" in repair

    def test_repair_script_has_warnings(self):
        """Repair script should have warnings about its effects."""
        repair = AVAILABLE_SCRIPTS["repair"]
        assert len(repair["warnings"]) > 0


class TestListAvailableScripts:
    """Tests for list_available_scripts function."""

    def test_returns_list(self):
        """Should return a list."""
        result = list_available_scripts()
        assert isinstance(result, list)

    def test_returns_scripts_with_required_fields(self):
        """Each script should have required fields."""
        result = list_available_scripts()
        for script in result:
            assert "name" in script
            assert "display_name" in script
            assert "description" in script
            assert "warnings" in script
            assert "available" in script

    def test_scripts_unavailable_in_docker_mode(self):
        """Scripts should be marked unavailable in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = list_available_scripts()
            for script in result:
                assert script["available"] is False

    def test_scripts_available_when_not_docker(self):
        """Scripts should be available when not in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = list_available_scripts()
            for script in result:
                assert script["available"] is True


class TestGetScriptStatus:
    """Tests for get_script_status function."""

    def test_returns_dict(self):
        """Should return a dict."""
        result = get_script_status()
        assert isinstance(result, dict)

    def test_has_running_field(self):
        """Should always have running field."""
        result = get_script_status()
        assert "running" in result

    def test_returns_not_running_in_docker_mode(self):
        """Should return not running in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = get_script_status()
            assert result["running"] is False

    def test_handles_systemctl_not_found(self):
        """Should handle systemctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_script_status()
                assert result["running"] is False

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 5)):
                result = get_script_status()
                assert result["running"] is False

    def test_returns_running_when_service_activating(self):
        """Should return running when service is activating."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "activating\n"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result):
                with mock.patch("controller.lib.scripts._get_service_timing", return_value=(None, None)):
                    result = get_script_status()
                    assert result["running"] is True
                    assert result["script_name"] == "repair"

    def test_returns_not_running_when_service_inactive(self):
        """Should return not running when service is inactive."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "inactive\n"
            mock_result.returncode = 3
            with mock.patch("subprocess.run", return_value=mock_result):
                result = get_script_status()
                assert result["running"] is False


class TestStartScript:
    """Tests for start_script function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = start_script("repair")
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_returns_error_for_unknown_script(self):
        """Should return error for unknown script."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = start_script("nonexistent")
            assert result["success"] is False
            assert "Unknown" in result.get("error", "")

    def test_returns_error_if_already_running(self):
        """Should return error if script is already running."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={
                "running": True,
                "script_name": "repair",
            }):
                result = start_script("repair")
                assert result["success"] is False
                assert "already running" in result.get("error", "").lower()

    def test_returns_error_if_another_script_running(self):
        """Should return error if another script is running."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={
                "running": True,
                "script_name": "other",
            }):
                result = start_script("repair")
                assert result["success"] is False
                assert "another script" in result.get("error", "").lower()

    def test_handles_systemctl_not_found(self):
        """Should handle systemctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={"running": False}):
                with mock.patch("subprocess.Popen", side_effect=FileNotFoundError()):
                    result = start_script("repair")
                    assert result["success"] is False
                    assert "not found" in result.get("error", "").lower()

    def test_starts_service_successfully(self):
        """Should start service successfully."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.scripts.get_script_status", return_value={"running": False}):
                mock_popen = mock.Mock()
                with mock.patch("subprocess.Popen", return_value=mock_popen) as mock_p:
                    result = start_script("repair")
                    assert result["success"] is True
                    assert "started" in result.get("message", "").lower()
                    # Verify correct command was called
                    mock_p.assert_called_once()
                    call_args = mock_p.call_args[0][0]
                    assert "systemctl" in call_args
                    assert "start" in call_args
                    assert "wrolpi-repair.service" in call_args


class TestGetScriptOutput:
    """Tests for get_script_output function."""

    def test_returns_docker_message_in_docker_mode(self):
        """Should return Docker not available message in Docker mode."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=True):
            result = get_script_output("repair")
            assert "Docker" in result.get("output", "")

    def test_returns_error_for_unknown_script(self):
        """Should return error for unknown script."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            result = get_script_output("nonexistent")
            assert "Unknown" in result.get("output", "")

    def test_handles_journalctl_not_found(self):
        """Should handle journalctl not being available."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_script_output("repair")
                assert "not found" in result.get("output", "").lower()

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("journalctl", 10)):
                result = get_script_output("repair")
                assert "Timeout" in result.get("output", "")

    def test_returns_log_output(self):
        """Should return log output from journalctl."""
        with mock.patch("controller.lib.scripts.is_docker_mode", return_value=False):
            mock_result = mock.Mock()
            mock_result.stdout = "Log line 1\nLog line 2\n"
            mock_result.returncode = 0
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                result = get_script_output("repair", lines=50)
                assert "Log line 1" in result.get("output", "")
                assert result["lines"] == 50
                assert result["script_name"] == "repair"
                # Verify correct command
                call_args = mock_run.call_args[0][0]
                assert "journalctl" in call_args
                assert "-u" in call_args
                assert "wrolpi-repair.service" in call_args
                assert "-n" in call_args
                assert "50" in call_args
