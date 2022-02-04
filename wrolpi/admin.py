import pathlib
import re
import subprocess

from wrolpi.common import logger
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# Location on an RPi
SUDO_BIN = pathlib.Path('/usr/bin/sudo')
if not SUDO_BIN.is_file() and not PYTEST:
    logger.error('COULD NOT FIND sudo!!!')
NMCLI_BIN = pathlib.Path('/usr/bin/nmcli')
if not NMCLI_BIN.is_file() and not PYTEST:
    logger.error('COULD NOT FIND nmcli!!!')

DEVICE_NAMES = ('wlan0', 'eth0')

DEVICE_MATCH = re.compile(r'^(.+?): (connected|unavailable).*$')
MAC_MATCH = re.compile(r'.+?(\w+?) \(.+?\), ([0-9A-F:]{17}).*')
INET_MATCH = re.compile(r'.+?(inet[46]) ([a-f0-9\./:]+).*')


def parse_nmcli_status(status: bytes) -> dict:
    status = status.decode()

    parsed = dict()
    device = dict()
    device_name = None
    for line in status.splitlines():
        if match := DEVICE_MATCH.match(line):
            device_name, connection = match.groups()
            if device_name not in DEVICE_NAMES:
                # We don't care about this device.
                device_name = None
                continue
            device['connection'] = connection
        elif match := MAC_MATCH.match(line):
            kind, mac = match.groups()
            device['kind'] = kind
            device['mac'] = mac
        elif match := INET_MATCH.match(line):
            net, ip = match.groups()
            if net == 'inet4':
                device[net] = ip
            elif net in device:
                device[net].append(ip)
            else:
                device[net] = [ip, ]
        elif line == '' and device_name:
            # Completed this device block
            parsed[device_name] = device
            device = dict()
            device_name = None

    return parsed


def hotspot_status():
    cmd = (NMCLI_BIN,)
    output = subprocess.check_output(cmd, stderr=subprocess.PIPE, timeout=10)

    parsed = parse_nmcli_status(output)

    devices = dict()
    for device_name, status in parsed.items():
        devices[device_name] = dict(
            kind=status.get('kind'),
            inet4=status.get('inet4'),
            inet6=status.get('inet6'),
            connection=status.get('connection'),
        )
    return devices


def hotspot_on():
    cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'on')
    code = subprocess.check_call(cmd)
    if code == 0:
        return True
    return False


def hotspot_off():
    cmd = (SUDO_BIN, NMCLI_BIN, 'radio', 'wifi', 'off')
    code = subprocess.check_call(cmd)
    if code == 0:
        return True
    return False
