"""
Scripts management for WROLPi Controller.

Manages maintenance scripts that run as systemd services (like repair.sh).
Uses systemd oneshot services for process survival across controller restarts.
"""

import subprocess
from datetime import datetime
from typing import Optional

from controller.lib.config import is_docker_mode

# Available scripts with their configurations
# Parameters define inputs that scripts accept:
#   - name: Parameter name (used as env var name, e.g., "branch" -> "BRANCH=value")
#   - label: Display label for the input field
#   - type: "branch" (auto-populates with current git branch) or "text"
#   - required: Whether the parameter must have a value
AVAILABLE_SCRIPTS = {
    "repair": {
        "name": "repair",
        "display_name": "Repair WROLPi",
        "description": "Repairs WROLPi installation by resetting configs and restarting services.",
        "service_name": "wrolpi-repair.service",
        "warnings": [
            "Resets git repository (discards any local code changes)",
            "Stops ALL WROLPi services temporarily",
            "May restore databases from backup blobs",
            "Generates new SSL certificates",
            "Takes several minutes to complete",
        ],
    },
    "upgrade": {
        "name": "upgrade",
        "display_name": "Upgrade WROLPi",
        "description": "Upgrades WROLPi to the latest version from the specified branch.",
        "service_name": "wrolpi-upgrade.service",
        "env_file": "/tmp/wrolpi-upgrade.env",
        "parameters": [
            {"name": "branch", "label": "Branch", "type": "branch", "required": False},
        ],
        "warnings": [
            "Downloads updates from the internet",
            "Restarts ALL WROLPi services",
            "May take several minutes depending on connection speed",
            "UI will be unavailable during upgrade",
        ],
    },
}


def get_current_branch() -> Optional[str]:
    """
    Get the current git branch of /opt/wrolpi.

    Returns:
        Branch name, or None if unable to determine
    """
    try:
        result = subprocess.run(
            ["git", "-C", "/opt/wrolpi", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def list_available_scripts() -> list[dict]:
    """
    List all available scripts with their info.

    Returns:
        List of script info dicts suitable for API response
    """
    scripts = []
    available = not is_docker_mode()

    for name, info in AVAILABLE_SCRIPTS.items():
        scripts.append({
            "name": info["name"],
            "display_name": info["display_name"],
            "description": info["description"],
            "warnings": info["warnings"],
            "available": available,
            "parameters": info.get("parameters", []),
        })

    return scripts


def get_script_status() -> dict:
    """
    Check if any script service is currently running.

    Returns:
        dict with:
            running: bool - Whether a script is running
            script_name: Optional[str] - Name of running script
            service_name: Optional[str] - Systemd service name
            started_at: Optional[str] - ISO timestamp when started
            elapsed_seconds: Optional[int] - Seconds since start
    """
    if is_docker_mode():
        return {"running": False}

    for name, info in AVAILABLE_SCRIPTS.items():
        service = info["service_name"]
        try:
            # Check if service is active (running)
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status = result.stdout.strip()

            if status == "activating":
                # Service is running - get start time
                started_at, elapsed = _get_service_timing(service)
                return {
                    "running": True,
                    "script_name": name,
                    "service_name": service,
                    "started_at": started_at,
                    "elapsed_seconds": elapsed,
                }

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            continue

    return {"running": False}


def _get_service_timing(service: str) -> tuple[Optional[str], Optional[int]]:
    """
    Get timing info for a running service.

    Returns:
        Tuple of (started_at ISO string, elapsed_seconds)
    """
    try:
        # Get ExecMainStartTimestamp from systemctl show
        result = subprocess.run(
            ["systemctl", "show", service, "--property=ExecMainStartTimestamp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Format: ExecMainStartTimestamp=Wed 2025-01-15 10:30:00 UTC
            line = result.stdout.strip()
            if "=" in line:
                timestamp_str = line.split("=", 1)[1].strip()
                if timestamp_str:
                    # Parse the timestamp
                    try:
                        # Try common systemd timestamp format
                        dt = datetime.strptime(timestamp_str, "%a %Y-%m-%d %H:%M:%S %Z")
                        elapsed = int((datetime.utcnow() - dt).total_seconds())
                        return dt.isoformat(), max(0, elapsed)
                    except ValueError:
                        pass
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass

    return None, None


def start_script(name: str, params: Optional[dict] = None) -> dict:
    """
    Start a script by starting its systemd service.

    Args:
        name: Script name (key in AVAILABLE_SCRIPTS)
        params: Optional dict of parameter values (e.g., {"branch": "release"})

    Returns:
        dict with:
            success: bool
            message: Optional[str]
            error: Optional[str]
    """
    if is_docker_mode():
        return {
            "success": False,
            "error": "Scripts are not available in Docker mode",
        }

    if name not in AVAILABLE_SCRIPTS:
        return {
            "success": False,
            "error": f"Unknown script: {name}",
        }

    # Check if already running
    status = get_script_status()
    if status.get("running"):
        if status.get("script_name") == name:
            return {
                "success": False,
                "error": f"Script '{name}' is already running",
            }
        else:
            return {
                "success": False,
                "error": f"Another script is already running: {status.get('script_name')}",
            }

    script_config = AVAILABLE_SCRIPTS[name]
    service = script_config["service_name"]

    # Write parameters to env file if script has one configured
    env_file = script_config.get("env_file")
    if env_file and params:
        try:
            with open(env_file, "w") as f:
                for key, value in params.items():
                    if value:  # Only write non-empty values
                        # Convert param name to uppercase for env var
                        env_name = key.upper()
                        f.write(f"{env_name}={value}\n")
        except OSError as e:
            return {
                "success": False,
                "error": f"Failed to write script config: {e}",
            }

    try:
        # Start the service (non-blocking via Popen)
        # No sudo needed - Controller runs as root
        subprocess.Popen(
            ["systemctl", "start", service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return {
            "success": True,
            "message": f"Script '{name}' started",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "systemctl not found",
        }
    except subprocess.SubprocessError as e:
        return {
            "success": False,
            "error": str(e),
        }


def get_script_output(name: str, lines: int = 100) -> dict:
    """
    Get output from a script's systemd service via journalctl.

    Args:
        name: Script name
        lines: Number of lines to retrieve (default 100)

    Returns:
        dict with:
            output: str - Log output
            lines: int - Lines requested
            script_name: str - Script name
    """
    if is_docker_mode():
        return {
            "output": "Scripts are not available in Docker mode",
            "lines": 0,
            "script_name": name,
        }

    if name not in AVAILABLE_SCRIPTS:
        return {
            "output": f"Unknown script: {name}",
            "lines": 0,
            "script_name": name,
        }

    service = AVAILABLE_SCRIPTS[name]["service_name"]

    try:
        result = subprocess.run(
            ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "output": result.stdout,
            "lines": lines,
            "script_name": name,
        }
    except subprocess.TimeoutExpired:
        return {
            "output": "Timeout fetching logs",
            "lines": 0,
            "script_name": name,
        }
    except FileNotFoundError:
        return {
            "output": "journalctl not found",
            "lines": 0,
            "script_name": name,
        }
    except subprocess.SubprocessError as e:
        return {
            "output": str(e),
            "lines": 0,
            "script_name": name,
        }
