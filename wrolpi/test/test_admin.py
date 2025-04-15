from pathlib import PosixPath
from unittest import mock
from unittest.mock import call

from wrolpi import admin
from wrolpi.admin import HotspotStatus
from wrolpi.common import WROLPI_CONFIG
from wrolpi.test.common import skip_circleci, skip_macos


@skip_circleci
@skip_macos
def test_hotspot_status():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess:
        mock_subprocess.check_output.return_value = b'wlan0: unavailable'
        assert admin.hotspot_status() == HotspotStatus.unavailable
        mock_subprocess.check_output.return_value = b'wlan0: disconnected'
        assert admin.hotspot_status() == HotspotStatus.disconnected
        mock_subprocess.check_output.return_value = b'wlan0: connected'
        assert admin.hotspot_status() == HotspotStatus.connected


def test_enable_hotspot_disconnected():
    """Enable hotspot with wifi on."""
    with mock.patch('wrolpi.admin.hotspot_status') as mock_hotspot_status, \
            mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.NMCLI_BIN', PosixPath('/usr/bin/nmcli')):
        mock_hotspot_status.return_value = HotspotStatus.disconnected
        mock_subprocess.check_output.return_value = 0
        assert admin.enable_hotspot() is True
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'device', 'wifi', 'hotspot', 'ifname', 'wlan0',
             'ssid', 'WROLPi', 'password', 'wrolpi hotspot'))


def test_enable_hotspot_unavailable():
    """Enable hotspot with wifi off."""
    with mock.patch('wrolpi.admin.hotspot_status') as mock_hotspot_status, \
            mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.NMCLI_BIN', PosixPath('/usr/bin/nmcli')):
        mock_hotspot_status.side_effect = [HotspotStatus.unavailable, HotspotStatus.disconnected]
        mock_subprocess.check_output.return_value = 0
        assert admin.enable_hotspot() is True
        mock_subprocess.check_call.assert_has_calls(
            [
                call((PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'radio', 'wifi', 'on')),
                call((PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'device', 'wifi', 'hotspot', 'ifname',
                      'wlan0', 'ssid', 'WROLPi', 'password', 'wrolpi hotspot'))]
        )


def test_enable_hotspot_connected():
    """Enable hotspot with the hotspot alaready enabled."""
    with mock.patch('wrolpi.admin.hotspot_status') as mock_hotspot_status, \
            mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.NMCLI_BIN', PosixPath('/usr/bin/nmcli')):
        mock_hotspot_status.side_effect = [
            HotspotStatus.connected,
            HotspotStatus.unavailable,
            HotspotStatus.disconnected,
        ]
        mock_subprocess.check_output.return_value = 0
        assert admin.enable_hotspot() is True
        mock_subprocess.check_call.assert_has_calls(
            [
                call((PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'radio', 'wifi', 'off')),
                call((PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'radio', 'wifi', 'on')),
                call((PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'device', 'wifi', 'hotspot', 'ifname',
                      'wlan0', 'ssid', 'WROLPi', 'password', 'wrolpi hotspot'))]
        )


def test_change_hotspot(test_wrolpi_config, async_client):
    """The hotspot can be configured."""
    with mock.patch('wrolpi.admin.hotspot_status') as mock_hotspot_status, \
            mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.NMCLI_BIN', PosixPath('/usr/bin/nmcli')):
        mock_subprocess.check_output.return_value = 0
        mock_hotspot_status.return_value = HotspotStatus.disconnected
        assert admin.enable_hotspot() is True
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'device', 'wifi', 'hotspot', 'ifname', 'wlan0',
             'ssid', 'WROLPi', 'password', 'wrolpi hotspot'))

    WROLPI_CONFIG.hotspot_ssid = 'New SSID'
    WROLPI_CONFIG.hotspot_password = '$uper Secure *#'
    with mock.patch('wrolpi.admin.hotspot_status') as mock_hotspot_status, \
            mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.NMCLI_BIN', PosixPath('/usr/bin/nmcli')):
        mock_subprocess.check_output.return_value = 0
        mock_hotspot_status.return_value = HotspotStatus.disconnected
        assert admin.enable_hotspot() is True
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'device', 'wifi', 'hotspot', 'ifname', 'wlan0',
             'ssid', 'New SSID', 'password', '$uper Secure *#'))


def test_throttle_on():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.CPUFREQ_SET_BIN', PosixPath('/usr/bin/cpufreq-set')):
        assert admin.throttle_cpu_on()
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/cpufreq-set'), '-g', 'powersave')
        )


def test_throttle_off():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.CPUFREQ_SET_BIN', PosixPath('/usr/bin/cpufreq-set')):
        assert admin.throttle_cpu_off()
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/cpufreq-set'), '-g', 'ondemand')
        )


@skip_circleci
@skip_macos
def test_hotspot_device(async_client):
    """Changing the hotspot device changes what device is turned on."""
    from wrolpi.common import WROLPI_CONFIG
    WROLPI_CONFIG.hotspot_device = 'wlp2s0'

    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess:
        mock_subprocess.check_output.return_value = b'wlp2s0: connected'
        assert admin.hotspot_status() == HotspotStatus.connected
