"""
Systemd service management for WROLPi Controller.

Provides start/stop/restart/status/logs for systemd services.
"""

import subprocess
from typing import Optional

from controller.lib.config import get_config


def get_managed_services() -> list[dict]:
    """
    Get list of managed services from config.

    Returns:
        list of service configs with name, systemd_name, port, etc.
    """
    config = get_config()
    return config.get("managed_services", [])


def get_service_config(name: str) -> Optional[dict]:
    """
    Get config for a specific service by name.

    Args:
        name: Service name (e.g., "wrolpi-api")

    Returns:
        Service config dict or None if not found
    """
    for service in get_managed_services():
        if service.get("name") == name:
            return service
    return None


def _run_systemctl(command: str, service: str, timeout: int = 30) -> dict:
    """
    Run a systemctl command.

    Args:
        command: systemctl command (start, stop, restart, status, etc.)
        service: systemd service name
        timeout: Command timeout in seconds

    Returns:
        dict with success, output, and error fields
    """
    try:
        result = subprocess.run(
            ["systemctl", command, service],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "systemctl not found"}


def get_service_status(name: str) -> dict:
    """
    Get status of a managed service.

    Args:
        name: Service name from config

    Returns:
        dict with status, active, enabled, etc.
    """
    service_config = get_service_config(name)
    if not service_config:
        # Allow dynamically discovered wrolpi-* services.
        if name.startswith("wrolpi-"):
            return get_discovered_service_status(name)
        return {"error": f"Unknown service: {name}"}

    systemd_name = service_config.get("systemd_name", name)

    try:
        # Get active state
        active_result = subprocess.run(
            ["systemctl", "is-active", systemd_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        is_active = active_result.stdout.strip()

        # Get enabled state
        enabled_result = subprocess.run(
            ["systemctl", "is-enabled", systemd_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        is_enabled = enabled_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {
            "name": name,
            "systemd_name": systemd_name,
            "status": "unknown",
            "active": "unknown",
            "enabled": False,
            "port": service_config.get("port"),
            "viewable": service_config.get("viewable", False),
            "view_path": service_config.get("view_path", ""),
            "use_https": service_config.get("use_https", False),
            "description": service_config.get("description", ""),
            "error": "systemctl not available",
        }

    # Map to simple status
    if is_active == "active":
        status = "running"
    elif is_active == "activating":
        status = "running"  # oneshot services show "activating" while running
    elif is_active == "inactive":
        status = "stopped"
    elif is_active == "failed":
        status = "failed"
    else:
        status = "unknown"

    return {
        "name": name,
        "systemd_name": systemd_name,
        "status": status,
        "active": is_active,
        "enabled": is_enabled == "enabled",
        "port": service_config.get("port"),
        "viewable": service_config.get("viewable", False),
        "view_path": service_config.get("view_path", ""),
        "use_https": service_config.get("use_https", False),
        "description": service_config.get("description", ""),
    }


def discover_running_wrolpi_services() -> list[str]:
    """
    Discover running wrolpi-* systemd services not in the managed services config.

    Returns:
        list of systemd unit names (e.g., ["wrolpi-fix-media-permissions.service"])
    """
    managed_systemd_names = {
        s.get("systemd_name", s["name"])
        for s in get_managed_services()
    }

    try:
        result = subprocess.run(
            ["systemctl", "list-units", "wrolpi-*", "--type=service", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    discovered = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        # Unit name is the first column, e.g. "wrolpi-fix-media-permissions.service"
        unit_name = parts[0]
        # Strip .service suffix to get the base name
        service_name = unit_name.removesuffix(".service")
        if service_name not in managed_systemd_names:
            discovered.append(service_name)

    return discovered


def get_discovered_service_status(name: str) -> dict:
    """
    Get status of a dynamically discovered wrolpi-* service (not in managed config).

    Args:
        name: Service name (e.g., "wrolpi-fix-media-permissions")

    Returns:
        dict with status fields
    """
    try:
        active_result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        is_active = active_result.stdout.strip()

        enabled_result = subprocess.run(
            ["systemctl", "is-enabled", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        is_enabled = enabled_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {
            "name": name,
            "systemd_name": name,
            "status": "unknown",
            "active": "unknown",
            "enabled": False,
            "port": None,
            "viewable": False,
            "view_path": "",
            "use_https": False,
            "description": "",
            "error": "systemctl not available",
        }

    if is_active == "active":
        status = "running"
    elif is_active == "activating":
        status = "running"
    elif is_active == "inactive":
        status = "stopped"
    elif is_active == "failed":
        status = "failed"
    else:
        status = "unknown"

    return {
        "name": name,
        "systemd_name": name,
        "status": status,
        "active": is_active,
        "enabled": is_enabled == "enabled",
        "port": None,
        "viewable": False,
        "view_path": "",
        "use_https": False,
        "description": "",
    }


def get_all_services_status() -> list[dict]:
    """
    Get status of all managed services, plus any running wrolpi-* services
    discovered dynamically.

    Services with show_only_when_running=True are excluded when not running.

    Returns:
        list of service status dicts
    """
    results = []
    for service in get_managed_services():
        status = get_service_status(service["name"])
        # Skip services with show_only_when_running if not running
        if service.get("show_only_when_running") and status.get("status") != "running":
            continue
        results.append(status)

    # Discover any running wrolpi-* services not in the managed list.
    for name in discover_running_wrolpi_services():
        status = get_discovered_service_status(name)
        if status.get("status") == "running":
            results.append(status)

    return results


def _get_systemd_name(name: str) -> Optional[str]:
    """Get the systemd unit name for a service, supporting both managed and discovered wrolpi-* services."""
    service_config = get_service_config(name)
    if service_config:
        return service_config.get("systemd_name", name)
    if name.startswith("wrolpi-"):
        return name
    return None


def start_service(name: str) -> dict:
    """
    Start a managed service.

    Args:
        name: Service name from config

    Returns:
        dict with success status
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"success": False, "error": f"Unknown service: {name}"}
    result = _run_systemctl("start", systemd_name)

    return {
        "success": result["success"],
        "service": name,
        "action": "start",
        "error": result.get("error"),
    }


def stop_service(name: str) -> dict:
    """
    Stop a managed service.

    Args:
        name: Service name from config

    Returns:
        dict with success status
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"success": False, "error": f"Unknown service: {name}"}
    result = _run_systemctl("stop", systemd_name)

    return {
        "success": result["success"],
        "service": name,
        "action": "stop",
        "error": result.get("error"),
    }


def restart_service(name: str) -> dict:
    """
    Restart a managed service.

    Args:
        name: Service name from config

    Returns:
        dict with success status
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"success": False, "error": f"Unknown service: {name}"}

    # Special handling for self-restart: use Popen to avoid blocking
    # (the process will be killed before subprocess.run can return)
    if systemd_name == "wrolpi-controller":
        try:
            subprocess.Popen(["systemctl", "restart", systemd_name])
            return {
                "success": True,
                "service": name,
                "action": "restart",
                "pending": True,
            }
        except Exception as e:
            return {
                "success": False,
                "service": name,
                "action": "restart",
                "error": str(e),
            }

    result = _run_systemctl("restart", systemd_name)

    return {
        "success": result["success"],
        "service": name,
        "action": "restart",
        "error": result.get("error"),
    }


def enable_service(name: str) -> dict:
    """
    Enable a service to start at boot.

    Args:
        name: Service name from config

    Returns:
        dict with success status
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"success": False, "error": f"Unknown service: {name}"}
    result = _run_systemctl("enable", systemd_name)

    return {
        "success": result["success"],
        "service": name,
        "action": "enable",
        "error": result.get("error"),
    }


def disable_service(name: str) -> dict:
    """
    Disable a service from starting at boot.

    Args:
        name: Service name from config

    Returns:
        dict with success status
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"success": False, "error": f"Unknown service: {name}"}
    result = _run_systemctl("disable", systemd_name)

    return {
        "success": result["success"],
        "service": name,
        "action": "disable",
        "error": result.get("error"),
    }


def get_service_logs(name: str, lines: int = 100, since: Optional[str] = None) -> dict:
    """
    Get logs for a service.

    Args:
        name: Service name from config
        lines: Number of lines to return
        since: Time specification (e.g., "1h", "30m", "2024-01-01")

    Returns:
        dict with logs and metadata
    """
    systemd_name = _get_systemd_name(name)
    if not systemd_name:
        return {"error": f"Unknown service: {name}"}

    cmd = ["journalctl", "-u", systemd_name, "-n", str(lines), "--no-pager"]
    if since:
        cmd.extend(["--since", since])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {
            "service": name,
            "lines": lines,
            "since": since,
            "logs": result.stdout,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout getting logs"}
    except FileNotFoundError:
        return {"error": "journalctl not found"}
