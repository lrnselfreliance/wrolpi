"""
System status collection for WROLPi Controller.

Provides functions to collect CPU, memory, load, disk, network, and power
status information. This is the authoritative source for system hardware status.

The status format matches the main WROLPi API's format so the React app
can seamlessly switch between data sources.
"""

import statistics
from pathlib import Path
from typing import Optional

import psutil

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


def get_iostat_status() -> dict:
    """
    Get IO statistics using iostat command.

    Returns format compatible with main API's iostat_stats:
        dict with keys: percent_idle, percent_iowait, percent_nice,
                       percent_steal, percent_system, percent_user
    """
    import subprocess

    result = {
        "percent_idle": None,
        "percent_iowait": None,
        "percent_nice": None,
        "percent_steal": None,
        "percent_system": None,
        "percent_user": None,
    }

    try:
        # Run iostat with 1 second interval, 2 counts (use second measurement)
        proc = subprocess.run(
            ['iostat', '1', '2'],
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout:
            try:
                import jc
                iostat_stats = jc.parse('iostat', proc.stdout.decode(), quiet=True)
                if iostat_stats:
                    # Filter CPU stats and get the second one (first is since boot)
                    cpu_stats_list = [s for s in iostat_stats if s.get('type') == 'cpu']
                    if len(cpu_stats_list) >= 2:
                        cpu_stats = cpu_stats_list[1]
                        result = {
                            "percent_idle": cpu_stats.get('percent_idle'),
                            "percent_iowait": cpu_stats.get('percent_iowait'),
                            "percent_nice": cpu_stats.get('percent_nice'),
                            "percent_steal": cpu_stats.get('percent_steal'),
                            "percent_system": cpu_stats.get('percent_system'),
                            "percent_user": cpu_stats.get('percent_user'),
                        }
            except ImportError:
                # jc not available, parse manually
                pass
    except Exception:
        pass

    return result


IGNORED_PROCESS_COMMANDS = {'<defunct>'}


def get_processes_status() -> list[dict]:
    """
    Get top CPU-consuming processes.

    Returns format compatible with main API's processes_stats:
        list of dicts with keys: pid, percent_cpu, percent_mem, command
    """
    processes = []

    try:
        # Get processes sorted by CPU usage
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']):
            try:
                info = proc.info
                cpu_percent = info.get('cpu_percent', 0)

                # Only include processes using > 1% CPU
                if cpu_percent and cpu_percent > 1:
                    cmdline = info.get('cmdline') or [info.get('name', '')]
                    command = ' '.join(cmdline) if cmdline else info.get('name', '')

                    # Skip ignored commands
                    if any(ignored in command for ignored in IGNORED_PROCESS_COMMANDS):
                        continue

                    processes.append({
                        "pid": info.get('pid'),
                        "percent_cpu": int(cpu_percent),
                        "percent_mem": int(info.get('memory_percent', 0)),
                        "command": command[:512],  # Limit command length
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Sort by CPU usage and return top 10
        processes = sorted(processes, key=lambda x: x['percent_cpu'], reverse=True)[:10]

    except Exception:
        pass

    return processes


IGNORED_DISK_NAMES = ('loop', 'ram')


def get_disk_bandwidth_status() -> dict:
    """
    Get disk IO bandwidth statistics.

    Returns format compatible with main API's disk_bandwidth_stats:
        dict of disk_name -> stats with bytes_read, bytes_write, etc.
    """
    from datetime import datetime
    timestamp = datetime.now().timestamp()
    counters = dict()

    try:
        for name, counter in sorted(psutil.disk_io_counters(perdisk=True).items(), key=lambda i: i[0]):
            # Skip partitions (only report main disks)
            if any(name.startswith(i) for i in counters):
                continue
            # Skip ignored disk types
            if any(name.startswith(i) for i in IGNORED_DISK_NAMES):
                continue

            counters[name] = {
                'name': name,
                'now': timestamp,
                'bytes_read': counter.read_bytes,
                'bytes_write': counter.write_bytes,
                # Initialize per-second rates to 0 (requires historical data)
                'bytes_read_ps': 0,
                'bytes_write_ps': 0,
                'max_read_ps': 500_000,  # Default max for display scaling
                'max_write_ps': 500_000,
            }
    except Exception:
        pass

    return counters
