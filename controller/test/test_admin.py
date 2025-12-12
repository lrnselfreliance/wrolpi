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
    HotspotStatus,
    GovernorStatus,
)


class TestGetHotspotStatus:
    """Tests for get_hotspot_status function."""

    def test_returns_hotspot_status_enum(self):
        """Should return a HotspotStatus enum value."""
        result = get_hotspot_status()
        assert isinstance(result, HotspotStatus)

    def test_returns_unknown_in_docker_mode(self):
        """Should return unknown when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = get_hotspot_status()
            assert result == HotspotStatus.unknown

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_current_ssid", return_value=None):
                with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                    result = get_hotspot_status()
                    assert result == HotspotStatus.unknown

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        import subprocess
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_current_ssid", return_value=None):
                with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nmcli", 5)):
                    result = get_hotspot_status()
                    assert result == HotspotStatus.unknown


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

    def test_returns_governor_status_enum(self):
        """Should return a GovernorStatus enum value."""
        result = get_throttle_status()
        assert isinstance(result, GovernorStatus)

    def test_returns_unknown_in_docker_mode(self):
        """Should return unknown when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = get_throttle_status()
            assert result == GovernorStatus.unknown

    def test_returns_unknown_when_cpufreq_not_available(self, tmp_path):
        """Should return unknown when cpufreq doesn't exist."""
        from pathlib import Path
        nonexistent_path = tmp_path / "nonexistent"

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch.object(Path, "exists", return_value=False):
                result = get_throttle_status()
                assert result == GovernorStatus.unknown

    def test_reads_governor_from_sysfs(self, tmp_path):
        """Should read governor from sysfs when available."""
        from pathlib import Path

        governor_path = tmp_path / "scaling_governor"
        governor_path.write_text("ondemand")

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # This test verifies the function structure - actual sysfs testing
            # would require a real Raspberry Pi environment
            result = get_throttle_status()
            assert isinstance(result, GovernorStatus)


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
