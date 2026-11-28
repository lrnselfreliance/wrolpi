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
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
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
    # How peers reach this WROLPi through the VPN: none; a port the provider forwards (fixed); or a port the tunnel
    # asks the VPN for with NAT-PMP (natpmp, e.g. Proton's P2P servers).
    'port_forwarding': 'none',
    'forwarded_port': None,
    # Where NAT-PMP asks for the port.  None: OpenVPN's pushed gateway, else the VPN's first IPv4 DNS server (Proton).
    'natpmp_gateway': None,
    # Fetched through the tunnel to show the address peers see.  None disables the check.
    'public_ip_url': 'https://api.ipify.org',
}
PORT_FORWARDING_MODES = ('none', 'fixed', 'natpmp')

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


def check_public_ip_url(url: str):
    """Only a web address: urllib would also read a `file:` URL, as root."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise VPNConfigError('The public address check must be an http:// or https:// URL')


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
#
# A provider's .ovpn is read with an allowlist.  OpenVPN options can run commands (up, iproute, plugin, engine...),
# read or write files as root (log, status, askpass...), or send the VPN's own traffic around the kill switch
# (http-proxy).  The tunnel keeps only the client options below, drops those providers commonly ship which the tunnel
# replaces or which do nothing on Linux, and refuses anything else by name.  OpenVPN also always runs with
# `--script-security 1` given after the config, so no script runs even if one got through.

OPENVPN_ALLOWED = {
    'allow-compression', 'auth', 'auth-nocache', 'auth-retry', 'bind', 'cipher', 'client', 'comp-lzo', 'compress',
    'connect-retry', 'connect-retry-max', 'connect-timeout', 'data-ciphers', 'data-ciphers-fallback', 'dhcp-option',
    'disable-occ', 'explicit-exit-notify', 'fast-io', 'float', 'fragment', 'hand-window', 'ifconfig-nowarn',
    'inactive', 'keepalive', 'key-direction', 'key-method', 'link-mtu', 'lport', 'mssfix', 'mtu-disc', 'mute',
    'mute-replay-warnings', 'ncp-ciphers', 'ncp-disable', 'nobind', 'ns-cert-type', 'persist-key',
    'persist-remote-ip', 'persist-tun', 'ping', 'ping-exit', 'ping-restart', 'ping-timer-rem', 'port', 'proto', 'pull',
    'pull-filter', 'push-peer-info', 'rcvbuf', 'redirect-gateway', 'remote', 'remote-cert-eku', 'remote-cert-ku',
    'remote-cert-tls', 'remote-random', 'remote-random-hostname', 'reneg-bytes', 'reneg-pkts', 'reneg-sec',
    'replay-window', 'resolv-retry', 'route', 'route-delay', 'route-ipv6', 'route-nopull', 'rport',
    'server-poll-timeout', 'setenv', 'sndbuf', 'static-challenge', 'tls-cipher', 'tls-ciphersuites', 'tls-client',
    'tls-groups', 'tls-timeout', 'tls-version-max', 'tls-version-min', 'tran-window', 'tun-ipv6', 'tun-mtu',
    'tun-mtu-extra', 'txqueuelen', 'verify-x509-name',
    # Key material, only accepted inline (<ca>...</ca>); a path would read any file on the WROLPi.
    'ca', 'cert', 'crl-verify', 'extra-certs', 'key', 'pkcs12', 'tls-auth', 'tls-crypt', 'tls-crypt-v2',
}
OPENVPN_INLINE_ONLY = {'ca', 'cert', 'crl-verify', 'extra-certs', 'key', 'pkcs12', 'tls-auth', 'tls-crypt',
                       'tls-crypt-v2'}
OPENVPN_INLINE_TAGS = OPENVPN_INLINE_ONLY | {'connection'}
# Common in providers' configs, and replaced by the tunnel (the device, the login, logging) or Windows-only.  Scripts
# are dropped, not run: the tunnel sets DNS itself.
OPENVPN_DROPPED = {
    'auth-user-pass', 'block-outside-dns', 'daemon', 'dev', 'dev-node', 'dev-type', 'dhcp-release', 'dhcp-renew',
    'down', 'down-pre', 'group', 'ip-win32', 'log', 'log-append', 'register-dns', 'route-method', 'route-noexec',
    'route-up', 'route-pre-down', 'script-security', 'status', 'tap-sleep', 'up', 'up-delay', 'up-restart', 'user',
    'verb', 'win-sys', 'writepid',
}
# OpenVPN prints this once the tunnel is up, and the server's pushed options (DNS) before it.
OPENVPN_CONNECTED = 'Initialization Sequence Completed'


# Options whose arguments providers quote (e.g. `pull-filter ignore "route-ipv6"`), and which cannot run anything.
OPENVPN_QUOTED_ARGS = {'pull-filter', 'static-challenge', 'verify-x509-name'}
OPENVPN_QUOTES = ('"', "'", '\\')


def _openvpn_directive(line: str) -> tuple[str, list[str]]:
    tokens = line.split()
    name = tokens[0]
    # OpenVPN un-quotes and un-escapes every word, so `"up"` is `up`, and `setenv "opt" up` is `setenv opt up`.
    # Quotes are only allowed in the arguments of options which are harmless whatever they say.
    if any(c in name for c in OPENVPN_QUOTES) or '\0' in line:
        raise VPNConfigError(f'Cannot read the OpenVPN option {name!r}')
    name = name[2:] if name.startswith('--') else name
    if name not in OPENVPN_QUOTED_ARGS and any(c in line for c in OPENVPN_QUOTES):
        raise VPNConfigError(f'Quotes are not supported in the OpenVPN option {name}')
    if name == 'setenv' and tokens[1:2] and tokens[1].lower() == 'opt':
        # `setenv opt X` applies the option X; it is judged as X.
        return _openvpn_directive(' '.join(tokens[2:])) if len(tokens) > 2 else ('setenv', [])
    return name, tokens[1:]


def _openvpn_lines(text: str):
    """Yield (line, directive, args, in_connection) for each line; directive is None for comments, blank lines and
    inline data (e.g. <ca>...</ca>), which are passed through unchanged.  Raises VPNConfigError for any option or
    inline block the tunnel does not allow."""
    # A block of inline data is never checked, so it must never be open while OpenVPN reads options: it opens only on
    # an exact allowed tag, and closes on any line which starts with its closing tag (however OpenVPN reads that line).
    inline = None
    in_connection = False
    for line in text.splitlines():
        stripped = line.strip()
        if inline:
            close = f'</{inline}>'
            if stripped.lower().startswith(close):
                if stripped[len(close):].strip():
                    raise VPNConfigError(f'Cannot read the OpenVPN line {stripped!r}')
                inline = None
            yield line, None, [], in_connection
            continue
        if stripped.startswith('<') and stripped.endswith('>'):
            tag = stripped[1:-1].strip()
            if tag == 'connection':
                in_connection = True
            elif tag == '/connection':
                in_connection = False
            elif tag in OPENVPN_INLINE_TAGS:
                inline = tag
            else:
                raise VPNConfigError(f'OpenVPN configs with an inline <{tag}> are not supported')
            yield line, None, [], in_connection
            continue
        if not stripped or stripped[0] in '#;':
            yield line, None, [], in_connection
            continue
        directive, args = _openvpn_directive(stripped)
        if directive in ('http-proxy', 'socks-proxy'):
            raise VPNConfigError(f'OpenVPN configs which use {directive} are not supported')
        if directive in ('dev', 'dev-type') and args and args[0].startswith('tap'):
            raise VPNConfigError('TAP VPNs are not supported; use a TUN config')
        if directive in OPENVPN_INLINE_ONLY and args and args[0] != '[inline]':
            raise VPNConfigError(f'The OpenVPN {directive} must be inside the config (<{directive}>...'
                                 f'</{directive}>), not in another file')
        if directive not in OPENVPN_ALLOWED and directive not in OPENVPN_DROPPED:
            raise VPNConfigError(f'The OpenVPN option {directive} is not supported')
        yield line, directive, args, in_connection
    if inline or in_connection:
        raise VPNConfigError(f'The OpenVPN config ends inside <{inline or "connection"}>')


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
    # Set by the config itself; servers usually push theirs.
    dns: list[str]


def parse_openvpn(text: str) -> OpenVPNConfig:
    # OpenVPN reads every option before it connects, so `proto`/`port` apply to a `remote` written above them.  A
    # <connection> block's own `proto`/`port` apply only to the `remote` in that block.
    defaults = {'proto': 'udp', 'port': 1194}
    blocks = []
    pending = []  # (host, port or None, proto or None, its <connection> block or None)
    wants_auth = False
    dns = []
    was_in_connection = False
    for _, directive, args, in_connection in _openvpn_lines(text):
        if in_connection and not was_in_connection:
            blocks.append({})
        was_in_connection = in_connection
        if directive is None:
            continue
        scope = blocks[-1] if in_connection else defaults
        if directive == 'auth-user-pass':
            wants_auth = True
        elif directive == 'dhcp-option' and len(args) >= 2 and args[0].upper() in ('DNS', 'DNS6') and is_ip(args[1]):
            dns.append(args[1])
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
    return OpenVPNConfig(text, remotes, wants_auth, dns)


def sanitize_openvpn(config: OpenVPNConfig, hosts: dict[str, list[str]]) -> str:
    """The config the tunnel runs: only allowed options, and each `remote` names an address (one line per address) so
    OpenVPN never needs DNS behind the kill switch."""
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


def pushed_gateway(line: str) -> str | None:
    """The VPN's gateway in OpenVPN's log of the server's PUSH_REPLY (`route-gateway 10.8.0.1`)."""
    if 'PUSH_REPLY' not in line:
        return None
    for option in line.split('PUSH_REPLY', 1)[1].split(','):
        parts = option.split()
        if len(parts) >= 2 and parts[0] == 'route-gateway' and is_ip(parts[1]):
            return parts[1]
    return None


def pushed_dns(line: str) -> list[str]:
    """The DNS servers in OpenVPN's log of the server's PUSH_REPLY, e.g.
    `PUSH: Received control message: 'PUSH_REPLY,route-gateway 10.8.0.1,dhcp-option DNS 10.8.0.1,...'`."""
    if 'PUSH_REPLY' not in line:
        return []
    dns = []
    for option in line.split('PUSH_REPLY', 1)[1].strip(" ,'\"\n").split(','):
        parts = option.split()
        if len(parts) >= 3 and parts[0] == 'dhcp-option' and parts[1].upper() in ('DNS', 'DNS6'):
            candidates = [parts[2]]
        elif len(parts) >= 5 and parts[:2] == ['dns', 'server'] and parts[3] == 'address':
            # OpenVPN 2.6: `dns server 0 address 10.8.0.1 [::1]:53`
            candidates = [a[1:a.index(']')] if a.startswith('[') else a.split(':')[0] if a.count(':') == 1 else a
                          for a in parts[4:]]
        else:
            continue
        dns.extend(c for c in candidates if is_ip(c) and c not in dns)
    return dns


class OpenVPNProcess:
    """OpenVPN, with its log read for the moment it connects and the DNS servers it is given (no `--up` script, so
    OpenVPN never needs permission to run one)."""

    def __init__(self, cmd: list[str]):
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        errors='replace')
        self.connected = threading.Event()
        self.dns: list[str] = []
        self.gateway: str | None = None
        threading.Thread(target=self._read_log, daemon=True).start()

    def _read_log(self):
        for line in self.process.stdout:
            # OpenVPN's log still reaches the journal (or `docker logs`).
            sys.stdout.write(line)
            self.dns.extend(d for d in pushed_dns(line) if d not in self.dns)
            self.gateway = pushed_gateway(line) or self.gateway
            if OPENVPN_CONNECTED in line:
                self.connected.set()

    def poll(self):
        return self.process.poll()

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


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


# --- NAT-PMP (RFC 6886) ---
#
# How a VPN (e.g. Proton) forwards a port: the tunnel asks the VPN's gateway for a mapping, and must ask again before
# the mapping's lifetime ends.  Peers then reach the forwarded port on the VPN's public address.

NATPMP_PORT = 5351
# Proton grants 60 seconds; a mapping is renewed at half its lifetime.
NATPMP_LIFETIME = 60
NATPMP_RESULTS = {1: 'unsupported version', 2: 'not authorized (port forwarding is off for this server or plan)',
                  3: 'network failure', 4: 'out of resources', 5: 'unsupported request'}


class NATPMPError(Exception):
    """The VPN did not forward a port.  The message is shown to the user."""


def natpmp_request(gateway: str, request: bytes, timeout: float = 1.0, tries: int = 3) -> bytes:
    """Send a NAT-PMP request, retrying with a doubling timeout, and return the reply to it."""
    expected_op = request[1] + 128
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((gateway, NATPMP_PORT))
        for attempt in range(tries):
            sock.send(request)
            sock.settimeout(timeout * 2 ** attempt)
            try:
                while True:
                    reply = sock.recv(64)
                    # Ignore anything which is not the answer to this request (e.g. a late answer to a retry).
                    if len(reply) >= 4 and reply[0] == 0 and reply[1] == expected_op:
                        break
            except (socket.timeout, ConnectionRefusedError):
                continue
            result = struct.unpack('!H', reply[2:4])[0]
            if result:
                raise NATPMPError(f'The VPN refused to forward a port: {NATPMP_RESULTS.get(result, result)}')
            return reply
    raise NATPMPError(f'The VPN ({gateway}) did not answer a port forwarding request.  It may not forward ports '
                      f'(for Proton, use a P2P server, and a config made with NAT-PMP on).')


def natpmp_map(gateway: str, proto: str, lifetime: int = NATPMP_LIFETIME) -> tuple[int, int]:
    """Ask the VPN to forward a port of its choosing; returns (port, lifetime granted).  As Proton documents
    (`natpmpc -a 1 0 udp 60`), the request names no ports, and the tunnel listens on the port it is given."""
    op = 1 if proto == 'udp' else 2
    reply = natpmp_request(gateway, struct.pack('!BBHHHI', 0, op, 0, 0, 1, lifetime))
    if len(reply) < 16:
        raise NATPMPError('The VPN sent a broken port forwarding reply')
    *_, port, granted = struct.unpack('!BBHIHHI', reply[:16])
    if not port:
        raise NATPMPError('The VPN forwarded no port')
    return port, granted


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


def interface_addresses(interface: str) -> list[str]:
    """The global addresses of an interface, e.g. ['10.8.0.6/24']."""
    addresses = []
    for entry in json.loads(run('ip', '-j', 'addr', 'show', 'dev', interface).stdout or '[]'):
        for address in entry.get('addr_info', []):
            if address.get('scope') == 'global':
                addresses.append(f"{address['local']}/{address['prefixlen']}")
    return addresses


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
    openvpn_dns: list[str] = dataclasses.field(default_factory=list)


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
        plan_kwargs = {'openvpn_text': sanitize_openvpn(openvpn, hosts), 'openvpn_dns': openvpn.dns}
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
        self.openvpn: OpenVPNProcess | None = None
        # (family flag, destination) of each route to a VPN server.
        self.routes: list[tuple[str, str]] = []
        self.addresses: list[str] = []
        self.dns: list[str] = []
        self.locked_down = False
        self.public_ip = None
        self.public_ip_checked = 0.0
        self.reset_port_forwarding()

    def reset_port_forwarding(self):
        self.forwarded_port: int | None = None
        self.port_forwarding_error: str | None = None
        self.port_forwarding_renewed = 0.0
        self.port_forwarding_lifetime = 0

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
        self.reset_port_forwarding()
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
        # Given after --config, so these win over anything in it.  `--script-security 1` lets OpenVPN run only `ip`,
        # never a script.
        cmd = ['openvpn', '--config', str(config), '--script-security', '1', '--dev', TUNNEL_INTERFACE,
               '--dev-type', 'tun', '--disable-dco', '--route-noexec', '--persist-tun', '--persist-key',
               '--auth-nocache', '--verb', '3']
        if plan.auth_path:
            cmd.extend(['--auth-user-pass', str(plan.auth_path)])
        self.openvpn = OpenVPNProcess(cmd)
        deadline = time.monotonic() + OPENVPN_CONNECT_SECONDS
        while not self.openvpn.connected.wait(1):
            if self.openvpn.poll() is not None:
                raise TunnelError(f'OpenVPN exited ({self.openvpn.poll()}); see its log for why')
            if time.monotonic() > deadline:
                raise TunnelError(f'OpenVPN did not connect within {OPENVPN_CONNECT_SECONDS} seconds')
        return interface_addresses(TUNNEL_INTERFACE), list(dict.fromkeys(self.openvpn.dns + plan.openvpn_dns))

    def down(self):
        """Take the tunnel down and close the kill switch to everything."""
        if self.openvpn:
            self.openvpn.stop()
            self.openvpn = None
        if self.plan or self.routes:
            run_quietly('ip', 'link', 'del', TUNNEL_INTERFACE)
            for family, destination in self.routes:
                run_quietly('ip', family, 'route', 'del', destination)
        self.routes = []
        self.plan = None
        self.addresses, self.dns = [], []
        # The VPN drops a mapping which is not renewed.
        self.reset_port_forwarding()
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
        self.public_ip = None
        try:
            check_public_ip_url(url)  # Also when controller.yaml was edited by hand.
            with urllib.request.urlopen(url, timeout=10) as response:
                reply = response.read(64).decode(errors='replace').strip()
        except (OSError, ValueError) as e:
            logger.warning('Could not read the public address through the VPN: %s', e)
            return
        if is_ip(reply):
            self.public_ip = reply
        else:
            logger.warning('The public address check did not answer with an address')

    def natpmp_gateway(self) -> str | None:
        if gateway := self.plan.settings.get('natpmp_gateway'):
            return gateway
        if self.openvpn and self.openvpn.gateway:
            return self.openvpn.gateway
        return next((d for d in self.dns if ip_version(d) == 4), None)

    def renew_port_forwarding(self):
        """Ask the VPN for a forwarded port, again at half the lifetime it granted."""
        if self.forwarded_port and \
                time.monotonic() - self.port_forwarding_renewed < self.port_forwarding_lifetime / 2:
            return
        gateway = self.natpmp_gateway()
        if not gateway:
            self.forwarded_port = None
            self.port_forwarding_error = 'Port forwarding needs the VPN gateway; set natpmp_gateway in controller.yaml'
            return
        try:
            udp_port, udp_lifetime = natpmp_map(gateway, 'udp')
            tcp_port, tcp_lifetime = natpmp_map(gateway, 'tcp')
        except (NATPMPError, OSError) as e:
            if self.forwarded_port:
                logger.warning('The VPN stopped forwarding port %s: %s', self.forwarded_port, e)
            self.forwarded_port = None
            self.port_forwarding_error = str(e)
            return
        if udp_port != tcp_port:
            # Torrents listen on one port for both; TCP carries most peer connections.
            logger.warning('The VPN forwarded UDP port %s and TCP port %s; using %s', udp_port, tcp_port, tcp_port)
        if tcp_port != self.forwarded_port:
            logger.info('The VPN forwards port %s', tcp_port)
        self.forwarded_port = tcp_port
        self.port_forwarding_error = None
        self.port_forwarding_renewed = time.monotonic()
        self.port_forwarding_lifetime = min(udp_lifetime, tcp_lifetime) or NATPMP_LIFETIME

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
        forwarded_port = None
        if settings.get('port_forwarding') == 'fixed':
            forwarded_port = settings.get('forwarded_port')
        elif settings.get('port_forwarding') == 'natpmp' and connected:
            self.renew_port_forwarding()
            forwarded_port = self.forwarded_port
            if self.port_forwarding_error:
                warnings.append(self.port_forwarding_error)
        self.write_status(
            'connected' if connected else 'connecting',
            kind=self.plan.kind,
            addresses=self.addresses,
            dns=self.dns,
            endpoints=[dataclasses.asdict(e) for e in self.plan.endpoints],
            public_ip=self.public_ip if connected else None,
            forwarded_port=forwarded_port,
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
    args = parser.parse_args(argv)

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    Tunnel(get_media_directory(), args.run_dir, args.resolv_conf).run_forever()


if __name__ == '__main__':
    main()
