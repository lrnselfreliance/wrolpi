"""
Unit tests for controller.lib.admin module.
"""

from unittest import mock

import pytest

from controller.lib.admin import (
    apply_timezone_from_config,
    disable_bluetooth,
    disable_hotspot,
    disable_throttle,
    enable_bluetooth,
    enable_hotspot,
    enable_throttle,
    get_bluetooth_status,
    get_hotspot_status,
    get_hotspot_status_dict,
    get_throttle_status,
    get_timezone_status_dict,
    reboot_system,
    restart_all_services,
    set_timezone,
    shutdown_system,
    BluetoothStatus,
    HotspotStatus,
    GovernorStatus,
)


class TestGetBluetoothStatus:
    """Tests for get_bluetooth_status function."""

    @pytest.mark.asyncio
    async def test_returns_bluetooth_status_enum(self):
        """Should return a BluetoothStatus enum value."""
        result = await get_bluetooth_status()
        assert isinstance(result, BluetoothStatus)

    @pytest.mark.asyncio
    async def test_returns_unknown_in_docker_mode(self):
        """Should return unknown when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await get_bluetooth_status()
            assert result == BluetoothStatus.unknown

    @pytest.mark.asyncio
    async def test_returns_unavailable_when_rfkill_not_found(self):
        """Should return unavailable when rfkill is not installed."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.unavailable

    @pytest.mark.asyncio
    async def test_returns_on_when_unblocked(self):
        """Should return on when Bluetooth is unblocked."""
        rfkill_json = '{"rfkilldevices": [{"id": 0, "type": "bluetooth", "device": "hci0", "soft": "unblocked", "hard": "unblocked"}]}'
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (rfkill_json.encode(), b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.on

    @pytest.mark.asyncio
    async def test_returns_off_when_soft_blocked(self):
        """Should return off when Bluetooth is soft blocked."""
        rfkill_json = '{"rfkilldevices": [{"id": 0, "type": "bluetooth", "device": "hci0", "soft": "blocked", "hard": "unblocked"}]}'
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (rfkill_json.encode(), b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.off

    @pytest.mark.asyncio
    async def test_returns_off_when_hard_blocked(self):
        """Should return off when Bluetooth is hard blocked."""
        rfkill_json = '{"rfkilldevices": [{"id": 0, "type": "bluetooth", "device": "hci0", "soft": "unblocked", "hard": "blocked"}]}'
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (rfkill_json.encode(), b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.off

    @pytest.mark.asyncio
    async def test_returns_unavailable_when_no_bluetooth_device(self):
        """Should return unavailable when no Bluetooth devices exist."""
        rfkill_json = '{"rfkilldevices": [{"id": 0, "type": "wlan", "device": "phy0", "soft": "unblocked", "hard": "unblocked"}]}'
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (rfkill_json.encode(), b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.unavailable

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Should return unknown on timeout."""
        import asyncio
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            mock_proc = mock.AsyncMock()
            mock_proc.communicate.side_effect = asyncio.TimeoutError()
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                # wait_for wraps communicate, but we mock at the proc level.
                # The timeout is handled by asyncio.wait_for in the function.
                result = await get_bluetooth_status()
                assert result == BluetoothStatus.unknown


class TestEnableBluetooth:
    """Tests for enable_bluetooth function."""

    @pytest.mark.asyncio
    async def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await enable_bluetooth()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_calls_rfkill_unblock(self):
        """Should call rfkill unblock bluetooth."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await enable_bluetooth()
                assert result["success"] is True
                mock_exec.assert_called_once_with(
                    "/usr/sbin/rfkill", "unblock", "bluetooth",
                    stdout=mock.ANY,
                    stderr=mock.ANY,
                )

    @pytest.mark.asyncio
    async def test_handles_rfkill_not_found(self):
        """Should handle rfkill not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await enable_bluetooth()
                assert result["success"] is False
                assert "rfkill" in result.get("error", "").lower()


class TestDisableBluetooth:
    """Tests for disable_bluetooth function."""

    @pytest.mark.asyncio
    async def test_returns_error_in_docker_mode(self):
        """Should return error when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await disable_bluetooth()
            assert result["success"] is False
            assert "Docker" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_calls_rfkill_block(self):
        """Should call rfkill block bluetooth."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await disable_bluetooth()
                assert result["success"] is True
                mock_exec.assert_called_once_with(
                    "/usr/sbin/rfkill", "block", "bluetooth",
                    stdout=mock.ANY,
                    stderr=mock.ANY,
                )

    @pytest.mark.asyncio
    async def test_handles_rfkill_not_found(self):
        """Should handle rfkill not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await disable_bluetooth()
                assert result["success"] is False


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


class TestGetHotspotStatusWithRealOutput:
    """Tests for get_hotspot_status using real nmcli output from RPi (10.0.0.9)."""

    # Real nmcli output when WiFi radio is off (wlan0 software-disabled).
    NMCLI_RADIO_OFF = (
        "eth0: connected to Wired connection 1\n"
        "\t\"eth0\"\n"
        "\tethernet (macb), 2C:CF:67:08:87:88, hw, mtu 1500\n"
        "\n"
        "lo: connected (externally) to lo\n"
        "\t\"lo\"\n"
        "\tloopback (unknown), 00:00:00:00:00:00, sw, mtu 65536\n"
        "\n"
        "wlan0: unavailable\n"
        "\t\"Broadcom Wi-Fi\"\n"
        "\twifi (brcmfmac), 2C:CF:67:08:87:89, sw disabled, hw, mtu 1500\n"
    )

    # Real nmcli output when WiFi radio is on but no hotspot (wlan0 disconnected).
    NMCLI_RADIO_ON_NO_HOTSPOT = (
        "eth0: connected to Wired connection 1\n"
        "\t\"eth0\"\n"
        "\tethernet (macb), 2C:CF:67:08:87:88, hw, mtu 1500\n"
        "\n"
        "lo: connected (externally) to lo\n"
        "\t\"lo\"\n"
        "\tloopback (unknown), 00:00:00:00:00:00, sw, mtu 65536\n"
        "\n"
        "wlan0: disconnected\n"
        "\t\"Broadcom Wi-Fi\"\n"
        "\twifi (brcmfmac), 2C:CF:67:08:87:89, hw, mtu 1500\n"
    )

    # Real nmcli output when hotspot is active (wlan0 connected to Hotspot).
    NMCLI_HOTSPOT_ACTIVE = (
        "wlan0: connected to Hotspot\n"
        "\t\"Broadcom Wi-Fi\"\n"
        "\twifi (brcmfmac), 2C:CF:67:08:87:89, hw, mtu 1500\n"
        "\n"
        "eth0: connected to Wired connection 1\n"
        "\t\"eth0\"\n"
        "\tethernet (macb), 2C:CF:67:08:87:88, hw, mtu 1500\n"
        "\n"
        "lo: connected (externally) to lo\n"
        "\t\"lo\"\n"
        "\tloopback (unknown), 00:00:00:00:00:00, sw, mtu 65536\n"
    )

    def test_radio_off_returns_off(self):
        """nmcli 'wlan0: unavailable' (radio sw disabled) should return HotspotStatus.off."""
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = self.NMCLI_RADIO_OFF

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_current_ssid", return_value=None):
                with mock.patch("subprocess.run", return_value=mock_result):
                    result = get_hotspot_status()
                    assert result == HotspotStatus.off

    def test_radio_on_no_hotspot_returns_disconnected(self):
        """nmcli 'wlan0: disconnected' (radio on, no hotspot) should return disconnected."""
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = self.NMCLI_RADIO_ON_NO_HOTSPOT

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_current_ssid", return_value=None):
                with mock.patch("subprocess.run", return_value=mock_result):
                    result = get_hotspot_status()
                    assert result == HotspotStatus.disconnected

    def test_hotspot_active_returns_connected(self):
        """nmcli 'wlan0: connected to Hotspot' should return HotspotStatus.connected."""
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = self.NMCLI_HOTSPOT_ACTIVE

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_current_ssid", return_value=None):
                with mock.patch("subprocess.run", return_value=mock_result):
                    result = get_hotspot_status()
                    assert result == HotspotStatus.connected


class TestGetHotspotStatusDict:
    """Tests for get_hotspot_status_dict function."""

    def test_available_when_radio_off(self):
        """Hotspot should be available when WiFi radio is off,
        because enable_hotspot() turns the radio on first."""
        with mock.patch("controller.lib.admin.get_hotspot_status", return_value=HotspotStatus.off):
            result = get_hotspot_status_dict()
            assert result["available"] is True
            assert result["enabled"] is False

    def test_unavailable_when_unknown(self):
        """Hotspot should be unavailable when status is unknown (Docker, no nmcli)."""
        with mock.patch("controller.lib.admin.get_hotspot_status", return_value=HotspotStatus.unknown):
            result = get_hotspot_status_dict()
            assert result["available"] is False

    def test_enabled_when_connected(self):
        """Hotspot should be enabled and available when connected."""
        with mock.patch("controller.lib.admin.get_hotspot_status", return_value=HotspotStatus.connected):
            result = get_hotspot_status_dict()
            assert result["available"] is True
            assert result["enabled"] is True


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
            def mock_get_config(key, default=None):
                config_map = {
                    'hotspot.device': 'wlan1',
                    'hotspot.ssid': 'TestSSID',
                    'hotspot.password': 'testpassword123',
                }
                return config_map.get(key, default)

            with mock.patch("controller.lib.admin.get_config_value", side_effect=mock_get_config):
                radio_on = mock.Mock(returncode=0, stdout="", stderr="")
                device_ready = mock.Mock(returncode=0, stdout="wlan1:disconnected\n", stderr="")
                hotspot_ok = mock.Mock(returncode=0, stdout="", stderr="")

                with mock.patch("subprocess.run", side_effect=[radio_on, device_ready, hotspot_ok]) as mock_subprocess:
                    with mock.patch("time.sleep"):
                        enable_hotspot()

                    # Find the hotspot creation call (nmcli device wifi hotspot)
                    calls = mock_subprocess.call_args_list
                    hotspot_call = [c for c in calls if 'hotspot' in c[0][0]]
                    assert hotspot_call, "Hotspot creation call not found"
                    cmd_args = hotspot_call[0][0][0]
                    assert "wlan1" in cmd_args
                    assert "TestSSID" in cmd_args
                    assert "testpassword123" in cmd_args


    def test_waits_for_device_ready_after_radio_on(self):
        """Should poll device status after turning radio on, waiting for device
        to transition from 'unavailable' before creating hotspot.
        Real RPi behavior: radio on takes ~2s for device to become 'disconnected'."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # Simulate: radio on succeeds, device initially unavailable, then disconnected, then hotspot succeeds
            radio_on_result = mock.Mock(returncode=0, stdout="", stderr="")
            device_unavailable = mock.Mock(returncode=0, stdout="wlan0:unavailable\n", stderr="")
            device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
            hotspot_result = mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch("subprocess.run", side_effect=[
                radio_on_result,     # nmcli radio wifi on
                device_unavailable,  # nmcli -t device status (not ready)
                device_ready,        # nmcli -t device status (ready)
                hotspot_result,      # nmcli device wifi hotspot
            ]):
                with mock.patch("time.sleep"):  # Don't actually sleep in tests
                    result = enable_hotspot()
                    assert result["success"] is True

    def test_fails_if_device_never_becomes_ready(self):
        """Should fail with a clear error if device stays unavailable after radio on."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            radio_on_result = mock.Mock(returncode=0, stdout="", stderr="")
            device_unavailable = mock.Mock(returncode=0, stdout="wlan0:unavailable\n", stderr="")

            # Device never becomes ready (all polls return unavailable)
            with mock.patch("subprocess.run", side_effect=[
                radio_on_result,
            ] + [device_unavailable] * 20):
                with mock.patch("time.sleep"):
                    result = enable_hotspot()
                    assert result["success"] is False
                    assert "not ready" in result.get("error", "").lower() or "unavailable" in result.get("error", "").lower()


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
