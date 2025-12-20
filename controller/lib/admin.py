"""
Admin operations for WROLPi Controller.

Migrated from wrolpi/admin.py - provides system control functions.
"""

import asyncio
import enum
import subprocess
from pathlib import Path

from controller.lib.config import is_docker_mode
from wrolpi.common import WROLPI_CONFIG
from wrolpi.vars import DEFAULT_CPU_FREQUENCY


class HotspotStatus(enum.Enum):
    """Hotspot status enum matching wrolpi/admin.py"""
    disconnected = enum.auto()  # Radio is on, but Hotspot is not connected.
    unavailable = enum.auto()  # Radio is off.
    connected = enum.auto()  # Radio is on, Hotspot is on.
    unknown = enum.auto()  # Unknown status. Hotspot may not be supported.
    in_use = enum.auto()  # Wi-Fi device is in use for a network connection.


class GovernorStatus(enum.Enum):
    """CPU governor status enum matching wrolpi/admin.py"""
    ondemand = enum.auto()
    powersave = enum.auto()
    unknown = enum.auto()


def get_current_ssid(interface: str = None) -> str | None:
    """
    Returns the name of the SSID that is currently connected.
    Returns None if Hotspot is active, or no Wi-Fi network is being used.
    """
    if interface is None:
        interface = WROLPI_CONFIG.hotspot_device
    try:
        result = subprocess.run(
            ['iwgetid', interface, '--raw'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ssid = result.stdout.strip()
            return ssid if ssid else None
        elif result.returncode == 255:
            # Hotspot is in use
            return None
        else:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def get_hotspot_status() -> HotspotStatus:
    """
    Get current hotspot status matching wrolpi/admin.py logic.

    Returns:
        HotspotStatus enum value
    """
    if is_docker_mode():
        return HotspotStatus.unknown

    device = WROLPI_CONFIG.hotspot_device

    # Check if device is connected to a Wi-Fi network (not hotspot)
    if get_current_ssid(device):
        return HotspotStatus.in_use

    # Check nmcli status
    try:
        result = subprocess.run(
            ["nmcli"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return HotspotStatus.unknown

        output = result.stdout.strip()
        for line in output.splitlines():
            if line.startswith(f'{device}: connected'):
                return HotspotStatus.connected
            elif line.startswith(f'{device}: disconnected'):
                return HotspotStatus.disconnected
            elif line.startswith(f'{device}: unavailable'):
                return HotspotStatus.unavailable

        return HotspotStatus.unknown

    except subprocess.TimeoutExpired:
        return HotspotStatus.unknown
    except FileNotFoundError:
        return HotspotStatus.unknown
    except subprocess.SubprocessError:
        return HotspotStatus.unknown


def get_hotspot_status_dict() -> dict:
    """
    Get hotspot status as a dict for API responses.

    Returns dict matching HotspotStatusResponse schema:
        enabled: bool - Whether hotspot is currently enabled
        available: bool - Whether hotspot functionality is available
        reason: Optional[str] - Reason if unavailable
        ssid: Optional[str] - Hotspot SSID when enabled
        device: Optional[str] - WiFi device name
    """
    device = WROLPI_CONFIG.hotspot_device
    status = get_hotspot_status()

    # Map enum status to enabled/available flags
    enabled = status == HotspotStatus.connected
    available = status not in (HotspotStatus.unknown, HotspotStatus.unavailable)

    reason = None
    if status == HotspotStatus.unknown:
        reason = "Hotspot not supported or nmcli unavailable"
    elif status == HotspotStatus.unavailable:
        reason = "WiFi radio is off"
    elif status == HotspotStatus.in_use:
        reason = "WiFi device is connected to a network"

    return {
        "enabled": enabled,
        "available": available,
        "reason": reason,
        "ssid": WROLPI_CONFIG.hotspot_ssid if enabled else None,
        "device": device,
    }


def enable_hotspot() -> dict:
    """
    Enable the WiFi hotspot.

    Returns:
        dict with success status and message
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    device = WROLPI_CONFIG.hotspot_device
    ssid = WROLPI_CONFIG.hotspot_ssid
    password = WROLPI_CONFIG.hotspot_password

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


GOVERNOR_MAP = {
    'ondemand': GovernorStatus.ondemand,
    'powersave': GovernorStatus.powersave,
}


def get_throttle_status() -> GovernorStatus:
    """
    Get CPU throttle (governor) status matching wrolpi/admin.py logic.

    Returns:
        GovernorStatus enum value
    """
    if is_docker_mode():
        return GovernorStatus.unknown

    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")

    if not governor_path.exists():
        return GovernorStatus.unknown

    try:
        current = governor_path.read_text().strip()
        return GOVERNOR_MAP.get(current, GovernorStatus.unknown)
    except IOError:
        return GovernorStatus.unknown


def get_throttle_status_dict() -> dict:
    """
    Get throttle status as a dict for API responses.

    Returns dict matching ThrottleStatusResponse schema:
        enabled: bool - Whether CPU throttle (powersave) is enabled
        available: bool - Whether throttle control is available
        reason: Optional[str] - Reason if unavailable
        governor: Optional[str] - Current CPU governor
        available_governors: Optional[list[str]] - Available governors
    """
    if is_docker_mode():
        return {
            "enabled": False,
            "available": False,
            "reason": "Docker mode",
            "governor": None,
            "available_governors": None,
        }

    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    available_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors")

    if not governor_path.exists():
        return {
            "enabled": False,
            "available": False,
            "reason": "cpufreq not available",
            "governor": None,
            "available_governors": None,
        }

    try:
        current = governor_path.read_text().strip()
        available_governors = available_path.read_text().strip().split() if available_path.exists() else []

        return {
            "enabled": current == "powersave",
            "available": True,
            "reason": None,
            "governor": current,
            "available_governors": available_governors,
        }
    except IOError as e:
        return {
            "enabled": False,
            "available": False,
            "reason": str(e),
            "governor": None,
            "available_governors": None,
        }


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

    default_governor = DEFAULT_CPU_FREQUENCY

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


def shutdown_system(delay: int = 10) -> dict:
    """
    Shut down the system after a delay.

    Args:
        delay: Seconds to wait before shutdown (default 10). Allows API to return response.

    Returns:
        dict with success status
    """
    import shutil

    if is_docker_mode():
        return {"success": False, "error": "Cannot shutdown from Docker container"}

    # Check if shutdown command exists before starting thread
    if not shutil.which("shutdown"):
        return {"success": False, "error": "shutdown command not found"}

    def _delayed_shutdown():
        import time
        time.sleep(delay)
        subprocess.Popen(["shutdown", "-h", "now"])

    try:
        import threading
        thread = threading.Thread(target=_delayed_shutdown, daemon=True)
        thread.start()
        return {"success": True, "message": f"System shutting down in {delay} seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reboot_system(delay: int = 10) -> dict:
    """
    Reboot the system after a delay.

    Args:
        delay: Seconds to wait before reboot (default 10). Allows API to return response.

    Returns:
        dict with success status
    """
    import shutil

    if is_docker_mode():
        return {"success": False, "error": "Cannot reboot from Docker container"}

    # Check if reboot command exists before starting thread
    if not shutil.which("reboot"):
        return {"success": False, "error": "reboot command not found"}

    def _delayed_reboot():
        import time
        time.sleep(delay)
        subprocess.Popen(["reboot"])

    try:
        import threading
        thread = threading.Thread(target=_delayed_reboot, daemon=True)
        thread.start()
        return {"success": True, "message": f"System rebooting in {delay} seconds"}
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
