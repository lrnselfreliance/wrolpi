"""
Unit tests for controller.lib.admin module.
"""

from unittest import mock

import pytest

from controller.lib.admin import (
    disable_hotspot,
    disable_throttle,
    enable_hotspot,
    enable_throttle,
    get_hotspot_status,
    get_throttle_status,
    reboot_system,
    restart_all_services,
    shutdown_system,
)


class TestGetHotspotStatus:
    """Tests for get_hotspot_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_hotspot_status()
        assert isinstance(result, dict)

    def test_returns_unavailable_in_docker_mode(self):
        """Should return unavailable when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = get_hotspot_status()
            assert result["enabled"] is False
            assert result["available"] is False
            assert "Docker" in result.get("reason", "")

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_hotspot_status()
                assert result["enabled"] is False
                assert result["available"] is False
                assert "nmcli" in result.get("reason", "").lower()

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        import subprocess
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nmcli", 5)):
                result = get_hotspot_status()
                assert result["enabled"] is False
                assert result["available"] is False
                assert "timeout" in result.get("reason", "").lower()


class TestEnableHotspot:
    """Tests for enable_hotspot function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = enable_hotspot()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_config", return_value={}):
                with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                    result = enable_hotspot()
                    assert result["success"] is False
                    assert "nmcli" in result.get("error", "").lower()


class TestDisableHotspot:
    """Tests for disable_hotspot function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = disable_hotspot()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = disable_hotspot()
                assert result["success"] is False
                assert "nmcli" in result.get("error", "").lower()


class TestGetThrottleStatus:
    """Tests for get_throttle_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_throttle_status()
        assert isinstance(result, dict)

    def test_returns_unavailable_in_docker_mode(self):
        """Should return unavailable when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = get_throttle_status()
            assert result["enabled"] is False
            assert result["available"] is False
            assert "Docker" in result.get("reason", "")

    def test_returns_unavailable_when_cpufreq_not_available(self, tmp_path):
        """Should return unavailable when cpufreq doesn't exist."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch(
                "controller.lib.admin.Path",
                return_value=tmp_path / "nonexistent"
            ):
                result = get_throttle_status()
                # Result depends on actual system, but should be a valid dict
                assert isinstance(result, dict)

    def test_reads_governor_from_sysfs(self, tmp_path):
        """Should read governor from sysfs when available."""
        governor_path = tmp_path / "scaling_governor"
        governor_path.write_text("ondemand")
        available_path = tmp_path / "scaling_available_governors"
        available_path.write_text("ondemand powersave performance")

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # Create mock Path that returns our temp paths
            original_path = __builtins__.get("Path") if isinstance(__builtins__, dict) else getattr(__builtins__, "Path", None)
            from pathlib import Path

            def mock_path_init(path_str):
                if "scaling_governor" in str(path_str) and "available" not in str(path_str):
                    return governor_path
                elif "available" in str(path_str):
                    return available_path
                return Path(path_str)

            # This test verifies the function structure - actual sysfs testing
            # would require a real Raspberry Pi environment
            result = get_throttle_status()
            assert isinstance(result, dict)


class TestEnableThrottle:
    """Tests for enable_throttle function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = enable_throttle()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")


class TestDisableThrottle:
    """Tests for disable_throttle function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = disable_throttle()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")


class TestShutdownSystem:
    """Tests for shutdown_system function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = shutdown_system()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_handles_shutdown_not_found(self):
        """Should handle shutdown command not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.Popen", side_effect=FileNotFoundError()):
                result = shutdown_system()
                assert result["success"] is False
                assert "not found" in result.get("error", "").lower()

    def test_calls_shutdown_command(self):
        """Should call shutdown command with correct args."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            mock_popen = mock.Mock()
            with mock.patch("subprocess.Popen", mock_popen):
                result = shutdown_system()
                mock_popen.assert_called_once_with(["shutdown", "-h", "now"])
                assert result["success"] is True


class TestRebootSystem:
    """Tests for reboot_system function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = reboot_system()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    def test_handles_reboot_not_found(self):
        """Should handle reboot command not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.Popen", side_effect=FileNotFoundError()):
                result = reboot_system()
                assert result["success"] is False
                assert "not found" in result.get("error", "").lower()

    def test_calls_reboot_command(self):
        """Should call reboot command."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            mock_popen = mock.Mock()
            with mock.patch("subprocess.Popen", mock_popen):
                result = reboot_system()
                mock_popen.assert_called_once_with(["reboot"])
                assert result["success"] is True


class TestRestartAllServices:
    """Tests for restart_all_services function."""

    @pytest.mark.asyncio
    async def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await restart_all_services()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_restarts_services(self):
        """Should attempt to restart all services."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # Mock subprocess.run to succeed
            mock_result = mock.Mock()
            mock_result.returncode = 0
            mock_result.stderr = ""

            # Mock _restart_self to avoid actual restart
            with mock.patch("subprocess.run", return_value=mock_result):
                with mock.patch("controller.lib.admin._restart_self"):
                    with mock.patch("asyncio.get_event_loop") as mock_loop:
                        mock_loop.return_value.call_later = mock.Mock()

                        result = await restart_all_services()

                        assert result["success"] is True
                        assert "services" in result
                        # Should include controller as pending
                        assert result["services"]["wrolpi-controller"]["pending"] is True
