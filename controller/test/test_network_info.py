"""
Unit tests for controller.lib.network_info.
"""

from unittest import mock

from controller.lib.network_info import get_network_info, _is_usable_ipv4, _pick_primary_ipv4


class TestIsUsableIpv4:
    def test_accepts_private(self):
        assert _is_usable_ipv4("192.168.1.10") is True
        assert _is_usable_ipv4("10.0.0.1") is True

    def test_rejects_loopback_and_link_local(self):
        assert _is_usable_ipv4("127.0.0.1") is False
        assert _is_usable_ipv4("169.254.1.1") is False


class TestPickPrimary:
    def test_prefers_up_interface(self):
        interfaces = [
            {"name": "wlan0", "ipv4": ["10.0.0.2"], "up": False},
            {"name": "eth0", "ipv4": ["192.168.1.5"], "up": True},
        ]
        assert _pick_primary_ipv4(interfaces) == "192.168.1.5"


class TestGetNetworkInfo:
    def test_shape_and_primary(self):
        snic = mock.Mock
        eth_addrs = [
            mock.Mock(family=__import__("socket").AF_INET, address="192.168.1.10"),
        ]
        lo_addrs = [
            mock.Mock(family=__import__("socket").AF_INET, address="127.0.0.1"),
        ]
        addrs = {"lo": lo_addrs, "eth0": eth_addrs}
        stats = {
            "lo": mock.Mock(isup=True),
            "eth0": mock.Mock(isup=True),
        }

        with mock.patch("controller.lib.network_info.psutil.net_if_addrs", return_value=addrs), \
             mock.patch("controller.lib.network_info.psutil.net_if_stats", return_value=stats), \
             mock.patch("controller.lib.network_info.socket.gethostname", return_value="wrolpi"):
            info = get_network_info()

        assert info["hostname"] == "wrolpi"
        assert info["primary_ipv4"] == "192.168.1.10"
        assert any(i["name"] == "eth0" and "192.168.1.10" in i["ipv4"] for i in info["interfaces"])
        assert not any(i["name"] == "lo" for i in info["interfaces"])
