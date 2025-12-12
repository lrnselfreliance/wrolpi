"""
Admin operations for WROLPi Controller.

Migrated from wrolpi/admin.py - provides system control functions.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from controller.lib.config import get_config, is_docker_mode


def get_hotspot_status() -> dict:
    """
    Get current hotspot status.

    Returns:
        dict with keys: enabled, available, and additional info if available
    """
    if is_docker_mode():
        return {"enabled": False, "available": False, "reason": "Docker mode"}

    config = get_config()
    hotspot_config = config.get("hotspot", {})
    device = hotspot_config.get("device", "wlan0")

    # Check if NetworkManager hotspot is active
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(":")
                if len(parts) >= 3 and parts[1] == "802-11-wireless":
                    # Check if it's a hotspot connection
                    if "Hotspot" in parts[0] or parts[2] == device:
                        return {
                            "enabled": True,
                            "available": True,
                            "ssid": hotspot_config.get("ssid", "WROLPi"),
                            "device": device,
                        }

        return {"enabled": False, "available": True, "device": device}

    except subprocess.TimeoutExpired:
        return {"enabled": False, "available": False, "reason": "Timeout checking status"}
    except FileNotFoundError:
        return {"enabled": False, "available": False, "reason": "nmcli not available"}
    except subprocess.SubprocessError as e:
        return {"enabled": False, "available": False, "reason": str(e)}


def enable_hotspot() -> dict:
    """
    Enable the WiFi hotspot.

    Returns:
        dict with success status and message
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    config = get_config()
    hotspot_config = config.get("hotspot", {})

    device = hotspot_config.get("device", "wlan0")
    ssid = hotspot_config.get("ssid", "WROLPi")
    password = hotspot_config.get("password", "wrolpi hotspot")

    try:
        # First ensure radio is on
        subprocess.run(
            ["nmcli", "radio", "wifi", "on"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Create hotspot using NetworkManager
        result = subprocess.run(
            [
                "nmcli", "device", "wifi", "hotspot",
                "ifname", device,
                "ssid", ssid,
                "password", password,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return {"success": True, "ssid": ssid, "device": device}
        else:
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout enabling hotspot"}
    except FileNotFoundError:
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        return {"success": False, "error": str(e)}


def disable_hotspot() -> dict:
    """
    Disable the WiFi hotspot.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    try:
        # Turn off the radio to disconnect hotspot
        result = subprocess.run(
            ["nmcli", "radio", "wifi", "off"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Success even if already off
        return {"success": True}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout disabling hotspot"}
    except FileNotFoundError:
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        return {"success": False, "error": str(e)}


def get_throttle_status() -> dict:
    """
    Get CPU throttle (governor) status.

    Returns:
        dict with keys: enabled (powersave), governor, available_governors
    """
    if is_docker_mode():
        return {"enabled": False, "available": False, "reason": "Docker mode"}

    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    available_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors")

    if not governor_path.exists():
        return {"enabled": False, "available": False, "reason": "cpufreq not available"}

    try:
        current = governor_path.read_text().strip()
        available = available_path.read_text().strip().split() if available_path.exists() else []

        return {
            "enabled": current == "powersave",
            "available": True,
            "governor": current,
            "available_governors": available,
        }
    except IOError as e:
        return {"enabled": False, "available": False, "reason": str(e)}


def enable_throttle() -> dict:
    """
    Enable CPU throttle (set powersave governor).

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    try:
        # Try cpufreq-set first
        result = subprocess.run(
            ["cpufreq-set", "-g", "powersave"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return {"success": True, "governor": "powersave"}
        else:
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except FileNotFoundError:
        # Try direct write to sysfs
        try:
            for cpu_path in Path("/sys/devices/system/cpu/").glob("cpu[0-9]*/cpufreq/scaling_governor"):
                cpu_path.write_text("powersave")
            return {"success": True, "governor": "powersave"}
        except IOError as e:
            return {"success": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout enabling throttle"}
    except subprocess.SubprocessError as e:
        return {"success": False, "error": str(e)}


def disable_throttle() -> dict:
    """
    Disable CPU throttle (set ondemand or performance governor).

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    config = get_config()
    default_governor = config.get("throttle", {}).get("default_governor", "ondemand")

    try:
        result = subprocess.run(
            ["cpufreq-set", "-g", default_governor],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return {"success": True, "governor": default_governor}
        else:
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except FileNotFoundError:
        # Try direct write to sysfs
        try:
            for cpu_path in Path("/sys/devices/system/cpu/").glob("cpu[0-9]*/cpufreq/scaling_governor"):
                cpu_path.write_text(default_governor)
            return {"success": True, "governor": default_governor}
        except IOError as e:
            return {"success": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout disabling throttle"}
    except subprocess.SubprocessError as e:
        return {"success": False, "error": str(e)}


def shutdown_system() -> dict:
    """
    Shut down the system.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Cannot shutdown from Docker container"}

    try:
        subprocess.Popen(["shutdown", "-h", "now"])
        return {"success": True, "message": "System shutting down"}
    except FileNotFoundError:
        return {"success": False, "error": "shutdown command not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reboot_system() -> dict:
    """
    Reboot the system.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Cannot reboot from Docker container"}

    try:
        subprocess.Popen(["reboot"])
        return {"success": True, "message": "System rebooting"}
    except FileNotFoundError:
        return {"success": False, "error": "reboot command not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def restart_all_services() -> dict:
    """
    Restart all WROLPi services including Controller itself.

    Controller restarts itself LAST so it can report success for other services.

    Returns:
        dict with results for each service
    """
    if is_docker_mode():
        # In Docker mode, we can't use systemctl
        return {
            "success": False,
            "error": "Service restart via systemctl not available in Docker mode",
        }

    services_to_restart = [
        "wrolpi-api",
        "wrolpi-app",
        "wrolpi-kiwix",
        "wrolpi-help",
        "renderd",
        "apache2",
        # Controller restarts itself last (scheduled after response)
    ]

    results = {}

    for service in services_to_restart:
        try:
            result = subprocess.run(
                ["systemctl", "restart", service],
                capture_output=True,
                text=True,
                timeout=30,
            )
            results[service] = {
                "success": result.returncode == 0,
                "error": result.stderr.strip() if result.returncode != 0 else None,
            }
        except subprocess.TimeoutExpired:
            results[service] = {"success": False, "error": "Timeout"}
        except FileNotFoundError:
            results[service] = {"success": False, "error": "systemctl not found"}
        except Exception as e:
            results[service] = {"success": False, "error": str(e)}

    # Schedule Controller self-restart after response is sent
    loop = asyncio.get_event_loop()
    loop.call_later(1.0, _restart_self)

    results["wrolpi-controller"] = {"success": True, "pending": True}
    return {"success": True, "services": results}


def _restart_self():
    """Restart the Controller service. Called after response is sent."""
    try:
        subprocess.Popen(["systemctl", "restart", "wrolpi-controller"])
    except Exception:
        # If we can't restart ourselves, not much we can do
        pass
