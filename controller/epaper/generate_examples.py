#!/usr/bin/env python3
"""Generate example carousel frames (large type, action on → row)."""

from __future__ import annotations

from pathlib import Path

from controller.epaper.nav import NavState, page_layout
from controller.epaper.qr import make_wifi_qr_image
from controller.epaper.render import image_to_bytes, render_page

OUT = Path(__file__).resolve().parent / "examples"
W, H = 264, 176


def save(name: str, state: NavState) -> Path:
    layout = page_layout(state)
    if state.page_index == 0 and state.status_hotspot:
        layout.qr_image = make_wifi_qr_image(
            state.status_hotspot["ssid"],
            state.status_hotspot.get("password") or "",
            max_size=100,
        )
        layout.qr_caption = "Scan WiFi"
    img = render_page(layout, width=W, height=H)
    path = OUT / f"{name}.png"
    path.write_bytes(image_to_bytes(img))
    print(f"  {path}")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    feats = {"hotspot": True, "ssh": True, "desktop": False, "wrol_mode": False}

    s = NavState(
        page_index=0,
        status_lines=[
            "up 3d4h",
            "CPU 42%  51C",
            "Mem 1.2G/7.8G",
            "Disk 45%",
            "wrolpi",
            "10.0.0.8",
            "HS WROLPi",
            "AP 10.42.0.1",
        ],
        status_hotspot={"ssid": "WROLPi", "password": "wrolpi hotspot"},
        feature_enabled=feats,
        network_lines=["wrolpi", "eth0 10.0.0.8", "wlan0 10.42.0.1", "docker0 172.17.0.1"],
    )
    save("01_dashboard_hotspot", s)

    s.page_index = 1
    save("03_network", s)

    s.page_index = 2
    s.feature_enabled = dict(feats)
    save("04_hotspot_on", s)
    s.feature_enabled["hotspot"] = False
    save("05_hotspot_off", s)

    s.page_index = 3
    s.feature_enabled["ssh"] = True
    save("06_ssh", s)

    s.page_index = 6
    save("09_reboot", s)

    print("done")


if __name__ == "__main__":
    main()
