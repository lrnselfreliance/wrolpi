"""
Admin operations for WROLPi Controller.

Migrated from wrolpi/admin.py - provides system control functions.
"""

import asyncio
import enum
import json
import logging
import subprocess
from pathlib import Path

import yaml

from controller.lib.config import is_docker_mode, get_config_value, get_media_directory

logger = logging.getLogger(__name__)

# Constants - use controller's own config instead of wrolpi module
DEFAULT_CPU_FREQUENCY = get_config_value('throttle.default_governor', 'ondemand')


class HotspotStatus(enum.Enum):
    """Hotspot status enum."""
    disconnected = enum.auto()  # Radio is on, but Hotspot is not connected.
    off = enum.auto()  # Radio is software-disabled. Can be turned on.
    connected = enum.auto()  # Radio is on, Hotspot is on.
    unknown = enum.auto()  # Unknown status. No nmcli, Docker, or no WiFi hardware.
    in_use = enum.auto()  # Wi-Fi device is in use for a network connection.


class BluetoothStatus(enum.Enum):
    """Bluetooth radio status."""
    on = enum.auto()  # Bluetooth radio is on (rfkill unblocked).
    off = enum.auto()  # Bluetooth radio is off (rfkill blocked).
    unavailable = enum.auto()  # No Bluetooth hardware or rfkill not installed.
    unknown = enum.auto()  # Docker mode or cannot determine.


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
        interface = get_config_value('hotspot.device', 'wlan0')
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

    device = get_config_value('hotspot.device', 'wlan0')

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
                return HotspotStatus.off

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
    device = get_config_value('hotspot.device', 'wlan0')
    status = get_hotspot_status()

    # Map enum status to enabled/available flags
    enabled = status == HotspotStatus.connected
    # Hotspot is available even when radio is off because enable_hotspot()
    # turns the radio on first.
    available = status != HotspotStatus.unknown

    reason = None
    if status == HotspotStatus.unknown:
        reason = "Hotspot not supported or nmcli unavailable"
    elif status == HotspotStatus.in_use:
        reason = "WiFi device is connected to a network"

    return {
        "enabled": enabled,
        "available": available,
        "reason": reason,
        "ssid": get_config_value('hotspot.ssid', 'WROLPi') if enabled else None,
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

    device = get_config_value('hotspot.device', 'wlan0')
    ssid = get_config_value('hotspot.ssid', 'WROLPi')
    password = get_config_value('hotspot.password', 'wrolpi hotspot')

    try:
        # First ensure radio is on
        subprocess.run(
            ["nmcli", "radio", "wifi", "on"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Create hotspot using NetworkManager
        logger.info("Enabling hotspot on %s with SSID %s", device, ssid)
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
            logger.info("Hotspot enabled successfully on %s", device)
            return {"success": True, "ssid": ssid, "device": device}
        else:
            logger.warning("Failed to enable hotspot: %s", result.stderr.strip())
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except subprocess.TimeoutExpired:
        logger.warning("Timeout enabling hotspot on %s", device)
        return {"success": False, "error": "Timeout enabling hotspot"}
    except FileNotFoundError:
        logger.warning("nmcli not found, cannot enable hotspot")
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to enable hotspot: %s", e)
        return {"success": False, "error": str(e)}


def disable_hotspot() -> dict:
    """
    Disable the WiFi hotspot.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Disabling hotspot")
    try:
        # Turn off the radio to disconnect hotspot
        result = subprocess.run(
            ["nmcli", "radio", "wifi", "off"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Success even if already off
        logger.info("Hotspot disabled successfully")
        return {"success": True}

    except subprocess.TimeoutExpired:
        logger.warning("Timeout disabling hotspot")
        return {"success": False, "error": "Timeout disabling hotspot"}
    except FileNotFoundError:
        logger.warning("nmcli not found, cannot disable hotspot")
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to disable hotspot: %s", e)
        return {"success": False, "error": str(e)}


# --- Bluetooth ---


async def get_bluetooth_status() -> BluetoothStatus:
    """
    Get current Bluetooth radio status using rfkill.

    Parses JSON output from `rfkill -J` to determine if Bluetooth is blocked.

    Returns:
        BluetoothStatus enum value
    """
    if is_docker_mode():
        return BluetoothStatus.unknown

    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/sbin/rfkill", "-J",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        if proc.returncode != 0:
            return BluetoothStatus.unknown

        data = json.loads(stdout.decode())
        bt_devices = [d for d in data.get("rfkilldevices", []) if d.get("type") == "bluetooth"]

        if not bt_devices:
            return BluetoothStatus.unavailable

        # If any Bluetooth device is soft or hard blocked, report as off.
        for device in bt_devices:
            if device.get("soft") == "blocked" or device.get("hard") == "blocked":
                return BluetoothStatus.off

        return BluetoothStatus.on

    except (json.JSONDecodeError, KeyError):
        return BluetoothStatus.unknown
    except asyncio.TimeoutError:
        return BluetoothStatus.unknown
    except FileNotFoundError:
        return BluetoothStatus.unavailable
    except OSError:
        return BluetoothStatus.unknown


async def get_bluetooth_status_dict() -> dict:
    """
    Get Bluetooth status as a dict for API responses.

    Returns dict matching BluetoothStatusResponse schema:
        enabled: bool - Whether Bluetooth radio is currently on
        available: bool - Whether Bluetooth functionality is available
        reason: Optional[str] - Reason if unavailable
    """
    status = await get_bluetooth_status()

    enabled = status == BluetoothStatus.on
    available = status not in (BluetoothStatus.unknown, BluetoothStatus.unavailable)

    reason = None
    if status == BluetoothStatus.unknown:
        reason = "Bluetooth not supported or rfkill unavailable"
    elif status == BluetoothStatus.unavailable:
        reason = "No Bluetooth hardware detected"

    return {
        "enabled": enabled,
        "available": available,
        "reason": reason,
    }


async def enable_bluetooth() -> dict:
    """
    Enable Bluetooth radio using rfkill.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Enabling Bluetooth radio")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/sbin/rfkill", "unblock", "bluetooth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode == 0:
            logger.info("Bluetooth radio enabled successfully")
            return {"success": True}
        else:
            error_msg = stderr.decode().strip()
            logger.warning("Failed to enable Bluetooth: %s", error_msg)
            return {"success": False, "error": error_msg or "Unknown error"}

    except asyncio.TimeoutError:
        logger.warning("Timeout enabling Bluetooth")
        return {"success": False, "error": "Timeout enabling Bluetooth"}
    except FileNotFoundError:
        logger.warning("rfkill not found, cannot enable Bluetooth")
        return {"success": False, "error": "rfkill not found"}
    except OSError as e:
        logger.warning("Failed to enable Bluetooth: %s", e)
        return {"success": False, "error": str(e)}


async def disable_bluetooth() -> dict:
    """
    Disable Bluetooth radio using rfkill.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Disabling Bluetooth radio")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/sbin/rfkill", "block", "bluetooth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode == 0:
            logger.info("Bluetooth radio disabled successfully")
            return {"success": True}
        else:
            error_msg = stderr.decode().strip()
            logger.warning("Failed to disable Bluetooth: %s", error_msg)
            return {"success": False, "error": error_msg or "Unknown error"}

    except asyncio.TimeoutError:
        logger.warning("Timeout disabling Bluetooth")
        return {"success": False, "error": "Timeout disabling Bluetooth"}
    except FileNotFoundError:
        logger.warning("rfkill not found, cannot disable Bluetooth")
        return {"success": False, "error": "rfkill not found"}
    except OSError as e:
        logger.warning("Failed to disable Bluetooth: %s", e)
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

    logger.info("Enabling CPU throttle (powersave)")
    try:
        # Try cpufreq-set first
        result = subprocess.run(
            ["cpufreq-set", "-g", "powersave"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.info("CPU throttle enabled (powersave)")
            return {"success": True, "governor": "powersave"}
        else:
            logger.warning("Failed to enable CPU throttle: %s", result.stderr.strip())
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except FileNotFoundError:
        # Try direct write to sysfs
        try:
            for cpu_path in Path("/sys/devices/system/cpu/").glob("cpu[0-9]*/cpufreq/scaling_governor"):
                cpu_path.write_text("powersave")
            logger.info("CPU throttle enabled (powersave) via sysfs")
            return {"success": True, "governor": "powersave"}
        except IOError as e:
            logger.warning("Failed to enable CPU throttle via sysfs: %s", e)
            return {"success": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        logger.warning("Timeout enabling CPU throttle")
        return {"success": False, "error": "Timeout enabling throttle"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to enable CPU throttle: %s", e)
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

    logger.info("Disabling CPU throttle (setting governor to %s)", default_governor)
    try:
        result = subprocess.run(
            ["cpufreq-set", "-g", default_governor],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.info("CPU throttle disabled (governor: %s)", default_governor)
            return {"success": True, "governor": default_governor}
        else:
            logger.warning("Failed to disable CPU throttle: %s", result.stderr.strip())
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

    except FileNotFoundError:
        # Try direct write to sysfs
        try:
            for cpu_path in Path("/sys/devices/system/cpu/").glob("cpu[0-9]*/cpufreq/scaling_governor"):
                cpu_path.write_text(default_governor)
            logger.info("CPU throttle disabled (governor: %s) via sysfs", default_governor)
            return {"success": True, "governor": default_governor}
        except IOError as e:
            logger.warning("Failed to disable CPU throttle via sysfs: %s", e)
            return {"success": False, "error": str(e)}
    except subprocess.TimeoutExpired:
        logger.warning("Timeout disabling CPU throttle")
        return {"success": False, "error": "Timeout disabling throttle"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to disable CPU throttle: %s", e)
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
        logger.info("System shutdown scheduled in %d seconds", delay)
        return {"success": True, "message": f"System shutting down in {delay} seconds"}
    except Exception as e:
        logger.warning("Failed to schedule system shutdown: %s", e)
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
        logger.info("System reboot scheduled in %d seconds", delay)
        return {"success": True, "message": f"System rebooting in {delay} seconds"}
    except Exception as e:
        logger.warning("Failed to schedule system reboot: %s", e)
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

    logger.info("Restarting all WROLPi services")
    for service in services_to_restart:
        logger.info("Restarting service %s", service)
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
            if result.returncode == 0:
                logger.info("Service %s restarted successfully", service)
            else:
                logger.warning("Failed to restart service %s: %s", service, result.stderr.strip())
        except subprocess.TimeoutExpired:
            logger.warning("Timeout restarting service %s", service)
            results[service] = {"success": False, "error": "Timeout"}
        except FileNotFoundError:
            logger.warning("systemctl not found while restarting %s", service)
            results[service] = {"success": False, "error": "systemctl not found"}
        except Exception as e:
            logger.warning("Failed to restart service %s: %s", service, e)
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


# --- Timezone ---


def get_timezone_status_dict() -> dict:
    """
    Get current system timezone status.

    Returns dict matching TimezoneStatusResponse schema:
        available: bool - Whether system timezone control is available
        timezone: Optional[str] - Current system timezone (IANA)
        reason: Optional[str] - Reason if unavailable
    """
    if is_docker_mode():
        return {
            "available": False,
            "timezone": None,
            "reason": "Docker mode",
        }

    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return {
                "available": True,
                "timezone": result.stdout.strip(),
                "reason": None,
            }
        else:
            return {
                "available": False,
                "timezone": None,
                "reason": result.stderr.strip() or "timedatectl returned an error",
            }
    except FileNotFoundError:
        return {
            "available": False,
            "timezone": None,
            "reason": "timedatectl not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "timezone": None,
            "reason": "timedatectl timed out",
        }
    except subprocess.SubprocessError as e:
        return {
            "available": False,
            "timezone": None,
            "reason": str(e),
        }


def set_timezone(timezone: str) -> dict:
    """
    Set the system timezone using timedatectl.

    Args:
        timezone: IANA timezone string (e.g. "America/Denver")

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "timezone": None, "error": "Not available in Docker mode"}

    if not timezone or not timezone.strip():
        return {"success": False, "timezone": None, "error": "Timezone must not be empty"}

    logger.info("Setting system timezone to %s", timezone)
    try:
        result = subprocess.run(
            ["timedatectl", "set-timezone", timezone],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            logger.info("System timezone set to %s", timezone)
            return {"success": True, "timezone": timezone, "error": None}
        else:
            logger.warning("Failed to set timezone to %s: %s", timezone, result.stderr.strip())
            return {"success": False, "timezone": None, "error": result.stderr.strip() or "Unknown error"}

    except FileNotFoundError:
        logger.warning("timedatectl not found, cannot set timezone")
        return {"success": False, "timezone": None, "error": "timedatectl not found"}
    except subprocess.TimeoutExpired:
        logger.warning("Timeout setting timezone to %s", timezone)
        return {"success": False, "timezone": None, "error": "Timeout setting timezone"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to set timezone: %s", e)
        return {"success": False, "timezone": None, "error": str(e)}


def apply_timezone_from_config():
    """
    Read the timezone from wrolpi.yaml and apply it to the system.
    Called on Controller startup to ensure system timezone matches config.
    """
    if is_docker_mode():
        return

    config_path = get_media_directory() / 'config' / 'wrolpi.yaml'
    if not config_path.exists():
        return

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        logger.warning("Failed to read wrolpi.yaml for timezone: %s", e)
        return

    timezone = config.get('timezone')
    if not timezone:
        return

    result = set_timezone(timezone)
    if result.get('success'):
        logger.info("Applied system timezone from config: %s", timezone)
    else:
        logger.warning("Failed to apply system timezone '%s': %s", timezone, result.get('error'))
