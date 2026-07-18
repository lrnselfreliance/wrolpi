"""Tests for WiFi QR helper and status rendering with QR."""

from controller.epaper.qr import make_wifi_qr_image, wifi_qr_payload
from controller.epaper.render import image_to_bytes, render_lines


class TestWifiQrPayload:
    def test_wpa_format(self):
        p = wifi_qr_payload("WROLPi", "wrolpi hotspot")
        assert p.startswith("WIFI:T:WPA;")
        assert "S:WROLPi;" in p
        assert "P:wrolpi hotspot;" in p
        assert p.endswith(";;")

    def test_escapes_special_chars(self):
        p = wifi_qr_payload('net;work', r'pass\word')
        assert r"S:net\;work;" in p
        assert r"P:pass\\word;" in p

    def test_open_network(self):
        p = wifi_qr_payload("OpenNet", "")
        assert "T:nopass" in p


class TestMakeWifiQrImage:
    def test_returns_1bit_image_within_max(self):
        img = make_wifi_qr_image("WROLPi", "wrolpi hotspot", max_size=100)
        assert img is not None
        assert img.mode == "1"
        assert img.size[0] <= 100
        assert img.size[1] <= 100

    def test_prefers_larger_when_space(self):
        small = make_wifi_qr_image("WROLPi", "wrolpi hotspot", max_size=70, preferred_scale=3, min_scale=2)
        large = make_wifi_qr_image("WROLPi", "wrolpi hotspot", max_size=100, preferred_scale=3, min_scale=2)
        assert small is not None and large is not None
        # With max 100, scale 3 should fit; with max 70, scale 2
        assert large.size[0] >= small.size[0]


class TestRenderWithQr:
    def test_status_with_qr_full_frame(self):
        lines = ["up 1h", "CPU 10%", "wrolpi", "192.168.1.1", "HS WROLPi"]
        qr = make_wifi_qr_image("WROLPi", "wrolpi hotspot", max_size=100)
        assert qr is not None
        with_qr = render_lines(lines, title="WROLPi", qr_image=qr, qr_caption="Scan WiFi")
        plain = render_lines(lines, title="WROLPi")
        assert with_qr.size == (264, 176)
        # QR adds ink; PNG payloads should differ
        assert image_to_bytes(with_qr) != image_to_bytes(plain)

    def test_no_qr_when_none(self):
        img = render_lines(["HS off"], title="WROLPi", qr_image=None)
        assert img.size == (264, 176)
