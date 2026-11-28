"""Torrents: qBittorrent kept as config/torrents/ says, and the config following qBittorrent's WebUI."""
import configparser
import json
from pathlib import Path
from unittest import mock

import pytest
import yaml

from modules.torrents import lib, qbittorrent_prepare

REPOSITORY = Path(__file__).parent.parent.parent.parent
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


def make_entity(config, slug, torrent_file=True, **values):
    entity = dict(slug=slug, name=f'torrent {slug[:4]}', save_path='torrents', **values)
    config.create(slug, entity)
    if torrent_file:
        config.get_torrent_file(slug).write_bytes(f'torrent {slug}'.encode())


def qbt_torrent(hash_, tags='wrolpi', state='uploading', progress=1.0, save_path=None, **values):
    return dict(hash=hash_, name=f'torrent {hash_[:4]}', tags=tags, state=state, progress=progress,
                save_path=save_path or str(lib.get_media_directory() / 'torrents'),
                magnet_uri=f'magnet:?xt=urn:btih:{hash_}', **values)


async def test_preferences(test_directory, fake_qbittorrent):
    client = fake_qbittorrent()
    changed = await lib.enforce_preferences(client, {'state': 'connected', 'forwarded_port': 36523})
    assert changed['upnp'] is False
    assert changed['lsd'] is False
    assert changed['listen_port'] == 36523
    assert changed['autorun_enabled'] is False and changed['autorun_on_torrent_added_enabled'] is False
    assert changed['save_path'] == str(test_directory / 'torrents')
    # Already right: not set again.
    assert 'current_network_interface' not in changed
    assert await lib.enforce_preferences(client, {'state': 'connected', 'forwarded_port': 36523}) == {}
    # Without a forwarded port, the listening port is left alone.
    assert 'listen_port' not in lib.desired_preferences({'state': 'connected', 'forwarded_port': None})


async def test_new_profile_gets_every_torrent(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A)
    make_entity(test_torrents_config, B, torrent_file=False, magnet=f'magnet:?xt=urn:btih:{B}', paused=True)
    client = fake_qbittorrent()

    done = await lib.reconcile(client, wrol_mode=False)
    assert sorted(done['added']) == [A, B]
    assert set(await client.tags()) == {lib.TAG, lib.WROL_MODE_TAG}
    adds = {c[2] or c[3]: c for c in client.calls if c[0] == 'add'}
    # From its .torrent file (re-checked, never re-downloaded), into its directory.
    _, save_path, torrent, url, tags, stopped = adds[f'torrent {A}'.encode()]
    assert save_path == str(lib.get_media_directory() / 'torrents')
    assert (tags, stopped) == ([lib.TAG], False)
    # Only a magnet link: added from that.  Paused stays paused.
    _, _, _, url, tags, stopped = adds[f'magnet:?xt=urn:btih:{B}']
    assert (tags, stopped) == ([lib.TAG], True)


async def test_new_profile_in_wrol_mode(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A)
    client = fake_qbittorrent()
    await lib.reconcile(client, wrol_mode=True)
    _, _, _, _, tags, stopped = next(c for c in client.calls if c[0] == 'add')
    # Started again when WROL Mode ends.
    assert stopped and lib.WROL_MODE_TAG in tags


async def test_adopts_torrents_added_in_the_webui(test_torrents_config, fake_qbittorrent):
    client = fake_qbittorrent([qbt_torrent(A, tags='', state='downloading', progress=0.2,
                                           save_path=str(lib.get_media_directory() / 'maps'))],
                              tags=[lib.TAG])
    done = await lib.reconcile(client, wrol_mode=False)
    assert done['adopted'] == [A]
    entity = test_torrents_config.get(A)
    assert entity['save_path'] == 'maps'
    assert entity['paused'] is False
    assert entity['magnet'] == f'magnet:?xt=urn:btih:{A}'
    assert test_torrents_config.get_torrent_file(A).read_bytes() == f'torrent {A}'.encode()
    assert (await client.torrents())[0]['tags'] == lib.TAG


async def test_waits_for_metadata_before_adopting(test_torrents_config, fake_qbittorrent):
    client = fake_qbittorrent([qbt_torrent(A, tags='', state='metaDL', progress=0)], tags=[lib.TAG], metadata=False)
    done = await lib.reconcile(client, wrol_mode=False)
    assert done['adopted'] == []
    assert test_torrents_config.get(A) is None


async def test_removed_in_the_webui_leaves_the_config(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A)
    client = fake_qbittorrent([], tags=[lib.TAG])
    done = await lib.reconcile(client, wrol_mode=False)
    assert done['forgotten'] == [A]
    assert test_torrents_config.get(A) is None
    assert not test_torrents_config.get_file(A).exists()
    assert not test_torrents_config.get_torrent_file(A).exists()


async def test_removed_from_the_config_leaves_qbittorrent_keeping_files(test_torrents_config, fake_qbittorrent):
    client = fake_qbittorrent([qbt_torrent(A)], tags=[lib.TAG])
    done = await lib.reconcile(client, wrol_mode=False)
    assert done['removed'] == [A]
    assert ('delete', [A], False) in client.calls


async def test_pausing_in_the_webui_is_saved(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A)
    client = fake_qbittorrent([qbt_torrent(A, state='stoppedUP')], tags=[lib.TAG])
    await lib.reconcile(client, wrol_mode=False)
    assert test_torrents_config.get(A)['paused'] is True
    await client.start([A])
    await lib.reconcile(client, wrol_mode=False)
    assert test_torrents_config.get(A)['paused'] is False


async def test_wrol_mode_stops_torrents_and_starts_them_again(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A, complete=True)
    make_entity(test_torrents_config, B, paused=True, complete=True)
    client = fake_qbittorrent([qbt_torrent(A), qbt_torrent(B, state='stoppedUP')], tags=[lib.TAG])

    done = await lib.reconcile(client, wrol_mode=True)
    assert done['stopped'] == [A]
    # The user's wishes are unchanged.
    assert test_torrents_config.get(A)['paused'] is False

    done = await lib.reconcile(client, wrol_mode=False)
    assert done['started'] == [A]
    torrents = {t['hash']: t for t in await client.torrents()}
    assert lib.WROL_MODE_TAG not in torrents[A]['tags']
    # Paused by the user: not started.
    assert torrents[B]['state'] == 'stoppedUP'


async def test_finished_torrent_is_indexed_once(test_torrents_config, fake_qbittorrent):
    make_entity(test_torrents_config, A)
    content = lib.get_media_directory() / 'torrents' / 'planet.pmtiles'
    client = fake_qbittorrent([qbt_torrent(A, content_path=str(content))], tags=[lib.TAG])
    with mock.patch('wrolpi.files.worker.file_worker') as file_worker:
        done = await lib.reconcile(client, wrol_mode=False)
        assert done['completed'] == [A]
        file_worker.queue_refresh.assert_called_once_with([content], expand_stems=True)
        await lib.reconcile(client, wrol_mode=False)
        assert file_worker.queue_refresh.call_count == 1
    assert test_torrents_config.get(A)['complete'] is True


async def test_sync_is_skipped_without_qbittorrent(test_torrents_config):
    client = mock.Mock()
    client.version = mock.AsyncMock(side_effect=lib.QBittorrentUnavailable('down'))
    assert await lib.sync_torrents(client) is None


async def test_status(test_torrents_config, fake_qbittorrent):
    client = fake_qbittorrent([qbt_torrent(A, size=10, ratio=2.5, upspeed=5, dlspeed=0, num_leechs=1, num_seeds=3)],
                              tags=[lib.TAG])
    with mock.patch.object(lib, 'get_vpn_status', mock.AsyncMock(return_value={'state': 'connected'})):
        status = await lib.get_torrents_status(client)
    assert status['running'] is True
    assert status['connection_status'] == 'connected'
    assert status['vpn'] == {'state': 'connected'}
    assert status['torrents'][0]['save_path'] == 'torrents'
    assert status['torrents'][0]['ratio'] == 2.5


class TestPrepare:

    def test_writes_webui_and_interface_keeping_the_rest(self, tmp_path):
        path = tmp_path / 'qBittorrent' / 'config' / 'qBittorrent.conf'
        path.parent.mkdir(parents=True)
        path.write_text('[Preferences]\nWebUI\\Port=8080\nDownloads\\SavePath=/media/wrolpi/x/\n'
                        '[Network]\nCookies=@Invalid()\n')
        qbittorrent_prepare.prepare(tmp_path, '10.211.0.2', ['10.211.0.1/32'])
        config = configparser.RawConfigParser(strict=False)
        config.optionxform = str
        config.read(path)
        preferences = config['Preferences']
        assert preferences['WebUI\\Address'] == '10.211.0.2'
        assert preferences['WebUI\\Port'] == '8091'
        assert preferences['WebUI\\AuthSubnetWhitelist'] == '10.211.0.1/32'
        assert preferences['WebUI\\AuthSubnetWhitelistEnabled'] == 'true'
        assert config['BitTorrent']['Session\\Interface'] == 'vpn0'
        assert config['AutoRun']['enabled'] == 'false'
        assert config['AutoRun']['OnTorrentAdded\\Enabled'] == 'false'
        # qBittorrent's own settings are kept, case and all.
        assert preferences['Downloads\\SavePath'] == '/media/wrolpi/x/'
        assert config['Network']['Cookies'] == '@Invalid()'
        assert 'WebUI\\Port=8091' in path.read_text()

    def test_uplink(self):
        outputs = {
            ('ip', '-j', '-4', 'route', 'show', 'default'):
                json.dumps([{'dev': 'vpn-uplink', 'gateway': '10.211.0.1'}]).encode(),
            ('ip', '-j', '-4', 'addr', 'show', 'dev', 'vpn-uplink'):
                json.dumps([{'addr_info': [{'local': '10.211.0.2', 'prefixlen': 30, 'scope': 'global'}]}]).encode(),
        }
        with mock.patch.object(qbittorrent_prepare.subprocess, 'check_output', lambda cmd: outputs[tuple(cmd)]):
            assert qbittorrent_prepare.find_uplink() == ('10.211.0.2', '10.211.0.0/30')

    def test_standalone(self):
        source = (REPOSITORY / 'modules/torrents/qbittorrent_prepare.py').read_text()
        imports = {line.split()[1].split('.')[0] for line in source.splitlines() if line.startswith(('import ', 'from '))}
        assert imports <= set(__import__('sys').stdlib_module_names)


class TestInstalled:

    def test_unit(self):
        unit = (REPOSITORY / 'etc/raspberrypios/wrolpi-torrent.service').read_text()
        assert 'NetworkNamespacePath=/run/netns/wrolpi-vpn' in unit
        assert 'BindsTo=wrolpi-vpn.service' in unit
        # systemd does not bind the namespace's resolv.conf the way `ip netns exec` does.
        assert 'BindReadOnlyPaths=/etc/netns/wrolpi-vpn/resolv.conf:/etc/resolv.conf' in unit
        assert '--allow 10.211.0.1/32' in unit
        assert 'ProtectSystem=strict' in unit and 'ReadWritePaths=/media/wrolpi' in unit
        # Never WROLPi's config; qBittorrent's own state is outside the library.
        assert 'ReadOnlyPaths=/media/wrolpi/config' in unit
        assert '--profile=/var/lib/wrolpi-torrent' in unit and 'StateDirectory=wrolpi-torrent' in unit
        assert 'User=wrolpi' in unit
        for script in ('repair.sh', 'pi-gen/stage2/04-wrolpi/03-run-chroot.sh',
                       'debian-live-config/config/includes.chroot/usr/local/sbin/wrolpi-bootstrap.sh',
                       'etc/raspberrypios/wrolpi.target'):
            assert 'wrolpi-torrent.service' in (REPOSITORY / script).read_text(), script
        for packages in ('pi-gen/stage2/04-wrolpi/01-packages-nr',
                         'debian-live-config/config/package-lists/wrolpi.list.chroot'):
            assert 'qbittorrent-nox' in (REPOSITORY / packages).read_text().splitlines()

    def test_docker(self):
        compose = yaml.safe_load((REPOSITORY / 'docker-compose.yml').read_text())
        torrent = compose['services']['torrent']
        assert torrent['network_mode'] == 'service:vpn'
        assert torrent['depends_on']['vpn']['restart'] is True
        assert './test/config:/media/wrolpi/config:ro' in torrent['volumes']
        assert 'torrent-profile:/profile' in torrent['volumes']
        assert '8091:8091' in compose['services']['web']['ports']
        assert 'qbittorrent_prepare.py' in (REPOSITORY / 'docker/torrent/Dockerfile').read_text()

    @pytest.mark.parametrize('caddyfile,upstream', [('etc/raspberrypios/Caddyfile', '10.211.0.2:8091'),
                                                    ('docker/web/Caddyfile', 'vpn:8091')])
    def test_caddy_serves_the_webui_but_not_its_settings(self, caddyfile, upstream):
        text = (REPOSITORY / caddyfile).read_text()
        block = text[text.index(':8091 {'):]
        block = block[:block.index('\n}\n')]
        assert f'reverse_proxy {upstream}' in block
        for refused in ('/api/v2/app/setPreferences', '/api/v2/app/shutdown', '/api/v2/search/*'):
            assert refused in block, refused
        assert 'respond @qbittorrent_settings' in block
        assert 'tls ' in block
