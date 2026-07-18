"""
WROL Mode for WROLPi Controller.

WROL Mode (Without Rule of Law) is an emergency mode that restricts
persistent configuration changes and (via the main API) stops downloads.

Sources of truth (kept in sync when Controller toggles):
1. Flag file ``/media/wrolpi/config/.wrol_mode`` — Controller mount/fstab guards
2. ``wrolpi.yaml`` key ``wrol_mode`` — main WROLPi API

When reading, prefer ``wrolpi.yaml`` if the file exists and the key is present;
otherwise fall back to the flag file. When writing, update both (and best-effort
notify the main API so the download manager reacts immediately).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from controller.lib.config import get_media_directory, is_docker_mode

logger = logging.getLogger(__name__)

# Main API settings endpoint (native install; behind Caddy or direct).
# Controller runs on port 80; API on 8081 by default.
_DEFAULT_API_SETTINGS_URL = "http://127.0.0.1:8081/api/settings"


def get_wrol_mode_flag_path() -> Path:
    """Get the path to the WROL Mode flag file."""
    return get_media_directory() / "config" / ".wrol_mode"


def get_wrolpi_yaml_path() -> Path:
    """Path to the main app's wrolpi.yaml config."""
    return get_media_directory() / "config" / "wrolpi.yaml"


def _read_yaml_wrol_mode() -> Optional[bool]:
    """
    Read wrol_mode from wrolpi.yaml if present.

    Returns:
        True/False if the key is set, None if file missing or key absent.
    """
    path = get_wrolpi_yaml_path()
    if not path.exists():
        return None
    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        logger.warning("Failed to read wrolpi.yaml for wrol_mode: %s", e)
        return None
    if "wrol_mode" not in config:
        return None
    return bool(config.get("wrol_mode"))


def _write_yaml_wrol_mode(enabled: bool) -> bool:
    """
    Patch wrol_mode in wrolpi.yaml if the file exists.

    Returns True if written (or already correct), False if file missing / error.
    Does not create wrolpi.yaml from scratch (that belongs to the main app).
    """
    path = get_wrolpi_yaml_path()
    if not path.exists():
        logger.info("wrolpi.yaml not found; skipping yaml wrol_mode write")
        return False
    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {}
        if "wrol_mode" in config and bool(config.get("wrol_mode")) == bool(enabled):
            return True
        config["wrol_mode"] = bool(enabled)
        with open(path, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info("Wrote wrol_mode=%s to wrolpi.yaml", enabled)
        return True
    except (IOError, yaml.YAMLError, OSError) as e:
        logger.warning("Failed to write wrol_mode to wrolpi.yaml: %s", e)
        return False


def _set_flag_file(enabled: bool) -> None:
    path = get_wrol_mode_flag_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        logger.info("Created WROL Mode flag file at %s", path)
    else:
        if path.exists():
            path.unlink()
            logger.info("Removed WROL Mode flag file at %s", path)


def is_wrol_mode() -> bool:
    """
    Check if WROL Mode is active.

    Prefers wrolpi.yaml when the key is present; otherwise uses the flag file.
    """
    yaml_value = _read_yaml_wrol_mode()
    if yaml_value is not None:
        return yaml_value
    return get_wrol_mode_flag_path().exists()


def require_normal_mode(operation: str) -> None:
    """
    Raise an error if WROL Mode is active.

    Use this to guard persistent operations that shouldn't be
    allowed during emergencies.

    Args:
        operation: Description of the operation being attempted

    Raises:
        PermissionError: If WROL Mode is active
    """
    if is_wrol_mode():
        raise PermissionError(
            f"Cannot {operation} while WROL Mode is active. "
            "Disable WROL Mode to make persistent changes."
        )


def get_wrol_mode_status_dict() -> dict:
    """Status dict for API responses."""
    yaml_value = _read_yaml_wrol_mode()
    flag = get_wrol_mode_flag_path().exists()
    enabled = is_wrol_mode()
    return {
        "enabled": enabled,
        "available": True,
        "reason": None,
        "flag_file": flag,
        "yaml_value": yaml_value,
    }


def _notify_main_api(enabled: bool) -> Optional[str]:
    """
    Best-effort PATCH to main API so download manager reacts immediately.

    Returns error string if the call failed, else None.
    """
    try:
        import urllib.error
        import urllib.request
        import json

        body = json.dumps({"wrol_mode": enabled}).encode()
        req = urllib.request.Request(
            _DEFAULT_API_SETTINGS_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                return f"API returned HTTP {resp.status}"
        return None
    except Exception as e:
        logger.info("Could not notify main API of wrol_mode change: %s", e)
        return str(e)


def enable_wrol_mode() -> dict:
    """
    Enable WROL Mode: flag file + yaml + best-effort API notify.
    """
    if is_docker_mode():
        # Still allow writing flag/yaml if media is mounted in docker? Plan said
        # admin ops often 500 in docker; flag/yaml on mounted media is useful.
        # Keep available — docker still can have media mount for tests.
        pass

    try:
        _set_flag_file(True)
        yaml_ok = _write_yaml_wrol_mode(True)
        api_error = _notify_main_api(True)
        return {
            "success": True,
            "error": None,
            "yaml_updated": yaml_ok,
            "api_notified": api_error is None,
            "api_error": api_error,
        }
    except OSError as e:
        logger.exception("Failed to enable WROL Mode")
        return {"success": False, "error": str(e)}


def disable_wrol_mode() -> dict:
    """
    Disable WROL Mode: remove flag + yaml + best-effort API notify.
    """
    try:
        _set_flag_file(False)
        yaml_ok = _write_yaml_wrol_mode(False)
        api_error = _notify_main_api(False)
        return {
            "success": True,
            "error": None,
            "yaml_updated": yaml_ok,
            "api_notified": api_error is None,
            "api_error": api_error,
        }
    except OSError as e:
        logger.exception("Failed to disable WROL Mode")
        return {"success": False, "error": str(e)}
