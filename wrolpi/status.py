#!/usr/bin/env python3
import asyncio
import json
import multiprocessing
import pathlib
import re
import statistics
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

import jc

from wrolpi.api_utils import api_app
from wrolpi.cmd import which
from wrolpi.common import logger, get_warn_once, unique_by_predicate
from wrolpi.dates import now

try:
    import psutil
except ImportError:
    logger.warning('Unable to import psutil!')
    psutil = None

logger = logger.getChild(__name__)

UPTIME_BIN = which('uptime', '/usr/bin/uptime')

warn_once = get_warn_once('Unable to use psutil', logger)
warn_cpu_once = get_warn_once('Cannot read CPU stats', logger)
status_worker_warn_once = get_warn_once('Status worker encountered error', logger)


@dataclass
class SystemLoad:
    minute_1: Decimal = 0
    minute_5: Decimal = 0
    minute_15: Decimal = 0

    def __json__(self) -> dict:
        return dict(
            minute_1=str(round(self.minute_1, 2)),
            minute_5=str(round(self.minute_5, 2)),
            minute_15=str(round(self.minute_15, 2)),
        )


LOAD_REGEX = re.compile(r'.+?load average: (.+?), (.+?), (.*)')
LOAD_AVG_FILE = pathlib.Path('/proc/loadavg')


async def get_load_stats() -> SystemLoad:
    """Read loadavg file and return the 1, 5, and 15 minute system loads."""
    # Read load information from proc file.
    # Example:  0.99 1.06 1.02 1/2305 43879
    loadavg = LOAD_AVG_FILE.read_text()
    load_1, load_5, load_15, *_ = loadavg.split(' ')
    load = SystemLoad(Decimal(load_1), Decimal(load_5), Decimal(load_15))
    return load


@dataclass
class ProcessInfo:
    pid: int = None
    percent_cpu: int = None
    percent_mem: int = None
    command: str = None

    def __json__(self) -> dict:
        return dict(
            pid=self.pid,
            percent_cpu=self.percent_cpu,
            percent_mem=self.percent_mem,
            command=self.command,
        )


@dataclass
class CPUInfo:
    cores: int = None
    cur_frequency: int = None
    max_frequency: int = None
    min_frequency: int = None
    percent: int = None
    temperature: Optional[int] = None
    high_temperature: Optional[float] = None
    critical_temperature: Optional[float] = None

    def __json__(self) -> dict:
        return dict(
            cores=self.cores,
            cur_frequency=self.cur_frequency,
            max_frequency=self.max_frequency,
            min_frequency=self.min_frequency,
            percent=self.percent,
            temperature=self.temperature,
            high_temperature=self.high_temperature,
            critical_temperature=self.critical_temperature,
        )


MIN_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq')
MAX_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq')
CUR_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')
TEMPERATURE_PATH = Path('/sys/class/thermal/thermal_zone0/temp')
TOP_REGEX = re.compile(r'^%Cpu\(s\):\s+(\d+\.\d+)', re.MULTILINE)


async def get_cpu_stats() -> CPUInfo:
    """Get core count, max freq, min freq, current freq, cpu temperature."""
    percent = int(psutil.cpu_percent())

    # Get temperature from system file.
    temperature = cur_frequency = max_frequency = min_frequency = None
    if TEMPERATURE_PATH.is_file():
        try:
            temperature = int(TEMPERATURE_PATH.read_text()) // 1000
            min_frequency = int(MIN_FREQUENCY_PATH.read_text())
            max_frequency = int(MAX_FREQUENCY_PATH.read_text())
            cur_frequency = int(CUR_FREQUENCY_PATH.read_text())
        except Exception as e:
            warn_cpu_once(e)

    # Get temperature using psutil.
    temp = psutil.sensors_temperatures()
    name = 'coretemp' if 'coretemp' in temp else list(temp.keys())[0]
    # Temperatures may be None.  Get average temperatures from CPU because one core may be hot.
    temperatures = temp.get(name)
    temperature = temperature or statistics.median([i.current or 0 for i in temperatures])
    high_temperature = statistics.median([i.high or 0 for i in temperatures])
    critical_temperature = statistics.median([i.critical or 0 for i in temperatures])

    # Temperatures may not exist.
    high_temperature = high_temperature or 60
    critical_temperature = critical_temperature or 95

    if high_temperature and high_temperature == critical_temperature:
        # Display yellow warning before red warning.
        high_temperature = critical_temperature - 25

    info = CPUInfo(
        cores=multiprocessing.cpu_count(),
        critical_temperature=int(critical_temperature) if critical_temperature else None,
        # Current frequency is between minimum and maximum.
        cur_frequency=cur_frequency - min_frequency if cur_frequency else None,
        high_temperature=int(high_temperature) if high_temperature else None,
        max_frequency=max_frequency,
        min_frequency=min_frequency,
        percent=percent,
        temperature=int(temperature) if temperature else None,
    )
    return info


PS_CMD = 'ps aux --sort=-%cpu --cols=512'
IGNORED_PROCESS_COMMANDS = {PS_CMD, '<defunct>'}


async def get_processes_stats() -> List[ProcessInfo]:
    proc = await asyncio.create_subprocess_shell(
        PS_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Do not include `ps` in the top processes.
    ps_pid = proc.pid
    stdout, stderr = await proc.communicate()

    ps_info = jc.parse('ps', stdout.decode(), quiet=True)
    processes = sorted(ps_info, key=lambda i: i['cpu_percent'], reverse=True)
    processes = [i for i in processes if i['pid'] != ps_pid
                 and i['cpu_percent'] > 1
                 and not any(j in i['command'] for j in IGNORED_PROCESS_COMMANDS)]
    processes = unique_by_predicate(processes, lambda i: i['command'][:30])
    processes = processes[:10]
    processes_info = [ProcessInfo(
        pid=int(i['pid']),
        percent_cpu=int(i['cpu_percent']),
        percent_mem=int(i['mem_percent']),
        command=i['command'],
    ) for i in processes]

    return processes_info


MEMORY_TOTAL = re.compile(r'^MemTotal:\s+(\d+)\s+kB$', re.MULTILINE)
MEMORY_FREE = re.compile(r'^MemFree:\s+(\d+)\s+kB$', re.MULTILINE)
MEMORY_CACHED = re.compile(r'^Cached:\s+(\d+)\s+kB$', re.MULTILINE)


@dataclass
class MemoryStats:
    total: int = None
    used: int = None
    free: int = None
    cached: int = None

    def __json__(self) -> dict:
        return dict(
            total=self.total,
            used=self.used,
            free=self.free,
            cached=self.cached,
        )


def get_memory_stats_psutil():
    mem = psutil.virtual_memory()
    mem = MemoryStats(
        total=mem.total,
        used=mem.used,
        free=mem.free,
        cached=mem.cached,
    )
    return mem


async def get_memory_stats():
    try:
        return get_memory_stats_psutil()
    except Exception as e:
        warn_once(e)

    meminfo = pathlib.Path('/proc/meminfo')
    if meminfo.is_file() and (contents := meminfo.read_text()):
        total = int(i[0]) if (i := MEMORY_TOTAL.findall(contents)) else None
        free = int(i[0]) if (i := MEMORY_FREE.findall(contents)) else None
        cached = int(i[0]) if (i := MEMORY_CACHED.findall(contents)) else None
        mem = MemoryStats(
            total=int(total * 1024) if total else None,
            free=int(free * 1024) if free else None,
            cached=int(cached * 1024) if cached else None,
            used=int(total - free) if total and free else None,
        )
        return mem

    return MemoryStats()


@dataclass
class DriveInfo:
    mount: str = None
    percent: int = 0
    size: int = 0
    used: int = 0

    def __json__(self) -> dict:
        return dict(
            mount=self.mount,
            percent=self.percent,
            size=self.size,
            used=self.used,
        )


DRIVE_REGEX = re.compile(r'^.+?'  # filesystem
                         r'\s+(\d+)K'  # size
                         r'\s+(\d+)K'  # used
                         r'\s+(\d+)K'  # available
                         r'\s+(\d+)%'  # use %
                         r'\s+(.*)',  # mount
                         re.MULTILINE)
IGNORED_DRIVES = ['/boot', '/etc']
VALID_FORMATS = {'btrfs', 'ext4', 'ext3', 'ext2', 'vfat', 'exfat'}


def get_drives_info_psutil() -> List[DriveInfo]:
    info = {}

    disks = psutil.disk_partitions()
    for disk in disks:
        if any(disk.mountpoint.startswith(i) for i in IGNORED_DRIVES):
            continue
        if disk.fstype not in VALID_FORMATS:
            continue
        if disk.device not in info:
            # Only use the first partition.
            usage = psutil.disk_usage(disk.mountpoint)
            info[disk.device] = DriveInfo(
                mount=disk.mountpoint,
                percent=int(usage.percent),
                size=int(usage.total),
                used=int(usage.used),
            )

    info = sorted(info.values(), key=lambda i: i.mount)
    return info


async def get_drives_stats() -> List[DriveInfo]:
    try:
        return get_drives_info_psutil()
    except Exception as e:
        warn_once(e)

    # Fallback to using `df` to fetch disk information.
    proc = await asyncio.subprocess.create_subprocess_shell(
        'df --type btrfs --type ext4 --type ext3 --type ext2 --type vfat -Bk',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    drives = []
    for size, used, _, percent, mount in DRIVE_REGEX.findall(stdout.decode()):
        mount = mount.strip()
        if any(mount.startswith(i) for i in IGNORED_DRIVES):
            continue

        size = int(size) * 1024
        used = int(used) * 1024

        drives.append(DriveInfo(
            mount=mount,
            percent=int(percent),
            size=size,
            used=used,
        ))

    drives = sorted(drives, key=lambda i: i.mount)
    return drives


@dataclass
class NICBandwidthInfo:
    bytes_recv: int = None
    bytes_sent: int = None
    elapsed: int = None
    name: str = None
    speed: int = None
    now: float = None

    def __json__(self) -> dict:
        return dict(
            bytes_recv=self.bytes_recv,
            bytes_sent=self.bytes_sent,
            elapsed=self.elapsed,
            name=self.name,
            speed=self.speed,
        )


IGNORED_NIC_NAMES = {
    'lo',
    'veth',
    'tun',
    'docker',
    'br-',
}


@dataclass
class DiskBandwidthInfo:
    bytes_recv: int = None
    bytes_sent: int = None
    bytes_read_ps: int = None
    bytes_write_ps: int = None
    elapsed: int = None
    name: str = None
    now: float = None
    max_read_ps: int = None
    max_write_ps: int = None

    def __json__(self) -> dict:
        return dict(
            bytes_recv=self.bytes_recv,
            bytes_sent=self.bytes_sent,
            bytes_read_ps=self.bytes_read_ps,
            bytes_write_ps=self.bytes_write_ps,
            elapsed=self.elapsed,
            name=self.name,
            now=self.now,
            max_read_ps=self.max_read_ps,
            max_write_ps=self.max_write_ps,
        )


IGNORED_DISK_NAMES = (
    'loop',
    'ram',
)


def _get_nic_counters() -> dict:
    """
    Get the instant network statistics for the provided NIC.
    """
    timestamp = now().timestamp()
    counters = dict()
    if_stats = psutil.net_if_stats()
    for name, counter in psutil.net_io_counters(pernic=True, nowrap=True).items():
        if name in IGNORED_NIC_NAMES:
            continue
        stats = if_stats[name]
        counters[name] = {
            'name': name,
            'now': timestamp,
            'bytes_recv': counter.bytes_recv,
            'bytes_sent': counter.bytes_sent,
            'speed': int(stats.speed),
        }
    return counters


def _get_disk_counters() -> dict:
    """
    Get the instant disk statistics for the provided NIC.
    """
    timestamp = now().timestamp()
    counters = dict()

    for name, counter in sorted(psutil.disk_io_counters(perdisk=True).items(), key=lambda i: i[0]):
        if any(name.startswith(i) for i in counters):
            # Report only the first disk.  Do not report its partitions.  Disks are sorted to make this work!
            # i.e. report "sda" but not "sda1" or "sda2".
            continue
        if any(name.startswith(i) for i in IGNORED_DISK_NAMES):
            continue
        counters[name] = {
            'name': name,
            'now': timestamp,
            'bytes_recv': counter.read_bytes,
            'bytes_sent': counter.write_bytes,
        }

    return counters


def _calculate_bytes_per_second(old_stats: dict, new_stats: dict) -> Tuple[int, int, int]:
    """Calculate the bytes-per-second between the oldest and newest tick."""
    old_now, old_recv, old_sent = old_stats['now'], old_stats['bytes_recv'], old_stats['bytes_sent']
    new_now, new_recv, new_sent = new_stats['now'], new_stats['bytes_recv'], new_stats['bytes_sent']
    elapsed = int(new_now - old_now)
    if elapsed == 0:
        return 0, 0, 0
    bytes_recv_ps = int((new_recv - old_recv) // elapsed)
    bytes_sent_ps = int((new_sent - old_sent) // elapsed)
    return bytes_recv_ps, bytes_sent_ps, elapsed


@api_app.signal('wrolpi.periodic.status')
async def status_worker(count: int = None, sleep_time: int = 5):
    """A background process which will gather historical data about system statistics."""
    shared_status = api_app.shared_ctx.status

    if count is not None and count <= 0:
        logger.debug('Status worker ran out of count')
        return dict(**shared_status)

    load_stats = None
    try:
        # Update global `status` dict with stats that are gathered instantly.
        cpu_stats, load_stats, drives_stats, memory_stats, processes_stats = await asyncio.gather(
            get_cpu_stats(),
            get_load_stats(),
            get_drives_stats(),
            get_memory_stats(),
            get_processes_stats(),
        )
        shared_status.update({
            'cpu_stats': cpu_stats.__json__(),
            'load_stats': load_stats.__json__(),
            'drives_stats': [i.__json__() for i in drives_stats],
            'processes_stats': [i.__json__() for i in processes_stats],
            'memory_stats': memory_stats.__json__(),
        })

        if 'disk_bandwidth_stats' not in shared_status:
            # Worker has just been started, fill it with some starting bandwidth data.
            disk_info = _get_disk_counters()
            for name in disk_info.keys():
                disk_info[name].update({'max_read_ps': 500_000, 'max_write_ps': 500_000})
            shared_status.update({
                'nic_bandwidth_stats': _get_nic_counters(),
                'disk_bandwidth_stats': disk_info,
            })
            # Break out and call the `finally` code below.
            return

        # Calculate the difference between the previous status worker's bandwidth count and now.
        new_nic_stats = _get_nic_counters()
        old_nic_stats = shared_status['nic_bandwidth_stats']
        nic_bandwidth_stats = dict()
        for name, old_stats in old_nic_stats.items():
            new_stats = new_nic_stats[name]
            bytes_recv_ps, bytes_sent_ps, elapsed = _calculate_bytes_per_second(old_stats, new_stats)
            new_stats.update(dict(
                bytes_recv_ps=bytes_recv_ps,
                bytes_sent_ps=bytes_sent_ps,
                elapsed=elapsed,
            ))
            nic_bandwidth_stats[name] = new_stats

        # Calculate the difference between the previous status worker's disk bandwidth count and now.
        new_disk_stats = _get_disk_counters()
        old_disk_stats = shared_status['disk_bandwidth_stats']
        disk_bandwidth_stats = dict()
        for name, old_stats in old_disk_stats.items():
            new_stats = new_disk_stats[name]
            bytes_read_ps, bytes_write_ps, elapsed = _calculate_bytes_per_second(old_stats, new_stats)
            new_stats.update(dict(
                bytes_read_ps=bytes_read_ps,
                bytes_write_ps=bytes_write_ps,
                elapsed=elapsed,
                max_read_ps=max(bytes_read_ps, old_stats['max_read_ps']),
                max_write_ps=max(bytes_write_ps, old_stats['max_write_ps']),
            ))
            disk_bandwidth_stats[name] = new_stats

        shared_status.update({
            'nic_bandwidth_stats': nic_bandwidth_stats,
            'disk_bandwidth_stats': disk_bandwidth_stats,
        })
    except Exception as e:
        status_worker_warn_once(e)
        raise
    finally:
        if load_stats and load_stats.minute_1 and load_stats.minute_1 > multiprocessing.cpu_count():
            # System is stressed, slow down status updates.
            await asyncio.sleep(sleep_time)

        # Always sleep so this does not become a busy loop with errors.
        await asyncio.sleep(sleep_time)
        if count:
            # Running in testing, or __main__.
            return await status_worker(count - 1, sleep_time)
        else:
            await api_app.dispatch('wrolpi.periodic.status', context={'sleep_time': sleep_time})


if __name__ == '__main__':
    from wrolpi.contexts import attach_shared_contexts

    loop = asyncio.get_event_loop()

    SKIP_DISPATCH = True
    attach_shared_contexts(api_app)
    loop.run_until_complete(status_worker(2, sleep_time=2))
    print(json.dumps(dict(api_app.shared_ctx.status), indent=2))
