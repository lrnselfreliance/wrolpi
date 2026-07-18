"""Pillow-based 1-bit frame rendering for 264x176 e-paper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

# Physical KEY1–KEY4 are a vertical column on the left of the HAT.
# Carousel: prev page / next page / action / home
DEFAULT_BUTTON_LABELS: Tuple[str, str, str, str] = ("↑", "↓", "→", "↺")

# Width reserved for the button rail (including separator).
RAIL_WIDTH = 22

# Larger type for readability on 2.7" e-paper
FONT_TITLE = 16
FONT_BODY = 16
FONT_ACTION = 18
FONT_SMALL = 12
FONT_RAIL = 16


def _font(size: int = 14):
    if ImageFont is None:
        return None
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(draw, text: str, font) -> Tuple[int, int]:
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return draw.textsize(text, font=font)


def band_geometry(height: int, n: int = 4) -> List[Tuple[int, int, int]]:
    """Return (top, bottom, mid) for each of n equal vertical bands."""
    out = []
    for i in range(n):
        top = int(i * height / n)
        bot = int((i + 1) * height / n)
        mid = (top + bot) // 2
        out.append((top, bot, mid))
    return out


def draw_button_rail(
    draw,
    height: int,
    labels: Sequence[str] = DEFAULT_BUTTON_LABELS,
    rail_width: int = RAIL_WIDTH,
    font=None,
) -> None:
    font = font or _font(FONT_RAIL)
    n = len(labels)
    if n == 0:
        return

    draw.line((rail_width - 1, 0, rail_width - 1, height - 1), fill=0)

    for i, label in enumerate(labels):
        band_top, band_bot, band_mid = band_geometry(height, n)[i]
        tw, th = _text_size(draw, label, font)
        x = max(0, (rail_width - 1 - tw) // 2)
        y = band_mid - th // 2
        draw.text((x, y), label, font=font, fill=0)
        if i < n - 1:
            draw.line((2, band_bot, rail_width - 4, band_bot), fill=0)


@dataclass
class PageLayout:
    """
    Structured page for carousel rendering.

    ``action`` is drawn vertically centered on the → button band so users
    reach for KEY3. ``body`` fills the area above that band.
    """

    title: str = ""
    body: List[str] = field(default_factory=list)
    action: Optional[str] = None  # aligned with →
    sub_action: Optional[str] = None  # smaller line under action / near ↺
    qr_image: Optional["Image.Image"] = None
    qr_caption: Optional[str] = None


def render_page(
    layout: PageLayout,
    width: int = 264,
    height: int = 176,
    button_labels: Sequence[str] = DEFAULT_BUTTON_LABELS,
) -> "Image.Image":
    """
    Render a carousel page: body text + optional action on the → band.

    Dashboard (no action) uses the full content height so status lines are not
    clipped. Action pages reserve the lower half for the → / ↺ rows.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for e-paper rendering (pip install Pillow)")

    img = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(img)

    has_action = bool(layout.action)
    # Dashboard packs more lines; use slightly smaller body type when dense / QR.
    dense = (not has_action) and (len(layout.body) >= 6 or layout.qr_image is not None)
    body_size = 13 if dense else FONT_BODY
    line_gap = 2 if dense else 4

    font_title = _font(FONT_TITLE)
    font_body = _font(body_size)
    font_action = _font(FONT_ACTION)
    font_sm = _font(FONT_SMALL)
    font_rail = _font(FONT_RAIL)

    content_left = RAIL_WIDTH + 4
    draw_button_rail(draw, height, labels=button_labels, font=font_rail)

    bands = band_geometry(height, 4)
    action_top, action_bot, action_mid = bands[2]
    home_top, home_bot, home_mid = bands[3]

    # Place QR first so we know content width (top-right, under header).
    header_h = 22 if layout.title else 0
    qr_left = width
    qr_bottom = header_h
    if layout.qr_image is not None:
        qw, qh = layout.qr_image.size
        qx = width - qw - 2
        qy = header_h + 2
        # Prefer QR that fits; shrink via nearest if taller than remaining height
        max_qr_h = height - qy - 16
        if qh > max_qr_h > 20:
            ratio = max_qr_h / qh
            new_w = max(40, int(qw * ratio))
            new_h = max_qr_h
            qr_img = layout.qr_image.convert("1").resize((new_w, new_h))
            qw, qh = new_w, new_h
        else:
            qr_img = layout.qr_image.convert("1")
        img.paste(qr_img, (qx, qy))
        qr_left = qx - 4
        qr_bottom = qy + qh
        if layout.qr_caption and qr_bottom + 12 < height:
            tw, _ = _text_size(draw, layout.qr_caption, font_sm)
            cap_x = qx + max(0, (qw - tw) // 2)
            draw.text((cap_x, qr_bottom + 1), layout.qr_caption, font=font_sm, fill=0)
            qr_bottom += 12

    content_right = qr_left - 2
    content_width = max(40, content_right - content_left)
    max_chars = max(8, int(content_width / (body_size * 0.52)))

    # Title bar only over the text column (do not paint over QR)
    y = 2
    if layout.title:
        bar_right = width if layout.qr_image is None else content_right + 2
        draw.rectangle((content_left - 2, 0, bar_right, header_h), fill=0)
        draw.text((content_left, 3), layout.title[:max_chars], font=font_title, fill=1)
        y = header_h + 3

    # Body: full height when no action; stop above → band when action present
    if has_action:
        body_limit = action_top - 4
    else:
        body_limit = height - 2

    line_h = body_size + line_gap
    for line in layout.body:
        if y + line_h > body_limit:
            break
        draw.text((content_left, y), line[:max_chars], font=font_body, fill=0)
        y += line_h

    if layout.action:
        draw.line((content_left - 2, action_top, width - 2, action_top), fill=0)
        aw, ah = _text_size(draw, layout.action, font_action)
        ay = action_mid - ah // 2
        ay = max(action_top + 2, min(ay, action_bot - ah - 2))
        pad_x, pad_y = 4, 3
        bar_right = min(width - 2, content_left + aw + pad_x * 2)
        draw.rectangle(
            (content_left - 2, ay - pad_y, bar_right, ay + ah + pad_y),
            fill=0,
        )
        draw.text((content_left + pad_x - 2, ay), layout.action[:max_chars], font=font_action, fill=1)

    if layout.sub_action:
        sw, sh = _text_size(draw, layout.sub_action, font_sm)
        sy = home_mid - sh // 2
        sy = max(home_top + 1, min(sy, home_bot - sh - 1))
        draw.text((content_left, sy), layout.sub_action[:max_chars], font=font_sm, fill=0)

    return img


def render_lines(
    lines: List[str],
    width: int = 264,
    height: int = 176,
    title: Optional[str] = None,
    footer: Optional[str] = None,
    button_labels: Sequence[str] = DEFAULT_BUTTON_LABELS,
    show_button_rail: bool = True,
    qr_image: Optional["Image.Image"] = None,
    qr_caption: Optional[str] = "Scan WiFi",
    action: Optional[str] = None,
    sub_action: Optional[str] = None,
) -> "Image.Image":
    """
    Back-compat wrapper: plain lines → PageLayout → render_page.
    If ``action`` is set, it is aligned with the → button band.
    """
    layout = PageLayout(
        title=title or "",
        body=list(lines),
        action=action,
        sub_action=sub_action or footer,
        qr_image=qr_image,
        qr_caption=qr_caption,
    )
    if not show_button_rail:
        # Rare path: still use render_page with empty rail labels
        return render_page(layout, width=width, height=height, button_labels=("", "", "", ""))
    return render_page(layout, width=width, height=height, button_labels=button_labels)


def image_to_bytes(img: "Image.Image") -> bytes:
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
