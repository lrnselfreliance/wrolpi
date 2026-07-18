"""
Carousel navigation for the e-paper HAT.

Buttons (KEY1–KEY4 top→bottom):
  ↑  previous page
  ↓  next page
  →  horizontal action (toggle / confirm power)
  ↺  always return to dashboard (refresh if already there)

No nested menus or confirm dialogs — landing on a page is the confirmation
context; → applies the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class Button(str, Enum):
    UP = "up"
    DOWN = "down"
    SELECT = "select"  # → horizontal action
    BACK = "back"  # ↺ home


@dataclass(frozen=True)
class Page:
    id: str
    title: str
    # Optional feature key for Controller toggle APIs
    feature: Optional[str] = None
    # Optional power action: reboot | shutdown
    power: Optional[str] = None


# Dashboard is page 0 and included in the carousel (wraps).
PAGES: Tuple[Page, ...] = (
    Page("dashboard", "WROLPi"),
    Page("network", "Network"),
    Page("hotspot", "Hotspot", feature="hotspot"),
    Page("ssh", "SSH", feature="ssh"),
    Page("desktop", "Desktop", feature="desktop"),
    Page("wrol_mode", "WROL Mode", feature="wrol_mode"),
    Page("reboot", "Reboot", power="reboot"),
    Page("shutdown", "Shutdown", power="shutdown"),
)


@dataclass
class NavState:
    page_index: int = 0
    # App-layer signals: "" | "refresh" | "toggle" | "power"
    message: str = ""
    # Feature key to toggle when message == "toggle"
    pending_feature: Optional[str] = None
    pending_enable: Optional[bool] = None
    # Power action when message == "power"
    pending_power: Optional[str] = None
    # Cached feature enabled flags (name -> bool|None)
    feature_enabled: dict = field(default_factory=dict)
    # Dashboard snapshot
    status_lines: List[str] = field(default_factory=list)
    status_hotspot: Optional[dict] = None
    # Network page lines (all interfaces)
    network_lines: List[str] = field(default_factory=list)
    error: Optional[str] = None
    # Short flash text after an action (cleared on page change)
    flash: str = ""


def current_page(state: NavState) -> Page:
    if not PAGES:
        raise RuntimeError("no pages")
    return PAGES[state.page_index % len(PAGES)]


def go_dashboard(state: NavState, *, refresh: bool = False) -> NavState:
    state.page_index = 0
    state.flash = ""
    state.pending_feature = None
    state.pending_enable = None
    state.pending_power = None
    state.message = "refresh" if refresh else ""
    return state


def handle_button(state: NavState, button: Button) -> NavState:
    """Apply a button press; mutates and returns state."""
    state.error = None
    state.message = ""
    n = len(PAGES)

    if button == Button.BACK:
        # Always home. On dashboard, force a status refresh.
        already_home = (state.page_index % n) == 0
        return go_dashboard(state, refresh=already_home)

    if button == Button.UP:
        state.page_index = (state.page_index - 1) % n
        state.flash = ""
        return state

    if button == Button.DOWN:
        state.page_index = (state.page_index + 1) % n
        state.flash = ""
        return state

    if button == Button.SELECT:
        page = current_page(state)
        if page.id == "dashboard":
            state.message = "refresh"
            return state
        if page.id == "network":
            return state
        if page.feature:
            currently = state.feature_enabled.get(page.feature)
            target = not currently if currently is not None else True
            state.pending_feature = page.feature
            state.pending_enable = target
            state.message = "toggle"
            return state
        if page.power:
            state.pending_power = page.power
            state.message = "power"
            return state

    return state


def _state_label(enabled: Optional[bool]) -> str:
    if enabled is True:
        return "Enabled"
    if enabled is False:
        return "Disabled"
    return "Unknown"


def page_layout(state: NavState):
    """
    Structured layout for rendering.

    ``action`` is drawn on the → button row (no leading arrow — rail has →).
    """
    # Local import avoids circular deps with render at module load in tests
    from controller.epaper.render import PageLayout

    page = current_page(state)
    flash = state.flash

    if page.id == "dashboard":
        body = list(state.status_lines) if state.status_lines else ["Loading…"]
        if flash:
            body.append(flash)
        return PageLayout(title=page.title, body=body)

    if page.id == "network":
        body = list(state.network_lines) if state.network_lines else ["No interfaces"]
        if flash:
            body = [flash] + body
        return PageLayout(title=page.title, body=body)

    if page.feature:
        en = state.feature_enabled.get(page.feature)
        label = _state_label(en)
        if en is True:
            action = "Disable"
            if page.feature in ("ssh", "desktop"):
                action = "Stop til reboot"
        elif en is False:
            action = "Enable"
            if page.feature in ("ssh", "desktop"):
                action = "Start"
        else:
            action = "Toggle"

        body = [label]
        if page.feature in ("ssh", "desktop"):
            body.append("(runtime only)")
        if flash:
            body.append(flash)
        return PageLayout(title=page.title, body=body, action=action)

    if page.power == "reboot":
        body = ["Reboot the system?"]
        if flash:
            body.append(flash)
        return PageLayout(
            title=page.title,
            body=body,
            action="Yes, reboot",
            sub_action="Home cancels",
        )

    if page.power == "shutdown":
        body = ["Shutdown the system?"]
        if flash:
            body.append(flash)
        return PageLayout(
            title=page.title,
            body=body,
            action="Yes, shutdown",
            sub_action="Home cancels",
        )

    return PageLayout(title=page.title, body=[page.title])


def page_lines(state: NavState) -> List[str]:
    """Flat lines for tests / simple consumers."""
    layout = page_layout(state)
    lines = list(layout.body)
    if layout.action:
        lines.append(layout.action)
    if layout.sub_action:
        lines.append(layout.sub_action)
    return lines


def page_title(state: NavState) -> str:
    return current_page(state).title


# Feature keys for refresh loops
FEATURE_KEYS: Tuple[str, ...] = tuple(p.feature for p in PAGES if p.feature)
