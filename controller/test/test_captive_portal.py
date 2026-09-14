"""
Tests for the hotspot captive portal: dnsmasq include, landing page, and probe redirects.
"""
import json
import subprocess
from unittest import mock

import pytest

from controller.lib import captive_portal
from controller.lib.captive_portal import (
    DEFAULT_HOTSPOT_IP,
    FRIENDLY_NAME,
    PROBE_HOSTS,
    PROBE_PATHS,
    apply_dnsmasq_config,
    dnsmasq_config_ip,
    get_hotspot_ip,
    is_captive_portal_enabled,
    render_dnsmasq_config,
)

IP_JSON = json.dumps([{
    "ifname": "wlan0",
    "addr_info": [{"family": "inet", "local": "10.42.0.1", "prefixlen": 24}],
}])


@pytest.fixture
def native_mode():
    with mock.patch("controller.lib.captive_portal.is_docker_mode", return_value=False):
        yield


class TestRenderDnsmasqConfig:

    def test_every_probe_host_and_friendly_name(self):
        """Each probe hostname and `wrolpi` resolve to the given IP."""
        config = render_dnsmasq_config('10.42.0.1')
        for host in PROBE_HOSTS:
            assert f'address=/{host}/10.42.0.1' in config
        assert f'address=/{FRIENDLY_NAME}/10.42.0.1' in config

    def test_probe_hosts_are_never_forwarded(self):
        """iOS asks for the HTTPS record type too; a forwarded answer leads it to the real Apple."""
        config = render_dnsmasq_config('10.42.0.1')
        for host in (*PROBE_HOSTS, FRIENDLY_NAME):
            assert f'local=/{host}/' in config

    def test_apple_cdn_alias_is_a_probe_host(self):
        assert 'captive.g.aaplimg.com' in PROBE_HOSTS

    def test_no_wildcard(self):
        """A wildcard would break the hotspot's Internet passthrough."""
        assert '/#/' not in render_dnsmasq_config('10.42.0.1')

    def test_uses_given_ip(self):
        config = render_dnsmasq_config('10.42.1.1')
        assert '10.42.1.1' in config
        assert '10.42.0.1' not in config


class TestApplyDnsmasqConfig:

    def test_enabled_writes_file(self, native_mode, reset_runtime_config, tmp_path):
        include = tmp_path / 'shared.d' / 'portal.conf'
        with mock.patch.object(captive_portal, 'INCLUDE_FILE', include):
            assert apply_dnsmasq_config('10.42.0.1') is True
            assert include.read_text() == render_dnsmasq_config('10.42.0.1')
            assert include.stat().st_mode & 0o777 == 0o644
            assert dnsmasq_config_ip() == '10.42.0.1'

    def test_disabled_removes_stale_file(self, native_mode, reset_runtime_config, tmp_path):
        include = tmp_path / 'portal.conf'
        include.write_text('address=/captive.apple.com/10.42.0.1\n')
        with mock.patch.object(captive_portal, 'INCLUDE_FILE', include), \
                mock.patch("controller.lib.captive_portal.get_config_value", return_value=False):
            assert apply_dnsmasq_config('10.42.0.1') is True
            assert not include.exists()
            assert dnsmasq_config_ip() is None

    def test_disabled_without_file_is_fine(self, native_mode, reset_runtime_config, tmp_path):
        include = tmp_path / 'portal.conf'
        with mock.patch.object(captive_portal, 'INCLUDE_FILE', include), \
                mock.patch("controller.lib.captive_portal.get_config_value", return_value=False):
            assert apply_dnsmasq_config() is True

    def test_write_failure_is_best_effort(self, native_mode, reset_runtime_config, tmp_path, caplog):
        """A read-only /etc must not stop the hotspot from starting."""
        include = tmp_path / 'portal.conf'
        with mock.patch.object(captive_portal, 'INCLUDE_FILE', include), \
                mock.patch("pathlib.Path.write_text", side_effect=PermissionError("read-only")):
            assert apply_dnsmasq_config('10.42.0.1') is False
        assert 'Could not update captive portal' in caplog.text

    def test_docker_never_writes(self, reset_runtime_config, tmp_path):
        include = tmp_path / 'portal.conf'
        with mock.patch.object(captive_portal, 'INCLUDE_FILE', include), \
                mock.patch("controller.lib.captive_portal.is_docker_mode", return_value=True):
            assert is_captive_portal_enabled() is False
            apply_dnsmasq_config('10.42.0.1')
            assert not include.exists()


class TestIsCaptivePortalEnabled:

    def test_default_true(self, native_mode, reset_runtime_config):
        assert is_captive_portal_enabled() is True

    def test_setting_false(self, native_mode, reset_runtime_config):
        with mock.patch("controller.lib.captive_portal.get_config_value", return_value=False):
            assert is_captive_portal_enabled() is False


class TestGetHotspotIp:

    def test_parses_ip_json(self, native_mode):
        result = mock.Mock(returncode=0, stdout=IP_JSON)
        with mock.patch("subprocess.run", return_value=result) as run:
            assert get_hotspot_ip('wlan0') == '10.42.0.1'
        assert run.call_args[0][0] == ['ip', '-4', '-j', 'addr', 'show', 'dev', 'wlan0']

    def test_no_address_when_hotspot_down(self, native_mode):
        result = mock.Mock(returncode=0, stdout=json.dumps([{"ifname": "wlan0", "addr_info": []}]))
        with mock.patch("subprocess.run", return_value=result):
            assert get_hotspot_ip('wlan0') is None

    def test_missing_device(self, native_mode):
        result = mock.Mock(returncode=1, stdout='')
        with mock.patch("subprocess.run", return_value=result):
            assert get_hotspot_ip('wlan9') is None

    @pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired('ip', 5)])
    def test_ip_unavailable(self, native_mode, error):
        with mock.patch("subprocess.run", side_effect=error):
            assert get_hotspot_ip('wlan0') is None

    def test_docker(self):
        with mock.patch("controller.lib.captive_portal.is_docker_mode", return_value=True):
            assert get_hotspot_ip('wlan0') is None


class TestProbeRedirects:
    """OS connectivity probes are redirected to the portal when the feature is on."""

    @pytest.mark.parametrize("path", PROBE_PATHS)
    def test_probe_redirects_when_enabled(self, test_client, path):
        response = test_client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers['location'] == '/portal'
        assert response.headers['cache-control'] == 'no-store'

    def test_head_probe_redirects(self, test_client):
        response = test_client.head('/hotspot-detect.html', follow_redirects=False)
        assert response.status_code == 302

    def test_probe_404_when_disabled(self, test_client):
        with mock.patch("controller.api.captive_portal.is_captive_portal_enabled", return_value=False):
            response = test_client.get('/generate_204', follow_redirects=False)
        assert response.status_code == 404

    def test_probe_404_in_docker(self, test_client_docker_mode):
        response = test_client_docker_mode.get('/hotspot-detect.html', follow_redirects=False)
        assert response.status_code == 404


class TestPortalPage:

    def test_shows_address_and_links(self, test_client):
        with mock.patch("controller.api.captive_portal.get_hotspot_ip", return_value='10.42.0.1'):
            response = test_client.get('/portal')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        body = response.text
        assert '10.42.0.1' in body
        assert 'https://10.42.0.1/' in body
        assert 'https://10.42.0.1/controller/' in body
        assert 'WROLPi' in body  # the SSID

    def test_404_when_hotspot_down(self, test_client):
        """A page with no address is worse than no page."""
        with mock.patch("controller.api.captive_portal.get_hotspot_ip", return_value=None):
            assert test_client.get('/portal').status_code == 404

    def test_404_in_docker(self, test_client_docker_mode):
        assert test_client_docker_mode.get('/portal').status_code == 404

    def test_served_even_when_probes_disabled(self, test_client):
        """The setting controls the automatic sheet, not the page itself."""
        with mock.patch("controller.api.captive_portal.get_hotspot_ip", return_value='10.42.0.1'), \
                mock.patch("controller.api.captive_portal.is_captive_portal_enabled", return_value=False):
            assert test_client.get('/portal').status_code == 200


class TestDefaultIp:

    def test_default_is_networkmanager_shared_subnet(self):
        assert DEFAULT_HOTSPOT_IP == '10.42.0.1'
