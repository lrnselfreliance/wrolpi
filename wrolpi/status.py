#!/usr/bin/env python3
import asyncio
import multiprocessing
import pathlib
import re
import statistics
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from wrolpi.cmd import which
from wrolpi.common import logger, limit_concurrent, get_warn_once
from wrolpi.dates import now

try:
    import psutil
except ImportError:
    logger.warning('Unable to import psutil!')
    psutil = None

logger = logger.getChild(__name__)

UPTIME_BIN = which('uptime', '/usr/bin/uptime')

warn_once = get_warn_once('Unable to use psutil', logger)


@dataclass
class SystemLoad:
    minute_1: Decimal = 0
    minute_5: Decimal = 0
    minute_15: Decimal = 0

    def __json__(self):
        return dict(
            minute_1=str(round(self.minute_1, 2)),
            minute_5=str(round(self.minute_5, 2)),
            minute_15=str(round(self.minute_15, 2)),
        )


LOAD_REGEX = re.compile(r'.+?load average: (.+?), (.+?), (.*)')


def get_load_psutil() -> SystemLoad:
    load = SystemLoad(*list(map(Decimal, psutil.getloadavg())))
    return load


LOAD_AVG_FILE = pathlib.Path('/proc/loadavg')


async def get_load() -> SystemLoad:
    """Read loadavg file and return the 1, 5, and 15 minute system loads."""
    # Read load information from proc file.
    # Example:  0.99 1.06 1.02 1/2305 43879
    loadavg = LOAD_AVG_FILE.read_text()
    load_1, load_5, load_15, *_ = loadavg.split(' ')
    load = SystemLoad(Decimal(load_1), Decimal(load_5), Decimal(load_15))
    return load


@dataclass
class CPUInfo:
    cores: int = None
    cur_frequency: int = None
    max_frequency: int = None
    min_frequency: int = None
    percent: int = None
    temperature: Optional[int] = None
    high_temperature: Optional[int] = None
    critical_temperature: Optional[int] = None

    def __json__(self):
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


def get_cpu_info_psutil() -> CPUInfo:
    cpu_freq = psutil.cpu_freq()
    percent = psutil.cpu_percent(interval=0.1)

    # Prefer "coretemp", fallback to the first temperature.
    temp = psutil.sensors_temperatures()
    name = 'coretemp' if 'coretemp' in temp else list(temp.keys())[0]
    # Temperatures may be None.  Get average temperatures from CPU because one core may be hot.
    temperatures = temp.get(name)
    temperature = statistics.median([i.current or 0 for i in temperatures])
    high_temperature = statistics.median([i.high or 0 for i in temperatures])
    critical_temperature = statistics.median([i.critical or 0 for i in temperatures])

    # Temperatures my not exist.
    if not high_temperature:
        high_temperature = 60
    if not critical_temperature:
        critical_temperature = 95

    if high_temperature and high_temperature == critical_temperature:
        # Display yellow warning before red warning.
        high_temperature = critical_temperature - 25

    info = CPUInfo(
        cores=psutil.cpu_count(logical=True),
        cur_frequency=int(cpu_freq.current),
        min_frequency=int(cpu_freq.min),
        max_frequency=int(cpu_freq.max),
        percent=int(percent),
        temperature=int(temperature),
        high_temperature=int(high_temperature),
        critical_temperature=int(critical_temperature),
    )
    return info


async def get_cpu_info() -> CPUInfo:
    """Get core count, max freq, min freq, current freq, cpu temperature."""
    try:
        return get_cpu_info_psutil()
    except Exception as e:
        warn_once(e)

    # Fallback to using `top` to fetch CPU information.
    proc = await asyncio.create_subprocess_shell(
        'top -bn1',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    match = TOP_REGEX.search(stdout.decode())
    if proc.returncode != 0 or not match:
        logger.warning(f'Unable to get CPU top with exit {proc.returncode}')
        percent = None
    else:
        percent = int(Decimal(match.groups()[0]))

    if not TEMPERATURE_PATH.is_file():
        warn_once(f'CPU temperature file does not exist!')
        return CPUInfo(percent=percent)

    try:
        temperature = int(TEMPERATURE_PATH.read_text()) // 1000
        min_frequency = int(MIN_FREQUENCY_PATH.read_text())
        max_frequency = int(MAX_FREQUENCY_PATH.read_text())
        cur_frequency = int(CUR_FREQUENCY_PATH.read_text())
    except Exception as e:
        logger.warning(f'Unable to get CPU info', exc_info=e)
        return CPUInfo(percent=percent)

    info = CPUInfo(
        cores=multiprocessing.cpu_count(),
        cur_frequency=cur_frequency - min_frequency,  # Current frequency is between minimum and maximum.
        max_frequency=max_frequency,
        min_frequency=min_frequency,
        percent=percent,
        temperature=temperature,
    )
    return info


MEMORY_TOTAL = re.compile(r'^MemTotal:\s+(\d+)\s+kB$', re.MULTILINE)
MEMORY_FREE = re.compile(r'^MemFree:\s+(\d+)\s+kB$', re.MULTILINE)
MEMORY_CACHED = re.compile(r'^Cached:\s+(\d+)\s+kB$', re.MULTILINE)


@dataclass
class MemoryStats:
    total: int = None
    used: int = None
    free: int = None
    cached: int = None

    def __json__(self):
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

    def __json__(self):
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
VALID_FORMATS = {'btrfs', 'ext4', 'ext3', 'ext2', 'vfat'}


def get_drives_info_psutil() -> List[DriveInfo]:
    info = {}

    disks = psutil.disk_partitions()
    for disk in disks:
        if any(disk.mountpoint.startswith(i) for i in IGNORED_DRIVES):
            continue
        if disk.fstype not in VALID_FORMATS:
            continue
        if disk.device not in info:
            # Only use the first use of the partition.
            usage = psutil.disk_usage(disk.mountpoint)
            info[disk.device] = DriveInfo(
                mount=disk.mountpoint,
                percent=int(usage.percent),
                size=int(usage.total),
                used=int(usage.used),
            )

    info = sorted(info.values(), key=lambda i: i.mount)
    return info


async def get_drives_info() -> List[DriveInfo]:
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

    def __json__(self):
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

BANDWIDTH = multiprocessing.Manager().dict()


def get_nic_names() -> List[str]:
    """Finds all non-virtual and non-docker network interface names."""
    names = []
    for name, nic in psutil.net_if_stats().items():
        if any(name.startswith(i) for i in IGNORED_NIC_NAMES):
            continue
        names.append(name)
    return names


@dataclass
class DiskBandwidthInfo:
    bytes_read_ps: int = None
    bytes_write_ps: int = None
    elapsed: int = None
    name: str = None
    maximum_read_ps: int = None
    maximum_write_ps: int = None

    def __json__(self):
        return dict(
            bytes_read_ps=self.bytes_read_ps,
            bytes_write_ps=self.bytes_write_ps,
            elapsed=self.elapsed,
            name=self.name,
            maximum_read_ps=self.maximum_read_ps,
            maximum_write_ps=self.maximum_write_ps,
        )


IGNORED_DISK_NAMES = (
    'loop',
    'ram',
)
DISKS_BANDWIDTH = multiprocessing.Manager().dict()
MAX_DISKS_BANDWIDTH = multiprocessing.Manager().dict()


async def get_bandwidth_info() -> Tuple[List[NICBandwidthInfo], List[DiskBandwidthInfo]]:
    """Get all bandwidth information for all NICs and Disks."""
    nics_info = []
    disks_info = []

    try:
        for name in sorted(BANDWIDTH.keys()):
            nic = BANDWIDTH[name]
            if 'bytes_recv_ps' not in nic:
                # Not stats collected yet.
                continue
            nics_info.append(NICBandwidthInfo(
                bytes_recv=nic['bytes_recv_ps'],
                bytes_sent=nic['bytes_sent_ps'],
                elapsed=nic['elapsed'],
                name=name,
                speed=nic['speed'],
            ))
        used_disks = []
        for name in sorted(DISKS_BANDWIDTH.keys()):
            disk = DISKS_BANDWIDTH[name]
            if 'bytes_read_ps' not in disk:
                # No status collected yet
                continue
            if any(name.startswith(i) for i in used_disks):
                # Report only the first disk.  Do not report it's partitions.  Disks are sorted to make this work!
                # i.e. report "sda" but not "sda1" or "sda2".
                continue
            if any(name.startswith(i) for i in IGNORED_DISK_NAMES):
                continue
            used_disks.append(name)

            try:
                maximum_read_ps = max(disk['bytes_read_ps'], MAX_DISKS_BANDWIDTH[name]['maximum_read_ps'])
                maximum_write_ps = max(disk['bytes_write_ps'], MAX_DISKS_BANDWIDTH[name]['maximum_write_ps'])
            except KeyError:
                # Use a low first value.  Hopefully all drives are capable of this speed.
                maximum_read_ps = 500_000
                maximum_write_ps = 500_000
            # Always write the new maximums.
            value = {name: {'maximum_read_ps': maximum_read_ps, 'maximum_write_ps': maximum_write_ps}}
            MAX_DISKS_BANDWIDTH.update(value)

            disks_info.append(DiskBandwidthInfo(
                bytes_read_ps=disk['bytes_read_ps'],
                bytes_write_ps=disk['bytes_write_ps'],
                elapsed=disk['elapsed'],
                name=name,
                maximum_read_ps=maximum_read_ps,
                maximum_write_ps=maximum_write_ps,
            ))
    except Exception as e:
        warn_once(e)

    return nics_info, disks_info


def _get_nic_tick(name_):
    """
    Get the instant network statistics for the provided NIC.
    """
    try:
        counter = psutil.net_io_counters(pernic=True, nowrap=True)[name_]
        stats = psutil.net_if_stats()[name_]
        return now().timestamp(), counter.bytes_recv, counter.bytes_sent, int(stats.speed)
    except Exception as e:
        warn_once(e)
        return 0, 0, 0, 0


def _calculate_bytes_per_second(history: List[Tuple]) -> Tuple[int, int, int]:
    """Calculate the bytes-per-second between the oldest and newest tick."""
    (oldest_now, oldest_recv, oldest_sent, *_), (newest_now, newest_recv, newest_sent, *_) = \
        history[0], history[-1]
    elapsed = int(newest_now - oldest_now)
    if elapsed == 0:
        return 0, 0, 0
    bytes_recv_ps = int((newest_recv - oldest_recv) // elapsed)
    bytes_sent_ps = int((newest_sent - oldest_sent) // elapsed)
    return bytes_recv_ps, bytes_sent_ps, elapsed


@limit_concurrent(1)
async def bandwidth_worker(count: int = None):
    """A background process which will gather historical data about all NIC bandwidth statistics."""
    if not psutil:
        return

    logger.info('Bandwidth worker started')

    nic_names = get_nic_names()

    def append_all_stats():
        for name_ in nic_names:
            nic = BANDWIDTH.get(name_)
            if not nic:
                # Initialize history for this NIC.
                BANDWIDTH.update({
                    name_: dict(historical=[_get_nic_tick(name_), ]),
                })
            else:
                # Append to history for this NIC.
                nic['historical'] = (nic['historical'] + [_get_nic_tick(name_), ])[-21:]
                BANDWIDTH.update({name_: nic})

        timestamp = now().timestamp()
        for name_, disk in psutil.disk_io_counters(perdisk=True).items():
            tic = timestamp, disk.read_bytes, disk.write_bytes
            if bw := DISKS_BANDWIDTH.get(name_):
                bw['historical'] = (bw['historical'] + [tic, ])[-21:]
                DISKS_BANDWIDTH.update({name_: bw})
            else:
                DISKS_BANDWIDTH.update({
                    name_: dict(historical=[tic, ]),
                })

    # Initialize the stats.
    append_all_stats()

    while count is None or count > 0:
        await asyncio.sleep(1)
        if count is not None:
            count -= 1

        append_all_stats()

        # Calculate the difference between the first and last bandwidth ticks for all NICs.
        for name, nic in BANDWIDTH.items():
            historical = nic['historical']
            bytes_recv_ps, bytes_sent_ps, elapsed = _calculate_bytes_per_second(historical)
            BANDWIDTH.update({
                name: dict(
                    historical=historical,
                    bytes_recv_ps=bytes_recv_ps,
                    bytes_sent_ps=bytes_sent_ps,
                    elapsed=elapsed,
                    speed=historical[-1][-1],  # Use the most recent speed.
                )
            })
        for name, stats in DISKS_BANDWIDTH.items():
            if 'historical' not in stats:
                continue

            historical = stats['historical']
            bytes_read_ps, bytes_write_ps, elapsed = _calculate_bytes_per_second(historical)
            DISKS_BANDWIDTH.update({
                name: dict(
                    historical=historical,
                    bytes_read_ps=bytes_read_ps,
                    bytes_write_ps=bytes_write_ps,
                    elapsed=elapsed,
                )
            })


@dataclass
class Status:
    cpu_info: CPUInfo
    load: SystemLoad
    drives: List[DriveInfo]
    bandwidth: NICBandwidthInfo
    disk_bandwidth: DiskBandwidthInfo
    memory_stats: MemoryStats


async def get_status() -> Status:
    cpu_info, load, drives, memory_stats, (nic_bandwidth, disk_bandwidth) = await asyncio.gather(
        get_cpu_info(),
        get_load(),
        get_drives_info(),
        get_memory_stats(),
        get_bandwidth_info(),
    )
    return Status(
        cpu_info=cpu_info,
        load=load,
        drives=drives,
        bandwidth=nic_bandwidth,
        disk_bandwidth=disk_bandwidth,
        memory_stats=memory_stats,
    )


if __name__ == '__main__':
    from pprint import pprint

    loop = asyncio.get_event_loop()

    loop.run_until_complete(bandwidth_worker(2))

    task = asyncio.gather(
        get_cpu_info(),
        get_memory_stats(),
        get_load(),
        get_drives_info(),
        get_bandwidth_info(),
    )
    info_ = loop.run_until_complete(task)
    pprint(info_)
