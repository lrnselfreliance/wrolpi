"""
SSH service control for WROLPi Controller.

Fail-open design: endpoints only start/stop the unit at runtime.
They never `systemctl enable` or `systemctl disable`, so a stopped SSH
daemon returns after reboot if the unit remains enabled at boot.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from controller.lib.config import is_docker_mode

logger = logging.getLogger(__name__)

# Debian / Raspberry Pi OS use "ssh"; some distros use "sshd".
_CANDIDATE_UNITS = ("ssh", "sshd")


def _systemctl(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def resolve_ssh_unit() -> Optional[str]:
    """
    Return the installed SSH systemd unit name, or None if not found.
    """
    for unit in _CANDIDATE_UNITS:
        try:
            result = _systemctl("show", "-p", "LoadState", "--value", unit, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if result.returncode == 0 and result.stdout.strip() not in ("", "not-found"):
            return unit
    return None


def _is_active(unit: str) -> bool:
    try:
        result = _systemctl("is-active", unit, timeout=5)
        return result.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _is_enabled_at_boot(unit: str) -> bool:
    try:
        result = _systemctl("is-enabled", unit, timeout=5)
        # enabled / enabled-runtime / static can all mean "will start somehow"
        state = result.stdout.strip()
        return state in ("enabled", "enabled-runtime", "static", "indirect")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_ssh_status_dict() -> dict:
    """
    SSH status for API responses.

    enabled: True when the daemon is currently running (UI "ON").
    enabled_at_boot: informational only; toggles never change this.
    """
    if is_docker_mode():
        return {
            "enabled": False,
            "enabled_at_boot": False,
            "available": False,
            "reason": "Not available in Docker mode",
            "unit": None,
        }

    unit = resolve_ssh_unit()
    if not unit:
        return {
            "enabled": False,
            "enabled_at_boot": False,
            "available": False,
            "reason": "SSH service not installed",
            "unit": None,
        }

    active = _is_active(unit)
    return {
        "enabled": active,
        "enabled_at_boot": _is_enabled_at_boot(unit),
        "available": True,
        "reason": None,
        "unit": unit,
    }


def start_ssh() -> dict:
    """Start SSH for the current session only (no enable)."""
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit = resolve_ssh_unit()
    if not unit:
        return {"success": False, "error": "SSH service not installed"}

    try:
        result = _systemctl("start", unit)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "systemctl not found"}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Failed to start SSH").strip()
        logger.warning("Failed to start SSH (%s): %s", unit, err)
        return {"success": False, "error": err}

    logger.info("SSH started (unit=%s, runtime only)", unit)
    return {"success": True, "error": None}


def stop_ssh() -> dict:
    """
    Stop SSH for the current session only (no disable).

    After reboot the unit starts again if still enabled at boot (fail open).
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit = resolve_ssh_unit()
    if not unit:
        return {"success": False, "error": "SSH service not installed"}

    try:
        result = _systemctl("stop", unit)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "systemctl not found"}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Failed to stop SSH").strip()
        logger.warning("Failed to stop SSH (%s): %s", unit, err)
        return {"success": False, "error": err}

    logger.info("SSH stopped (unit=%s, runtime only — returns on reboot)", unit)
    return {"success": True, "error": None}


# API-facing aliases matching hotspot enable/disable naming.
enable_ssh = start_ssh
disable_ssh = stop_ssh
