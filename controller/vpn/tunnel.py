#!/usr/bin/env python3
"""
WROLPi VPN tunnel: the fail-closed network that torrents use.

This runs inside a network namespace of its own: `wrolpi-vpn` on a Raspberry Pi or Debian (made by
etc/raspberrypios/wrolpi-vpn-netns.sh), or the `vpn` container on Docker.  That namespace has one "uplink" interface
which reaches the Internet.  The kill switch (the nftables table `wrolpi_vpn`) lets only the VPN's own traffic, to the
endpoints in the user's config, out of the uplink.  Everything else must use the tunnel, so when the tunnel is down
nothing in the namespace can reach the Internet; it never falls back to the home connection.

The kill switch is installed before the tunnel is brought up, and it is left in place when the tunnel is taken down or
this program exits.

The VPN config is a WireGuard `.conf` or an OpenVPN `.ovpn` from any provider.  Endpoint host names are resolved by
the Controller (outside the kill switch) into `endpoints.json`, so nothing here needs DNS before the tunnel is up.

This file runs standalone in the Docker `vpn` container, so it imports only the standard library and PyYAML.  The
Controller imports it to share the parsing and the defaults.
"""
import argparse
import dataclasses
import hashlib
import ipaddress
import json
import logging
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import yaml

logger = logging.getLogger('wrolpi-vpn')

# The `vpn` section of controller.yaml.
VPN_DEFAULTS = {
    'enabled': False,
    # Relative to the config directory, e.g. vpn/wireguard.conf or vpn/openvpn.ovpn.
    'config_file': None,
    # OpenVPN only: a file holding the username line and the password line.
    'auth_file': None,
    # How peers reach this WROLPi through the VPN: none, or a port the provider forwards (fixed).
    'port_forwarding': 'none',
    'forwarded_port': None,
    # Fetched through the tunnel to show the address peers see.  None disables the check.
    'public_ip_url': 'https://api.ipify.org',
}
PORT_FORWARDING_MODES = ('none', 'fixed')

TUNNEL_INTERFACE = 'vpn0'
# The torrent client's WebUI, which WROLPi reaches from the uplink's network.
WEBUI_PORT = 8090
NFT_TABLE = 'wrolpi_vpn'
# Docker's embedded DNS server.  It forwards to the host's resolver, which would leak queries around the tunnel.
DOCKER_DNS = '127.0.0.11'

RUN_DIR = pathlib.Path(os.environ.get('WROLPI_VPN_RUN_DIR', '/run/wrolpi-vpn'))
STATUS_FILE = 'status.json'
ENDPOINTS_FILE = 'endpoints.json'
OPENVPN_CONFIG_FILE = 'openvpn.ovpn'
OPENVPN_UP_FILE = 'openvpn-up.json'

LOOP_SECONDS = 15
# WireGuard re-handshakes every two minutes while traffic flows.
HANDSHAKE_FRESH_SECONDS = 180
PUBLIC_IP_SECONDS = 300
OPENVPN_CONNECT_SECONDS = 60
# Keeps the provider's NAT mapping (and so a forwarded port) open while the tunnel is idle.
DEFAULT_KEEPALIVE = 25


class VPNConfigError(ValueError):
    """The user's VPN config or settings cannot be used.  The message is shown to the user."""


class TunnelError(RuntimeError):
    """A command which builds the tunnel failed."""


class Waiting(Exception):
    """The tunnel cannot start yet (e.g. the Controller has not resolved the endpoints)."""


@dataclasses.dataclass(frozen=True)
class Remote:
    """A VPN server named by the config; `host` may be a name or an address."""
    host: str
    port: int
    proto: str  # udp or tcp


@dataclasses.dataclass(frozen=True)
class Endpoint:
    """A VPN server address the kill switch lets the uplink reach."""
    ip: str
    port: int
    proto: str


@dataclasses.dataclass
class Uplink:
    interface: str
    gateway: str | None
    gateway6: str | None
    networks: list[str]


def get_media_directory() -> pathlib.Path:
    return pathlib.Path(os.environ.get('MEDIA_DIRECTORY', '/media/wrolpi'))


def get_config_directory(media_directory: pathlib.Path = None) -> pathlib.Path:
    return (media_directory or get_media_directory()) / 'config'


def load_settings(media_directory: pathlib.Path = None) -> dict:
    """Read the `vpn` section of controller.yaml, filled in with the defaults."""
    path = get_config_directory(media_directory) / 'controller.yaml'
    try:
        config = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        config = {}
    vpn = config.get('vpn') or {}
    return {**VPN_DEFAULTS, **{k: v for k, v in vpn.items() if k in VPN_DEFAULTS}}


def config_kind(filename: str) -> str:
    suffix = pathlib.PurePath(filename).suffix.lower()
    if suffix == '.conf':
        return 'wireguard'
    if suffix == '.ovpn':
        return 'openvpn'
    raise VPNConfigError('A VPN config must be a WireGuard .conf or an OpenVPN .ovpn file')


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def ip_version(address: str) -> int:
    return ipaddress.ip_interface(address).version


def split_list(value: str) -> list[str]:
    return [i.strip() for i in value.split(',') if i.strip()]


def split_host_port(endpoint: str) -> tuple[str, int]:
    if endpoint.startswith('['):
        host, _, rest = endpoint[1:].partition(']')
        port = rest[1:] if rest.startswith(':') else ''
    else:
        host, _, port = endpoint.rpartition(':')
    if not host or not port.isdigit():
        raise VPNConfigError(f'Cannot read the WireGuard Endpoint {endpoint!r}; expected host:port')
    return host, int(port)


# --- WireGuard ---

# The only keys `wg setconf` accepts.  wg-quick's keys (Address, DNS, MTU, PostUp...) are applied here, or ignored; a
# config's PreUp/PostUp commands are never run.
WIREGUARD_SETCONF_KEYS = {
    'interface': {'privatekey': 'PrivateKey', 'listenport': 'ListenPort', 'fwmark': 'FwMark'},
    'peer': {'publickey': 'PublicKey', 'presharedkey': 'PresharedKey', 'allowedips': 'AllowedIPs',
             'endpoint': 'Endpoint', 'persistentkeepalive': 'PersistentKeepalive'},
}
# wg-quick joins these when they are repeated.
WIREGUARD_LIST_KEYS = {'address', 'dns', 'allowedips'}


@dataclasses.dataclass
class WireGuardConfig:
    interface: dict  # lower-cased key -> value
    peers: list[dict]

    @property
    def addresses(self) -> list[str]:
        return split_list(self.interface.get('address', ''))

    @property
    def dns(self) -> list[str]:
        # wg-quick's DNS also holds search domains; only addresses are servers.
        return [i for i in split_list(self.interface.get('dns', '')) if is_ip(i)]

    @property
    def mtu(self) -> int | None:
        mtu = self.interface.get('mtu')
        return int(mtu) if mtu and mtu.isdigit() else None

    def remotes(self) -> list[Remote]:
        return [Remote(*split_host_port(peer['endpoint']), 'udp') for peer in self.peers]


def parse_wireguard(text: str) -> WireGuardConfig:
    interface = None
    peers = []
    section = None
    for number, line in enumerate(text.splitlines(), 1):
        # Keys are base64, which has no '#'.
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            name = line[1:-1].strip().lower()
            if name == 'interface':
                if interface is not None:
                    raise VPNConfigError('The WireGuard config has more than one [Interface]')
                section = interface = {}
            elif name == 'peer':
                section = {}
                peers.append(section)
            else:
                raise VPNConfigError(f'Unknown WireGuard section [{name}] on line {number}')
            continue
        if section is None or '=' not in line:
            raise VPNConfigError(f'Cannot read line {number} of the WireGuard config')
        key, value = line.split('=', 1)
        key, value = key.strip().lower(), value.strip()
        if key in WIREGUARD_LIST_KEYS and section.get(key):
            section[key] = f'{section[key]}, {value}'
        else:
            section[key] = value

    if interface is None:
        raise VPNConfigError('The WireGuard config has no [Interface]')
    if not interface.get('privatekey'):
        raise VPNConfigError('The WireGuard config has no PrivateKey')
    if not interface.get('address'):
        raise VPNConfigError('The WireGuard config has no Address')
    if not peers:
        raise VPNConfigError('The WireGuard config has no [Peer]')
    for peer in peers:
        if not peer.get('publickey'):
            raise VPNConfigError('A WireGuard [Peer] has no PublicKey')
        if not peer.get('endpoint'):
            raise VPNConfigError('A WireGuard [Peer] has no Endpoint')
    config = WireGuardConfig(interface, peers)
    for address in config.addresses:
        try:
            ipaddress.ip_interface(address)
        except ValueError:
            raise VPNConfigError(f'Cannot read the WireGuard Address {address!r}')
    config.remotes()  # Raises for an unreadable Endpoint.
    return config


def wireguard_setconf(config: WireGuardConfig, hosts: dict[str, list[str]]) -> str:
    """The config `wg setconf` takes, with each Endpoint's host replaced by its resolved address."""
    lines = ['[Interface]']
    for key, name in WIREGUARD_SETCONF_KEYS['interface'].items():
        if config.interface.get(key):
            lines.append(f'{name} = {config.interface[key]}')
    for peer in config.peers:
        lines.extend(['', '[Peer]'])
        for key, name in WIREGUARD_SETCONF_KEYS['peer'].items():
            value = peer.get(key)
            if key == 'endpoint':
                host, port = split_host_port(value)
                ip = addresses_of(host, hosts)[0]
                value = f'[{ip}]:{port}' if ip_version(ip) == 6 else f'{ip}:{port}'
            elif key == 'persistentkeepalive' and not value:
                value = DEFAULT_KEEPALIVE
            if value:
                lines.append(f'{name} = {value}')
    return '\n'.join(lines) + '\n'


# --- OpenVPN ---

# Directives which would run commands, change users, detach, or name the device.  The tunnel sets what it needs on
# the command line.
OPENVPN_DROPPED = {
    'auth-user-pass', 'auth-user-pass-verify', 'cd', 'chroot', 'client-connect', 'client-disconnect', 'config',
    'daemon', 'dev', 'dev-node', 'dev-type', 'down', 'down-pre', 'group', 'ifconfig-noexec', 'ipchange',
    'learn-address', 'log', 'log-append', 'management', 'management-hold', 'management-query-passwords', 'plugin',
    'route-noexec', 'route-pre-down', 'route-up', 'script-security', 'status', 'tls-verify', 'up', 'up-delay',
    'up-restart', 'user', 'writepid',
}
# These would send the VPN's own traffic somewhere other than the endpoints the kill switch allows.
OPENVPN_REJECTED = {'http-proxy', 'socks-proxy'}


def _openvpn_directive(line: str) -> tuple[str, list[str]]:
    tokens = line.split()
    return tokens[0].lstrip('-').lower(), tokens[1:]


def _openvpn_lines(text: str):
    """Yield (line, directive, args, in_connection) for each line; directive is None for comments, blank lines and
    inline data (e.g. <ca>...</ca>), which are passed through unchanged."""
    inline = None
    in_connection = False
    for line in text.splitlines():
        stripped = line.strip()
        if inline:
            if stripped.lower() == f'</{inline}>':
                inline = None
            yield line, None, [], in_connection
            continue
        if stripped.startswith('<') and stripped.endswith('>'):
            tag = stripped[1:-1].strip().lower()
            if tag == 'connection':
                in_connection = True
            elif tag == '/connection':
                in_connection = False
            elif not tag.startswith('/'):
                inline = tag
            yield line, None, [], in_connection
            continue
        if not stripped or stripped[0] in '#;':
            yield line, None, [], in_connection
            continue
        directive, args = _openvpn_directive(stripped)
        yield line, directive, args, in_connection


def normalize_proto(proto: str) -> str:
    proto = proto.lower()
    if proto.startswith('udp'):
        return 'udp'
    if proto.startswith('tcp'):
        return 'tcp'
    raise VPNConfigError(f'Unknown OpenVPN protocol {proto!r}')


@dataclasses.dataclass
class OpenVPNConfig:
    text: str
    remotes: list[Remote]
    wants_auth: bool


def parse_openvpn(text: str) -> OpenVPNConfig:
    # OpenVPN reads every option before it connects, so `proto`/`port` apply to a `remote` written above them.  A
    # <connection> block's own `proto`/`port` apply only to the `remote` in that block.
    defaults = {'proto': 'udp', 'port': 1194}
    blocks = []
    pending = []  # (host, port or None, proto or None, its <connection> block or None)
    wants_auth = False
    was_in_connection = False
    for _, directive, args, in_connection in _openvpn_lines(text):
        if in_connection and not was_in_connection:
            blocks.append({})
        was_in_connection = in_connection
        if directive is None:
            continue
        scope = blocks[-1] if in_connection else defaults
        if directive in OPENVPN_REJECTED:
            raise VPNConfigError(f'OpenVPN configs which use {directive} are not supported')
        if directive in ('dev', 'dev-type') and args and args[0].lower().startswith('tap'):
            raise VPNConfigError('TAP VPNs are not supported; use a TUN config')
        if directive == 'auth-user-pass':
            wants_auth = True
        elif directive == 'proto' and args:
            scope['proto'] = normalize_proto(args[0])
        elif directive in ('port', 'rport') and args and args[0].isdigit():
            scope['port'] = int(args[0])
        elif directive == 'remote':
            if not args:
                raise VPNConfigError('An OpenVPN remote has no server')
            remote_port = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
            remote_proto = normalize_proto(args[2]) if len(args) > 2 else None
            pending.append((args[0], remote_port, remote_proto, blocks[-1] if in_connection else {}))

    remotes = [Remote(host,
                      remote_port or block.get('port') or defaults['port'],
                      remote_proto or block.get('proto') or defaults['proto'])
               for host, remote_port, remote_proto, block in pending]
    if not remotes:
        raise VPNConfigError('The OpenVPN config has no remote server')
    return OpenVPNConfig(text, remotes, wants_auth)


def sanitize_openvpn(config: OpenVPNConfig, hosts: dict[str, list[str]]) -> str:
    """The config the tunnel runs: no commands, and each `remote` names an address (one line per address) so OpenVPN
    never needs DNS behind the kill switch."""
    remotes = iter(config.remotes)
    lines = []
    for line, directive, _, _ in _openvpn_lines(config.text):
        if directive in OPENVPN_DROPPED:
            continue
        if directive == 'remote':
            remote = next(remotes)
            for ip in addresses_of(remote.host, hosts):
                lines.append(f'remote {ip} {remote.port} {remote.proto}')
            continue
        lines.append(line)
    return '\n'.join(lines) + '\n'


def openvpn_up_hook(run_dir: pathlib.Path):
    """Called by OpenVPN (`--up`) once the tunnel device has its address; records what the server pushed."""
    dns = []
    options = sorted((k for k in os.environ if k.startswith('foreign_option_')),
                     key=lambda k: int(k.rpartition('_')[2]) if k.rpartition('_')[2].isdigit() else 0)
    for key in options:
        parts = os.environ[key].split()
        if len(parts) >= 3 and parts[0] == 'dhcp-option' and parts[1].upper() in ('DNS', 'DNS6') and is_ip(parts[2]):
            dns.append(parts[2])
    addresses = []
    if local := os.environ.get('ifconfig_local'):
        netmask = os.environ.get('ifconfig_netmask')
        prefix = ipaddress.ip_network(f'0.0.0.0/{netmask}').prefixlen if netmask else 32
        addresses.append(f'{local}/{prefix}')
    if local6 := os.environ.get('ifconfig_ipv6_local'):
        addresses.append(f"{local6}/{os.environ.get('ifconfig_ipv6_netbits', '128')}")
    write_json(run_dir / OPENVPN_UP_FILE, {'dev': os.environ.get('dev'), 'addresses': addresses, 'dns': dns})


# --- Endpoints ---

def remotes_of(kind: str, text: str) -> list[Remote]:
    """The servers named by a config; raises VPNConfigError when the config cannot be used."""
    if kind == 'wireguard':
        return parse_wireguard(text).remotes()
    return parse_openvpn(text).remotes


def resolve_host(host: str) -> list[str]:
    addresses = []
    for *_, sockaddr in socket.getaddrinfo(host, None, type=socket.SOCK_DGRAM):
        if sockaddr[0] not in addresses:
            addresses.append(sockaddr[0])
    return addresses


def addresses_of(host: str, hosts: dict[str, list[str]]) -> list[str]:
    if is_ip(host):
        return [host]
    if not hosts.get(host):
        raise Waiting(f'Waiting for the Controller to look up the VPN server {host}')
    return hosts[host]


def endpoints_of(remotes: list[Remote], hosts: dict[str, list[str]]) -> list[Endpoint]:
    endpoints = []
    for remote in remotes:
        for ip in addresses_of(remote.host, hosts):
            endpoint = Endpoint(ip, remote.port, remote.proto)
            if endpoint not in endpoints:
                endpoints.append(endpoint)
    return endpoints


def config_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_endpoint_hosts(run_dir: pathlib.Path, text: str) -> dict[str, list[str]]:
    """The host names the Controller resolved for this config, or {} if it has not resolved this config yet."""
    try:
        data = json.loads((run_dir / ENDPOINTS_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if data.get('config_sha256') != config_sha256(text):
        return {}
    return data.get('hosts') or {}


# --- Kill switch ---

def build_ruleset(uplink: Uplink, endpoints: list[Endpoint], tunnel: str = TUNNEL_INTERFACE,
                  webui_port: int = WEBUI_PORT) -> str:
    """The kill switch.  The first two lines make replacing the table one atomic transaction."""
    up = uplink.interface
    inbound, outbound = [], []
    for network in uplink.networks:
        family = 'ip6' if ip_version(network) == 6 else 'ip'
        inbound.append(f'iifname "{up}" {family} saddr {network} tcp dport {webui_port} accept')
        outbound.append(f'oifname "{up}" {family} daddr {network} ct state established,related accept')
    for endpoint in endpoints:
        family = 'ip6' if ip_version(endpoint.ip) == 6 else 'ip'
        outbound.append(f'oifname "{up}" {family} daddr {endpoint.ip} {endpoint.proto} dport {endpoint.port} accept')

    def rules(lines):
        return ''.join(f'\t\t{line}\n' for line in lines)

    return (
        f'table inet {NFT_TABLE}\n'
        f'delete table inet {NFT_TABLE}\n'
        f'table inet {NFT_TABLE} {{\n'
        f'\tchain input {{\n'
        f'\t\ttype filter hook input priority filter; policy drop;\n'
        f'\t\tiifname "lo" accept\n'
        f'\t\tct state established,related accept\n'
        f'\t\tiifname "{tunnel}" accept\n'
        f'{rules(inbound)}'
        f'\t}}\n'
        f'\tchain output {{\n'
        f'\t\ttype filter hook output priority filter; policy drop;\n'
        f'\t\tip daddr {DOCKER_DNS} drop\n'
        f'\t\toifname "lo" accept\n'
        f'\t\toifname "{tunnel}" accept\n'
        f'{rules(outbound)}'
        f'\t}}\n'
        f'\tchain forward {{\n'
        f'\t\ttype filter hook forward priority filter; policy drop;\n'
        f'\t}}\n'
        f'}}\n'
    )


# --- Commands ---

def run(*cmd, input_: str = None) -> subprocess.CompletedProcess:
    result = subprocess.run([str(i) for i in cmd], input=input_, capture_output=True, text=True)
    if result.returncode != 0:
        raise TunnelError(f'{" ".join(map(str, cmd))} failed: {result.stderr.strip() or result.stdout.strip()}')
    return result


def run_quietly(*cmd):
    """Run a clean-up command whose failure (e.g. nothing to delete) does not matter."""
    subprocess.run([str(i) for i in cmd], capture_output=True)


def write_json(path: pathlib.Path, data: dict):
    """Write atomically so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, prefix=f'.{path.name}.') as f:
        json.dump(data, f)
    os.replace(f.name, path)


def write_private(path: pathlib.Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    os.chmod(path, 0o600)


def write_resolv_conf(path: pathlib.Path, servers: list[str]):
    # Rewritten in place, never replaced: on a Raspberry Pi `ip netns exec` bind-mounts this file over
    # /etc/resolv.conf, and a bind mount keeps showing the old file if it is replaced.
    with open(path, 'w') as f:
        f.write(''.join(f'nameserver {server}\n' for server in servers))


def find_uplink() -> Uplink:
    """The interface of the namespace's default route.  The tunnel never replaces the default route (it routes the
    two halves of the address space instead), so this is found the same way while the tunnel is up."""
    routes = json.loads(run('ip', '-j', '-4', 'route', 'show', 'default').stdout or '[]')
    routes = [r for r in routes if r.get('dev') and r['dev'] != TUNNEL_INTERFACE]
    if not routes:
        raise TunnelError('The VPN namespace has no default route, so it cannot reach the VPN server')
    interface, gateway = routes[0]['dev'], routes[0].get('gateway')
    routes6 = json.loads(run('ip', '-j', '-6', 'route', 'show', 'default').stdout or '[]')
    gateway6 = next((r.get('gateway') for r in routes6 if r.get('dev') == interface), None)
    networks = []
    for entry in json.loads(run('ip', '-j', 'addr', 'show', 'dev', interface).stdout or '[]'):
        for address in entry.get('addr_info', []):
            if address.get('scope') == 'global':
                network = str(ipaddress.ip_interface(f"{address['local']}/{address['prefixlen']}").network)
                networks.append(network)
    return Uplink(interface, gateway, gateway6, networks)


def apply_ruleset(ruleset: str):
    run('nft', '-f', '-', input_=ruleset)


@dataclasses.dataclass
class Plan:
    """What the tunnel should be, from the settings and the config."""
    kind: str
    config_path: pathlib.Path
    auth_path: pathlib.Path | None
    endpoints: list[Endpoint]
    hosts: dict[str, list[str]]
    settings: dict
    fingerprint: str
    wireguard: WireGuardConfig = None
    openvpn_text: str = None


def make_plan(settings: dict, config_directory: pathlib.Path, run_dir: pathlib.Path) -> Plan | None:
    """None when the VPN is disabled."""
    if not settings.get('enabled'):
        return None
    if not settings.get('config_file'):
        raise VPNConfigError('No VPN config has been uploaded')
    config_path = config_directory / settings['config_file']
    kind = config_kind(config_path.name)
    try:
        text = config_path.read_text()
    except FileNotFoundError:
        raise VPNConfigError(f'The VPN config {settings["config_file"]} is missing')
    hosts = read_endpoint_hosts(run_dir, text)
    auth_path, auth_text = None, ''
    if kind == 'wireguard':
        wireguard = parse_wireguard(text)
        endpoints = endpoints_of(wireguard.remotes(), hosts)
        plan_kwargs = {'wireguard': wireguard}
    else:
        openvpn = parse_openvpn(text)
        endpoints = endpoints_of(openvpn.remotes, hosts)
        plan_kwargs = {'openvpn_text': sanitize_openvpn(openvpn, hosts)}
        if openvpn.wants_auth:
            if not settings.get('auth_file') or not (config_directory / settings['auth_file']).is_file():
                raise VPNConfigError('This OpenVPN config needs a username and password')
            auth_path = config_directory / settings['auth_file']
            auth_text = auth_path.read_text()
    fingerprint = config_sha256(json.dumps([settings, text, auth_text, hosts], sort_keys=True, default=str))
    return Plan(kind, config_path, auth_path, endpoints, hosts, settings, fingerprint, **plan_kwargs)


class Tunnel:

    def __init__(self, media_directory: pathlib.Path, run_dir: pathlib.Path, resolv_conf: pathlib.Path):
        self.config_directory = get_config_directory(media_directory)
        self.media_directory = media_directory
        self.run_dir = run_dir
        self.resolv_conf = resolv_conf
        self.uplink: Uplink | None = None
        self.plan: Plan | None = None
        self.openvpn: subprocess.Popen | None = None
        # (family flag, destination) of each route to a VPN server.
        self.routes: list[tuple[str, str]] = []
        self.addresses: list[str] = []
        self.dns: list[str] = []
        self.locked_down = False
        self.public_ip = None
        self.public_ip_checked = 0.0

    def lock_down(self):
        """The kill switch with no endpoints: nothing leaves the namespace except replies to WROLPi."""
        if not self.locked_down:
            apply_ruleset(build_ruleset(self.uplink, []))
            self.locked_down = True

    def start(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.uplink = find_uplink()
        # A previous run may have died with its tunnel up.
        run_quietly('ip', 'link', 'del', TUNNEL_INTERFACE)
        self.lock_down()

    def step(self):
        """Bring the tunnel to what the settings ask for, then report its status."""
        try:
            plan = make_plan(load_settings(self.media_directory), self.config_directory, self.run_dir)
        except Waiting as e:
            self.down()
            self.write_status('waiting', error=str(e))
            return
        except (VPNConfigError, OSError, yaml.YAMLError) as e:
            self.down()
            self.write_status('error', error=str(e))
            return

        if plan is None:
            self.down()
            self.write_status('disabled')
            return

        if self.plan is None or plan.fingerprint != self.plan.fingerprint or not self.alive():
            self.down()
            try:
                self.up(plan)
            except (TunnelError, VPNConfigError, OSError) as e:
                logger.error('Failed to bring up the VPN: %s', e)
                self.down()
                self.write_status('error', kind=plan.kind, error=str(e))
                return
        self.report()

    def alive(self) -> bool:
        if self.openvpn:
            return self.openvpn.poll() is None
        return pathlib.Path(f'/sys/class/net/{TUNNEL_INTERFACE}').exists()

    def up(self, plan: Plan):
        logger.info('Bringing up the %s VPN to %s', plan.kind, ', '.join(e.ip for e in plan.endpoints))
        self.plan = plan
        self.public_ip, self.public_ip_checked = None, 0.0
        # IPv6 servers are only reachable when the uplink has IPv6.
        endpoints = [e for e in plan.endpoints if ip_version(e.ip) == 4 or self.uplink.gateway6]
        if not endpoints:
            raise TunnelError('The VPN servers are IPv6 only, and this network has no IPv6')
        apply_ruleset(build_ruleset(self.uplink, endpoints))
        self.locked_down = False
        # The VPN's own traffic reaches its servers through the uplink, not through the tunnel.
        for endpoint in endpoints:
            if ip_version(endpoint.ip) == 6:
                family, destination, gateway = '-6', f'{endpoint.ip}/128', self.uplink.gateway6
            else:
                family, destination, gateway = '-4', f'{endpoint.ip}/32', self.uplink.gateway
            via = ('via', gateway) if gateway else ()
            run('ip', family, 'route', 'replace', destination, *via, 'dev', self.uplink.interface)
            self.routes.append((family, destination))

        if plan.kind == 'wireguard':
            self.addresses, self.dns = plan.wireguard.addresses, plan.wireguard.dns
            self.up_wireguard(plan)
        else:
            self.addresses, self.dns = self.up_openvpn(plan)

        run('ip', 'route', 'replace', '0.0.0.0/1', 'dev', TUNNEL_INTERFACE)
        run('ip', 'route', 'replace', '128.0.0.0/1', 'dev', TUNNEL_INTERFACE)
        if any(ip_version(a) == 6 for a in self.addresses):
            run('ip', '-6', 'route', 'replace', '::/1', 'dev', TUNNEL_INTERFACE)
            run('ip', '-6', 'route', 'replace', '8000::/1', 'dev', TUNNEL_INTERFACE)
        write_resolv_conf(self.resolv_conf, self.dns)

    def up_wireguard(self, plan: Plan):
        setconf = self.run_dir / 'wireguard.conf'
        write_private(setconf, wireguard_setconf(plan.wireguard, plan.hosts))
        try:
            run('ip', 'link', 'add', TUNNEL_INTERFACE, 'type', 'wireguard')
            run('wg', 'setconf', TUNNEL_INTERFACE, setconf)
        finally:
            setconf.unlink(missing_ok=True)
        for address in plan.wireguard.addresses:
            run('ip', 'address', 'add', address, 'dev', TUNNEL_INTERFACE)
        run('ip', 'link', 'set', 'dev', TUNNEL_INTERFACE, 'mtu', plan.wireguard.mtu or 1420, 'up')

    def up_openvpn(self, plan: Plan) -> tuple[list[str], list[str]]:
        config = self.run_dir / OPENVPN_CONFIG_FILE
        write_private(config, plan.openvpn_text)
        up_file = self.run_dir / OPENVPN_UP_FILE
        up_file.unlink(missing_ok=True)
        hook = f'{sys.executable} {pathlib.Path(__file__).resolve()} openvpn-up --run-dir {self.run_dir}'
        cmd = ['openvpn', '--config', str(config), '--dev', TUNNEL_INTERFACE, '--dev-type', 'tun',
               '--disable-dco', '--route-noexec', '--persist-tun', '--persist-key', '--auth-nocache',
               '--script-security', '2', '--up', hook, '--verb', '3']
        if plan.auth_path:
            cmd.extend(['--auth-user-pass', str(plan.auth_path)])
        # OpenVPN logs to this program's output (the journal, or `docker logs`).
        self.openvpn = subprocess.Popen(cmd)
        deadline = time.monotonic() + OPENVPN_CONNECT_SECONDS
        while time.monotonic() < deadline:
            if self.openvpn.poll() is not None:
                raise TunnelError(f'OpenVPN exited ({self.openvpn.returncode}); see its log for why')
            if up_file.is_file():
                data = json.loads(up_file.read_text())
                return data.get('addresses') or [], data.get('dns') or []
            time.sleep(1)
        raise TunnelError(f'OpenVPN did not connect within {OPENVPN_CONNECT_SECONDS} seconds')

    def down(self):
        """Take the tunnel down and close the kill switch to everything."""
        if self.openvpn:
            self.openvpn.terminate()
            try:
                self.openvpn.wait(10)
            except subprocess.TimeoutExpired:
                self.openvpn.kill()
                self.openvpn.wait()
            self.openvpn = None
        if self.plan or self.routes:
            run_quietly('ip', 'link', 'del', TUNNEL_INTERFACE)
            for family, destination in self.routes:
                run_quietly('ip', family, 'route', 'del', destination)
        self.routes = []
        self.plan = None
        self.addresses, self.dns = [], []
        if self.uplink:
            self.lock_down()

    def connected(self) -> bool:
        if not self.alive():
            return False
        if self.plan.kind == 'openvpn':
            return True
        result = subprocess.run(['wg', 'show', TUNNEL_INTERFACE, 'latest-handshakes'], capture_output=True,
                                text=True)
        handshakes = [int(line.split()[1]) for line in result.stdout.splitlines() if len(line.split()) == 2]
        return any(time.time() - h < HANDSHAKE_FRESH_SECONDS for h in handshakes if h)

    def check_public_ip(self):
        url = self.plan.settings.get('public_ip_url')
        if not url or time.monotonic() - self.public_ip_checked < PUBLIC_IP_SECONDS:
            return
        self.public_ip_checked = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                self.public_ip = response.read(64).decode().strip() or None
        except (OSError, ValueError) as e:
            logger.warning('Could not read the public address through the VPN: %s', e)
            self.public_ip = None

    def report(self):
        # Traffic through the tunnel also makes WireGuard handshake, so check before asking if it connected.
        self.check_public_ip()
        connected = self.connected()
        if not connected:
            # Look again soon after a handshake.
            self.public_ip_checked = 0.0
        settings = self.plan.settings
        warnings = []
        if not self.dns:
            warnings.append('The VPN gave no DNS server, so torrents cannot look up names')
        self.write_status(
            'connected' if connected else 'connecting',
            kind=self.plan.kind,
            addresses=self.addresses,
            dns=self.dns,
            endpoints=[dataclasses.asdict(e) for e in self.plan.endpoints],
            public_ip=self.public_ip if connected else None,
            forwarded_port=settings.get('forwarded_port') if settings.get('port_forwarding') == 'fixed' else None,
            warnings=warnings,
        )

    def write_status(self, state: str, **fields):
        status = {'state': state, 'interface': TUNNEL_INTERFACE, 'updated_at': time.time(), 'kind': None,
                  'addresses': [], 'dns': [], 'endpoints': [], 'public_ip': None, 'forwarded_port': None,
                  'warnings': [], 'error': None, **fields}
        write_json(self.run_dir / STATUS_FILE, status)

    def run_forever(self):
        self.start()
        try:
            while True:
                self.step()
                time.sleep(LOOP_SECONDS)
        finally:
            self.down()
            self.write_status('stopped')


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    run_parser = sub.add_parser('run', help='Keep the tunnel as controller.yaml asks, until stopped')
    run_parser.add_argument('--resolv-conf', type=pathlib.Path, required=True,
                            help="The namespace's resolv.conf, which gets the VPN's DNS servers")
    run_parser.add_argument('--run-dir', type=pathlib.Path, default=RUN_DIR)
    up_parser = sub.add_parser('openvpn-up', help="OpenVPN's --up hook")
    up_parser.add_argument('--run-dir', type=pathlib.Path, default=RUN_DIR)
    # OpenVPN appends the device, MTUs and addresses; the hook reads its environment instead.
    args, _ = parser.parse_known_args(argv)

    if args.command == 'openvpn-up':
        openvpn_up_hook(args.run_dir)
        return

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    Tunnel(get_media_directory(), args.run_dir, args.resolv_conf).run_forever()


if __name__ == '__main__':
    main()
