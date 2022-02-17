import enum
import pathlib
import subprocess

from wrolpi.common import logger
from wrolpi.vars import PYTEST, DEFAULT_CPU_FREQUENCY, DOCKERIZED

logger = logger.getChild(__name__)

# Location on an RPi
SUDO_BIN = pathlib.Path('/usr/bin/sudo')
if not SUDO_BIN.is_file() and not PYTEST and not DOCKERIZED:
    logger.error('COULD NOT FIND sudo!!!')

NMCLI_BIN = pathlib.Path('/usr/bin/nmcli')
if not NMCLI_BIN.is_file() and not PYTEST and not DOCKERIZED:
    logger.error('COULD NOT FIND nmcli!!!')

CPUFREQ_INFO_BIN = pathlib.Path('/usr/bin/cpufreq-info')
if not CPUFREQ_INFO_BIN.is_file() and not PYTEST and not DOCKERIZED:
    logger.error('COULD NOT FIND cpufreq-info!!!')

CPUFREQ_SET_BIN = pathlib.Path('/usr/bin/cpufreq-set')
if not CPUFREQ_SET_BIN.is_file() and not PYTEST and not DOCKERIZED:
    logger.error('COULD NOT FIND cpufreq-set!!!')

POWER_SAVE_FREQ = 'powersave'  # noqa


class HotspotStatus(enum.Enum):
    disconnected = enum.auto()  # Radio is on, but Hotspot is not connected.
    unavailable = enum.auto()  # Radio is off.
    connected = enum.auto()  # Radio is on, Hotspot is on.
    unknown = enum.auto()  # Unknown status.  Hotspot may not be supported on this hardware.


def hotspot_status() -> HotspotStatus:
    cmd = (NMCLI_BIN,)
    try:
        output = subprocess.check_output(cmd).decode().strip()
    except FileNotFoundError as e:
        if not DOCKERIZED:
            logger.debug(f'Could not get hotspot status', exc_info=e)
        return HotspotStatus.unknown

    for line in output.splitlines():
        if line.startswith('wlan0: connected'):
            return HotspotStatus.connected
        elif line.startswith('wlan0: disconnected'):
            return HotspotStatus.disconnected
        elif line.startswith('wlan0: unavailable'):
            return HotspotStatus.unavailable

    return HotspotStatus.unknown


def enable_hotspot():
    """Turn the wlan0 interface into a hotspot.

    If wlan0 is already running, replace that with a hotspot.
    """
    status = hotspot_status()
    logger.warning(f'Hotspot status: {status}')

    if status == HotspotStatus.connected:
        disable_hotspot()
        return enable_hotspot()
    elif status == HotspotStatus.disconnected:
        # Radio is on, but not connected.  Good, turn it into a hotspot.
        cmd = (SUDO_BIN, NMCLI_BIN, 'device', 'wifi', 'hotspot', 'ifname', 'wlan0',
               'ssid', 'WROLPi', 'password', 'wrolpi hotspot')
        subprocess.check_call(cmd)
        return True
    elif status == HotspotStatus.unavailable:
        # Radio is not on, turn it on.
        cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'on')
        subprocess.check_call(cmd)
        return enable_hotspot()
    elif status == HotspotStatus.unknown:
        logger.error('Cannot enable hotspot with unknown status!')


def disable_hotspot():
    """Turn off the wlan0 interface."""
    cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'off')
    try:
        subprocess.check_call(cmd)
        return True
    except Exception as e:
        logger.error('Failed to disable hotspot', exc_info=e)
        return False


class GovernorStatus(enum.Enum):
    ondemand = enum.auto()
    powersave = enum.auto()
    unknown = enum.auto()
    # These are unused by WROLPi.
    # performance = enum.auto()
    # schedutil = enum.auto()
    # userspace = enum.auto()
    # conservative = enum.auto()


GOVERNOR_MAP = {
    'governor "ondemand"': GovernorStatus.ondemand,
    'governor "powersave"': GovernorStatus.powersave,
}


def throttle_status() -> GovernorStatus:
    cmd = (CPUFREQ_INFO_BIN,)
    try:
        output = subprocess.check_output(cmd)
    except FileNotFoundError as e:
        if not DOCKERIZED:
            logger.debug(f'Could not get CPU throttle info', exc_info=e)
        return GovernorStatus.unknown
    output = output.decode().strip()

    for line in output.splitlines():
        for governor, status in GOVERNOR_MAP.items():
            if governor in line:
                return status

    return GovernorStatus.unknown


def throttle_cpu_on() -> bool:
    """Call cpufreq-set to throttle CPU."""
    try:
        cmd = (SUDO_BIN, CPUFREQ_SET_BIN, '-g', POWER_SAVE_FREQ)
        subprocess.check_call(cmd)
        return True
    except FileNotFoundError:
        if not DOCKERIZED:
            logger.error('Could not enable CPU throttle', exc_info=True)


def throttle_cpu_off() -> bool:
    """Call cpufreq-set to un-throttle CPU."""
    try:
        cmd = (SUDO_BIN, CPUFREQ_SET_BIN, '-g', DEFAULT_CPU_FREQUENCY)
        subprocess.check_call(cmd)
        return True
    except FileNotFoundError:
        if not DOCKERIZED:
            logger.error('Could not disable CPU throttle', exc_info=True)
