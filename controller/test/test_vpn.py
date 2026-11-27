"""
Tests for the Controller's VPN settings, server lookups, status, and API.
"""
import json
import stat
import time
from pathlib import Path
from unittest import mock

import pytest
import yaml

from controller.lib import vpn
from controller.vpn import tunnel
from controller.vpn.tunnel import VPNConfigError

WIREGUARD = """\
[Interface]
PrivateKey = cHJpdmF0ZWtleXByaXZhdGVrZXlwcml2YXRla2V5cHI=
Address = 10.2.0.2/32
DNS = 10.2.0.1

[Peer]
PublicKey = cHVibGlja2V5cHVibGlja2V5cHVibGlja2V5cHVibGk=
AllowedIPs = 0.0.0.0/0
Endpoint = vpn.example.com:51820
"""

OPENVPN = """\
client
remote 198.51.100.7 1194
auth-user-pass
"""


@pytest.fixture
def drive(test_directory, mock_config_path, reset_runtime_config, monkeypatch) -> Path:
    """A mounted drive: controller.yaml and the VPN files share one config directory, as on a WROLPi."""
    monkeypatch.setenv('MEDIA_DIRECTORY', str(test_directory))
    return test_directory / 'config'


@pytest.fixture
def resolver():
    with mock.patch.object(tunnel, 'resolve_host', return_value=['203.0.113.5']) as resolve_host:
        yield resolve_host


def saved_vpn_settings(drive: Path) -> dict:
    return yaml.safe_load((drive / 'controller.yaml').read_text())['vpn']


class TestSaveConfig:

    def test_wireguard(self, drive, resolver):
        response = vpn.save_vpn_config('proton-US-1.conf', WIREGUARD)
        assert response['kind'] == 'wireguard'
        assert response['servers'] == ['vpn.example.com']
        assert response['enabled'] is False

        path = drive / vpn.WIREGUARD_CONFIG
        assert path.read_text() == WIREGUARD
        # It holds a private key.
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        # The tunnel reads the same key the Controller saved.
        assert saved_vpn_settings(drive)['config_file'] == vpn.WIREGUARD_CONFIG
        assert tunnel.load_settings(drive.parent)['config_file'] == vpn.WIREGUARD_CONFIG

        # The server's name is looked up for the tunnel, which cannot use DNS until it is up.
        endpoints = json.loads((tunnel.RUN_DIR / tunnel.ENDPOINTS_FILE).read_text())
        assert endpoints['hosts'] == {'vpn.example.com': ['203.0.113.5']}
        assert endpoints['config_sha256'] == tunnel.config_sha256(WIREGUARD)

    def test_replaces_the_other_kind(self, drive, resolver):
        vpn.save_vpn_config('a.conf', WIREGUARD)
        response = vpn.save_vpn_config('b.ovpn', OPENVPN)
        assert response['kind'] == 'openvpn'
        assert response['needs_auth'] is True
        assert response['has_auth'] is False
        assert not (drive / vpn.WIREGUARD_CONFIG).exists()
        assert saved_vpn_settings(drive)['config_file'] == vpn.OPENVPN_CONFIG

    @pytest.mark.parametrize('filename,content,message', [
        ('vpn.txt', WIREGUARD, '.conf'),
        ('vpn.conf', '[Interface]\n', 'PrivateKey'),
        ('vpn.ovpn', 'client\n', 'no remote'),
        ('vpn.conf', 'x' * (vpn.MAX_CONFIG_BYTES + 1), 'too large'),
    ])
    def test_invalid_config_is_not_saved(self, drive, resolver, filename, content, message):
        with pytest.raises(VPNConfigError, match=message):
            vpn.save_vpn_config(filename, content)
        assert not (drive / 'vpn').exists()

    def test_lookup_failure_does_not_stop_saving(self, drive):
        with mock.patch.object(tunnel, 'resolve_host', side_effect=__import__('socket').gaierror('no Internet')):
            response = vpn.save_vpn_config('a.conf', WIREGUARD)
        assert response['kind'] == 'wireguard'
        assert vpn.endpoints_need_resolving() is False  # The VPN is off.


class TestSettings:

    def test_enable_needs_a_config(self, drive):
        with pytest.raises(VPNConfigError, match='Upload a VPN config'):
            vpn.update_vpn_settings(enabled=True)

    def test_enable(self, drive, resolver):
        vpn.save_vpn_config('a.conf', WIREGUARD)
        assert vpn.update_vpn_settings(enabled=True)['enabled'] is True
        assert saved_vpn_settings(drive)['enabled'] is True

    def test_openvpn_needs_its_login_before_enabling(self, drive, resolver):
        vpn.save_vpn_config('a.ovpn', OPENVPN)
        with pytest.raises(VPNConfigError, match='username and password'):
            vpn.update_vpn_settings(enabled=True)
        response = vpn.save_openvpn_auth('user', 'secret')
        assert response['has_auth'] is True
        auth = drive / vpn.OPENVPN_AUTH
        assert auth.read_text() == 'user\nsecret\n'
        assert stat.S_IMODE(auth.stat().st_mode) == 0o600
        assert vpn.update_vpn_settings(enabled=True)['enabled'] is True

    @pytest.mark.parametrize('username,password', [('', 'p'), ('u', ''), ('u\nx', 'p'), ('u', 'p\r')])
    def test_invalid_login(self, drive, username, password):
        with pytest.raises(VPNConfigError):
            vpn.save_openvpn_auth(username, password)

    def test_port_forwarding(self, drive):
        with pytest.raises(VPNConfigError, match='Enter the port'):
            vpn.update_vpn_settings(port_forwarding='fixed')
        with pytest.raises(VPNConfigError, match='between 1 and 65535'):
            vpn.update_vpn_settings(port_forwarding='fixed', forwarded_port=70000)
        with pytest.raises(VPNConfigError, match='must be one of'):
            vpn.update_vpn_settings(port_forwarding='upnp')
        response = vpn.update_vpn_settings(port_forwarding='fixed', forwarded_port=51413)
        assert (response['port_forwarding'], response['forwarded_port']) == ('fixed', 51413)
        # Only differences from the defaults are saved.
        assert saved_vpn_settings(drive) == {'port_forwarding': 'fixed', 'forwarded_port': 51413}

    def test_natpmp(self, drive):
        response = vpn.update_vpn_settings(port_forwarding='natpmp')
        assert response['port_forwarding'] == 'natpmp'
        with pytest.raises(VPNConfigError, match='IPv4'):
            vpn.update_vpn_settings(natpmp_gateway='vpn.example.com')
        with pytest.raises(VPNConfigError, match='IPv4'):
            vpn.update_vpn_settings(natpmp_gateway='fd00::1')
        assert vpn.update_vpn_settings(natpmp_gateway='10.64.0.1')['natpmp_gateway'] == '10.64.0.1'
        assert vpn.update_vpn_settings(natpmp_gateway='')['natpmp_gateway'] is None

    @pytest.mark.parametrize('url', ['file:///etc/shadow', 'ftp://example.com/', 'https://', 'example.com'])
    def test_public_ip_url_must_be_a_web_address(self, drive, url):
        with pytest.raises(VPNConfigError, match='http'):
            vpn.update_vpn_settings(public_ip_url=url)
        # Empty turns the check off.
        assert vpn.update_vpn_settings(public_ip_url='')['public_ip_url'] is None

    def test_delete(self, drive, resolver):
        vpn.save_vpn_config('a.ovpn', OPENVPN)
        vpn.save_openvpn_auth('user', 'secret')
        vpn.update_vpn_settings(enabled=True)
        response = vpn.delete_vpn_config()
        assert response['enabled'] is False
        assert response['kind'] is None
        assert not (drive / vpn.OPENVPN_CONFIG).exists()
        assert not (drive / vpn.OPENVPN_AUTH).exists()


class TestEndpoints:

    def test_need_resolving(self, drive, resolver):
        vpn.save_vpn_config('a.conf', WIREGUARD)
        vpn.update_vpn_settings(enabled=True)
        assert vpn.endpoints_need_resolving() is False

        # Old lookups are refreshed in case the provider moved a server.
        path = tunnel.RUN_DIR / tunnel.ENDPOINTS_FILE
        data = json.loads(path.read_text())
        data['resolved_at'] = time.time() - vpn.ENDPOINTS_MAX_AGE - 1
        path.write_text(json.dumps(data))
        assert vpn.endpoints_need_resolving() is True

        # A lookup which failed (e.g. no Internet at boot) is tried again.
        data['resolved_at'], data['hosts'] = time.time(), {}
        path.write_text(json.dumps(data))
        assert vpn.endpoints_need_resolving() is True

        path.unlink()
        assert vpn.endpoints_need_resolving() is True

    def test_addresses_need_no_lookup(self, drive, resolver):
        vpn.save_vpn_config('a.ovpn', 'remote 198.51.100.7 1194\n')
        assert vpn.resolve_endpoints() == {}
        resolver.assert_not_called()


class TestStatus:

    def test_stopped_without_status(self, drive):
        assert vpn.get_vpn_status()['state'] == 'stopped'

    def test_reports_the_tunnels_status(self, drive):
        tunnel.write_json(tunnel.RUN_DIR / tunnel.STATUS_FILE, {
            'state': 'connected', 'kind': 'wireguard', 'interface': 'vpn0', 'public_ip': '203.0.113.99',
            'forwarded_port': 51413, 'updated_at': time.time()})
        status = vpn.get_vpn_status()
        assert (status['state'], status['public_ip'], status['forwarded_port']) == ('connected', '203.0.113.99', 51413)

    def test_stale_status_is_stopped(self, drive):
        tunnel.write_json(tunnel.RUN_DIR / tunnel.STATUS_FILE, {
            'state': 'connected', 'public_ip': '203.0.113.99',
            'updated_at': time.time() - vpn.STALE_STATUS_SECONDS - 1})
        status = vpn.get_vpn_status()
        assert status['state'] == 'stopped'
        assert status['public_ip'] is None


class TestAPI:

    def test_status(self, test_client):
        response = test_client.get('/api/vpn/status')
        assert response.status_code == 200
        assert response.json()['state'] == 'stopped'

    def test_upload_and_enable(self, test_client, drive, resolver):
        response = test_client.post('/api/vpn/config', json={'filename': 'a.conf', 'content': WIREGUARD})
        assert response.status_code == 200, response.text
        assert response.json()['kind'] == 'wireguard'

        response = test_client.post('/api/vpn/settings', json={'enabled': True})
        assert response.status_code == 200, response.text
        assert test_client.get('/api/vpn/settings').json()['enabled'] is True

        response = test_client.delete('/api/vpn/config')
        assert response.status_code == 200
        assert response.json()['enabled'] is False

    def test_refusals_are_400(self, test_client, drive):
        response = test_client.post('/api/vpn/config', json={'filename': 'a.conf', 'content': 'nope'})
        assert response.status_code == 400
        response = test_client.post('/api/vpn/settings', json={'port_forwarding': 'fixed'})
        assert response.status_code == 400
        assert 'Enter the port' in response.json()['detail']
        response = test_client.post('/api/vpn/auth', json={'username': '', 'password': ''})
        assert response.status_code == 400

    def test_unmounted_drive_is_409(self, test_client, resolver):
        # controller.yaml cannot be saved until the drive is mounted.
        with mock.patch('controller.lib.config.CONFIG_PATH_ON_DRIVE', Path('/nonexistent/config/controller.yaml')):
            response = test_client.post('/api/vpn/settings', json={'port_forwarding': 'none'})
        assert response.status_code == 409
