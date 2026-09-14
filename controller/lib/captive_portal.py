"""
Hotspot captive portal: the dnsmasq include which points OS connectivity-probe hostnames at this
WROLPi, so devices that join the hotspot are shown its address.  Native only (Docker has no hotspot).
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from controller.lib.config import get_config_value, is_docker_mode

logger = logging.getLogger(__name__)

# Hostnames the major operating systems probe for Internet access.  Only these are hijacked: a
# wildcard would break the hotspot's forwarding of everything else to the WROLPi's uplink.
PROBE_HOSTS = (
    'captive.apple.com',  # iOS / macOS
    'connectivitycheck.gstatic.com',  # Android
    'connectivitycheck.android.com',  # Android (older)
    'www.msftconnecttest.com',  # Windows 10+
    'www.msftncsi.com',  # Windows 7/8
    'detectportal.firefox.com',  # Firefox
    'connectivity-check.ubuntu.com',  # Ubuntu / NetworkManager (probes `/`, served by the dashboard)
    'nmcheck.gnome.org',  # GNOME
)

# Paths those probes request.  The Controller redirects each of these to the portal.
# `/` is not listed: the dashboard already answers it with HTML, which a probe treats as a portal.
PROBE_PATHS = (
    '/hotspot-detect.html',  # Apple
    '/generate_204',  # Android
    '/connecttest.txt',  # Windows 10+
    '/ncsi.txt',  # Windows 7/8
    '/success.txt',  # Firefox
    '/canonical.html',  # Firefox
    '/check_network_status.txt',  # GNOME
)

# `http://wrolpi/` also reaches the WROLPi from a hotspot client.
FRIENDLY_NAME = 'wrolpi'

# NetworkManager starts its shared-mode dnsmasq with `--conf-dir=` pointing here and reads it
# only when the Hotspot connection is activated.
DNSMASQ_SHARED_DIR = Path('/etc/NetworkManager/dnsmasq-shared.d')
INCLUDE_FILE = DNSMASQ_SHARED_DIR / '50-wrolpi-captive-portal.conf'

# NetworkManager's default shared-mode subnet.  The real address is read once the hotspot is up.
DEFAULT_HOTSPOT_IP = '10.42.0.1'

PORTAL_PATH = '/portal'


def is_captive_portal_enabled() -> bool:
    """The maintainer's `hotspot.captive_portal` setting in controller.yaml.  Never true in Docker."""
    if is_docker_mode():
        return False
    return bool(get_config_value('hotspot.captive_portal', True))


def get_hotspot_ip(device: str) -> Optional[str]:
    """
    The IPv4 address the hotspot device currently has, or None when it has none (hotspot down),
    the device is missing, or `ip` is unavailable (Docker, macOS).
    """
    if is_docker_mode() or not device:
        return None
    try:
        result = subprocess.run(
            ['ip', '-4', '-j', 'addr', 'show', 'dev', device],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        for interface in json.loads(result.stdout or '[]'):
            for addr in interface.get('addr_info') or []:
                if addr.get('family') == 'inet' and addr.get('local'):
                    return addr['local']
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.debug('Could not read hotspot IP of %s: %s', device, e)
    return None


def render_dnsmasq_config(ip: str) -> str:
    """The dnsmasq include which points the probe hostnames and the friendly name at the hotspot."""
    lines = [
        '# Managed by the WROLPi Controller; changes are overwritten when the hotspot starts.',
        '# Captive portal: captive-portal probe hostnames resolve to this WROLPi.',
        '# Only these names are hijacked so the hotspot still forwards everything else.',
    ]
    lines.extend(f'address=/{host}/{ip}' for host in PROBE_HOSTS)
    lines.append(f'address=/{FRIENDLY_NAME}/{ip}')
    return '\n'.join(lines) + '\n'


def apply_dnsmasq_config(ip: str = DEFAULT_HOTSPOT_IP) -> bool:
    """
    Write the dnsmasq include when the captive portal is enabled, remove it when disabled.

    Best-effort: a failure is logged and swallowed, because a working hotspot matters more than
    the portal.  Returns True when the include file now matches the setting.
    """
    try:
        if is_captive_portal_enabled():
            INCLUDE_FILE.parent.mkdir(parents=True, exist_ok=True)
            INCLUDE_FILE.write_text(render_dnsmasq_config(ip))
            INCLUDE_FILE.chmod(0o644)
            logger.info('Captive portal dnsmasq config written for %s', ip)
        elif INCLUDE_FILE.exists():
            INCLUDE_FILE.unlink()
            logger.info('Captive portal disabled; dnsmasq config removed')
        return True
    except OSError as e:
        logger.warning('Could not update captive portal dnsmasq config %s: %s', INCLUDE_FILE, e)
        return False


def dnsmasq_config_ip() -> Optional[str]:
    """The IP the current include file points at, or None when there is no include file."""
    try:
        for line in INCLUDE_FILE.read_text().splitlines():
            if line.startswith('address=/'):
                return line.rsplit('/', 1)[-1].strip() or None
    except OSError:
        pass
    return None
