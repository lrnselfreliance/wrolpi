#!/usr/bin/env python3
import asyncio
import multiprocessing
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List

from wrolpi.common import logger

from wrolpi.cmd import which

logger = logger.getChild(__name__)

UPTIME_BIN = which('uptime', '/usr/bin/uptime')


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


async def get_load() -> SystemLoad:
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
    temperature: int = None

    def __json__(self):
        return dict(
            cores=self.cores,
            cur_frequency=self.cur_frequency,
            max_frequency=self.max_frequency,
            min_frequency=self.min_frequency,
            percent=self.percent,
            temperature=self.temperature,
        )


MIN_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq')
MAX_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq')
CUR_FREQUENCY_PATH = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')
TEMPERATURE_PATH = Path('/sys/class/thermal/thermal_zone0/temp')
TOP_REGEX = re.compile(r'^%Cpu\(s\):\s+(\d+\.\d+)', re.MULTILINE)


async def get_cpu_info() -> CPUInfo:
    """Get core count, max freq, min freq, current freq, cpu temperature."""
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


async def get_drives_info() -> List[DriveInfo]:
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


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    print(loop.run_until_complete(get_cpu_info()))
    print(loop.run_until_complete(get_load()))
    print(loop.run_until_complete(get_drives_info()))
