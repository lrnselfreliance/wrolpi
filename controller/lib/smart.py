"""
SMART disk health monitoring for WROLPi Controller.
"""

from typing import Optional

# Import pySMART only if available
try:
    from pySMART import DeviceList, Device

    SMART_AVAILABLE = True
except ImportError:
    SMART_AVAILABLE = False

from controller.lib.config import is_docker_mode


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
        devices = DeviceList()
        results = []

        for device in devices.devices:
            results.append(_get_device_smart(device))

        return results
    except Exception:
        return []


def _get_device_smart(device) -> dict:
    """Extract SMART data from a pySMART device."""
    return {
        "device": device.name,
        "path": f"/dev/{device.name}",
        "model": device.model,
        "serial": device.serial,
        "capacity": device.capacity,
        "assessment": device.assessment,  # PASS, FAIL, WARN
        "temperature": _get_temperature(device),
        "power_on_hours": _get_attribute(device, "Power_On_Hours"),
        "reallocated_sectors": _get_attribute(device, "Reallocated_Sector_Ct"),
        "pending_sectors": _get_attribute(device, "Current_Pending_Sector"),
        "smart_enabled": device.smart_enabled,
    }


def _get_temperature(device) -> Optional[int]:
    """Get drive temperature from SMART attributes."""
    temp = _get_attribute(device, "Temperature_Celsius")
    if temp is None:
        temp = _get_attribute(device, "Airflow_Temperature_Cel")
    return temp


def _get_attribute(device, name: str) -> Optional[int]:
    """Get a specific SMART attribute value."""
    if not hasattr(device, 'attributes') or device.attributes is None:
        return None

    for attr in device.attributes:
        if attr and attr.name == name:
            try:
                return int(attr.raw)
            except (ValueError, TypeError):
                return None
    return None
