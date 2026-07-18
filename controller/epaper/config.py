"""E-paper process configuration (env + defaults)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class EpaperConfig:
    """Runtime settings for the e-paper UI process."""

    controller_base_url: str = "http://127.0.0.1"
    # Status auto-refresh on home screen (e-paper friendly).
    status_refresh_seconds: float = 90.0
    # After a button action, re-poll sooner.
    action_refresh_seconds: float = 2.0
    # Waveshare 2.7" landscape: 264 x 176
    width: int = 264
    height: int = 176
    # KEY1–KEY4 top→bottom: Up, Down, Select, Back
    pin_up: int = 5
    pin_down: int = 6
    pin_select: int = 13
    pin_back: int = 19
    # Mock mode writes frames to disk (no SPI/GPIO).
    mock: bool = False
    mock_frame_path: str = "/tmp/wrolpi-epaper.png"
    debounce_seconds: float = 0.08


def load_config() -> EpaperConfig:
    env_mock = os.environ.get("WROLPI_EPAPER_MOCK", "").lower()
    if env_mock in ("1", "true", "yes"):
        mock = True
    elif env_mock in ("0", "false", "no"):
        mock = False
    else:
        # Default: hardware on Linux (RPi), mock elsewhere.
        mock = sys.platform != "linux"

    base = os.environ.get("WROLPI_CONTROLLER_URL", "http://127.0.0.1").rstrip("/")
    return EpaperConfig(
        controller_base_url=base,
        mock=mock,
        mock_frame_path=os.environ.get("WROLPI_EPAPER_FRAME", "/tmp/wrolpi-epaper.png"),
        status_refresh_seconds=float(os.environ.get("WROLPI_EPAPER_REFRESH", "90")),
        pin_up=int(os.environ.get("WROLPI_EPAPER_PIN_UP", "5")),
        pin_down=int(os.environ.get("WROLPI_EPAPER_PIN_DOWN", "6")),
        pin_select=int(os.environ.get("WROLPI_EPAPER_PIN_SELECT", "13")),
        pin_back=int(os.environ.get("WROLPI_EPAPER_PIN_BACK", "19")),
    )
