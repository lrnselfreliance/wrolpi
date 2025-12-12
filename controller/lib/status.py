"""
System status collection for WROLPi Controller.

Provides functions to collect CPU, memory, load, disk, network, and power
status information. This is the authoritative source for system hardware status.
"""

import psutil
from pathlib import Path
from typing import Optional


def get_cpu_status() -> dict:
    """
    Get CPU usage, frequency, temperature, and core count.

    Returns:
        dict with keys: percent, frequency_mhz, frequency_max_mhz,
                       temperature_c, cores
    """
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_freq = psutil.cpu_freq()
    cpu_count = psutil.cpu_count()

    # Temperature - Raspberry Pi specific path
    temperature = None
    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if temp_path.exists():
        try:
            temp_raw = temp_path.read_text().strip()
            temperature = round(int(temp_raw) / 1000, 1)  # millidegrees to degrees
        except (ValueError, IOError):
            pass

    return {
        "percent": cpu_percent,
        "frequency_mhz": round(cpu_freq.current) if cpu_freq else None,
        "frequency_max_mhz": round(cpu_freq.max) if cpu_freq else None,
        "temperature_c": temperature,
        "cores": cpu_count,
    }


def get_memory_status() -> dict:
    """
    Get memory usage statistics.

    Returns:
        dict with keys: total_bytes, available_bytes, used_bytes, percent,
                       total_gb, used_gb, available_gb
    """
    mem = psutil.virtual_memory()
    return {
        "total_bytes": mem.total,
        "available_bytes": mem.available,
        "used_bytes": mem.used,
        "percent": mem.percent,
        # Convenience fields in GB
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
    }


def get_load_status() -> dict:
    """
    Get system load averages.

    Returns:
        dict with keys: load_1min, load_5min, load_15min
    """
    load1, load5, load15 = psutil.getloadavg()
    return {
        "load_1min": round(load1, 2),
        "load_5min": round(load5, 2),
        "load_15min": round(load15, 2),
    }


def get_drive_status() -> list[dict]:
    """
    Get disk usage for mounted filesystems.
    Focuses on /media mounts but includes root.

    Returns:
        list of dicts with keys: device, mount_point, fstype,
                                 total_bytes, used_bytes, free_bytes, percent,
                                 total_gb, used_gb, free_gb
    """
    drives = []

    for partition in psutil.disk_partitions():
        # Include /media mounts and root
        if not (partition.mountpoint.startswith("/media") or
                partition.mountpoint == "/"):
            continue

        try:
            usage = psutil.disk_usage(partition.mountpoint)
            drives.append({
                "device": partition.device,
                "mount_point": partition.mountpoint,
                "fstype": partition.fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent": usage.percent,
                # Convenience fields in GB
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
            })
        except (PermissionError, OSError):
            pass

    return drives


def get_primary_drive_status() -> Optional[dict]:
    """
    Get status of the primary WROLPi drive (/media/wrolpi).

    Returns:
        dict with drive status, or None if not mounted
    """
    for drive in get_drive_status():
        if drive["mount_point"] == "/media/wrolpi":
            return drive
    return None


def get_network_status() -> list[dict]:
    """
    Get network interface statistics.

    Returns:
        list of dicts with keys: name, ipv4, ipv6, mac,
                                 bytes_sent, bytes_recv,
                                 bytes_sent_mb, bytes_recv_mb
    """
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_io_counters(pernic=True)

    for iface, addresses in addrs.items():
        # Skip loopback
        if iface == "lo":
            continue

        iface_stats = stats.get(iface)

        # Extract addresses by type
        ipv4 = None
        ipv6 = None
        mac = None
        for addr in addresses:
            if addr.family.name == "AF_INET":
                ipv4 = addr.address
            elif addr.family.name == "AF_INET6":
                ipv6 = addr.address
            elif addr.family.name == "AF_PACKET":
                mac = addr.address

        interfaces.append({
            "name": iface,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "mac": mac,
            "bytes_sent": iface_stats.bytes_sent if iface_stats else 0,
            "bytes_recv": iface_stats.bytes_recv if iface_stats else 0,
            # Convenience in MB
            "bytes_sent_mb": round((iface_stats.bytes_sent if iface_stats else 0) / (1024**2), 1),
            "bytes_recv_mb": round((iface_stats.bytes_recv if iface_stats else 0) / (1024**2), 1),
        })

    return interfaces


def get_power_status() -> dict:
    """
    Get power/voltage status (Raspberry Pi specific).

    Returns:
        dict with keys: undervoltage_detected, currently_throttled,
                       undervoltage_occurred, throttling_occurred
    """
    result = {
        "undervoltage_detected": False,
        "currently_throttled": False,
        "undervoltage_occurred": False,
        "throttling_occurred": False,
    }

    # Check via /sys (Raspberry Pi)
    throttled_path = Path("/sys/devices/platform/soc/soc:firmware/get_throttled")
    if throttled_path.exists():
        try:
            value = int(throttled_path.read_text().strip(), 16)
            result["undervoltage_detected"] = bool(value & 0x1)     # Bit 0
            result["currently_throttled"] = bool(value & 0x4)       # Bit 2
            result["undervoltage_occurred"] = bool(value & 0x10000) # Bit 16
            result["throttling_occurred"] = bool(value & 0x40000)   # Bit 18
        except (ValueError, IOError):
            pass

    return result


def get_full_status() -> dict:
    """
    Get complete system status.

    Returns:
        dict with all status categories
    """
    primary_drive = get_primary_drive_status()

    return {
        "cpu": get_cpu_status(),
        "memory": get_memory_status(),
        "load": get_load_status(),
        "drives": get_drive_status(),
        "primary_drive": primary_drive,
        "network": get_network_status(),
        "power": get_power_status(),
    }
