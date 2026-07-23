"""
Systemd service management for WROLPi Controller.

Provides start/stop/restart/status/logs for systemd services.
"""

import logging
import subprocess
from typing import Optional

from controller.lib.config import get_config

logger = logging.getLogger(__name__)


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


def get_service_kind(service_config: dict) -> str:
    """
    Classify a service as 'persistent' or 'task'.

    'persistent' services are the always-on parts of a running WROLPi (api,
    app, caddy, kiwix, ...). 'task' services are one-off/dev/maintenance units
    (bootstrap, repair, upgrade, *-dev) that run on demand and are not expected
    to stay running.

    An explicit "kind" in the service config wins. Otherwise services flagged
    show_only_when_running (dev/upgrade units) are treated as tasks, and
    everything else defaults to persistent.
    """
    kind = service_config.get("kind")
    if kind:
        return kind
    if service_config.get("show_only_when_running"):
        return "task"
    return "persistent"


def classify_service_group(kind: str, enabled: bool) -> str:
    """
    Group a service for display in the Controller UI.

    Returns:
        "core"     - a persistent service enabled at boot: the normal running
                     system the user cares about day-to-day.
        "optional" - one-off/dev/maintenance tasks, or persistent services the
                     user has disabled at boot (e.g. Samba with no shares).

    Membership only changes when the user toggles Boot for a persistent
    service, never on start/stop or polling, so rows stay put.
    """
    if kind == "persistent" and enabled:
        return "core"
    return "optional"


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

        # Loaded state distinguishes a stopped unit from one that does not
        # exist on this box at all.
        load_result = subprocess.run(
            ["systemctl", "show", "-p", "LoadState", "--value", systemd_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        load_state = load_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        kind = get_service_kind(service_config)
        return {
            "name": name,
            "systemd_name": systemd_name,
            "status": "unknown",
            "active": "unknown",
            "enabled": False,
            "installed": False,
            "port": service_config.get("port"),
            "viewable": service_config.get("viewable", False),
            "view_path": service_config.get("view_path", ""),
            "use_https": service_config.get("use_https", False),
            "description": service_config.get("description", ""),
            "kind": kind,
            "group": classify_service_group(kind, False),
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

    enabled = is_enabled == "enabled"
    kind = get_service_kind(service_config)
    return {
        "name": name,
        "systemd_name": systemd_name,
        "status": status,
        "installed": load_state not in ("not-found", ""),
        "active": is_active,
        "enabled": enabled,
        "port": service_config.get("port"),
        "viewable": service_config.get("viewable", False),
        "view_path": service_config.get("view_path", ""),
        "use_https": service_config.get("use_https", False),
        "description": service_config.get("description", ""),
        "kind": kind,
        "group": classify_service_group(kind, enabled),
    }


def discover_wrolpi_services() -> list[str]:
    """
    Discover wrolpi-* systemd services not in the managed services config.

    Unions loaded units (--all also catches transient units and units that
    have exited this boot) with installed unit files, so a finished oneshot
    (e.g. wrolpi-upgrade) or a dev service stays visible in the UI and its
    logs remain reachable.

    Returns:
        list of service names without the .service suffix
    """
    managed_systemd_names = {
        s.get("systemd_name", s["name"])
        for s in get_managed_services()
    }

    commands = (
        ["systemctl", "list-units", "wrolpi-*", "--type=service",
         "--all", "--plain", "--no-legend", "--no-pager"],
        ["systemctl", "list-unit-files", "wrolpi-*", "--type=service",
         "--no-legend", "--no-pager"],
    )

    discovered: list[str] = []
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.strip().splitlines():
            unit_name = next((p for p in line.split() if p.endswith(".service")), None)
            if not unit_name:
                continue
            service_name = unit_name.removesuffix(".service")
            if service_name not in managed_systemd_names and service_name not in discovered:
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
            "kind": "task",
            "group": "optional",
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
        # Discovered wrolpi-* units are always one-off/maintenance tasks.
        "kind": "task",
        "group": "optional",
    }


def get_all_services_status() -> list[dict]:
    """
    Get status of all managed services, plus any running wrolpi-* services
    discovered dynamically.

    Services with show_only_when_running=True are hidden only when their
    unit is not installed on this box (e.g. wrolpi-api-dev on production).
    Installed-but-stopped services stay visible so a finished oneshot
    (wrolpi-upgrade) keeps its logs reachable from the UI.

    Returns:
        list of service status dicts
    """
    results = []
    for service in get_managed_services():
        status = get_service_status(service["name"])
        if service.get("show_only_when_running") and not status.get("installed"):
            continue
        results.append(status)

    # Any other wrolpi-* services (installed or transient), regardless of
    # running state.
    for name in discover_wrolpi_services():
        results.append(get_discovered_service_status(name))

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
    logger.info("Starting service %s (systemd: %s)", name, systemd_name)
    result = _run_systemctl("start", systemd_name)
    if result["success"]:
        logger.info("Service %s started successfully", name)
    else:
        logger.warning("Failed to start service %s: %s", name, result.get("error"))

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
    logger.info("Stopping service %s (systemd: %s)", name, systemd_name)
    result = _run_systemctl("stop", systemd_name)
    if result["success"]:
        logger.info("Service %s stopped successfully", name)
    else:
        logger.warning("Failed to stop service %s: %s", name, result.get("error"))

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

    logger.info("Restarting service %s (systemd: %s)", name, systemd_name)

    # Special handling for self-restart: use Popen to avoid blocking
    # (the process will be killed before subprocess.run can return)
    if systemd_name == "wrolpi-controller":
        try:
            subprocess.Popen(["systemctl", "restart", systemd_name])
            logger.info("Service %s self-restart initiated", name)
            return {
                "success": True,
                "service": name,
                "action": "restart",
                "pending": True,
            }
        except Exception as e:
            logger.warning("Failed to restart service %s: %s", name, e)
            return {
                "success": False,
                "service": name,
                "action": "restart",
                "error": str(e),
            }

    result = _run_systemctl("restart", systemd_name)
    if result["success"]:
        logger.info("Service %s restarted successfully", name)
    else:
        logger.warning("Failed to restart service %s: %s", name, result.get("error"))

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
    logger.info("Enabling service %s (systemd: %s)", name, systemd_name)
    result = _run_systemctl("enable", systemd_name)
    if result["success"]:
        logger.info("Service %s enabled successfully", name)
    else:
        logger.warning("Failed to enable service %s: %s", name, result.get("error"))

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
    logger.info("Disabling service %s (systemd: %s)", name, systemd_name)
    result = _run_systemctl("disable", systemd_name)
    if result["success"]:
        logger.info("Service %s disabled successfully", name)
    else:
        logger.warning("Failed to disable service %s: %s", name, result.get("error"))

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
