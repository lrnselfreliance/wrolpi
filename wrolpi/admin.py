import asyncio
import enum
import subprocess

from wrolpi.cmd import NMCLI_BIN, CPUFREQ_INFO_BIN, SUDO_BIN, CPUFREQ_SET_BIN, run_command
from wrolpi.common import logger, WROLPI_CONFIG, get_warn_once, background_task
from wrolpi.errors import ShutdownFailed
from wrolpi.events import Events
from wrolpi.vars import DEFAULT_CPU_FREQUENCY, DOCKERIZED

logger = logger.getChild(__name__)

POWER_SAVE_FREQ = 'powersave'  # noqa

nmcli_warn_once = get_warn_once('Unable to use nmcli', logger)
iwgetid_warn_once = get_warn_once('Unable to use iwgetid', logger)


class HotspotStatus(enum.Enum):
    disconnected = enum.auto()  # Radio is on, but Hotspot is not connected.
    unavailable = enum.auto()  # Radio is off.
    connected = enum.auto()  # Radio is on, Hotspot is on.
    unknown = enum.auto()  # Unknown status.  Hotspot may not be supported on this hardware.
    in_use = enum.auto()  # WI-FI device is in use, and cannot be used for Hotspot.


def hotspot_status() -> HotspotStatus:
    if NMCLI_BIN is None:
        return HotspotStatus.unknown

    device = WROLPI_CONFIG.hotspot_device

    if get_current_ssid(device):
        # Hotspot device is currently connected to a WI-FI network.
        return HotspotStatus.in_use

    cmd = (NMCLI_BIN,)
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode().strip()
    except Exception as e:
        nmcli_warn_once(e)
        return HotspotStatus.unknown

    for line in output.splitlines():
        if line.startswith(f'{device}: connected'):
            return HotspotStatus.connected
        elif line.startswith(f'{device}: disconnected'):
            return HotspotStatus.disconnected
        elif line.startswith(f'{device}: unavailable'):
            return HotspotStatus.unavailable

    return HotspotStatus.unknown


def get_current_ssid(interface='wlan0') -> str | None:
    """Returns the name of the SSID that is currently connected.  Returns None if Hotspot, or no WI-FI network is being
    used."""
    try:
        # Run the iwgetid command and capture the output
        cmd = ('iwgetid', interface, '--raw')
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check if the command was successful
        if result.returncode == 0:
            ssid = result.stdout.strip()
            return ssid
        elif result.returncode == 255:
            # Hotspot is in use.
            return None
        else:
            logger.error(f'Failed to get current ssid: {result.stderr}')
            return None
    except FileNotFoundError as e:
        iwgetid_warn_once(e)
        return None
    except Exception as e:
        logger.error('Failed to get current ssid', exc_info=e)
        return None


def enable_hotspot(depth: int = 10, overwrite: bool = False):
    """Turn the Wi-Fi interface into a hotspot.

    If Wi-Fi is already running, replace that with a hotspot.
    """
    if depth < 0:
        raise RuntimeError(f'Failed to start hotspot!')

    status = hotspot_status()
    logger.info(f'Hotspot status: {status}')

    if overwrite is False and (current_ssid := get_current_ssid(WROLPI_CONFIG.hotspot_device)):
        raise RuntimeError(f'Refusing to start hotspot because Wi-Fi device is already being used for {current_ssid}.')

    if status == HotspotStatus.connected:
        logger.info('Hotspot already connected.  Rebooting hotspot.')
        disable_hotspot()
        return enable_hotspot(depth=depth - 1)
    elif status == HotspotStatus.in_use:
        logger.info('Wifi already in use.  Rebooting hotspot.')
        disable_hotspot()
        return enable_hotspot(depth=depth - 1)
    elif status == HotspotStatus.disconnected:
        # Radio is on, but not connected.  Good, turn it into a hotspot.
        cmd = (SUDO_BIN, NMCLI_BIN, 'device', 'wifi', 'hotspot', 'ifname', WROLPI_CONFIG.hotspot_device,
               'ssid', WROLPI_CONFIG.hotspot_ssid, 'password', WROLPI_CONFIG.hotspot_password)
        subprocess.check_call(cmd)
        logger.info('Enabling hotspot successful')
        return True
    elif status == HotspotStatus.unavailable:
        # Radio is not on, turn it on.
        cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'on')
        subprocess.check_call(cmd)
        logger.info('Turned on hotspot radio.')
        return enable_hotspot(depth=depth - 1)
    elif status == HotspotStatus.unknown:
        logger.error('Cannot enable hotspot with unknown status!')


def disable_hotspot():
    """Turn off the Wi-Fi interface."""
    cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'off')
    try:
        subprocess.check_call(cmd)
        logger.info('Disabling hotspot successful')
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
    if not CPUFREQ_INFO_BIN:
        return GovernorStatus.unknown

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


async def shutdown(reboot: bool = False, delay: int = 10):
    """Shutdown or reboot the WROLPi.  Schedules an asyncio sleep to delay the shutdown.

    @raise ShutdownFailed: If not possible, or if sudo command failed."""
    if DOCKERIZED:
        raise ShutdownFailed('Cannot Reboot because we are dockerized')

    cmd = (SUDO_BIN, 'shutdown', '--reboot', '0') if reboot else (SUDO_BIN, 'shutdown', '0')

    async def _():
        await asyncio.sleep(delay)

        try:
            # Call shutdown (or reboot) with no delay now that we have slept.
            result = await run_command(cmd)
        except subprocess.CalledProcessError as e:
            if reboot:
                Events.send_shutdown_failed('Reboot failed')
            else:
                Events.send_shutdown_failed('Shutdown failed')
            raise ShutdownFailed() from e

        if result.return_code != 0:
            if reboot:
                Events.send_shutdown_failed('Reboot failed')
            else:
                Events.send_shutdown_failed('Shutdown failed')
            raise ShutdownFailed(f'Got return code {result.return_code}')

    background_task(_())
    if reboot:
        Events.send_shutdown(f'Reboot in {delay} seconds')
    else:
        Events.send_shutdown(f'Shutdown in {delay} seconds')
