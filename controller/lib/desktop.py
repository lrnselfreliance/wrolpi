"""
Desktop / display-manager control for WROLPi Controller.

Fail-open design: endpoints only start/stop the display manager at runtime.
They never change the systemd default target (graphical vs multi-user), so
the desktop returns after reboot if the image still boots to graphical.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from controller.lib.config import is_docker_mode

logger = logging.getLogger(__name__)

# Prefer the distro alias, then common concrete units.
_CANDIDATE_UNITS = ("display-manager", "lightdm", "gdm3", "gdm", "sddm")


def _systemctl(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def resolve_display_manager_unit() -> Optional[str]:
    """Return an installed display-manager unit name, or None."""
    for unit in _CANDIDATE_UNITS:
        try:
            result = _systemctl("show", "-p", "LoadState", "--value", unit, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if result.returncode == 0 and result.stdout.strip() not in ("", "not-found"):
            return unit
    return None


def get_default_target() -> Optional[str]:
    """Return the systemd default target name if available."""
    try:
        result = _systemctl("get-default", timeout=5)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _is_active(unit: str) -> bool:
    try:
        result = _systemctl("is-active", unit, timeout=5)
        return result.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_desktop_status_dict() -> dict:
    """
    Desktop status for API responses.

    enabled: True when the display manager is currently running (UI "ON").
    default_target: informational only; toggles never change this.
    """
    if is_docker_mode():
        return {
            "enabled": False,
            "default_target": None,
            "available": False,
            "reason": "Not available in Docker mode",
            "unit": None,
        }

    unit = resolve_display_manager_unit()
    if not unit:
        return {
            "enabled": False,
            "default_target": get_default_target(),
            "available": False,
            "reason": "No display manager installed",
            "unit": None,
        }

    return {
        "enabled": _is_active(unit),
        "default_target": get_default_target(),
        "available": True,
        "reason": None,
        "unit": unit,
    }


def start_desktop() -> dict:
    """Start the display manager for this session only (no set-default)."""
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit = resolve_display_manager_unit()
    if not unit:
        return {"success": False, "error": "No display manager installed"}

    try:
        result = _systemctl("start", unit)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "systemctl not found"}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Failed to start desktop").strip()
        logger.warning("Failed to start desktop (%s): %s", unit, err)
        return {"success": False, "error": err}

    logger.info("Desktop started (unit=%s, runtime only)", unit)
    return {"success": True, "error": None}


def stop_desktop() -> dict:
    """
    Stop the display manager for this session only (no set-default).

    After reboot the desktop returns if the default target remains graphical
    (fail open).
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit = resolve_display_manager_unit()
    if not unit:
        return {"success": False, "error": "No display manager installed"}

    try:
        result = _systemctl("stop", unit)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "systemctl not found"}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Failed to stop desktop").strip()
        logger.warning("Failed to stop desktop (%s): %s", unit, err)
        return {"success": False, "error": err}

    logger.info(
        "Desktop stopped (unit=%s, runtime only — returns on reboot if graphical default)",
        unit,
    )
    return {"success": True, "error": None}


# API-facing aliases matching hotspot enable/disable naming.
enable_desktop = start_desktop
disable_desktop = stop_desktop
