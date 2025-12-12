"""
System status collection for WROLPi Controller.

Provides functions to collect CPU, memory, load, disk, network, and power
status information. This is the authoritative source for system hardware status.

The status format matches the main WROLPi API's format so the React app
can seamlessly switch between data sources.
"""

import os
import statistics
import psutil
from pathlib import Path
from typing import Optional


# CPU frequency paths
MIN_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq')
MAX_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq')
CUR_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')


def get_cpu_status() -> dict:
    """
    Get CPU usage, frequency, temperature, and core count.

    Returns format compatible with main API's cpu_stats:
        dict with keys: cores, cur_frequency, max_frequency, min_frequency,
                       percent, temperature, high_temperature, critical_temperature
    """
    cpu_percent = int(psutil.cpu_percent(interval=0.1))
    cpu_count = psutil.cpu_count()

    # Get frequency from sys files (more reliable than psutil on RPi)
    min_frequency = max_frequency = cur_frequency = None
    try:
        if MIN_FREQUENCY_PATH.exists():
            min_frequency = int(MIN_FREQUENCY_PATH.read_text())
        if MAX_FREQUENCY_PATH.exists():
            max_frequency = int(MAX_FREQUENCY_PATH.read_text())
        if CUR_FREQUENCY_PATH.exists():
            cur_frequency = int(CUR_FREQUENCY_PATH.read_text())
    except (ValueError, IOError):
        pass

    # Get temperature using psutil
    temperature = high_temperature = critical_temperature = None
    try:
        temp = psutil.sensors_temperatures()
        if temp:
            name = 'coretemp' if 'coretemp' in temp else list(temp.keys())[0]
            temperatures = temp.get(name)
            if temperatures:
                temperature = statistics.median([i.current or 0 for i in temperatures])
                high_temperature = statistics.median([i.high or 0 for i in temperatures])
                critical_temperature = statistics.median([i.critical or 0 for i in temperatures])

                # Temperatures may not exist.
                high_temperature = high_temperature or 60
                critical_temperature = critical_temperature or 95

                if high_temperature and high_temperature == critical_temperature:
                    # Display yellow warning before red warning.
                    high_temperature = critical_temperature - 25
    except Exception:
        pass

    return {
        "cores": cpu_count,
        "cur_frequency": cur_frequency - min_frequency if cur_frequency and min_frequency else None,
        "max_frequency": max_frequency,
        "min_frequency": min_frequency,
        "percent": cpu_percent,
        "temperature": int(temperature) if temperature else None,
        "high_temperature": int(high_temperature) if high_temperature else None,
        "critical_temperature": int(critical_temperature) if critical_temperature else None,
    }


def get_memory_status() -> dict:
    """
    Get memory usage statistics.

    Returns format compatible with main API's memory_stats:
        dict with keys: total, used, free, cached
    """
    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "used": mem.used,
        "free": mem.free,
        "cached": getattr(mem, 'cached', 0),  # cached may not exist on all platforms (e.g., macOS)
    }


def get_load_status() -> dict:
    """
    Get system load averages.

    Returns format compatible with main API's load_stats:
        dict with keys: minute_1, minute_5, minute_15
    """
    load1, load5, load15 = psutil.getloadavg()
    return {
        "minute_1": str(round(load1, 2)),
        "minute_5": str(round(load5, 2)),
        "minute_15": str(round(load15, 2)),
    }


IGNORED_DRIVES = ['/boot', '/etc']
VALID_FORMATS = {'btrfs', 'ext4', 'ext3', 'ext2', 'vfat', 'exfat', 'apfs'}


def get_drive_status() -> list[dict]:
    """
    Get disk usage for mounted filesystems.

    Returns format compatible with main API's drives_stats:
        list of dicts with keys: mount, percent, size, used
    """
    drives = []
    seen_devices = set()

    for partition in psutil.disk_partitions():
        # Skip ignored directories
        if any(partition.mountpoint.startswith(i) for i in IGNORED_DRIVES):
            continue
        # Skip non-standard filesystems
        if partition.fstype not in VALID_FORMATS:
            continue
        # Skip duplicate devices (only use first partition)
        if partition.device in seen_devices:
            continue
        seen_devices.add(partition.device)

        try:
            usage = psutil.disk_usage(partition.mountpoint)
            drives.append({
                "mount": partition.mountpoint,
                "percent": int(usage.percent),
                "size": int(usage.total),
                "used": int(usage.used),
            })
        except (PermissionError, OSError):
            pass

    return sorted(drives, key=lambda i: i["mount"])


def get_primary_drive_status() -> Optional[dict]:
    """
    Get status of the primary WROLPi drive (/media/wrolpi).

    Returns:
        dict with drive status, or None if not mounted
    """
    for drive in get_drive_status():
        if drive["mount"] == "/media/wrolpi":
            return drive
    return None


IGNORED_NIC_NAMES = {'lo', 'veth', 'tun', 'docker', 'br-'}


def get_network_status() -> dict:
    """
    Get network interface statistics.

    Returns format compatible with main API's nic_bandwidth_stats:
        dict of interface_name -> stats
    """
    from datetime import datetime
    timestamp = datetime.now().timestamp()
    counters = dict()
    if_stats = psutil.net_if_stats()

    for name, counter in sorted(psutil.net_io_counters(pernic=True, nowrap=True).items(), key=lambda i: i[0]):
        if name in IGNORED_NIC_NAMES:
            continue
        stats = if_stats.get(name)
        counters[name] = {
            'name': name,
            'now': timestamp,
            'bytes_recv': counter.bytes_recv,
            'bytes_sent': counter.bytes_sent,
            'speed': int(stats.speed) if stats else 0,
            # Initialize bandwidth per second to 0 (requires historical data to calculate)
            'bytes_recv_ps': 0,
            'bytes_sent_ps': 0,
        }

    return counters


def get_power_status() -> dict:
    """
    Get power/voltage status (Raspberry Pi specific).

    Returns format compatible with main API's power_stats:
        dict with keys: under_voltage, over_current
    """
    import subprocess

    result = {
        "under_voltage": False,
        "over_current": False,
    }

    try:
        # Check via dmesg (same method as main API)
        proc = subprocess.run(
            ['dmesg'],
            capture_output=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout:
            result["under_voltage"] = b' Undervoltage detected' in proc.stdout
            result["over_current"] = b' over-current change ' in proc.stdout
    except Exception:
        pass

    return result


def get_full_status() -> dict:
    """
    Get complete system status.

    Returns format compatible with main API's /api/status response.
    The React Status.js component expects this exact format.
    """
    from datetime import datetime
    from controller.lib.config import is_docker_mode

    cpu_stats = get_cpu_status()
    memory_stats = get_memory_status()
    load_stats = get_load_status()
    drives_stats = get_drive_status()
    power_stats = get_power_status()
    nic_bandwidth_stats = get_network_status()

    # Build disk bandwidth stats (similar format to NIC)
    disk_bandwidth_stats = {}
    timestamp = datetime.now().timestamp()
    try:
        for name, counter in sorted(psutil.disk_io_counters(perdisk=True).items(), key=lambda i: i[0]):
            # Skip partitions, only report base disks
            if any(name.startswith(skip) for skip in ('loop', 'ram')):
                continue
            # Skip partition numbers (report sda, not sda1)
            if name not in disk_bandwidth_stats:
                disk_bandwidth_stats[name] = {
                    'name': name,
                    'now': timestamp,
                    'bytes_read': counter.read_bytes,
                    'bytes_write': counter.write_bytes,
                    'bytes_read_ps': 0,
                    'bytes_write_ps': 0,
                    'max_read_ps': 500_000,
                    'max_write_ps': 500_000,
                }
    except Exception:
        pass

    return {
        # Core status fields expected by Status.js
        "cpu_stats": cpu_stats,
        "memory_stats": memory_stats,
        "load_stats": load_stats,
        "drives_stats": drives_stats,
        "nic_bandwidth_stats": nic_bandwidth_stats,
        "disk_bandwidth_stats": disk_bandwidth_stats,
        "power_stats": power_stats,
        "processes_stats": [],  # Empty list, processes require more complex gathering
        "iostat_stats": {},  # Empty dict, iostat requires more complex gathering

        # Additional fields expected by the React app
        "dockerized": is_docker_mode(),
        "last_status": datetime.now().isoformat(),
    }
