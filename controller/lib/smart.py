"""
SMART disk health monitoring for WROLPi Controller.
"""

import re
import subprocess
from typing import Optional

# Import pySMART only if available
try:
    from pySMART import DeviceList, Device

    SMART_AVAILABLE = True
except ImportError:
    SMART_AVAILABLE = False

from controller.lib.config import is_docker_mode

# Warning thresholds for hard-drive temperature, in Celsius.  Unlike CPU
# temperature, neither SMART nor psutil reports a recommended limit, so we
# carry sensible spinning-disk defaults in the payload (warn 55, critical 65)
# and let the frontend stay dumb.
HDD_HIGH_TEMPERATURE = 55
HDD_CRITICAL_TEMPERATURE = 65

SMARTCTL_SCAN_TIMEOUT = 10
SMARTCTL_STANDBY_TIMEOUT = 5


def is_smart_available() -> bool:
    """Check if SMART monitoring is available."""
    if is_docker_mode():
        return False
    return SMART_AVAILABLE


def get_all_smart_status() -> list[dict]:
    """
    Get SMART status for all drives.

    Returns:
        list of SMART status dicts
    """
    if not is_smart_available():
        return []

    try:
        results = []
        covered = set()
        for device in DeviceList().devices:
            results.append(_get_device_smart(device))
            covered.add(f"/dev/{device.name}")

        # Drives behind USB enclosures that reject ATA pass-through (e.g.
        # Seagate Expansion, WD easystore) are invisible to pySMART/DeviceList.
        # smartctl --scan still lists them; add a coarse SCSI health entry so
        # the drive is at least represented instead of silently unmonitored.
        for path, _interface in _scan_devices():
            if path in covered:
                continue
            limited = _limited_device_smart(path)
            if limited is not None:
                results.append(limited)

        return results
    except Exception:
        return []


def _get_device_smart(device) -> dict:
    """Extract SMART data from a pySMART device."""
    pending = _get_attribute(device, "Current_Pending_Sector")
    reallocated = _get_attribute(device, "Reallocated_Sector_Ct")
    uncorrectable = _get_attribute(device, "Offline_Uncorrectable")
    return {
        "device": device.name,
        "path": f"/dev/{device.name}",
        "model": device.model,
        "serial": device.serial,
        "capacity": device.capacity,
        "assessment": device.assessment,  # PASS, FAIL, WARN (pySMART's view)
        "health": _derive_health(device.assessment, pending, uncorrectable),
        "temperature": _get_temperature(device),
        "power_on_hours": _get_attribute(device, "Power_On_Hours"),
        "reallocated_sectors": reallocated,
        "pending_sectors": pending,
        "offline_uncorrectable": uncorrectable,
        "smart_enabled": device.smart_enabled,
    }


def _derive_health(assessment, pending_sectors, offline_uncorrectable) -> Optional[str]:
    """Derive the overall health verdict shown in the navbar and UIs.

    pySMART's ``assessment`` only reflects the drive's own pass/fail
    self-assessment, which is driven by attributes flagged FAILING_NOW.  A
    drive can be quietly losing data to unreadable sectors while still
    self-assessing PASS, so we downgrade to WARN when sectors are pending
    reallocation or already uncorrectable.

    ``Reallocated_Sector_Ct`` is intentionally NOT a trigger: a small,
    stable reallocated count is common and benign, and warning on it would
    cry wolf.  ``assessment`` of None (unsupported drive) passes through
    unchanged.
    """
    if (assessment or "").upper() == "FAIL":
        return "FAIL"
    if (pending_sectors or 0) > 0 or (offline_uncorrectable or 0) > 0:
        return "WARN"
    return assessment


def _get_temperature(device) -> Optional[int]:
    """Get drive temperature.

    Prefer pySMART's `temperature` property: it parses real-world raw
    values like "52 (Min/Max 16/57)" that int() cannot, and works for
    NVMe devices which have no ATA attribute table.  Fall back to the
    plain attributes for devices where the property is unavailable.
    """
    temp = getattr(device, "temperature", None)
    if isinstance(temp, int):
        return temp
    temp = _get_attribute(device, "Temperature_Celsius")
    if temp is None:
        temp = _get_attribute(device, "Airflow_Temperature_Cel")
    return temp


def _get_attribute(device, name: str) -> Optional[int]:
    """Get a specific SMART attribute value as an integer."""
    if not hasattr(device, 'attributes') or device.attributes is None:
        return None

    for attr in device.attributes:
        if attr and attr.name == name:
            return _parse_raw_int(attr.raw)
    return None


def _parse_raw_int(raw) -> Optional[int]:
    """Parse the integer value out of a SMART attribute's raw field.

    smartctl/pySMART decorate some raw values in vendor-specific ways that
    plain int() cannot handle: Seagate reports Power_On_Hours as
    ``'50287h+00m+00.000s'`` and Temperature_Celsius as ``'53 (0 17 0 0 0)'``.
    Extract the leading integer so these are not silently discarded.
    """
    try:
        return int(raw)
    except (ValueError, TypeError):
        pass
    if raw is None:
        return None
    match = re.match(r'\s*(-?\d+)', str(raw))
    return int(match.group(1)) if match else None


def _scan_devices() -> list[tuple[str, Optional[str]]]:
    """List SMART-capable devices via ``smartctl --scan``.

    ``--scan`` only enumerates devices; it does not read SMART data, so it
    does not wake a drive that has spun down.  Returns (path, interface)
    tuples, where interface is the ``-d`` type smartctl detected (e.g.
    "sat") or None.
    """
    try:
        result = subprocess.run(
            ["smartctl", "--scan"],
            capture_output=True, text=True, timeout=SMARTCTL_SCAN_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return []

    devices = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: "/dev/sda -d sat # /dev/sda [SAT], ATA device"
        parts = line.split()
        path = parts[0]
        if not path.startswith("/dev/"):
            continue
        interface = None
        if "-d" in parts:
            idx = parts.index("-d")
            if idx + 1 < len(parts):
                interface = parts[idx + 1]
        devices.append((path, interface))
    return devices


def _read_scsi_limited(path: str) -> tuple:
    """Read the coarse SCSI health (and identity) for a USB-bridge drive.

    USB enclosures that reject ATA pass-through expose no SMART attributes,
    but many still answer the SCSI health query.  Both the health check and
    INQUIRY are non-media SCSI commands, so they do not spin up a parked
    drive.

    The health and identity reads MUST be issued as separate smartctl calls:
    when ``-i`` reports "SMART support is: Unavailable" (which these bridges
    do), combining it with ``-H`` makes smartctl suppress the health line,
    even though the standalone ``-d scsi -H`` query answers fine.

    Returns ``(health, model, serial, capacity)`` where health is 'PASS',
    'FAIL', or None.  This is the only signal available for such drives; it
    carries no attributes or temperature, and some bridges report 'OK'
    statically, so it is a weak signal — callers mark it ``smart_limited``.
    """
    health = _scsi_health(path)
    if health is None:
        # No health signal means nothing useful; skip the identity read too.
        return (None, None, None, None)
    model, serial, capacity = _scsi_identity(path)
    return (health, model, serial, capacity)


def _scsi_health(path: str) -> Optional[str]:
    """Return 'PASS'/'FAIL'/None from ``smartctl -d scsi -H`` (alone)."""
    try:
        result = subprocess.run(
            ["smartctl", "-d", "scsi", "-H", path],
            capture_output=True, text=True, timeout=SMARTCTL_STANDBY_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    for line in result.stdout.splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip().lower() == "smart health status":
            val = val.strip()
            if not val:
                return None
            return "PASS" if val.upper() == "OK" else "FAIL"
    return None


def _scsi_identity(path: str) -> tuple:
    """Return ``(model, serial, capacity)`` from ``smartctl -d scsi -i``."""
    try:
        result = subprocess.run(
            ["smartctl", "-d", "scsi", "-i", path],
            capture_output=True, text=True, timeout=SMARTCTL_STANDBY_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return (None, None, None)
    vendor = product = serial = capacity = None
    for line in result.stdout.splitlines():
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        val = val.strip()
        if key == "vendor":
            vendor = val
        elif key == "product":
            product = val
        elif key == "serial number":
            serial = val
        elif key == "user capacity":
            # e.g. "26,000,658,267,648 bytes [26.0 TB]" -> "26.0 TB"
            bracket = re.search(r'\[([^\]]+)\]', val)
            capacity = bracket.group(1) if bracket else (val or None)
    model = " ".join(p for p in (vendor, product) if p) or None
    return (model, serial, capacity)


def _limited_device_smart(path: str) -> Optional[dict]:
    """Build a coarse SMART payload for a drive pySMART cannot read.

    Used for USB-bridge drives without ATA pass-through.  Only the SCSI
    health is available; attributes, temperature and power-on hours are
    unknown.  The payload is shaped like ``_get_device_smart`` so the UIs can
    render it uniformly, but is marked ``smart_limited`` so a green PASS is
    not mistaken for full monitoring.  Returns None when even the SCSI health
    is unavailable (nothing useful to show).
    """
    health, model, serial, capacity = _read_scsi_limited(path)
    if health is None:
        return None
    return {
        "device": path.rsplit("/", 1)[-1],
        "path": path,
        "model": model,
        "serial": serial,
        "capacity": capacity,
        "assessment": None,  # the drive's own ATA self-assessment is unreachable
        "health": health,
        "temperature": None,
        "power_on_hours": None,
        "reallocated_sectors": None,
        "pending_sectors": None,
        "offline_uncorrectable": None,
        "smart_enabled": False,
        "smart_limited": True,
    }


def _drive_is_asleep(path: str) -> bool:
    """Return True if the drive at ``path`` is in standby/sleep.

    Uses ``smartctl -n standby``, which checks the drive's power mode and
    exits WITHOUT waking it when it is in standby.  This goes through the
    same SAT translation smartctl already uses to read these drives, so it
    works on the USB-SATA bridges where ``hdparm -C`` only reports
    "unknown".  On any error we return False so the caller falls back to a
    normal SMART read (better to read an awake drive than to never read it).
    """
    try:
        result = subprocess.run(
            ["smartctl", "-n", "standby", "-i", path],
            capture_output=True, text=True, timeout=SMARTCTL_STANDBY_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    # In a low-power mode smartctl prints e.g. "Device is in STANDBY mode,
    # exit(2)" (or "SLEEP" for the deeper mode) and skips the data read.  An
    # awake -i read mentions neither.
    output = result.stdout.upper()
    return "STANDBY" in output or "SLEEP" in output


def build_smart_stats(previous: Optional[dict] = None) -> dict:
    """Collect SMART status for the navbar/Disk Management warning.

    Reading SMART wakes a sleeping drive, so any drive in standby is NOT
    read: instead we reuse its last-known data from ``previous`` (matched by
    path).  A spun-down drive is not hot, so this is safe.  The warning
    thresholds travel in the payload alongside the per-drive list so the
    frontend does not hardcode them.

    Returns ``{"drives": [...], "high_temperature": int,
    "critical_temperature": int}``.  In Docker mode or without pySMART the
    drive list is empty.
    """
    stats = {
        "drives": [],
        "high_temperature": HDD_HIGH_TEMPERATURE,
        "critical_temperature": HDD_CRITICAL_TEMPERATURE,
    }
    if not is_smart_available():
        return stats

    previous_by_path = {}
    if previous:
        for drive in previous.get("drives", []):
            previous_by_path[drive.get("path")] = drive

    try:
        for path, interface in _scan_devices():
            if _drive_is_asleep(path):
                # Don't wake it; reuse the last reading if we have one.
                prior = previous_by_path.get(path)
                if prior is not None:
                    stats["drives"].append(prior)
                continue
            try:
                device = Device(path, interface=interface)
            except Exception:
                continue
            stats["drives"].append(_get_device_smart(device))
    except Exception:
        # Never let a status-collection failure blank the whole payload.
        pass

    return stats
