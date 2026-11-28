#!/usr/bin/env python3
"""
Prepare qBittorrent's config before it starts, inside the VPN's network namespace.

qBittorrent runs in the namespace the VPN's kill switch guards (controller/vpn/tunnel.py): the `wrolpi-vpn` namespace
on a Raspberry Pi or Debian, or the `vpn` container's on Docker.  Its WebUI must be reachable by WROLPi (the API, and
Caddy, which serves it to the LAN on port 8091) through the namespace's uplink, and never through the tunnel.  So the
WebUI listens only on the uplink's address, and needs no password from the uplink's network (WROLPi has no logins;
the LAN reaches it only through Caddy).  Torrents use only the tunnel's interface from the first moment; WROLPi
enforces the rest of the preferences once qBittorrent is up.

This runs standalone (in the torrent container, or before wrolpi-torrent.service), so it imports only the standard
library.
"""
import argparse
import configparser
import ipaddress
import json
import pathlib
import subprocess

WEBUI_PORT = 8091
TUNNEL_INTERFACE = 'vpn0'


def find_uplink() -> tuple[str, str]:
    """The namespace's uplink: (its address, its network).  The tunnel never replaces the default route, so the
    default route's interface is the uplink."""
    routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default']) or b'[]')
    interfaces = [r['dev'] for r in routes if r.get('dev') and r['dev'] != TUNNEL_INTERFACE]
    if not interfaces:
        raise RuntimeError('The VPN namespace has no uplink; is the VPN service running?')
    addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', interfaces[0]]) or b'[]')
    for entry in addresses:
        for address in entry.get('addr_info', []):
            if address.get('scope') == 'global':
                interface = ipaddress.ip_interface(f"{address['local']}/{address['prefixlen']}")
                return str(interface.ip), str(interface.network)
    raise RuntimeError(f'The VPN namespace uplink {interfaces[0]} has no address')


def prepare(profile: pathlib.Path, address: str, network: str) -> pathlib.Path:
    """Write the WebUI and interface settings into qBittorrent's config, keeping everything else in it."""
    path = profile / 'qBittorrent' / 'config' / 'qBittorrent.conf'
    # qBittorrent's config is Qt's INI: case-sensitive keys, `\` in key names, no interpolation.
    config = configparser.RawConfigParser(strict=False)
    config.optionxform = str
    if path.is_file():
        config.read(path, encoding='utf-8')
    settings = {
        'Preferences': {
            'WebUI\\Enabled': 'true',
            'WebUI\\Address': address,
            'WebUI\\Port': str(WEBUI_PORT),
            'WebUI\\LocalHostAuth': 'false',
            'WebUI\\AuthSubnetWhitelistEnabled': 'true',
            'WebUI\\AuthSubnetWhitelist': network,
            # Reached by the LAN through Caddy, so the Host is this WROLPi's LAN address, not the uplink's.
            'WebUI\\HostHeaderValidation': 'false',
        },
        'BitTorrent': {
            'Session\\Interface': TUNNEL_INTERFACE,
            'Session\\InterfaceName': TUNNEL_INTERFACE,
        },
        'LegalNotice': {
            'Accepted': 'true',
        },
    }
    for section, values in settings.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in values.items():
            config.set(section, key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        config.write(f, space_around_delimiters=False)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--profile', type=pathlib.Path, required=True, help="qBittorrent's --profile directory")
    args = parser.parse_args(argv)
    address, network = find_uplink()
    path = prepare(args.profile, address, network)
    print(f'qBittorrent WebUI on {address}:{WEBUI_PORT}, without a password from {network}; config {path}')


if __name__ == '__main__':
    main()
