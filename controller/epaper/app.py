"""
Main e-paper UI loop.

Carousel: Dashboard → Network → Hotspot → SSH → Desktop → WROL → Reboot → Shutdown
Buttons (KEY1–KEY4): ↑ page-prev, ↓ page-next, → action, ↺ dashboard.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import List, Optional

from controller.epaper.client import ControllerClient
from controller.epaper.config import EpaperConfig, load_config
from controller.epaper.display import open_display
from controller.epaper.nav import (
    FEATURE_KEYS,
    Button,
    NavState,
    current_page,
    handle_button,
    page_layout,
)
from controller.epaper.qr import make_wifi_qr_image
from controller.epaper.render import render_page

logger = logging.getLogger(__name__)


def _format_bytes(n: Optional[int]) -> str:
    if n is None:
        return "--"
    gb = n / (1024 ** 3)
    if gb >= 10:
        return f"{gb:.0f}G"
    return f"{gb:.1f}G"


def _iface_ipv4(net: dict, name: str) -> Optional[str]:
    if not name:
        return None
    for iface in net.get("interfaces") or []:
        if iface.get("name") == name:
            addrs = iface.get("ipv4") or []
            if addrs:
                return addrs[0]
    return None


def build_network_lines(net: dict) -> List[str]:
    """All non-empty interfaces for the Network page."""
    host = net.get("hostname") or ""
    lines: List[str] = []
    if host:
        lines.append(host)
    ifaces = net.get("interfaces") or []
    if not ifaces:
        lines.append("No interfaces")
        return lines
    for iface in ifaces:
        name = iface.get("name") or "?"
        addrs = iface.get("ipv4") or []
        up = iface.get("up")
        flag = "" if up else " down"
        if addrs:
            for addr in addrs:
                lines.append(f"{name} {addr}{flag}")
        else:
            lines.append(f"{name} —{flag}")
    return lines


def build_status_snapshot(client: ControllerClient) -> tuple[list[str], Optional[dict], list[str]]:
    """
    Returns:
        (status_lines, hotspot_credentials or None, network_lines)
    """
    try:
        stats = client.stats()
    except RuntimeError as e:
        return ["Controller offline", str(e)[:40]], None, ["Controller offline"]

    net: dict = {}
    try:
        net = client.network_info()
    except RuntimeError:
        pass

    network_lines = build_network_lines(net)

    cpu = stats.get("cpu_stats") or {}
    mem = stats.get("memory_stats") or {}
    drive = None
    for d in stats.get("drives_stats") or []:
        if d.get("mount") == "/media/wrolpi":
            drive = d
            break
    if not drive and stats.get("drives_stats"):
        drive = stats["drives_stats"][0]

    uptime = stats.get("uptime_stats") or {}
    up_s = uptime.get("uptime_seconds") or 0
    up_h = int(up_s // 3600)
    up_d = up_h // 24
    up_str = f"{up_d}d {up_h % 24}h" if up_d else f"{up_h}h"

    # Compact multi-field lines so dashboard fits beside the QR code.
    temp = cpu.get("temperature")
    if isinstance(temp, (int, float)):
        temp_s = f"{int(round(temp))}C"
    else:
        temp_s = "--C"
    cpu_pct = cpu.get("percent", "--")

    lines = [
        f"up {up_str}",
        f"CPU {cpu_pct}% {temp_s}",
        f"Mem {_format_bytes(mem.get('used'))}/{_format_bytes(mem.get('total'))}",
    ]
    if drive:
        lines.append(f"Disk {drive.get('percent', '--')}% {_format_bytes(drive.get('used'))}")
    else:
        lines.append("Disk --")

    ip = net.get("primary_ipv4") or "--"
    host = net.get("hostname") or ""
    if host and ip != "--":
        lines.append(f"{host}")
        lines.append(f"{ip}")
    elif host:
        lines.append(host)
    elif ip != "--":
        lines.append(str(ip))

    hotspot_creds: Optional[dict] = None
    try:
        hs = client.feature_status("hotspot")
        if bool(hs.get("enabled")):
            try:
                settings = client.hotspot_settings()
                ssid = settings.get("ssid") or hs.get("ssid") or "WROLPi"
                password = settings.get("password") or ""
                hs_device = settings.get("device") or "wlan0"
                hotspot_creds = {"ssid": ssid, "password": password}
                ap_ip = _iface_ipv4(net, hs_device) or _iface_ipv4(net, "wlan0")
                if ap_ip:
                    lines.append(f"HS {ssid}")
                    lines.append(f"AP {ap_ip}")
                else:
                    lines.append(f"HS {ssid}")
            except RuntimeError:
                ap_ip = _iface_ipv4(net, "wlan0")
                lines.append("HS ON")
                if ap_ip:
                    lines.append(f"AP {ap_ip}")
        else:
            lines.append("HS off")
    except RuntimeError:
        lines.append("HS ?")

    bits = []
    for key, short in (("ssh", "SSH"), ("desktop", "Desk")):
        try:
            st = client.feature_status(key)
            bits.append(f"{short}:{'Y' if st.get('enabled') else 'N'}")
        except RuntimeError:
            bits.append(f"{short}:?")
    lines.append(" ".join(bits))

    return lines, hotspot_creds, network_lines


def refresh_features(client: ControllerClient, state: NavState) -> None:
    for key in FEATURE_KEYS:
        try:
            st = client.feature_status(key)
            state.feature_enabled[key] = bool(st.get("enabled"))
        except RuntimeError:
            state.feature_enabled[key] = None


def refresh_all(client: ControllerClient, state: NavState) -> None:
    lines, hotspot, network = build_status_snapshot(client)
    state.status_lines = lines
    state.status_hotspot = hotspot
    state.network_lines = network
    refresh_features(client, state)


def paint(display, state: NavState, cfg: EpaperConfig) -> None:
    layout = page_layout(state)
    page = current_page(state)
    if page.id == "dashboard" and state.status_hotspot:
        ssid = state.status_hotspot.get("ssid") or ""
        password = state.status_hotspot.get("password") or ""
        if ssid:
            layout.qr_image = make_wifi_qr_image(ssid, password, max_size=100)
            layout.qr_caption = "Scan WiFi"

    img = render_page(
        layout,
        width=cfg.width,
        height=cfg.height,
        button_labels=("↑", "↓", "→", "↺"),
    )
    display.show(img)
    display.sleep()


def execute_toggle(client: ControllerClient, state: NavState) -> None:
    key = state.pending_feature
    enable = state.pending_enable
    state.pending_feature = None
    state.pending_enable = None
    state.message = ""
    if not key or enable is None:
        return
    try:
        client.feature_set(key, bool(enable))
        refresh_features(client, state)
        state.flash = "Done" if enable else "Done"
        # Prefer a clear state flash
        state.flash = "Enabled" if state.feature_enabled.get(key) else "Disabled"
    except RuntimeError as e:
        state.flash = f"Err: {e}"[:28]
        refresh_features(client, state)


def execute_power(client: ControllerClient, state: NavState) -> None:
    action = state.pending_power
    state.pending_power = None
    state.message = ""
    if not action:
        return
    try:
        if action == "reboot":
            client.reboot()
            state.flash = "Rebooting…"
        else:
            client.shutdown()
            state.flash = "Shutting down…"
    except RuntimeError as e:
        state.flash = f"Err: {e}"[:28]


def _poll_buttons_mock(timeout: float) -> Optional[Button]:
    import select

    if not sys.stdin.isatty():
        time.sleep(min(timeout, 0.5))
        return None
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return None
    ch = sys.stdin.read(1)
    return {
        "u": Button.UP,
        "k": Button.UP,
        "d": Button.DOWN,
        "j": Button.DOWN,
        "s": Button.SELECT,
        "\n": Button.SELECT,
        "b": Button.BACK,
        "q": None,
    }.get(ch)


def _poll_buttons_gpio(cfg: EpaperConfig, timeout: float) -> Optional[Button]:
    """
    Waveshare 2.7\" HAT keys (BCM): KEY1=5, KEY2=6, KEY3=13, KEY4=19.
    """
    try:
        from gpiozero import Button as GpioButton
    except ImportError:
        logger.warning("gpiozero not available; no physical buttons")
        time.sleep(timeout)
        return None

    global _GPIO_BTNS
    if _GPIO_BTNS is None:
        kwargs = dict(pull_up=True, bounce_time=cfg.debounce_seconds)
        _GPIO_BTNS = {
            Button.UP: GpioButton(cfg.pin_up, **kwargs),
            Button.DOWN: GpioButton(cfg.pin_down, **kwargs),
            Button.SELECT: GpioButton(cfg.pin_select, **kwargs),
            Button.BACK: GpioButton(cfg.pin_back, **kwargs),
        }
        logger.info(
            "HAT buttons: ↑=GPIO%d ↓=GPIO%d →=GPIO%d ↺=GPIO%d",
            cfg.pin_up,
            cfg.pin_down,
            cfg.pin_select,
            cfg.pin_back,
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, btn in _GPIO_BTNS.items():
            if btn.is_pressed:
                t_rel = time.monotonic() + 0.5
                while btn.is_pressed and time.monotonic() < t_rel:
                    time.sleep(0.01)
                return name
        time.sleep(0.02)
    return None


_GPIO_BTNS = None


def run(cfg: Optional[EpaperConfig] = None) -> int:
    cfg = cfg or load_config()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info(
        "Starting e-paper UI (mock=%s, controller=%s)",
        cfg.mock,
        cfg.controller_base_url,
    )

    client = ControllerClient(cfg.controller_base_url)
    display = open_display(cfg.mock, cfg.mock_frame_path)
    state = NavState()
    running = True

    def _stop(*_args):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    refresh_all(client, state)
    paint(display, state, cfg)
    last_status = time.monotonic()

    while running:
        on_dashboard = current_page(state).id == "dashboard"
        timeout = cfg.status_refresh_seconds if on_dashboard else 60.0
        if cfg.mock:
            btn = _poll_buttons_mock(min(timeout, 1.0) if not sys.stdin.isatty() else timeout)
        else:
            btn = _poll_buttons_gpio(cfg, timeout)

        if btn is None:
            if on_dashboard and (time.monotonic() - last_status) >= cfg.status_refresh_seconds:
                refresh_all(client, state)
                paint(display, state, cfg)
                last_status = time.monotonic()
            continue

        logger.info("Button: %s page=%s", btn.value, current_page(state).id)
        state = handle_button(state, btn)

        if state.message == "refresh":
            state.message = ""
            refresh_all(client, state)
            last_status = time.monotonic()
            paint(display, state, cfg)
            continue

        if state.message == "toggle":
            # Stay on the feature page; apply then repaint with new state.
            execute_toggle(client, state)
            time.sleep(cfg.action_refresh_seconds)
            refresh_all(client, state)
            paint(display, state, cfg)
            continue

        if state.message == "power":
            execute_power(client, state)
            paint(display, state, cfg)
            continue

        # Page change or no-op select: refresh feature cache when landing on toggle pages
        page = current_page(state)
        if page.feature:
            refresh_features(client, state)
        if page.id in ("dashboard", "network"):
            refresh_all(client, state)
            last_status = time.monotonic()

        paint(display, state, cfg)

    display.close()
    logger.info("e-paper UI stopped")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
