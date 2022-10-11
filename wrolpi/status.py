#!/usr/bin/env python3
import asyncio
import multiprocessing
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from wrolpi.cmd import which
from wrolpi.common import logger
from wrolpi.dates import now

try:
    import psutil
except ImportError:
    logger.warning('Unable to import psutil!')
    psutil = None

logger = logger.getChild(__name__)

UPTIME_BIN = which('uptime', '/usr/bin/uptime')
PSUTIL_WARNED = multiprocessing.Event()


def warn_once(exception: Exception):
    """
    Don't spam the logs with errors when status can't use psutil.
    """
    if not PSUTIL_WARNED.is_set():
        logger.error(f'Unable to use psutil', exc_info=exception)
        PSUTIL_WARNED.set()


@dataclass
class SystemLoad:
    minute_1: Decimal = 0
    minute_5: Decimal = 0
    minute_15: Decimal = 0

    def __json__(self):
        return dict(
            minute_1=str(self.minute_1),
            minute_5=str(self.minute_5),
            minute_15=str(self.minute_15),
        )


LOAD_REGEX = re.compile(r'.+?load average: (.+?), (.+?), (.*)')


def get_load_psutil() -> SystemLoad:
    load = SystemLoad(*list(map(Decimal, psutil.getloadavg())))
    return load


async def get_load() -> SystemLoad:
    try:
        return get_load_psutil()
    except Exception as e:
        warn_once(e)

    # Fallback to using `uptime` to fetch load information.
    proc = await asyncio.subprocess.create_subprocess_shell(
        str(UPTIME_BIN),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    stdout = stdout.strip()
    if proc.returncode != 0 or not stdout:
        logger.warning(f'{UPTIME_BIN} exited with {proc.returncode} or was empty')
        return SystemLoad()

    stdout = stdout.decode()
    load = SystemLoad(*[Decimal(i) for i in LOAD_REGEX.search(stdout).groups()])
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
    temperature = int(temp.get(name)[0].current)
    high_temperature = int(temp.get(name)[0].high)
    critical_temperature = int(temp.get(name)[0].critical)

    info = CPUInfo(
        cores=psutil.cpu_count(logical=True),
        cur_frequency=int(cpu_freq.current),
        min_frequency=int(cpu_freq.min),
        max_frequency=int(cpu_freq.max),
        percent=int(percent),
        temperature=temperature,
        high_temperature=high_temperature,
        critical_temperature=critical_temperature,
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
    if proc.returncode != 0:
        logger.warning(f'Unable to get CPU top with exit {proc.returncode}')
        percent = None
    else:
        percent = int(Decimal(TOP_REGEX.search(stdout.decode()).groups()[0]))

    if not TEMPERATURE_PATH.is_file():
        logger.warning(f'CPU temperature file does not exist!')
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
class BandwidthInfo:
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


def get_nic_names() -> List[str]:
    """Finds all non-virtual and non-docker network interface names."""
    names = []
    for name, nic in psutil.net_if_stats().items():
        if any(name.startswith(i) for i in IGNORED_NIC_NAMES):
            continue
        names.append(name)
    return names


BANDWIDTH = multiprocessing.Manager().dict()


async def get_bandwidth_info() -> List[BandwidthInfo]:
    """
    Get all bandwidth information for all NICs.
    """
    infos = []
    try:
        for name in sorted(BANDWIDTH.keys()):
            nic = BANDWIDTH[name]
            if 'bytes_recv_ps' not in nic:
                # Not stats collected yet.
                continue
            infos.append(BandwidthInfo(
                bytes_recv=nic['bytes_recv_ps'],
                bytes_sent=nic['bytes_sent_ps'],
                elapsed=nic['elapsed'],
                name=name,
                speed=nic['speed'],
            ))
    except Exception as e:
        warn_once(e)

    return infos


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
    (oldest_now, oldest_recv, oldest_sent, _), (newest_now, newest_recv, newest_sent, _) = \
        history[0], history[-1]
    elapsed = int(newest_now - oldest_now)
    if elapsed == 0:
        return 0, 0, 0
    bytes_recv_ps = int((newest_recv - oldest_recv) // elapsed)
    bytes_sent_ps = int((newest_sent - oldest_sent) // elapsed)
    return bytes_recv_ps, bytes_sent_ps, elapsed


async def bandwidth_worker(count: int = None):
    """A background process which will gather historical data about all NIC bandwidth statistics."""
    if not psutil:
        return

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


@dataclass
class Status:
    cpu_info: CPUInfo
    load: SystemLoad
    drives: List[DriveInfo]
    bandwidth: BandwidthInfo


async def get_status() -> Status:
    cpu_info, load, drives, bandwidth = await asyncio.gather(
        get_cpu_info(),
        get_load(),
        get_drives_info(),
        get_bandwidth_info(),
    )
    return Status(
        cpu_info=cpu_info,
        load=load,
        drives=drives,
        bandwidth=bandwidth,
    )


if __name__ == '__main__':
    from pprint import pprint

    loop = asyncio.get_event_loop()

    loop.run_until_complete(bandwidth_worker(2))

    task = asyncio.gather(
        get_cpu_info(),
        get_load(),
        get_drives_info(),
        get_bandwidth_info(),
    )
    info_ = loop.run_until_complete(task)
    pprint(info_)
