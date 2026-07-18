"""Carousel navigation tests (no hardware)."""

from controller.epaper.nav import (
    PAGES,
    Button,
    NavState,
    current_page,
    handle_button,
    page_lines,
)


class TestCarousel:
    def test_down_wraps_through_pages(self):
        s = NavState(page_index=0)
        assert current_page(s).id == "dashboard"
        s = handle_button(s, Button.DOWN)
        assert current_page(s).id == "network"
        s = handle_button(s, Button.DOWN)
        assert current_page(s).id == "hotspot"

    def test_up_from_dashboard_wraps_to_last(self):
        s = NavState(page_index=0)
        s = handle_button(s, Button.UP)
        assert current_page(s).id == PAGES[-1].id
        assert current_page(s).id == "shutdown"

    def test_back_always_dashboard(self):
        s = NavState(page_index=3)  # ssh
        s = handle_button(s, Button.BACK)
        assert s.page_index == 0
        assert current_page(s).id == "dashboard"
        assert s.message == ""

    def test_back_on_dashboard_refreshes(self):
        s = NavState(page_index=0)
        s = handle_button(s, Button.BACK)
        assert s.page_index == 0
        assert s.message == "refresh"

    def test_select_on_dashboard_refreshes(self):
        s = NavState(page_index=0)
        s = handle_button(s, Button.SELECT)
        assert s.message == "refresh"


class TestToggles:
    def test_hotspot_select_toggles_on(self):
        s = NavState(page_index=2, feature_enabled={"hotspot": False})  # hotspot
        assert current_page(s).feature == "hotspot"
        s = handle_button(s, Button.SELECT)
        assert s.message == "toggle"
        assert s.pending_feature == "hotspot"
        assert s.pending_enable is True
        # Stay on hotspot page
        assert current_page(s).id == "hotspot"

    def test_ssh_select_toggles_off(self):
        idx = next(i for i, p in enumerate(PAGES) if p.id == "ssh")
        s = NavState(page_index=idx, feature_enabled={"ssh": True})
        s = handle_button(s, Button.SELECT)
        assert s.pending_enable is False
        assert s.message == "toggle"

    def test_page_lines_show_action(self):
        from controller.epaper.nav import page_layout

        s = NavState(page_index=2, feature_enabled={"hotspot": True})
        layout = page_layout(s)
        assert any("Enabled" in ln for ln in layout.body)
        assert layout.action == "Disable"


class TestPower:
    def test_reboot_select_powers(self):
        idx = next(i for i, p in enumerate(PAGES) if p.id == "reboot")
        s = NavState(page_index=idx)
        s = handle_button(s, Button.SELECT)
        assert s.message == "power"
        assert s.pending_power == "reboot"

    def test_back_from_reboot_to_dashboard(self):
        idx = next(i for i, p in enumerate(PAGES) if p.id == "reboot")
        s = NavState(page_index=idx)
        s = handle_button(s, Button.BACK)
        assert current_page(s).id == "dashboard"


class TestNetworkLines:
    def test_network_page_uses_network_lines(self):
        s = NavState(
            page_index=1,
            network_lines=["wrolpi", "eth0 10.0.0.8", "wlan0 10.42.0.1"],
        )
        lines = page_lines(s)
        assert "eth0 10.0.0.8" in lines
        assert "wlan0 10.42.0.1" in lines
