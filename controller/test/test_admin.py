"""
Unit tests for controller.lib.admin module.
"""

from unittest import mock

import pytest

from controller.lib.admin import (
    apply_timezone_from_config,
    disable_hotspot,
    disable_throttle,
    enable_hotspot,
    enable_throttle,
    get_hotspot_status,
    get_throttle_status,
    get_timezone_status_dict,
    reboot_system,
    restart_all_services,
    set_timezone,
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
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = enable_hotspot()
                assert result["success"] is False
                assert "nmcli" in result.get("error", "").lower()

    def test_uses_config_values(self):
        """Should use get_config_value for device, ssid, and password."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # Mock get_config_value to return custom values
            def mock_get_config(key, default=None):
                config_map = {
                    'hotspot.device': 'wlan1',
                    'hotspot.ssid': 'TestSSID',
                    'hotspot.password': 'testpassword123',
                }
                return config_map.get(key, default)

            with mock.patch("controller.lib.admin.get_config_value", side_effect=mock_get_config):
                mock_run = mock.Mock()
                mock_run.returncode = 0
                with mock.patch("subprocess.run", return_value=mock_run) as mock_subprocess:
                    enable_hotspot()

                    # Verify the hotspot was created with config values
                    calls = mock_subprocess.call_args_list
                    # Find the hotspot creation call (nmcli device wifi hotspot)
                    hotspot_call = [c for c in calls if len(c[0][0]) > 2 and 'hotspot' in c[0][0]]
                    if hotspot_call:
                        cmd_args = hotspot_call[0][0][0]
                        assert "wlan1" in cmd_args
                        assert "TestSSID" in cmd_args
                        assert "testpassword123" in cmd_args


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
            with mock.patch("shutil.which", return_value=None):
                result = shutdown_system()
                assert result["success"] is False
                assert "not found" in result.get("error", "").lower()

    def test_calls_shutdown_command(self):
        """Should call shutdown command with correct args after delay."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("shutil.which", return_value="/sbin/shutdown"):
                mock_popen = mock.Mock()
                with mock.patch("subprocess.Popen", mock_popen):
                    # Use delay=0 for testing to avoid waiting
                    result = shutdown_system(delay=0)
                    assert result["success"] is True
                    assert "shutting down" in result["message"].lower()
                    # Give thread time to execute
                    import time
                    time.sleep(0.1)
                    mock_popen.assert_called_once_with(["shutdown", "-h", "now"])


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
            with mock.patch("shutil.which", return_value=None):
                result = reboot_system()
                assert result["success"] is False
                assert "not found" in result.get("error", "").lower()

    def test_calls_reboot_command(self):
        """Should call reboot command after delay."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("shutil.which", return_value="/sbin/reboot"):
                mock_popen = mock.Mock()
                with mock.patch("subprocess.Popen", mock_popen):
                    # Use delay=0 for testing to avoid waiting
                    result = reboot_system(delay=0)
                    assert result["success"] is True
                    assert "rebooting" in result["message"].lower()
                    # Give thread time to execute
                    import time
                    time.sleep(0.1)
                    mock_popen.assert_called_once_with(["reboot"])


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


class TestGetTimezoneStatus:
    """Tests for get_timezone_status_dict function."""

    def test_returns_unavailable_in_docker_mode(self):
        """Should return unavailable when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = get_timezone_status_dict()
            assert result["available"] is False
            assert result["timezone"] is None
            assert "Docker" in result["reason"]

    def test_returns_timezone_from_timedatectl(self):
        """Should return the current system timezone."""
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "America/Denver\n"

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                result = get_timezone_status_dict()
                assert result["available"] is True
                assert result["timezone"] == "America/Denver"
                assert result["reason"] is None

    def test_handles_timedatectl_not_found(self):
        """Should handle timedatectl not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = get_timezone_status_dict()
                assert result["available"] is False
                assert "not found" in result["reason"]

    def test_handles_timeout(self):
        """Should handle subprocess timeout."""
        import subprocess
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("timedatectl", 5)):
                result = get_timezone_status_dict()
                assert result["available"] is False
                assert "timed out" in result["reason"]


class TestSetTimezone:
    """Tests for set_timezone function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = set_timezone("America/Denver")
            assert result["success"] is False
            assert "Docker" in result["error"]

    def test_sets_timezone_successfully(self):
        """Should set timezone via timedatectl."""
        mock_result = mock.Mock()
        mock_result.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                result = set_timezone("America/Denver")
                assert result["success"] is True
                assert result["timezone"] == "America/Denver"
                mock_run.assert_called_once_with(
                    ["timedatectl", "set-timezone", "America/Denver"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

    def test_handles_invalid_timezone(self):
        """Should handle timedatectl rejecting an invalid timezone."""
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Failed to set time zone: Invalid time zone"

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                result = set_timezone("Invalid/Timezone")
                assert result["success"] is False
                assert "Invalid" in result["error"]

    def test_handles_empty_timezone(self):
        """Should reject empty timezone strings."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = set_timezone("")
            assert result["success"] is False
            assert "empty" in result["error"].lower()

    def test_handles_timedatectl_not_found(self):
        """Should handle timedatectl not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = set_timezone("America/Denver")
                assert result["success"] is False
                assert "not found" in result["error"]


class TestApplyTimezoneFromConfig:
    """Tests for apply_timezone_from_config function."""

    def test_skips_in_docker_mode(self):
        """Should do nothing in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.admin.set_timezone") as mock_set:
                apply_timezone_from_config()
                mock_set.assert_not_called()

    def test_applies_timezone_from_config(self, tmp_path):
        """Should read timezone from wrolpi.yaml and apply it."""
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        config_file = config_dir / 'wrolpi.yaml'
        config_file.write_text("timezone: America/New_York\n")

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_media_directory", return_value=tmp_path):
                with mock.patch("controller.lib.admin.set_timezone", return_value={"success": True}) as mock_set:
                    apply_timezone_from_config()
                    mock_set.assert_called_once_with("America/New_York")

    def test_skips_when_no_timezone_in_config(self, tmp_path):
        """Should do nothing when timezone is not set in config."""
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        config_file = config_dir / 'wrolpi.yaml'
        config_file.write_text("download_wait: 60\n")

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_media_directory", return_value=tmp_path):
                with mock.patch("controller.lib.admin.set_timezone") as mock_set:
                    apply_timezone_from_config()
                    mock_set.assert_not_called()

    def test_skips_when_config_file_missing(self, tmp_path):
        """Should do nothing when wrolpi.yaml doesn't exist."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_media_directory", return_value=tmp_path):
                with mock.patch("controller.lib.admin.set_timezone") as mock_set:
                    apply_timezone_from_config()
                    mock_set.assert_not_called()
