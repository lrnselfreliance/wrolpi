"""WiFi QR codes for the e-paper status dashboard."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import segno
except ImportError:  # pragma: no cover
    segno = None  # type: ignore

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


def _escape_wifi_field(value: str) -> str:
    """Escape special characters in WIFI: QR fields (\\, ;, ,, \", :)."""
    out = []
    for ch in value:
        if ch in ("\\", ";", ",", '"', ":"):
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def wifi_qr_payload(ssid: str, password: str, auth: str = "WPA") -> str:
    """
    Build a standard WiFi network QR payload.

    Phones open this as "join network" when scanned.
    Format: WIFI:T:WPA;S:<ssid>;P:<password>;;
    """
    if not ssid:
        raise ValueError("ssid is required")
    # Open networks use T:nopass and empty P
    t = auth if password else "nopass"
    s = _escape_wifi_field(ssid)
    if t == "nopass":
        return f"WIFI:T:nopass;S:{s};;"
    p = _escape_wifi_field(password)
    return f"WIFI:T:{t};S:{s};P:{p};;"


def make_wifi_qr_image(
    ssid: str,
    password: str,
    *,
    max_size: int = 100,
    min_scale: int = 2,
    preferred_scale: int = 3,
    border: int = 1,
) -> Optional["Image.Image"]:
    """
    Render a 1-bit WiFi QR image that fits within max_size×max_size.

    Prefers preferred_scale (3) for scannability; falls back to min_scale (2).
    Returns None if segno/Pillow missing or generation fails.
    """
    if segno is None or Image is None:
        logger.warning("segno/Pillow not available; cannot render WiFi QR")
        return None
    try:
        payload = wifi_qr_payload(ssid, password)
        qr = segno.make(payload, error="m")
    except Exception as e:
        logger.warning("Failed to build WiFi QR: %s", e)
        return None

    for scale in (preferred_scale, min_scale, 1):
        if scale < 1:
            continue
        try:
            buf = BytesIO()
            qr.save(buf, kind="png", scale=scale, border=border, dark="black", light="white")
            buf.seek(0)
            img = Image.open(buf).convert("1")
        except Exception as e:
            logger.warning("QR save failed scale=%s: %s", scale, e)
            continue
        if img.size[0] <= max_size and img.size[1] <= max_size:
            return img
        # Too big for this scale; try smaller
    # Last resort: return smallest even if slightly over (caller can skip)
    try:
        buf = BytesIO()
        qr.save(buf, kind="png", scale=min_scale, border=border, dark="black", light="white")
        buf.seek(0)
        return Image.open(buf).convert("1")
    except Exception:
        return None


def qr_fits(qr_size: Tuple[int, int], panel_height: int, header: int = 18, caption: int = 12) -> bool:
    """Whether a QR of qr_size fits under the header with optional caption."""
    return header + qr_size[1] + caption <= panel_height
