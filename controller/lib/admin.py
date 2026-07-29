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

from controller.lib import config as config_lib
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


class DesktopStatus(enum.Enum):
    """Graphical desktop (display manager) status."""
    on = enum.auto()  # Display manager is running.
    off = enum.auto()  # Display manager is installed, but stopped.
    unavailable = enum.auto()  # No display manager installed.
    unknown = enum.auto()  # Docker mode or cannot determine.


class VncStatus(enum.Enum):
    """VNC server status."""
    on = enum.auto()  # VNC server is running.
    off = enum.auto()  # A VNC server is installed, but stopped.
    unavailable = enum.auto()  # No usable VNC server installed.
    unknown = enum.auto()  # Docker mode or cannot determine.


class GovernorStatus(enum.Enum):
    """CPU governor status enum matching wrolpi/admin.py"""
    ondemand = enum.auto()
    powersave = enum.auto()
    unknown = enum.auto()


def get_hotspot_device() -> str:
    return get_config_value('hotspot.device', 'wlan0')


def get_hotspot_ssid() -> str:
    return get_config_value('hotspot.ssid', 'WROLPi')


def get_hotspot_password() -> str:
    return get_config_value('hotspot.password', 'wrolpi hotspot')


# WPA2 uses nmcli's default `wpa-psk` key management; WPA3 uses `sae`.
HOTSPOT_PROTOCOLS = ('wpa2', 'wpa3')


def get_hotspot_protocol() -> str:
    return get_config_value('hotspot.protocol', 'wpa2')


def get_device_hotspot_protocols(device: str) -> list[str]:
    """
    Probe a WiFi device with `iw` and report which hotspot protocols it can host.

    WPA2 only requires AP mode.  WPA3 requires SAE in AP mode, which is only possible
    when the firmware offloads SAE for APs (SAE_OFFLOAD_AP), or the driver is
    mac80211-based (advertises AP/VLAN) with the CMAC cipher so wpa_supplicant can run
    SAE in software.  Notably the Raspberry Pi's brcmfmac driver supports neither.
    """
    if is_docker_mode():
        return []

    try:
        # Absolute path like rfkill; `iw` is in /usr/sbin which is not on every PATH.
        result = subprocess.run(
            ["/usr/sbin/iw", "dev", device, "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        wiphy = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("wiphy "):
                wiphy = stripped.split()[1]
                break
        if wiphy is None:
            return []

        result = subprocess.run(
            ["/usr/sbin/iw", "phy", f"phy{wiphy}", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        # Cannot probe without `iw`; assume the WPA2 hotspot nmcli has always created.
        return ['wpa2']

    modes, ciphers, ext_features = set(), set(), set()
    section = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith('Supported interface modes:'):
            section = 'modes'
            continue
        elif stripped.startswith('Supported Ciphers:'):
            section = 'ciphers'
            continue
        elif stripped.startswith(('Supported extended features:', 'Extended features:')):
            # Real Pi hardware prints "Supported extended features:"; older iw
            # releases print "Extended features:".
            section = 'ext'
            continue
        if not stripped.startswith('*'):
            section = None
            continue
        value = stripped.lstrip('* ').strip()
        if section == 'modes':
            modes.add(value)
        elif section == 'ciphers':
            ciphers.add(value.split()[0])
        elif section == 'ext' and '[' in stripped and ']' in stripped:
            ext_features.add(stripped.split('[', 1)[1].split(']', 1)[0].strip())

    protocols = []
    if 'AP' in modes:
        protocols.append('wpa2')
        sae_offload_ap = 'SAE_OFFLOAD_AP' in ext_features
        software_sae = 'AP/VLAN' in modes and any('CMAC' in cipher for cipher in ciphers)
        if sae_offload_ap or software_sae:
            protocols.append('wpa3')
    return protocols


def update_hotspot_settings(device: str = None, ssid: str = None, password: str = None,
                            protocol: str = None) -> dict:
    """
    Update hotspot settings in controller.yaml.  Only provided values are changed.

    Returns:
        dict with success status and the current settings
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    if device is not None and not device.strip():
        return {"success": False, "error": "Hotspot device must not be empty"}
    if ssid is not None and not ssid.strip():
        return {"success": False, "error": "Hotspot SSID must not be empty"}
    # nmcli requires a WPA password of 8 to 63 characters.
    if password is not None and not 8 <= len(password) <= 63:
        return {"success": False, "error": "Hotspot password must be 8 to 63 characters"}
    if protocol is not None and protocol not in HOTSPOT_PROTOCOLS:
        return {"success": False, "error": f"Hotspot protocol must be one of: {', '.join(HOTSPOT_PROTOCOLS)}"}

    changed = False
    if device:
        config_lib.update_config('hotspot.device', device)
        changed = True
    if ssid:
        config_lib.update_config('hotspot.ssid', ssid)
        changed = True
    if password:
        config_lib.update_config('hotspot.password', password)
        changed = True
    if protocol:
        config_lib.update_config('hotspot.protocol', protocol)
        changed = True

    if changed:
        try:
            config_lib.save_config()
        except RuntimeError as e:
            return {"success": False, "error": str(e)}

    logger.info("Hotspot settings updated (device=%s, ssid=%s, protocol=%s)",
                get_hotspot_device(), get_hotspot_ssid(), get_hotspot_protocol())
    return {
        "success": True,
        "device": get_hotspot_device(),
        "ssid": get_hotspot_ssid(),
        "password": get_hotspot_password(),
        "protocol": get_hotspot_protocol(),
    }


def migrate_hotspot_settings_from_wrolpi_config():
    """
    One-time copy of hotspot settings from wrolpi.yaml into controller.yaml.

    Hotspot settings used to be saved in wrolpi.yaml by the Settings page; the
    Controller now owns them in controller.yaml.  Copy any values the user set
    in wrolpi.yaml unless controller.yaml already sets them explicitly.
    Called on Controller startup after the primary drive is mounted.
    """
    if not config_lib.CONFIG_PATH_ON_DRIVE.exists():
        return

    try:
        with open(config_lib.CONFIG_PATH_ON_DRIVE) as f:
            controller_config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        logger.warning("Failed to read controller.yaml for hotspot migration: %s", e)
        return

    wrolpi_config_path = get_media_directory() / 'config' / 'wrolpi.yaml'
    if not wrolpi_config_path.exists():
        return

    try:
        with open(wrolpi_config_path) as f:
            wrolpi_config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        logger.warning("Failed to read wrolpi.yaml for hotspot migration: %s", e)
        return

    explicit = controller_config.get('hotspot') or {}
    key_map = {'device': 'hotspot_device', 'ssid': 'hotspot_ssid', 'password': 'hotspot_password'}
    changed = False
    for controller_key, wrolpi_key in key_map.items():
        value = wrolpi_config.get(wrolpi_key)
        if value and controller_key not in explicit and value != get_config_value(f'hotspot.{controller_key}'):
            config_lib.update_config(f'hotspot.{controller_key}', value)
            changed = True

    if changed:
        try:
            config_lib.save_config()
            logger.info("Migrated hotspot settings from wrolpi.yaml to controller.yaml")
        except RuntimeError as e:
            logger.warning("Could not save migrated hotspot settings: %s", e)


def get_wifi_devices() -> list[str]:
    """
    List WiFi device names (e.g. wlan0, wlp2s0) using nmcli.

    Returns an empty list in Docker mode or when nmcli is unavailable.
    """
    if is_docker_mode():
        return []

    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        devices = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            # Exact "wifi" match excludes wifi-p2p devices.
            if len(parts) >= 2 and parts[1] == "wifi":
                devices.append(parts[0])
        return devices
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return []


def get_current_ssid(interface: str = None) -> str | None:
    """
    Returns the name of the SSID that is currently connected.
    Returns None if Hotspot is active, or no Wi-Fi network is being used.
    """
    if interface is None:
        interface = get_hotspot_device()
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

    device = get_hotspot_device()

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
    device = get_hotspot_device()
    status = get_hotspot_status()

    # Map enum status to enabled/available flags
    enabled = status == HotspotStatus.connected
    # Hotspot is available even when radio is off because start_hotspot()
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
        "ssid": get_hotspot_ssid() if enabled else None,
        "device": device,
    }


def start_hotspot() -> dict:
    """
    Start the WiFi hotspot (turn the radio on and bring up the Hotspot connection).

    Returns:
        dict with success status and message
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    device = get_hotspot_device()
    ssid = get_hotspot_ssid()
    password = get_hotspot_password()
    protocol = get_hotspot_protocol()

    try:
        # First ensure radio is on
        subprocess.run(
            ["nmcli", "radio", "wifi", "on"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Wait for device to become ready after radio on.
        # On real hardware, the device transitions from 'unavailable' to 'disconnected'
        # which can take a few seconds.
        import time
        device_ready = False
        for _ in range(20):  # 20 * 0.5s = 10s max
            check = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if check.returncode == 0:
                for line in check.stdout.strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[0] == device and parts[1] != "unavailable":
                        device_ready = True
                        break
            if device_ready:
                break
            time.sleep(0.5)

        if not device_ready:
            logger.warning("WiFi device %s did not become ready after turning radio on", device)
            return {"success": False, "error": f"WiFi device {device} not ready after turning radio on"}

        # Create hotspot using NetworkManager
        logger.info("Starting hotspot on %s with SSID %s", device, ssid)
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

        if result.returncode != 0:
            logger.warning("Failed to start hotspot: %s", result.stderr.strip())
            return {"success": False, "error": result.stderr.strip() or "Unknown error"}

        # Explicitly set the key management so a reused "Hotspot" profile does not
        # keep a previously configured protocol.  WPA3 (SAE) requires PMF.
        key_mgmt = "sae" if protocol == "wpa3" else "wpa-psk"
        pmf = "3" if protocol == "wpa3" else "0"  # 3=required, 0=default
        modify = subprocess.run(
            ["nmcli", "connection", "modify", "Hotspot",
             "802-11-wireless-security.key-mgmt", key_mgmt,
             "802-11-wireless-security.pmf", pmf],
            capture_output=True,
            text=True,
            timeout=10,
        )
        up = None
        if modify.returncode == 0:
            # Re-activate so the profile change takes effect.
            up = subprocess.run(
                ["nmcli", "connection", "up", "Hotspot"],
                capture_output=True,
                text=True,
                timeout=30,
            )

        if modify.returncode != 0 or up.returncode != 0:
            error = (modify.stderr if modify.returncode != 0 else up.stderr).strip()
            if protocol == "wpa3":
                # The driver likely rejected SAE; revert so the hotspot still works.
                logger.warning("Failed to start WPA3 hotspot, reverting to WPA2: %s", error)
                revert_modify = subprocess.run(
                    ["nmcli", "connection", "modify", "Hotspot",
                     "802-11-wireless-security.key-mgmt", "wpa-psk",
                     "802-11-wireless-security.pmf", "0"],
                    capture_output=True, text=True, timeout=10,
                )
                revert_up = None
                if revert_modify.returncode == 0:
                    revert_up = subprocess.run(
                        ["nmcli", "connection", "up", "Hotspot"],
                        capture_output=True, text=True, timeout=30,
                    )
                if revert_modify.returncode == 0 and revert_up.returncode == 0:
                    return {"success": False,
                            "error": f"WPA3 is not supported by {device}; hotspot reverted to WPA2: {error}"}
                revert_error = (revert_modify.stderr if revert_modify.returncode != 0 else revert_up.stderr).strip()
                logger.error("Reverting hotspot to WPA2 also failed: %s", revert_error)
                return {"success": False,
                        "error": f"WPA3 failed on {device} and falling back to WPA2 also failed;"
                                 f" the hotspot may be down: {error}"}
            # WPA2 is what nmcli created the hotspot with anyway; not fatal.
            logger.warning("Failed to explicitly set WPA2 on hotspot: %s", error)

        logger.info("Hotspot started successfully on %s (%s)", device, protocol)
        return {"success": True, "ssid": ssid, "device": device}

    except subprocess.TimeoutExpired:
        logger.warning("Timeout starting hotspot on %s", device)
        return {"success": False, "error": "Timeout starting hotspot"}
    except FileNotFoundError:
        logger.warning("nmcli not found, cannot start hotspot")
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to start hotspot: %s", e)
        return {"success": False, "error": str(e)}


def stop_hotspot() -> dict:
    """
    Stop the WiFi hotspot by turning the WiFi radio off.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Stopping hotspot (turning WiFi radio off)")
    try:
        # Turn off the radio to disconnect hotspot
        result = subprocess.run(
            ["nmcli", "radio", "wifi", "off"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Success even if already off
        logger.info("Hotspot stopped successfully")
        return {"success": True}

    except subprocess.TimeoutExpired:
        logger.warning("Timeout stopping hotspot")
        return {"success": False, "error": "Timeout stopping hotspot"}
    except FileNotFoundError:
        logger.warning("nmcli not found, cannot stop hotspot")
        return {"success": False, "error": "nmcli not found"}
    except subprocess.SubprocessError as e:
        logger.warning("Failed to stop hotspot: %s", e)
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


async def unblock_bluetooth() -> dict:
    """
    Unblock the Bluetooth radio using rfkill (turns it on).

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Unblocking Bluetooth radio")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/sbin/rfkill", "unblock", "bluetooth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode == 0:
            logger.info("Bluetooth radio unblocked successfully")
            return {"success": True}
        else:
            error_msg = stderr.decode().strip()
            logger.warning("Failed to unblock Bluetooth: %s", error_msg)
            return {"success": False, "error": error_msg or "Unknown error"}

    except asyncio.TimeoutError:
        logger.warning("Timeout unblocking Bluetooth")
        return {"success": False, "error": "Timeout unblocking Bluetooth"}
    except FileNotFoundError:
        logger.warning("rfkill not found, cannot unblock Bluetooth")
        return {"success": False, "error": "rfkill not found"}
    except OSError as e:
        logger.warning("Failed to unblock Bluetooth: %s", e)
        return {"success": False, "error": str(e)}


async def block_bluetooth() -> dict:
    """
    Block the Bluetooth radio using rfkill (turns it off).

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("Blocking Bluetooth radio")
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/sbin/rfkill", "block", "bluetooth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode == 0:
            logger.info("Bluetooth radio blocked successfully")
            return {"success": True}
        else:
            error_msg = stderr.decode().strip()
            logger.warning("Failed to block Bluetooth: %s", error_msg)
            return {"success": False, "error": error_msg or "Unknown error"}

    except asyncio.TimeoutError:
        logger.warning("Timeout blocking Bluetooth")
        return {"success": False, "error": "Timeout blocking Bluetooth"}
    except FileNotFoundError:
        logger.warning("rfkill not found, cannot block Bluetooth")
        return {"success": False, "error": "rfkill not found"}
    except OSError as e:
        logger.warning("Failed to block Bluetooth: %s", e)
        return {"success": False, "error": str(e)}


# --- systemd units ---

async def _unit_properties(unit: str, *properties: str) -> dict | None:
    """
    Read systemd properties for a unit, e.g. LoadState and ActiveState.

    `systemctl show` exits 0 even for a unit that does not exist (reporting
    LoadState=not-found), so callers must judge existence from LoadState.
    Note ConditionResult is useless here: it reports "no" for any unit that has
    never been started, configured or not.

    Returns None when systemctl itself failed.  Timeouts and OSError propagate so
    callers can tell "no systemd here" from "systemd would not answer".
    """
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "show", unit, f"--property={','.join(properties)}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

    if proc.returncode != 0:
        return None

    return dict(
        line.split("=", 1) for line in stdout.decode().strip().splitlines() if "=" in line
    )


async def _systemctl_unit(action: str, unit: str, label: str) -> dict:
    """Run `systemctl <start|stop> <unit>` and report the result."""
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    logger.info("%s %s requested (%s)", label, action, unit)
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", action, unit,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode == 0:
            logger.info("%s %s succeeded", label, action)
            return {"success": True}
        else:
            error_msg = stderr.decode().strip()
            logger.warning("Failed to %s %s: %s", action, label.lower(), error_msg)
            return {"success": False, "error": error_msg or "Unknown error"}

    except asyncio.TimeoutError:
        logger.warning("Timeout during %s %s", label.lower(), action)
        return {"success": False, "error": f"Timeout during {label.lower()} {action}"}
    except FileNotFoundError:
        logger.warning("systemctl not found, cannot %s %s", action, label.lower())
        return {"success": False, "error": "systemctl not found"}
    except OSError as e:
        logger.warning("Failed to %s %s: %s", action, label.lower(), e)
        return {"success": False, "error": str(e)}


# --- Desktop ---

# Every display manager (lightdm on RPi OS, gdm3/sddm on Debian) provides this
# systemd alias, so the Controller does not need to know which one is installed.
DISPLAY_MANAGER_UNIT = "display-manager.service"


async def get_desktop_status() -> DesktopStatus:
    """
    Get the graphical desktop status by checking the display manager's systemd unit.

    Returns:
        DesktopStatus enum value
    """
    if is_docker_mode():
        return DesktopStatus.unknown

    try:
        properties = await _unit_properties(DISPLAY_MANAGER_UNIT, "LoadState", "ActiveState")
        if properties is None:
            return DesktopStatus.unknown

        if properties.get("LoadState") != "loaded":
            # "not-found" when no display manager is installed (e.g. RPi OS Lite).
            return DesktopStatus.unavailable

        return DesktopStatus.on if properties.get("ActiveState") == "active" else DesktopStatus.off

    except asyncio.TimeoutError:
        return DesktopStatus.unknown
    except FileNotFoundError:
        return DesktopStatus.unavailable
    except OSError:
        return DesktopStatus.unknown


async def get_desktop_status_dict() -> dict:
    """
    Get desktop status as a dict for API responses.

    Returns dict matching DesktopStatusResponse schema:
        running: bool - Whether the display manager is currently running
        available: bool - Whether a display manager is installed
        reason: Optional[str] - Reason if unavailable
    """
    status = await get_desktop_status()

    running = status == DesktopStatus.on
    available = status in (DesktopStatus.on, DesktopStatus.off)

    reason = None
    if status == DesktopStatus.unknown:
        reason = "Desktop not supported or systemctl unavailable"
    elif status == DesktopStatus.unavailable:
        reason = "No display manager installed"

    return {
        "running": running,
        "available": available,
        "reason": reason,
    }


async def _systemctl_desktop(action: str) -> dict:
    """Run `systemctl <start|stop> display-manager.service` and report the result."""
    return await _systemctl_unit(action, DISPLAY_MANAGER_UNIT, "Desktop")


# Stopping the display manager leaves the monitor black with only a blinking
# cursor, even though the console VT is already in the foreground with a getty
# and a shell on it: the display manager hands the display back without the
# console being repainted.  Bouncing through another VT forces a modeset and
# redraw, and a short message guarantees there is something legible on screen.
CONSOLE_VT = "1"
CONSOLE_GETTY_UNIT = "getty@tty1.service"
CONSOLE_DEVICE = "/dev/tty1"
REPAINT_VT = "2"

CONSOLE_MESSAGE = (
    "\n*** The WROLPi Controller stopped the desktop. ***\n"
    "*** Press Enter for a prompt.  Start the desktop again with: ***\n"
    "***   sudo systemctl start display-manager ***\n\n"
)


async def _console_getty_active() -> bool:
    """Whether a getty is running on the console VT (i.e. switching there gives a terminal)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", CONSOLE_GETTY_UNIT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return False


async def _chvt(vt: str) -> bool:
    """Activate a virtual terminal.  Returns True on success."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/chvt", vt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return True
        logger.warning("Failed to switch to VT %s: %s", vt, stderr.decode().strip())
        return False
    except asyncio.TimeoutError:
        logger.warning("Timeout switching to VT %s", vt)
        return False
    except FileNotFoundError:
        logger.warning("chvt not found; cannot switch VTs")
        return False
    except OSError as e:
        logger.warning("Failed to switch to VT %s: %s", vt, e)
        return False


def _write_console_message():
    """Print a short message on the console so the screen is not left blank."""
    try:
        with open(CONSOLE_DEVICE, "w") as console:
            console.write(CONSOLE_MESSAGE)
    except OSError as e:
        logger.warning("Could not write to %s: %s", CONSOLE_DEVICE, e)


async def _switch_to_console_vt() -> bool:
    """
    Leave the physical display showing a usable terminal.

    Best-effort: never fails the caller.  Returns True when the console was
    activated and repainted.
    """
    if not await _console_getty_active():
        # Without a getty there is no terminal to show, so leave the display alone.
        logger.warning("No getty on %s; leaving the display as-is", CONSOLE_GETTY_UNIT)
        return False

    if not await _chvt(CONSOLE_VT):
        return False

    # The console VT is usually already in the foreground, but stale after the
    # display manager released the display; bounce off another VT to repaint it.
    if await _chvt(REPAINT_VT) and not await _chvt(CONSOLE_VT):
        logger.error("Left the display on VT %s after failing to return to VT %s",
                     REPAINT_VT, CONSOLE_VT)
        return False

    _write_console_message()
    logger.info("Console VT %s activated and repainted", CONSOLE_VT)
    return True


async def start_desktop() -> dict:
    """
    Start the graphical desktop (display manager) until stopped or reboot.

    This deliberately does not `systemctl enable` the unit; whether the desktop
    starts on boot is left to the system's default target.

    Returns:
        dict with success status
    """
    return await _systemctl_desktop("start")


async def stop_desktop() -> dict:
    """
    Stop the graphical desktop (display manager) until started or reboot, then
    drop the physical display to a console terminal.

    Fail open: this deliberately does not `systemctl disable` the unit, so the
    desktop returns on the next boot.

    Returns:
        dict with success status and whether the display reached the console
    """
    result = await _systemctl_desktop("stop")
    if result.get("success"):
        result["switched_to_console"] = await _switch_to_console_vt()
    return result


# --- VNC ---

# Raspberry Pi OS ships wayvnc for Wayland sessions and RealVNC for X11; a Pi may
# have both installed.  wayvnc only works when its config exists, which is also
# the unit's own ConditionPathExists.
WAYVNC_UNIT = "wayvnc.service"
WAYVNC_CONFIG = Path("/etc/wayvnc/config")
REALVNC_UNIT = "vncserver-x11-serviced.service"
VNC_PORT = 5900


async def _unit_is_loaded(unit: str) -> bool:
    """Whether systemd knows about a unit."""
    properties = await _unit_properties(unit, "LoadState")
    return bool(properties) and properties.get("LoadState") == "loaded"


async def get_vnc_backend() -> tuple[str | None, str | None, str | None]:
    """
    Pick the VNC backend to control.

    Prefers wayvnc (Raspberry Pi OS uses Wayland), falling back to RealVNC.

    Deliberately does not copy `raspi-config`'s live-compositor probe
    (`pgrep labwc || pgrep wayfire`), which reports X11 — and would therefore pick
    RealVNC — whenever the desktop happens to be stopped.

    Never raises: a host without systemd simply has no VNC backend.

    Returns:
        (unit, name, reason) where reason explains an absent backend
    """
    try:
        wayvnc_loaded = await _unit_is_loaded(WAYVNC_UNIT)
        if wayvnc_loaded and WAYVNC_CONFIG.is_file():
            return WAYVNC_UNIT, "wayvnc", None

        if await _unit_is_loaded(REALVNC_UNIT):
            return REALVNC_UNIT, "realvnc", None
    except (asyncio.TimeoutError, OSError):
        return None, None, "VNC not supported or systemctl unavailable"

    if wayvnc_loaded:
        # Installed but unconfigured; starting it would fail its own condition.
        return None, None, f"wayvnc is installed but not configured ({WAYVNC_CONFIG} is missing)"

    return None, None, "No VNC server installed"


async def get_vnc_status() -> VncStatus:
    """
    Get the VNC server status from whichever backend is installed.

    Returns:
        VncStatus enum value
    """
    if is_docker_mode():
        return VncStatus.unknown

    try:
        unit, _, _ = await get_vnc_backend()
        if unit is None:
            return VncStatus.unavailable

        properties = await _unit_properties(unit, "ActiveState")
        if properties is None:
            return VncStatus.unknown

        return VncStatus.on if properties.get("ActiveState") == "active" else VncStatus.off

    except asyncio.TimeoutError:
        return VncStatus.unknown
    except FileNotFoundError:
        return VncStatus.unavailable
    except OSError:
        return VncStatus.unknown


async def get_vnc_status_dict() -> dict:
    """
    Get VNC status as a dict for API responses.

    Returns dict matching VncStatusResponse schema:
        running: bool - Whether the VNC server is currently running
        available: bool - Whether a usable VNC server is installed
        desktop_running: bool - Whether the desktop VNC would serve is running
        can_start: bool - Whether VNC can be started right now
        reason: Optional[str] - Why VNC is unavailable or cannot be started
        backend: Optional[str] - "wayvnc" or "realvnc"
        port: int - Port the VNC server listens on
    """
    status = await get_vnc_status()
    _, backend, unavailable_reason = await get_vnc_backend()
    desktop_running = await get_desktop_status() == DesktopStatus.on

    running = status == VncStatus.on
    available = status in (VncStatus.on, VncStatus.off)
    # VNC serves the desktop session, so there is nothing to show without it.
    can_start = available and desktop_running

    reason = None
    if status == VncStatus.unknown:
        reason = "VNC not supported or systemctl unavailable"
    elif status == VncStatus.unavailable:
        reason = unavailable_reason or "No VNC server installed"
    elif not desktop_running:
        reason = "The Desktop must be running to use VNC"

    return {
        "running": running,
        "available": available,
        "desktop_running": desktop_running,
        "can_start": can_start,
        "reason": reason,
        "backend": backend,
        "port": VNC_PORT,
    }


async def start_vnc() -> dict:
    """
    Start the VNC server until stopped or reboot.

    Requires a running desktop: VNC serves that session, so starting it without
    one gives clients a blank screen.

    Fail open in the same sense as the desktop: the unit is never enabled, so VNC
    does not come back after a reboot.  Users who want it permanently on can
    enable it with raspi-config.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit, _, reason = await get_vnc_backend()
    if unit is None:
        return {"success": False, "error": reason or "No VNC server installed"}

    if await get_desktop_status() != DesktopStatus.on:
        return {
            "success": False,
            "error": "The Desktop must be running to start VNC",
            "precondition_failed": True,
        }

    return await _systemctl_unit("start", unit, "VNC")


async def stop_vnc() -> dict:
    """
    Stop the VNC server.

    Always allowed, even with the desktop stopped, so a running VNC server can
    never be left on with no way to turn it off.

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    unit, _, reason = await get_vnc_backend()
    if unit is None:
        return {"success": False, "error": reason or "No VNC server installed"}

    return await _systemctl_unit("stop", unit, "VNC")


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
