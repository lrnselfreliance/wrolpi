"""
Samba share management for WROLPi Controller.

Manages smb.conf generation, smbd/nmbd service control, and share CRUD.
Works in both native (systemd) and Docker modes.

The controller manages samba's lifecycle: samba is started when shares
are added and stopped when the last share is removed.
"""

import enum
import logging
import platform
import re
import subprocess
from pathlib import Path

from controller.lib.config import (
    get_config_value,
    get_media_directory,
    is_docker_mode,
    save_config,
    update_config,
)

logger = logging.getLogger(__name__)

# Share name must be alphanumeric with hyphens, underscores, or spaces.
SHARE_NAME_RE = re.compile(r'^[\w\s-]+$')


class SambaStatus(enum.Enum):
    running = enum.auto()
    stopped = enum.auto()
    unavailable = enum.auto()
    unknown = enum.auto()


def _get_smb_conf_path() -> Path:
    """Get the smb.conf path for the current mode."""
    if is_docker_mode():
        return get_media_directory() / "config" / "smb.conf"
    return Path("/etc/samba/smb.conf")


def get_samba_status() -> SambaStatus:
    """Get Samba service status."""
    if is_docker_mode():
        from controller.lib.docker_services import can_manage_containers, get_container_status
        if not can_manage_containers():
            return SambaStatus.unavailable
        status = get_container_status("samba")
        container_status = status.get("status")
        if container_status == "running":
            return SambaStatus.running
        elif container_status in ("stopped", "not_found"):
            return SambaStatus.stopped
        return SambaStatus.unknown

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "smbd"],
            capture_output=True, text=True, timeout=5,
        )
        active = result.stdout.strip()
        if active == "active":
            return SambaStatus.running
        elif active in ("inactive", "dead"):
            return SambaStatus.stopped
        return SambaStatus.unknown
    except FileNotFoundError:
        return SambaStatus.unavailable
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return SambaStatus.unknown


def get_samba_status_dict() -> dict:
    """Get Samba status as dict for API responses."""
    status = get_samba_status()
    shares = get_config_value("samba.shares", [])

    reason = None
    if status == SambaStatus.unavailable:
        reason = "Samba not available (Docker mode or not installed)"
    elif status == SambaStatus.unknown:
        reason = "Could not determine Samba status"

    return {
        "enabled": status == SambaStatus.running,
        "available": status != SambaStatus.unavailable,
        "reason": reason,
        "shares": shares,
    }


def _generate_smb_conf() -> str:
    """Generate smb.conf content from config."""
    shares = get_config_value("samba.shares", [])
    media_dir = str(get_media_directory())

    hostname = platform.node() or "WROLPi"

    lines = [
        "[global]",
        "   workgroup = WORKGROUP",
        f"   server string = {hostname}",
        "   security = user",
        "   map to guest = Bad User",
        "   guest account = nobody",
        "   log file = /var/log/samba/log.%m",
        "   max log size = 1000",
        "   logging = file",
        "   server role = standalone server",
        "",
    ]

    for share in shares:
        name = share.get("name", "share")
        path = share.get("path", media_dir)
        read_only = "yes" if share.get("read_only", True) else "no"
        comment = share.get("comment", "")

        lines.extend([
            f"[{name}]",
            f"   comment = {comment}",
            f"   path = {path}",
            "   browseable = yes",
            f"   read only = {read_only}",
            "   guest ok = yes",
            "   create mask = 0644",
            "   directory mask = 0755",
            "",
        ])

    return "\n".join(lines)


def _start_samba():
    """Start samba services."""
    if is_docker_mode():
        from controller.lib.docker_services import can_manage_containers, start_container
        if can_manage_containers():
            start_container("samba")
    else:
        for service in ("smbd", "nmbd"):
            try:
                subprocess.run(["systemctl", "start", service],
                               capture_output=True, text=True, timeout=10)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass


def _stop_samba():
    """Stop samba services."""
    if is_docker_mode():
        from controller.lib.docker_services import can_manage_containers, stop_container
        if can_manage_containers():
            stop_container("samba")
    else:
        for service in ("smbd", "nmbd"):
            try:
                subprocess.run(["systemctl", "stop", service],
                               capture_output=True, text=True, timeout=10)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass


def _reload_samba():
    """Reload Samba config. Native uses smbcontrol, Docker restarts the container."""
    if is_docker_mode():
        from controller.lib.docker_services import can_manage_containers, restart_container
        if can_manage_containers():
            restart_container("samba")
    else:
        if get_samba_status() == SambaStatus.running:
            subprocess.run(
                ["smbcontrol", "all", "reload-config"],
                capture_output=True, text=True, timeout=10,
            )


def _write_smb_conf() -> dict:
    """Write smb.conf and reload Samba config if running."""
    try:
        content = _generate_smb_conf()
        conf_path = _get_smb_conf_path()
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(content)
        return {"success": True}
    except PermissionError:
        return {"success": False, "error": "Permission denied writing smb.conf"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"success": False, "error": str(e)}


def _validate_share_path(path: str) -> str | None:
    """Validate that a share path is under the media directory. Returns error message or None."""
    media_dir = get_media_directory()
    try:
        share_path = Path(path).resolve()
    except (ValueError, OSError):
        return f"Invalid path: {path}"
    if not str(share_path).startswith(str(media_dir.resolve())):
        return f"Share path must be under {media_dir}"
    if not share_path.is_dir():
        return f"Path does not exist: {path}"
    return None


def add_share(name: str, path: str, read_only: bool = True, comment: str = "") -> dict:
    """Add a Samba share."""
    if not SHARE_NAME_RE.match(name):
        return {"success": False, "error": "Share name must be alphanumeric (hyphens/underscores/spaces allowed)"}

    path_error = _validate_share_path(path)
    if path_error:
        return {"success": False, "error": path_error}

    shares = get_config_value("samba.shares", [])

    # Check for duplicate name.
    for s in shares:
        if s["name"].lower() == name.lower():
            return {"success": False, "error": f"Share '{name}' already exists"}

    share_path = str(Path(path).resolve())
    new_share = {"name": name, "path": share_path, "read_only": read_only, "comment": comment}
    shares.append(new_share)
    update_config("samba.shares", shares)
    save_config()

    _write_smb_conf()

    # Start samba if it isn't running.
    if get_samba_status() != SambaStatus.running:
        _start_samba()
    else:
        _reload_samba()

    return {"success": True, "share": new_share}


def remove_share(name: str) -> dict:
    """Remove a Samba share by name."""
    shares = get_config_value("samba.shares", [])
    new_shares = [s for s in shares if s["name"].lower() != name.lower()]

    if len(new_shares) == len(shares):
        return {"success": False, "error": f"Share '{name}' not found"}

    update_config("samba.shares", new_shares)
    save_config()
    _write_smb_conf()

    if not new_shares:
        # Last share removed, stop samba.
        _stop_samba()
    else:
        _reload_samba()

    return {"success": True}


def apply_samba_from_config():
    """Apply Samba config on startup. Called from lifespan.

    Writes smb.conf and manages samba lifecycle based on configured shares.
    """
    shares = get_config_value("samba.shares", [])

    # Always write a valid smb.conf so samba doesn't crash if started manually.
    result = _write_smb_conf()
    if not result["success"]:
        logger.warning("Failed to write Samba config: %s", result.get("error"))
        return

    if shares:
        logger.info("Applied Samba config with %d shares, starting samba", len(shares))
        if get_samba_status() != SambaStatus.running:
            _start_samba()
    else:
        logger.info("No Samba shares configured, stopping samba")
        if get_samba_status() == SambaStatus.running:
            _stop_samba()
