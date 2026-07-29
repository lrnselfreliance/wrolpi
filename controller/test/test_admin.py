"""
Unit tests for controller.lib.admin module.
"""

from unittest import mock

import pytest
import yaml

from controller.lib.config import reload_config_from_drive
from controller.lib.admin import (
    apply_timezone_from_config,
    block_bluetooth,
    stop_hotspot,
    disable_throttle,
    unblock_bluetooth,
    start_hotspot,
    enable_throttle,
    get_bluetooth_status,
    get_hotspot_status,
    get_hotspot_status_dict,
    get_throttle_status,
    get_timezone_status_dict,
    get_device_hotspot_protocols,
    get_hotspot_device,
    get_hotspot_password,
    get_hotspot_protocol,
    get_hotspot_ssid,
    get_wifi_devices,
    migrate_hotspot_settings_from_wrolpi_config,
    reboot_system,
    restart_all_services,
    set_timezone,
    shutdown_system,
    update_hotspot_settings,
    get_desktop_status,
    get_desktop_status_dict,
    start_desktop,
    stop_desktop,
    get_vnc_backend,
    get_vnc_status,
    get_vnc_status_dict,
    start_vnc,
    stop_vnc,
    BluetoothStatus,
    DesktopStatus,
    VncStatus,
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


class TestBluetoothBlockUnblock:
    """Tests for unblock_bluetooth / block_bluetooth — they share the same shape."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func,rfkill_arg", [
        (unblock_bluetooth, "unblock"),
        (block_bluetooth, "block"),
    ])
    async def test_calls_rfkill_with_correct_action(self, func, rfkill_arg):
        """Each function should invoke rfkill with the expected action."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await func()
                assert result["success"] is True
                mock_exec.assert_called_once_with(
                    "/usr/sbin/rfkill", rfkill_arg, "bluetooth",
                    stdout=mock.ANY,
                    stderr=mock.ANY,
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func", [unblock_bluetooth, block_bluetooth])
    async def test_handles_rfkill_not_found(self, func):
        """Should handle rfkill not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await func()
                assert result["success"] is False


def _mock_systemctl_show_proc(load_state: str, active_state: str) -> mock.AsyncMock:
    """A mocked `systemctl show` process reporting the given unit states."""
    mock_proc = mock.AsyncMock()
    output = f"LoadState={load_state}\nActiveState={active_state}\n"
    mock_proc.communicate.return_value = (output.encode(), b"")
    mock_proc.returncode = 0
    return mock_proc


class TestGetDesktopStatus:
    """Tests for get_desktop_status function."""

    @pytest.mark.asyncio
    async def test_returns_unknown_in_docker_mode(self):
        """Should return unknown when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await get_desktop_status()
            assert result == DesktopStatus.unknown

    @pytest.mark.asyncio
    @pytest.mark.parametrize("load_state,active_state,expected", [
        ("loaded", "active", DesktopStatus.on),
        ("loaded", "inactive", DesktopStatus.off),
        ("loaded", "failed", DesktopStatus.off),
        ("not-found", "inactive", DesktopStatus.unavailable),
    ])
    async def test_parses_systemctl_show(self, load_state, active_state, expected):
        """Should map the display manager's LoadState/ActiveState to a DesktopStatus."""
        mock_proc = _mock_systemctl_show_proc(load_state, active_state)
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_desktop_status()
                assert result == expected

    @pytest.mark.asyncio
    async def test_returns_unavailable_when_systemctl_not_found(self):
        """Should return unavailable when systemctl is not installed."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await get_desktop_status()
                assert result == DesktopStatus.unavailable

    @pytest.mark.asyncio
    async def test_returns_unknown_when_systemctl_fails(self):
        """Should return unknown when systemctl returns an error."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"some error")
        mock_proc.returncode = 1
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await get_desktop_status()
                assert result == DesktopStatus.unknown


class TestGetDesktopStatusDict:
    """Tests for get_desktop_status_dict function."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,running,available", [
        (DesktopStatus.on, True, True),
        (DesktopStatus.off, False, True),
        (DesktopStatus.unavailable, False, False),
        (DesktopStatus.unknown, False, False),
    ])
    async def test_maps_status_to_flags(self, status, running, available):
        """Should map each DesktopStatus to running/available flags."""
        with mock.patch("controller.lib.admin.get_desktop_status", return_value=status):
            result = await get_desktop_status_dict()
            assert result["running"] is running
            assert result["available"] is available
            if available:
                assert result["reason"] is None
            else:
                assert result["reason"]


class TestDesktopStartStop:
    """Tests for start_desktop / stop_desktop — they share the same shape."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func,systemctl_action", [
        (start_desktop, "start"),
        (stop_desktop, "stop"),
    ])
    async def test_calls_systemctl_with_correct_action(self, func, systemctl_action):
        """Each function should invoke systemctl with the expected action; never enable/disable."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await func()
                assert result["success"] is True
                assert mock_exec.call_args_list[0] == mock.call(
                    "systemctl", systemctl_action, "display-manager.service",
                    stdout=mock.ANY,
                    stderr=mock.ANY,
                )
                # Fail open: never enable/disable the unit or change the default target.
                forbidden = {"enable", "disable", "mask", "unmask", "set-default", "isolate"}
                for call in mock_exec.call_args_list:
                    assert not forbidden.intersection(call.args), call.args

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func", [start_desktop, stop_desktop])
    async def test_reports_systemctl_error(self, func):
        """Should report systemctl's stderr when the action fails."""
        mock_proc = mock.AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Unit display-manager.service not loaded.")
        mock_proc.returncode = 5

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = await func()
                assert result["success"] is False
                assert "not loaded" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func", [start_desktop, stop_desktop])
    async def test_handles_systemctl_not_found(self, func):
        """Should handle systemctl not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
                result = await func()
                assert result["success"] is False


class TestStopDesktopDropsToConsole:
    """Stopping the desktop must leave the physical display on a usable terminal.

    The display manager owns its own VT (7 on Raspberry Pi OS); stopping it leaves
    that VT blank with only a cursor, so the display is switched to the console VT.
    """

    @staticmethod
    def _proc(returncode=0, stdout=b"", stderr=b""):
        proc = mock.AsyncMock()
        proc.communicate.return_value = (stdout, stderr)
        proc.returncode = returncode
        return proc

    @pytest.mark.asyncio
    async def test_activates_and_repaints_console(self):
        """Should check for a getty, activate the console VT, then bounce to repaint it.

        The console VT is normally already in the foreground when the display manager
        stops, but the monitor is left black until something forces a redraw.
        """
        procs = [self._proc(), self._proc(0, b"active\n"), self._proc(), self._proc(), self._proc()]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs) as mock_exec:
                with mock.patch("builtins.open", mock.mock_open()) as mock_console:
                    result = await stop_desktop()

        assert result["success"] is True
        assert result["switched_to_console"] is True
        commands = [call.args for call in mock_exec.call_args_list]
        assert commands[0] == ("systemctl", "stop", "display-manager.service")
        assert commands[1] == ("systemctl", "is-active", "getty@tty1.service")
        # Land on the console, bounce away, and come back so it is repainted.
        assert commands[2:] == [("/usr/bin/chvt", "1"), ("/usr/bin/chvt", "2"), ("/usr/bin/chvt", "1")]
        mock_console.assert_called_once_with("/dev/tty1", "w")
        written = mock_console().write.call_args.args[0]
        assert "stopped the desktop" in written
        assert "systemctl start display-manager" in written

    @pytest.mark.asyncio
    async def test_console_write_failure_is_tolerated(self):
        """A console that cannot be written to must not fail the stop."""
        procs = [self._proc(), self._proc(0, b"active\n"), self._proc(), self._proc(), self._proc()]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs):
                with mock.patch("builtins.open", side_effect=OSError("No such device")):
                    result = await stop_desktop()

        assert result["success"] is True
        assert result["switched_to_console"] is True

    @pytest.mark.asyncio
    async def test_reports_failure_when_stranded_on_repaint_vt(self):
        """If the bounce cannot return to the console, say so rather than claim success."""
        procs = [self._proc(), self._proc(0, b"active\n"), self._proc(), self._proc(), self._proc(1)]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs):
                result = await stop_desktop()

        assert result["success"] is True
        assert result["switched_to_console"] is False

    @pytest.mark.asyncio
    async def test_does_not_switch_when_no_getty(self):
        """Without a getty on the console VT, switching would be just as blank — skip it."""
        procs = [self._proc(), self._proc(3, b"inactive\n")]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs) as mock_exec:
                result = await stop_desktop()

        assert result["success"] is True
        assert result["switched_to_console"] is False
        assert len(mock_exec.call_args_list) == 2  # no chvt

    @pytest.mark.asyncio
    async def test_chvt_failure_does_not_fail_the_stop(self):
        """A missing or failing chvt is reported, but the desktop is still stopped."""
        procs = [self._proc(), self._proc(0, b"active\n"), FileNotFoundError()]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs):
                result = await stop_desktop()

        assert result["success"] is True
        assert result["switched_to_console"] is False

    @pytest.mark.asyncio
    async def test_no_switch_when_stop_failed(self):
        """A failed stop leaves the desktop up, so the display must not be switched."""
        procs = [self._proc(5, b"", b"Unit not loaded.")]

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs) as mock_exec:
                result = await stop_desktop()

        assert result["success"] is False
        assert "switched_to_console" not in result
        assert len(mock_exec.call_args_list) == 1

    @pytest.mark.asyncio
    async def test_start_never_switches_vt(self):
        """Starting the desktop must not touch the VT; the display manager claims one itself."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=self._proc()) as mock_exec:
                result = await start_desktop()

        assert result["success"] is True
        assert "switched_to_console" not in result
        assert len(mock_exec.call_args_list) == 1


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
        because start_hotspot() turns the radio on first."""
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


class TestHotspotSettingsMigration:
    """Legacy hotspot settings in wrolpi.yaml are copied into controller.yaml on startup."""

    @staticmethod
    def _write_wrolpi_yaml(test_config_directory, **values):
        lines = ''.join(f'{key}: {value}\n' for key, value in values.items())
        (test_config_directory / 'wrolpi.yaml').write_text(lines)

    def test_migrates_wrolpi_yaml_values(self, test_directory, test_config_directory, mock_config_path,
                                         reset_runtime_config):
        """wrolpi.yaml hotspot settings should be copied to controller.yaml."""
        mock_config_path.write_text("{}\n")
        self._write_wrolpi_yaml(test_config_directory, hotspot_device='wlp2s0', hotspot_ssid='RafaelPi',
                                hotspot_password='password123')

        with mock.patch("controller.lib.admin.get_media_directory", return_value=test_directory):
            migrate_hotspot_settings_from_wrolpi_config()

        assert get_hotspot_device() == 'wlp2s0'
        assert get_hotspot_ssid() == 'RafaelPi'
        assert get_hotspot_password() == 'password123'
        # The migrated values are persisted in controller.yaml.
        saved = yaml.safe_load(mock_config_path.read_text())
        assert saved['hotspot'] == {'device': 'wlp2s0', 'ssid': 'RafaelPi', 'password': 'password123'}

    def test_does_not_overwrite_explicit_controller_values(self, test_directory, test_config_directory,
                                                           mock_config_path, reset_runtime_config):
        """Explicit controller.yaml values win over legacy wrolpi.yaml values."""
        mock_config_path.write_text("hotspot:\n  device: wlan1\n")
        reload_config_from_drive()
        self._write_wrolpi_yaml(test_config_directory, hotspot_device='wlp2s0', hotspot_ssid='RafaelPi')

        with mock.patch("controller.lib.admin.get_media_directory", return_value=test_directory):
            migrate_hotspot_settings_from_wrolpi_config()

        # The explicit device is kept, but the SSID is still migrated.
        assert get_hotspot_device() == 'wlan1'
        assert get_hotspot_ssid() == 'RafaelPi'

    def test_noop_without_wrolpi_yaml(self, test_directory, test_config_directory, mock_config_path,
                                      reset_runtime_config):
        """Nothing happens when wrolpi.yaml does not exist."""
        mock_config_path.write_text("{}\n")

        with mock.patch("controller.lib.admin.get_media_directory", return_value=test_directory):
            migrate_hotspot_settings_from_wrolpi_config()

        assert get_hotspot_device() == 'wlan0'
        assert yaml.safe_load(mock_config_path.read_text()) == {}

    def test_noop_when_drive_not_mounted(self, test_directory, test_config_directory, mock_config_path,
                                         reset_runtime_config):
        """Nothing happens when controller.yaml does not exist (drive not mounted)."""
        self._write_wrolpi_yaml(test_config_directory, hotspot_device='wlp2s0')

        with mock.patch("controller.lib.admin.get_media_directory", return_value=test_directory):
            migrate_hotspot_settings_from_wrolpi_config()

        assert get_hotspot_device() == 'wlan0'


class TestUpdateHotspotSettings:
    """Tests for update_hotspot_settings function."""

    def test_updates_and_saves(self, mock_config_path, reset_runtime_config):
        """New settings should be applied to the runtime config and saved to controller.yaml."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = update_hotspot_settings(device='wlp2s0', ssid='RafaelPi', password='password123')

        assert result["success"] is True
        assert get_hotspot_device() == 'wlp2s0'
        saved = yaml.safe_load(mock_config_path.read_text())
        assert saved['hotspot'] == {'device': 'wlp2s0', 'ssid': 'RafaelPi', 'password': 'password123'}

    def test_partial_update(self, mock_config_path, reset_runtime_config):
        """Only provided values are changed."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = update_hotspot_settings(device='wlp2s0')

        assert result["success"] is True
        assert result["device"] == 'wlp2s0'
        assert result["ssid"] == 'WROLPi'
        assert result["password"] == 'wrolpi hotspot'

    def test_updates_protocol(self, mock_config_path, reset_runtime_config):
        """The protocol is saved to controller.yaml and returned."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = update_hotspot_settings(protocol='wpa3')

        assert result["success"] is True
        assert result["protocol"] == 'wpa3'
        assert get_hotspot_protocol() == 'wpa3'
        saved = yaml.safe_load(mock_config_path.read_text())
        assert saved['hotspot']['protocol'] == 'wpa3'

    def test_rejects_invalid_protocol(self, mock_config_path, reset_runtime_config):
        """Only wpa2 and wpa3 are valid protocols."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = update_hotspot_settings(protocol='wep')

        assert result["success"] is False
        assert "protocol" in result["error"].lower()
        assert get_hotspot_protocol() == 'wpa2'

    def test_rejects_short_password(self, mock_config_path, reset_runtime_config):
        """nmcli requires a WPA password of 8 to 63 characters."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            result = update_hotspot_settings(password='short')

        assert result["success"] is False
        assert "8" in result["error"]
        assert get_hotspot_password() == 'wrolpi hotspot'

    def test_rejects_in_docker_mode(self, reset_runtime_config):
        """Hotspot settings cannot be changed in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = update_hotspot_settings(device='wlp2s0')

        assert result["success"] is False
        assert "Docker" in result["error"]

    def test_noop_does_not_save(self, tmp_path, reset_runtime_config):
        """An empty update succeeds without writing controller.yaml."""
        missing_path = tmp_path / 'missing' / 'controller.yaml'
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            # save_config() would raise RuntimeError here; success proves it was skipped.
            with mock.patch("controller.lib.config.CONFIG_PATH_ON_DRIVE", missing_path):
                result = update_hotspot_settings()

        assert result["success"] is True
        assert not missing_path.exists()

    def test_error_when_drive_not_mounted(self, tmp_path, reset_runtime_config):
        """Saving fails cleanly when the primary drive is not mounted."""
        missing_path = tmp_path / 'missing' / 'controller.yaml'
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.config.CONFIG_PATH_ON_DRIVE", missing_path):
                result = update_hotspot_settings(device='wlp2s0')

        assert result["success"] is False
        assert "not mounted" in result["error"]


# `iw dev wlan0 info` output; only the "wiphy" line matters.
IW_DEV_INFO = """Interface wlan0
\tifindex 3
\twdev 0x1
\taddr d8:3a:dd:11:22:33
\ttype managed
\twiphy 0
\ttxpower 31.00 dBm
"""

# Raspberry Pi brcmfmac (verified on real Pi 4/Pi 5 hardware): AP mode, but no
# AP/VLAN (fullmac driver) and no AP-mode SAE, so WPA3 hotspot is not possible.
# "SAE with AUTHENTICATE command" is station-mode WPA3 (joining, not hosting).
IW_PHY_BRCMFMAC = """Wiphy phy0
\twiphy index: 0
\tmax # scan SSIDs: 10
\tSupported Ciphers:
\t\t* WEP40 (00-0f-ac:1)
\t\t* WEP104 (00-0f-ac:5)
\t\t* TKIP (00-0f-ac:2)
\t\t* CCMP-128 (00-0f-ac:4)
\t\t* CMAC (00-0f-ac:6)
\tAvailable Antennas: TX 0 RX 0
\tSupported interface modes:
\t\t * IBSS
\t\t * managed
\t\t * AP
\t\t * P2P-client
\t\t * P2P-GO
\t\t * P2P-device
\tDevice supports SAE with AUTHENTICATE command
\tSupported extended features:
\t\t* [ CQM_RSSI_LIST ]: multiple CQM_RSSI_THOLD records
\t\t* [ DFS_OFFLOAD ]: DFS offload
"""

# mac80211 driver (Intel/Atheros style): AP/VLAN plus the CMAC cipher means
# wpa_supplicant can run SAE in software for the AP.
IW_PHY_MAC80211 = """Wiphy phy0
\tmax # scan SSIDs: 4
\tSupported Ciphers:
\t\t* WEP40 (00-0f-ac:1)
\t\t* TKIP (00-0f-ac:2)
\t\t* CCMP-128 (00-0f-ac:4)
\t\t* CMAC (00-0f-ac:6)
\tSupported interface modes:
\t\t * IBSS
\t\t * managed
\t\t * AP
\t\t * AP/VLAN
\t\t * monitor
\t\t * mesh point
\tSupported extended features:
\t\t* [ RRM ]: RRM
\t\t* [ FILS_STA ]: FILS shared key authentication support
"""

# Fullmac driver with AP-mode SAE offload advertised by the firmware.
# Older iw releases print "Extended features:" instead of "Supported extended features:".
IW_PHY_SAE_OFFLOAD_AP = """Wiphy phy0
\tSupported Ciphers:
\t\t* CCMP-128 (00-0f-ac:4)
\tSupported interface modes:
\t\t * managed
\t\t * AP
\tExtended features:
\t\t* [ SAE_OFFLOAD ]: SAE offload support
\t\t* [ SAE_OFFLOAD_AP ]: SAE offload support (AP mode)
"""

# Station-only hardware which cannot host a hotspot at all.
IW_PHY_NO_AP = """Wiphy phy0
\tSupported Ciphers:
\t\t* CCMP-128 (00-0f-ac:4)
\tSupported interface modes:
\t\t * managed
\t\t * monitor
"""


class TestGetDeviceHotspotProtocols:
    """Tests for get_device_hotspot_protocols; WPA3 requires SAE support in AP mode."""

    @staticmethod
    def _protocols(phy_info: str) -> list:
        dev_info = mock.Mock(returncode=0, stdout=IW_DEV_INFO, stderr="")
        phy = mock.Mock(returncode=0, stdout=phy_info, stderr="")
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=[dev_info, phy]) as mock_run:
                result = get_device_hotspot_protocols("wlan0")
        # The wiphy index from `iw dev` is used to query the phy.
        assert mock_run.call_args_list[1][0][0] == ["/usr/sbin/iw", "phy", "phy0", "info"]
        return result

    def test_rpi_brcmfmac_is_wpa2_only(self):
        """The Raspberry Pi's fullmac driver cannot host a WPA3 (SAE) AP."""
        assert self._protocols(IW_PHY_BRCMFMAC) == ["wpa2"]

    def test_mac80211_driver_supports_wpa3(self):
        """mac80211 drivers (AP/VLAN listed) with the CMAC cipher can run software SAE."""
        assert self._protocols(IW_PHY_MAC80211) == ["wpa2", "wpa3"]

    def test_sae_offload_ap_supports_wpa3(self):
        """Firmware advertising SAE_OFFLOAD_AP can host a WPA3 AP."""
        assert self._protocols(IW_PHY_SAE_OFFLOAD_AP) == ["wpa2", "wpa3"]

    def test_station_only_hardware_has_no_protocols(self):
        """A device without AP mode cannot host a hotspot at all."""
        assert self._protocols(IW_PHY_NO_AP) == []

    def test_returns_empty_in_docker_mode(self):
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            assert get_device_hotspot_protocols("wlan0") == []

    def test_unknown_device_has_no_protocols(self):
        """`iw dev` fails for a device which does not exist."""
        dev_info = mock.Mock(returncode=237, stdout="", stderr="command failed: No such device")
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=[dev_info]):
                assert get_device_hotspot_protocols("wlan9") == []

    def test_assumes_wpa2_when_iw_missing(self):
        """Without `iw` we cannot probe; assume the WPA2 hotspot nmcli has always created."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                assert get_device_hotspot_protocols("wlan0") == ["wpa2"]


class TestGetWifiDevices:
    """Tests for get_wifi_devices function."""

    # Real terse nmcli output from an x86 PC: `nmcli -t -f DEVICE,TYPE device`
    NMCLI_TERSE_DEVICES = (
        "eno1:ethernet\n"
        "wlp2s0:wifi\n"
        "p2p-dev-wlp2s0:wifi-p2p\n"
        "lo:loopback\n"
    )

    def test_returns_wifi_devices_only(self):
        """Should return only wifi-type devices, excluding wifi-p2p and ethernet."""
        mock_result = mock.Mock(returncode=0, stdout=self.NMCLI_TERSE_DEVICES)
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                assert get_wifi_devices() == ["wlp2s0"]

    def test_returns_empty_in_docker_mode(self):
        """Should return an empty list in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            assert get_wifi_devices() == []

    def test_returns_empty_when_nmcli_missing(self):
        """Should return an empty list when nmcli is not installed."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                assert get_wifi_devices() == []

    def test_returns_empty_when_nmcli_fails(self):
        """Should return an empty list when nmcli returns an error."""
        mock_result = mock.Mock(returncode=8, stdout="")
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                assert get_wifi_devices() == []


class TestDockerModeErrors:
    """Admin functions should return an error result when running in Docker mode."""

    @pytest.mark.parametrize("func,is_async,args", [
        (unblock_bluetooth, True, ()),
        (block_bluetooth, True, ()),
        (start_hotspot, False, ()),
        (stop_hotspot, False, ()),
        (start_desktop, True, ()),
        (stop_desktop, True, ()),
        (start_vnc, True, ()),
        (stop_vnc, True, ()),
        (enable_throttle, False, ()),
        (disable_throttle, False, ()),
        (shutdown_system, False, ()),
        (reboot_system, False, ()),
        (restart_all_services, True, ()),
        (set_timezone, False, ("America/Denver",)),
    ])
    @pytest.mark.asyncio
    async def test_returns_error_in_docker_mode(self, func, is_async, args):
        """In Docker mode each function should refuse with a Docker-mentioning error."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            result = await func(*args) if is_async else func(*args)
            assert result["success"] is False
            # set_timezone uses "error" string verbatim; others use the same shape.
            error = result.get("error", "")
            assert "Docker" in error


class TestStartHotspot:
    """Tests for start_hotspot function."""

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = start_hotspot()
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
                ok = mock.Mock(returncode=0, stdout="", stderr="")

                with mock.patch("subprocess.run",
                                side_effect=[radio_on, device_ready, ok, ok, ok]) as mock_subprocess:
                    with mock.patch("time.sleep"):
                        start_hotspot()

                    # Find the hotspot creation call (nmcli device wifi hotspot)
                    calls = mock_subprocess.call_args_list
                    hotspot_call = [c for c in calls if 'hotspot' in c[0][0]]
                    assert hotspot_call, "Hotspot creation call not found"
                    cmd_args = hotspot_call[0][0][0]
                    assert "wlan1" in cmd_args
                    assert "TestSSID" in cmd_args
                    assert "testpassword123" in cmd_args

    @staticmethod
    def _run_enable(protocol: str, results: list) -> tuple:
        """Run start_hotspot() with the given hotspot.protocol and subprocess results."""
        def mock_get_config(key, default=None):
            return {'hotspot.protocol': protocol}.get(key, default)

        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_config_value", side_effect=mock_get_config):
                with mock.patch("subprocess.run", side_effect=results) as mock_subprocess:
                    with mock.patch("time.sleep"):
                        result = start_hotspot()
        return result, mock_subprocess.call_args_list

    def test_wpa2_sets_psk_key_mgmt(self):
        """The Hotspot connection is explicitly set to WPA2 so a reused profile
        does not keep a previously configured protocol."""
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
        result, calls = self._run_enable('wpa2', [ok, device_ready, ok, ok, ok])

        assert result["success"] is True
        modify_call = [c[0][0] for c in calls if 'modify' in c[0][0]]
        assert modify_call and "wpa-psk" in modify_call[0]

    def test_wpa3_sets_sae_key_mgmt(self):
        """WPA3 modifies the Hotspot connection to SAE with required PMF, then re-activates."""
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
        result, calls = self._run_enable('wpa3', [ok, device_ready, ok, ok, ok])

        assert result["success"] is True
        modify_call = [c[0][0] for c in calls if 'modify' in c[0][0]]
        assert modify_call and "sae" in modify_call[0]
        assert "802-11-wireless-security.pmf" in modify_call[0]
        up_call = [c[0][0] for c in calls if 'up' in c[0][0]]
        assert up_call, "Hotspot connection was not re-activated"

    def test_wpa3_failure_reverts_to_wpa2(self):
        """If the driver rejects WPA3, the hotspot is reverted to WPA2 and an error returned."""
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
        sae_failed = mock.Mock(returncode=1, stdout="", stderr="Error: SAE not supported")
        # radio, poll, hotspot, modify(sae) fails, revert modify, revert up.
        result, calls = self._run_enable('wpa3', [ok, device_ready, ok, sae_failed, ok, ok])

        assert result["success"] is False
        assert "wpa3" in result["error"].lower()
        modify_calls = [c[0][0] for c in calls if 'modify' in c[0][0]]
        assert len(modify_calls) == 2 and "wpa-psk" in modify_calls[1]

    def test_wpa3_failed_revert_is_reported(self):
        """If reverting to WPA2 also fails, the error must not claim the hotspot was reverted."""
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
        sae_failed = mock.Mock(returncode=1, stdout="", stderr="Error: SAE not supported")
        revert_failed = mock.Mock(returncode=1, stdout="", stderr="Error: connection not found")
        # radio, poll, hotspot, modify(sae) fails, revert modify fails.
        result, _ = self._run_enable('wpa3', [ok, device_ready, ok, sae_failed, revert_failed])

        assert result["success"] is False
        assert "reverted" not in result["error"].lower()
        assert "wpa3" in result["error"].lower()

    def test_wpa2_modify_failure_still_succeeds(self):
        """A failure setting WPA2 explicitly is not fatal; nmcli already created a WPA2 hotspot."""
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        device_ready = mock.Mock(returncode=0, stdout="wlan0:disconnected\n", stderr="")
        failed = mock.Mock(returncode=1, stdout="", stderr="Error: unknown property")
        result, _ = self._run_enable('wpa2', [ok, device_ready, ok, failed])

        assert result["success"] is True

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
                hotspot_result,      # nmcli connection modify Hotspot
                hotspot_result,      # nmcli connection up Hotspot
            ]):
                with mock.patch("time.sleep"):  # Don't actually sleep in tests
                    result = start_hotspot()
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
                    result = start_hotspot()
                    assert result["success"] is False
                    assert "not ready" in result.get("error", "").lower() or "unavailable" in result.get("error", "").lower()


class TestStopHotspot:
    """Tests for stop_hotspot function."""

    def test_handles_nmcli_not_found(self):
        """Should handle nmcli not being available."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                result = stop_hotspot()
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


class TestShutdownSystem:
    """Tests for shutdown_system function."""

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


def _show_proc(output: str, returncode: int = 0) -> mock.AsyncMock:
    """A mocked `systemctl show` process printing the given properties."""
    proc = mock.AsyncMock()
    proc.communicate.return_value = (output.encode(), b"")
    proc.returncode = returncode
    return proc


def _ok_proc() -> mock.AsyncMock:
    proc = mock.AsyncMock()
    proc.communicate.return_value = (b"", b"")
    proc.returncode = 0
    return proc


class TestGetVncBackend:
    """wayvnc is preferred over RealVNC, and must actually be configured."""

    @pytest.mark.asyncio
    async def test_prefers_wayvnc_when_configured(self):
        """A loaded, configured wayvnc wins even when RealVNC is also installed."""
        with mock.patch("asyncio.create_subprocess_exec", return_value=_show_proc("LoadState=loaded\n")):
            with mock.patch("controller.lib.admin.WAYVNC_CONFIG") as config:
                config.is_file.return_value = True
                unit, name, reason = await get_vnc_backend()

        assert unit == "wayvnc.service"
        assert name == "wayvnc"
        assert reason is None

    @pytest.mark.asyncio
    async def test_falls_back_to_realvnc_when_wayvnc_unconfigured(self):
        """An unconfigured wayvnc must not be chosen; RealVNC is used instead."""
        with mock.patch("asyncio.create_subprocess_exec", return_value=_show_proc("LoadState=loaded\n")):
            with mock.patch("controller.lib.admin.WAYVNC_CONFIG") as config:
                config.is_file.return_value = False
                unit, name, reason = await get_vnc_backend()

        assert unit == "vncserver-x11-serviced.service"
        assert name == "realvnc"
        assert reason is None

    @pytest.mark.asyncio
    async def test_reports_unconfigured_wayvnc_when_alone(self):
        """wayvnc installed but unconfigured, with no RealVNC, explains itself."""
        procs = [_show_proc("LoadState=loaded\n"), _show_proc("LoadState=not-found\n")]
        with mock.patch("asyncio.create_subprocess_exec", side_effect=procs):
            with mock.patch("controller.lib.admin.WAYVNC_CONFIG") as config:
                config.is_file.return_value = False
                unit, name, reason = await get_vnc_backend()

        assert unit is None
        assert name is None
        assert "not configured" in reason

    @pytest.mark.asyncio
    async def test_reports_nothing_installed(self):
        """Neither backend installed is reported plainly."""
        with mock.patch("asyncio.create_subprocess_exec", return_value=_show_proc("LoadState=not-found\n")):
            unit, name, reason = await get_vnc_backend()

        assert unit is None
        assert reason == "No VNC server installed"

    @pytest.mark.asyncio
    async def test_does_not_probe_the_compositor(self):
        """Backend choice must not depend on a running compositor.

        raspi-config uses `pgrep labwc` to decide Wayland-vs-X11, which reports X11
        whenever the desktop is stopped and would pick the wrong backend.
        """
        with mock.patch("asyncio.create_subprocess_exec", return_value=_show_proc("LoadState=loaded\n")) as mock_exec:
            with mock.patch("controller.lib.admin.WAYVNC_CONFIG") as config:
                config.is_file.return_value = True
                await get_vnc_backend()

        for call in mock_exec.call_args_list:
            assert "pgrep" not in call.args[0]


class TestGetVncStatus:
    """Tests for get_vnc_status."""

    @pytest.mark.asyncio
    async def test_returns_unknown_in_docker_mode(self):
        """Should return unknown when in Docker mode."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=True):
            assert await get_vnc_status() == VncStatus.unknown

    @pytest.mark.asyncio
    @pytest.mark.parametrize("active_state,expected", [
        ("active", VncStatus.on),
        ("inactive", VncStatus.off),
        ("failed", VncStatus.off),
    ])
    async def test_maps_active_state(self, active_state, expected):
        """ActiveState of the chosen unit decides on/off."""
        procs = [_show_proc("LoadState=loaded\n"), _show_proc(f"ActiveState={active_state}\n")]
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", side_effect=procs):
                with mock.patch("controller.lib.admin.WAYVNC_CONFIG") as config:
                    config.is_file.return_value = True
                    assert await get_vnc_status() == expected

    @pytest.mark.asyncio
    async def test_unavailable_without_a_backend(self):
        """No installed backend reports unavailable."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("asyncio.create_subprocess_exec", return_value=_show_proc("LoadState=not-found\n")):
                assert await get_vnc_status() == VncStatus.unavailable


class TestGetVncStatusDict:
    """The status dict gates starting on the desktop being up."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vnc,desktop_up,running,available,can_start", [
        (VncStatus.on, True, True, True, True),
        (VncStatus.off, True, False, True, True),
        (VncStatus.off, False, False, True, False),  # desktop stopped: cannot start
        (VncStatus.on, False, True, True, False),  # running, but could not be started now
        (VncStatus.unavailable, True, False, False, False),
        (VncStatus.unknown, True, False, False, False),
    ])
    async def test_flags(self, vnc, desktop_up, running, available, can_start):
        """running/available/can_start reflect VNC and desktop state."""
        desktop = DesktopStatus.on if desktop_up else DesktopStatus.off
        with mock.patch("controller.lib.admin.get_vnc_status", return_value=vnc):
            with mock.patch("controller.lib.admin.get_vnc_backend", return_value=("u", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=desktop):
                    result = await get_vnc_status_dict()

        assert result["running"] is running
        assert result["available"] is available
        assert result["can_start"] is can_start
        assert result["desktop_running"] is desktop_up
        assert result["port"] == 5900

    @pytest.mark.asyncio
    async def test_explains_a_stopped_desktop(self):
        """The reason should name the desktop when that is what blocks VNC."""
        with mock.patch("controller.lib.admin.get_vnc_status", return_value=VncStatus.off):
            with mock.patch("controller.lib.admin.get_vnc_backend", return_value=("u", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=DesktopStatus.off):
                    result = await get_vnc_status_dict()

        assert "Desktop must be running" in result["reason"]


class TestVncStartStop:
    """Starting requires a desktop; stopping never does."""

    @pytest.mark.asyncio
    async def test_start_runs_systemctl_start(self):
        """With a desktop up, start should start the chosen unit and nothing else."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_vnc_backend",
                            return_value=("wayvnc.service", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=DesktopStatus.on):
                    with mock.patch("asyncio.create_subprocess_exec", return_value=_ok_proc()) as mock_exec:
                        result = await start_vnc()

        assert result["success"] is True
        mock_exec.assert_called_once_with(
            "systemctl", "start", "wayvnc.service", stdout=mock.ANY, stderr=mock.ANY)

    @pytest.mark.asyncio
    async def test_start_refused_when_desktop_stopped(self):
        """The gate lives here, not only in the UI, so curl callers get it too."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_vnc_backend",
                            return_value=("wayvnc.service", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=DesktopStatus.off):
                    with mock.patch("asyncio.create_subprocess_exec") as mock_exec:
                        result = await start_vnc()

        assert result["success"] is False
        assert result["precondition_failed"] is True
        assert "Desktop must be running" in result["error"]
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_allowed_with_desktop_stopped(self):
        """A running VNC must always be stoppable, or it could be stranded on."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_vnc_backend",
                            return_value=("wayvnc.service", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=DesktopStatus.off):
                    with mock.patch("asyncio.create_subprocess_exec", return_value=_ok_proc()) as mock_exec:
                        result = await stop_vnc()

        assert result["success"] is True
        mock_exec.assert_called_once_with(
            "systemctl", "stop", "wayvnc.service", stdout=mock.ANY, stderr=mock.ANY)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func", [start_vnc, stop_vnc])
    async def test_never_enables_or_disables(self, func):
        """Runtime-only: VNC must not be persisted across reboots."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_vnc_backend",
                            return_value=("wayvnc.service", "wayvnc", None)):
                with mock.patch("controller.lib.admin.get_desktop_status", return_value=DesktopStatus.on):
                    with mock.patch("asyncio.create_subprocess_exec", return_value=_ok_proc()) as mock_exec:
                        await func()

        forbidden = {"enable", "disable", "mask", "unmask", "set-default", "isolate"}
        for call in mock_exec.call_args_list:
            assert not forbidden.intersection(call.args), call.args

    @pytest.mark.asyncio
    @pytest.mark.parametrize("func", [start_vnc, stop_vnc])
    async def test_reports_missing_backend(self, func):
        """Without a backend both actions explain themselves instead of failing obscurely."""
        with mock.patch("controller.lib.admin.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.admin.get_vnc_backend",
                            return_value=(None, None, "No VNC server installed")):
                result = await func()

        assert result["success"] is False
        assert result["error"] == "No VNC server installed"
