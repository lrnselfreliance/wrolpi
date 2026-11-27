"""
VPN settings and status for the Controller.

The tunnel itself (controller/vpn/tunnel.py) runs in the `wrolpi-vpn` service (Raspberry Pi / Debian) or the `vpn`
container (Docker); it follows the `vpn` section of controller.yaml on its own.  The Controller saves the settings and
the user's VPN config, resolves the config's server names (the tunnel's kill switch blocks DNS until the tunnel is
up), and reports the status the tunnel writes.
"""

import asyncio
import json
import logging
import os
import socket
import time
from pathlib import Path

from controller.lib.config import get_config_value, get_media_directory, save_config, update_config
from controller.vpn import tunnel

logger = logging.getLogger(__name__)

# Relative to the config directory.
WIREGUARD_CONFIG = 'vpn/wireguard.conf'
OPENVPN_CONFIG = 'vpn/openvpn.ovpn'
OPENVPN_AUTH = 'vpn/openvpn-auth.txt'
CONFIG_FILES = {'wireguard': WIREGUARD_CONFIG, 'openvpn': OPENVPN_CONFIG}
MAX_CONFIG_BYTES = 256 * 1024

# The tunnel writes its status every 15 seconds; older than this, it is not running.
STALE_STATUS_SECONDS = 60
# Provider host names rarely move; look them up again this often in case they do.
ENDPOINTS_MAX_AGE = 6 * 60 * 60
ENDPOINTS_LOOP_SECONDS = 60


def get_run_dir() -> Path:
    return tunnel.RUN_DIR


def get_config_directory() -> Path:
    return get_media_directory() / 'config'


def get_vpn_settings() -> dict:
    return {**tunnel.VPN_DEFAULTS, **(get_config_value('vpn') or {})}


def _write_private(path: Path, text: str):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.tmp')
    tunnel.write_private(tmp, text)
    os.replace(tmp, path)


def read_vpn_config() -> tuple[str, str] | None:
    """(kind, text) of the uploaded VPN config, or None."""
    config_file = get_vpn_settings().get('config_file')
    if not config_file:
        return None
    try:
        text = (get_config_directory() / config_file).read_text()
    except FileNotFoundError:
        return None
    return tunnel.config_kind(config_file), text


def _save_settings(**values):
    for key, value in values.items():
        update_config(f'vpn.{key}', value)
    save_config()


def save_vpn_config(filename: str, content: str) -> dict:
    """Validate and store an uploaded WireGuard or OpenVPN config, replacing any previous one."""
    if len(content.encode()) > MAX_CONFIG_BYTES:
        raise tunnel.VPNConfigError('That file is too large to be a VPN config')
    kind = tunnel.config_kind(filename)
    tunnel.remotes_of(kind, content)  # Raises when the config cannot be used.

    config_directory = get_config_directory()
    _write_private(config_directory / CONFIG_FILES[kind], content)
    for other_kind, other in CONFIG_FILES.items():
        if other_kind != kind:
            (config_directory / other).unlink(missing_ok=True)
    _save_settings(config_file=CONFIG_FILES[kind])
    resolve_endpoints_safely()
    return get_vpn_settings_response()


def save_openvpn_auth(username: str, password: str) -> dict:
    if not username or not password:
        raise tunnel.VPNConfigError('Enter the VPN username and password')
    if any(c in s for s in (username, password) for c in '\r\n'):
        raise tunnel.VPNConfigError('The VPN username and password cannot contain line breaks')
    _write_private(get_config_directory() / OPENVPN_AUTH, f'{username}\n{password}\n')
    _save_settings(auth_file=OPENVPN_AUTH)
    return get_vpn_settings_response()


def update_vpn_settings(enabled: bool = None, port_forwarding: str = None, forwarded_port: int = None,
                        public_ip_url: str = None, natpmp_gateway: str = None) -> dict:
    settings = get_vpn_settings()
    values = {}
    if port_forwarding is not None:
        if port_forwarding not in tunnel.PORT_FORWARDING_MODES:
            raise tunnel.VPNConfigError(f'Port forwarding must be one of {", ".join(tunnel.PORT_FORWARDING_MODES)}')
        values['port_forwarding'] = port_forwarding
    if forwarded_port is not None:
        if not 1 <= forwarded_port <= 65535:
            raise tunnel.VPNConfigError('The forwarded port must be between 1 and 65535')
        values['forwarded_port'] = forwarded_port
    if (values.get('port_forwarding', settings['port_forwarding']) == 'fixed'
            and not values.get('forwarded_port', settings['forwarded_port'])):
        raise tunnel.VPNConfigError('Enter the port your VPN provider forwards to you')
    if natpmp_gateway is not None:
        if natpmp_gateway and not (tunnel.is_ip(natpmp_gateway) and tunnel.ip_version(natpmp_gateway) == 4):
            raise tunnel.VPNConfigError('The port forwarding gateway must be an IPv4 address')
        values['natpmp_gateway'] = natpmp_gateway or None
    if public_ip_url is not None:
        if public_ip_url:
            tunnel.check_public_ip_url(public_ip_url)
        values['public_ip_url'] = public_ip_url or None
    if enabled is not None:
        if enabled:
            loaded = read_vpn_config()
            if not loaded:
                raise tunnel.VPNConfigError('Upload a VPN config before turning the VPN on')
            kind, text = loaded
            if (kind == 'openvpn' and tunnel.parse_openvpn(text).wants_auth
                    and not (get_config_directory() / OPENVPN_AUTH).is_file()):
                raise tunnel.VPNConfigError('This OpenVPN config needs a username and password')
        values['enabled'] = enabled
    _save_settings(**values)
    resolve_endpoints_safely()
    return get_vpn_settings_response()


def delete_vpn_config() -> dict:
    """Forget the VPN config and login, and turn the VPN off."""
    config_directory = get_config_directory()
    for path in (*CONFIG_FILES.values(), OPENVPN_AUTH):
        (config_directory / path).unlink(missing_ok=True)
    _save_settings(enabled=False, config_file=None, auth_file=None)
    (get_run_dir() / tunnel.ENDPOINTS_FILE).unlink(missing_ok=True)
    return get_vpn_settings_response()


def get_vpn_settings_response() -> dict:
    settings = get_vpn_settings()
    loaded = read_vpn_config()
    kind, remotes, wants_auth = None, [], False
    if loaded:
        kind, text = loaded
        try:
            remotes = [r.host for r in tunnel.remotes_of(kind, text)]
            wants_auth = kind == 'openvpn' and tunnel.parse_openvpn(text).wants_auth
        except tunnel.VPNConfigError:
            pass
    return {
        'enabled': bool(settings['enabled']),
        'kind': kind,
        'servers': list(dict.fromkeys(remotes)),
        'needs_auth': wants_auth,
        'has_auth': (get_config_directory() / OPENVPN_AUTH).is_file(),
        'port_forwarding': settings['port_forwarding'],
        'forwarded_port': settings['forwarded_port'],
        'public_ip_url': settings['public_ip_url'],
        'natpmp_gateway': settings['natpmp_gateway'],
    }


def resolve_endpoints() -> dict[str, list[str]]:
    """Look up the config's server names for the tunnel, which cannot use DNS until it is up."""
    run_dir = get_run_dir()
    loaded = read_vpn_config()
    if not loaded:
        (run_dir / tunnel.ENDPOINTS_FILE).unlink(missing_ok=True)
        return {}
    kind, text = loaded
    names = dict.fromkeys(r.host for r in tunnel.remotes_of(kind, text) if not tunnel.is_ip(r.host))
    hosts = {}
    for name in names:
        try:
            hosts[name] = tunnel.resolve_host(name)
        except socket.gaierror as e:
            logger.warning('Could not look up the VPN server %s: %s', name, e)
    tunnel.write_json(run_dir / tunnel.ENDPOINTS_FILE,
                      {'config_sha256': tunnel.config_sha256(text), 'hosts': hosts, 'resolved_at': time.time()})
    return hosts


def resolve_endpoints_safely():
    try:
        resolve_endpoints()
    except (OSError, tunnel.VPNConfigError) as e:
        logger.warning('Could not look up the VPN servers: %s', e)


def endpoints_need_resolving() -> bool:
    if not get_vpn_settings()['enabled']:
        return False
    loaded = read_vpn_config()
    if not loaded:
        return False
    _, text = loaded
    try:
        data = json.loads((get_run_dir() / tunnel.ENDPOINTS_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    names = {r.host for r in tunnel.remotes_of(*loaded) if not tunnel.is_ip(r.host)}
    return (data.get('config_sha256') != tunnel.config_sha256(text)
            or not names.issubset(data.get('hosts') or {})
            or time.time() - data.get('resolved_at', 0) > ENDPOINTS_MAX_AGE)


async def vpn_endpoints_loop():
    """Keep the tunnel's server addresses current, e.g. when the Internet was down at boot."""
    while True:
        try:
            if await asyncio.to_thread(endpoints_need_resolving):
                await asyncio.to_thread(resolve_endpoints)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning('Could not look up the VPN servers: %s', e)
        await asyncio.sleep(ENDPOINTS_LOOP_SECONDS)


def get_vpn_status() -> dict:
    settings = get_vpn_settings()
    try:
        status = json.loads((get_run_dir() / tunnel.STATUS_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        status = {}
    if not status or time.time() - status.get('updated_at', 0) > STALE_STATUS_SECONDS:
        # The tunnel is not running; its kill switch (if it ever ran) still blocks torrents.
        status = {'state': 'stopped'}
    return {
        'enabled': bool(settings['enabled']),
        'state': status.get('state'),
        'kind': status.get('kind'),
        'interface': status.get('interface'),
        'addresses': status.get('addresses') or [],
        'dns': status.get('dns') or [],
        'public_ip': status.get('public_ip'),
        'port_forwarding': settings['port_forwarding'],
        'forwarded_port': status.get('forwarded_port'),
        'warnings': status.get('warnings') or [],
        'error': status.get('error'),
        'updated_at': status.get('updated_at'),
    }
