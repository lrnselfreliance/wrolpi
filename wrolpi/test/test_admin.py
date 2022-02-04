from pathlib import PosixPath
from unittest import mock

from wrolpi import admin

nmcli_status_example1 = b'''wlan0: connected to Hotspot
        "Broadcom BCM43438 combo and Bluetooth Low Energy"
        wifi (brcmfmac), AB:CD:EF:F1:23:45, hw, mtu 1500
        inet4 192.168.0.1/24
        route4 192.168.0.0/24
        route4 0.0.0.0/0
        inet6 fe80::5a1b:7312:ab3:80e7/64
        route6 fe80::/64

eth0: connected to Wired connection 1
        "eth0"
        ethernet (bcmgenet), AB:CD:EF:F1:23:45, hw, mtu 1500
        ip4 default
        inet4 10.0.0.6/24
        route4 0.0.0.0/0
        route4 10.0.0.0/24
        inet6 fd57:d3d7:5699:4a24:b1ec:31b8:1f7a:fa13/64
        inet6 fe80::611b:154f:8022:c8ca/64
        route6 fdbd:1f76:f9a5::/64
        route6 fd57:d3d7:5699:4a24::/64
        route6 fe80::/64

p2p-dev-wlan0: disconnected
        "p2p-dev-wlan0"
        wifi-p2p, hw

lo: unmanaged
        "lo"
        loopback (unknown), 00:00:00:00:00:00, sw, mtu 65536

DNS configuration:
        servers: 10.0.0.1
        interface: eth0

Use "nmcli device show" to get complete information about known devices and
"nmcli connection show" to get an overview on active connection profiles.

Consult nmcli(1) and nmcli-examples(7) manual pages for complete usage details.
'''

nmcli_status_example2 = b'''eth0: connected to Wired connection 1
        "eth0"
        ethernet (bcmgenet), AB:CD:EF:F1:23:45, hw, mtu 1500
        ip4 default
        inet4 10.0.0.6/24
        route4 0.0.0.0/0
        route4 10.0.0.0/24
        inet6 fd57:d3d7:5699:4a24:b1ec:31b8:1f7a:fa13/64
        inet6 fe80::611b:154f:8022:c8ca/64
        route6 fdbd:1f76:f9a5::/64
        route6 fd57:d3d7:5699:4a24::/64
        route6 fe80::/64

wlan0: unavailable
        "Broadcom BCM43438 combo and Bluetooth Low Energy"
        wifi (brcmfmac), AB:CD:EF:F1:23:45, sw disabled, hw, mtu 1500

p2p-dev-wlan0: unavailable
        "p2p-dev-wlan0"
        wifi-p2p, sw disabled, hw

lo: unmanaged
        "lo"
        loopback (unknown), 00:00:00:00:00:00, sw, mtu 65536

DNS configuration:
        servers: 10.0.0.1
        interface: eth0

Use "nmcli device show" to get complete information about known devices and
"nmcli connection show" to get an overview on active connection profiles.

Consult nmcli(1) and nmcli-examples(7) manual pages for complete usage details.
'''


def test_parse_nmcli_status():
    result = admin.parse_nmcli_status(nmcli_status_example1)
    assert result == {
        'wlan0': {
            'connection': 'connected',
            'kind': 'wifi',
            'mac': 'AB:CD:EF:F1:23:45',
            'inet4': '192.168.0.1/24',
            'inet6': ['fe80::5a1b:7312:ab3:80e7/64'],
        },
        'eth0': {
            'connection': 'connected',
            'kind': 'ethernet',
            'mac': 'AB:CD:EF:F1:23:45',
            'inet4': '10.0.0.6/24',
            'inet6': ['fd57:d3d7:5699:4a24:b1ec:31b8:1f7a:fa13/64', 'fe80::611b:154f:8022:c8ca/64'],
        },
    }

    result = admin.parse_nmcli_status(nmcli_status_example2)
    assert result == {
        'wlan0': {
            'connection': 'unavailable',
            'kind': 'wifi',
            'mac': 'AB:CD:EF:F1:23:45',
        },
        'eth0': {
            'connection': 'connected',
            'kind': 'ethernet',
            'mac': 'AB:CD:EF:F1:23:45',
            'inet4': '10.0.0.6/24',
            'inet6': ['fd57:d3d7:5699:4a24:b1ec:31b8:1f7a:fa13/64', 'fe80::611b:154f:8022:c8ca/64'],
        },
    }


def test_hotspot_status():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess:
        mock_subprocess.check_output.return_value = nmcli_status_example1
        assert admin.hotspot_status() == {
            'wlan0': {
                'connection': 'connected',
                'kind': 'wifi',
                'inet4': '192.168.0.1/24',
                'inet6': ['fe80::5a1b:7312:ab3:80e7/64'],
            },
            'eth0': {
                'connection': 'connected',
                'kind': 'ethernet',
                'inet4': '10.0.0.6/24',
                'inet6': ['fd57:d3d7:5699:4a24:b1ec:31b8:1f7a:fa13/64', 'fe80::611b:154f:8022:c8ca/64'],
            }
        }


def test_hotspot_on():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess:
        mock_subprocess.check_call.return_value = 0
        assert admin.hotspot_on() is True
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'radio', 'wifi', 'on')
        )

        mock_subprocess.check_call.return_value = 1
        assert admin.hotspot_on() is False


def test_hotspot_off():
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess:
        mock_subprocess.check_call.return_value = 0
        assert admin.hotspot_off() is True
        mock_subprocess.check_call.assert_called_once_with(
            (PosixPath('/usr/bin/sudo'), PosixPath('/usr/bin/nmcli'), 'radio', 'wifi', 'off')
        )

        mock_subprocess.check_call.return_value = 1
        assert admin.hotspot_off() is False
