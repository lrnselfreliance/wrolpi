"""
Torrents: qBittorrent, inside the VPN's network namespace, kept as config/torrents/ says.

Each torrent is `config/torrents/<hash>.yaml`, with its `.torrent` file beside it, so a restored WROLPi re-adds
(and re-checks, never re-downloads) every torrent.  There is no database.  The torrents can also be managed in
qBittorrent's own WebUI (port 8091), so WROLPi follows it too:

- A torrent WROLPi knows carries the `wrolpi` tag in qBittorrent.  An untagged torrent (added in the WebUI) is
  adopted into the config once its metadata has arrived.
- qBittorrent keeps its tags in its profile.  Without the `wrolpi` tag, the profile is new (first start, or a
  restore), and every torrent in the config is added.  With it, a torrent missing from qBittorrent was removed in the
  WebUI, and leaves the config; a tagged torrent missing from the config was removed from the config, and leaves
  qBittorrent (its files are kept).
- `paused` in the config is what the user wants.  WROL Mode stops torrents with the `wrolpi-wrol-mode` tag, so they
  are started again when it ends; any other stop or start of a torrent is the user's, and is saved.
"""
import asyncio
import pathlib
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

from wrolpi import flags
from wrolpi.api_utils import perpetual_signal
from wrolpi.common import MultiFileConfig, get_media_directory, logger, wrol_mode_enabled, get_relative_to_media_directory
from wrolpi.vars import DOCKERIZED, PYTEST
from modules.torrents.qbittorrent import QBittorrent, QBittorrentError, QBittorrentUnavailable

logger = logger.getChild(__name__)

TAG = 'wrolpi'
WROL_MODE_TAG = 'wrolpi-wrol-mode'
TUNNEL_INTERFACE = 'vpn0'
# Where torrents are saved unless asked otherwise, relative to the media directory.
DEFAULT_SAVE_PATH = 'torrents'
STOPPED_STATES = {'stoppedUP', 'stoppedDL'}
# Downloaded, and being (or ready to be) seeded.
COMPLETE_STATES = {'uploading', 'stalledUP', 'forcedUP', 'queuedUP', 'stoppedUP', 'checkingUP'}
SYNC_SECONDS = 10
CONTROLLER_URL = 'http://controller' if DOCKERIZED else 'http://127.0.0.1'


@dataclass
class TorrentConfigValidator:
    version: int
    slug: str
    name: str
    save_path: str
    paused: bool = False
    magnet: str = None
    complete: bool = False


class TorrentsConfig(MultiFileConfig):
    subdirectory = 'torrents'
    name = 'torrents'
    validator = TorrentConfigValidator
    default_entity = dict(version=0, slug=None, name=None, save_path=DEFAULT_SAVE_PATH, paused=False, magnet=None,
                          complete=False)

    def get_torrent_file(self, slug: str) -> pathlib.Path:
        return self.get_directory() / f'{slug}.torrent'

    def update(self, slug: str, **values):
        entity = self.get(slug)
        if entity is None:
            return
        entity.update(values)
        self.replace(slug, entity)

    def delete(self, slug: str):
        with self.save_lock():
            self._configs.pop(slug, None)
            self.get_file(slug).unlink(missing_ok=True)
            self.get_torrent_file(slug).unlink(missing_ok=True)


TORRENTS_CONFIG = TorrentsConfig()
TEST_TORRENTS_CONFIG: Optional[TorrentsConfig] = None


def get_torrents_config() -> TorrentsConfig:
    if isinstance(TEST_TORRENTS_CONFIG, TorrentsConfig):
        return TEST_TORRENTS_CONFIG
    return TORRENTS_CONFIG


def set_test_torrents_config(enabled: bool):
    global TEST_TORRENTS_CONFIG
    TEST_TORRENTS_CONFIG = TorrentsConfig() if enabled else None


def save_path_of(entity: dict) -> str:
    """The absolute directory qBittorrent saves a torrent in."""
    save_path = pathlib.Path(entity.get('save_path') or DEFAULT_SAVE_PATH)
    return str(save_path if save_path.is_absolute() else get_media_directory() / save_path)


def config_save_path(save_path: str) -> str:
    """How the config records qBittorrent's save path: relative to the media directory when it is in it."""
    try:
        return str(get_relative_to_media_directory(save_path))
    except ValueError:
        return save_path


async def get_vpn_status() -> dict:
    """The Controller's report of the VPN torrents use; {} when the Controller cannot be reached."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f'{CONTROLLER_URL}/api/vpn/status') as response:
                return await response.json() if response.status == 200 else {}
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return {}


def desired_preferences(vpn_status: dict) -> dict:
    preferences = {
        # Torrents use only the tunnel.  (The kill switch already blocks everything else.)
        'current_network_interface': TUNNEL_INTERFACE,
        'current_interface_address': '',
        # The router UPnP or NAT-PMP would ask is the VPN's; the tunnel asks for the port itself.
        'upnp': False,
        # Nothing to discover on the tunnel's "local" network.
        'lsd': False,
        # A file still downloading is never mistaken for a finished one.
        'incomplete_files_ext': True,
        'save_path': str(get_media_directory() / DEFAULT_SAVE_PATH),
        'random_port': False,
        # Peers are not told which client (and version) this is, so a known flaw in one cannot be aimed at it.
        'anonymous_mode': True,
        # Running a program would be code execution for anyone who can reach the WebUI.
        'autorun_enabled': False,
        'autorun_on_torrent_added_enabled': False,
    }
    if port := vpn_status.get('forwarded_port'):
        # Peers connect to the port the VPN forwards.
        preferences['listen_port'] = port
    return preferences


async def enforce_preferences(client: QBittorrent, vpn_status: dict) -> dict:
    """Set the preferences which differ from what WROLPi needs; returns those changed."""
    current = await client.preferences()
    changed = {k: v for k, v in desired_preferences(vpn_status).items() if current.get(k) != v}
    if changed:
        logger.info(f'Setting qBittorrent preferences: {changed}')
        await client.set_preferences(changed)
    return changed


async def add_from_config(client: QBittorrent, entity: dict, stopped: bool):
    config = get_torrents_config()
    torrent_file = config.get_torrent_file(entity['slug'])
    torrent = torrent_file.read_bytes() if torrent_file.is_file() else None
    if not torrent and not entity.get('magnet'):
        logger.error(f'Cannot add torrent {entity["name"]}: it has no .torrent file and no magnet link')
        return
    pathlib.Path(save_path_of(entity)).mkdir(parents=True, exist_ok=True)
    tags = [TAG, WROL_MODE_TAG] if stopped and not entity.get('paused') else [TAG]
    await client.add(save_path_of(entity), torrent=torrent, url=None if torrent else entity['magnet'], tags=tags,
                     stopped=stopped)
    logger.info(f'Added torrent {entity["name"]} to qBittorrent')


async def adopt(client: QBittorrent, torrent: dict) -> bool:
    """Add a torrent added in qBittorrent's WebUI to the config, once its metadata has arrived."""
    exported = await client.export(torrent['hash'])
    if not exported:
        return False
    config = get_torrents_config()
    slug = torrent['hash']
    config.get_torrent_file(slug).parent.mkdir(parents=True, exist_ok=True)
    config.get_torrent_file(slug).write_bytes(exported)
    config.create(slug, dict(slug=slug, name=torrent['name'], save_path=config_save_path(torrent['save_path']),
                             paused=torrent['state'] in STOPPED_STATES, magnet=torrent.get('magnet_uri')))
    await client.add_tags([slug], TAG)
    logger.info(f'Adopted torrent {torrent["name"]} added in qBittorrent')
    return True


async def reconcile(client: QBittorrent, wrol_mode: bool) -> dict:
    """Make qBittorrent and the config agree; returns what was done (for tests and logs)."""
    config = get_torrents_config()
    done = dict(added=[], adopted=[], forgotten=[], removed=[], stopped=[], started=[], completed=[])
    torrents = {t['hash']: t for t in await client.torrents()}
    entities = {e['slug']: e for e in config.all()}

    if TAG not in await client.tags():
        # A new qBittorrent profile: add every torrent the config has.
        await client.create_tags(TAG, WROL_MODE_TAG)
        for slug, entity in entities.items():
            if slug not in torrents:
                await add_from_config(client, entity, stopped=wrol_mode or bool(entity.get('paused')))
                done['added'].append(slug)
        return done

    for slug, torrent in torrents.items():
        tags = {t.strip() for t in (torrent.get('tags') or '').split(',') if t.strip()}
        if TAG not in tags:
            if await adopt(client, torrent):
                done['adopted'].append(slug)
            continue
        entity = entities.get(slug)
        if entity is None:
            # Removed from the config: removed from qBittorrent, its files kept.
            await client.delete([slug], delete_files=False)
            done['removed'].append(slug)
            continue

        stopped = torrent['state'] in STOPPED_STATES
        if wrol_mode:
            if not stopped:
                await client.add_tags([slug], WROL_MODE_TAG)
                await client.stop([slug])
                done['stopped'].append(slug)
        elif WROL_MODE_TAG in tags:
            # Stopped by WROL Mode, which has ended.
            await client.remove_tags([slug], WROL_MODE_TAG)
            if not entity.get('paused'):
                await client.start([slug])
                done['started'].append(slug)
        elif stopped != bool(entity.get('paused')):
            # Stopped or started in the WebUI: that is what the user wants now.
            config.update(slug, paused=stopped)

        if not entity.get('complete') and torrent['state'] in COMPLETE_STATES and torrent.get('progress', 0) >= 1:
            config.update(slug, complete=True)
            done['completed'].append(slug)
            index_downloaded(torrent)

        if not config.get_torrent_file(slug).is_file() and (exported := await client.export(slug)):
            config.get_torrent_file(slug).write_bytes(exported)

    for slug in entities.keys() - torrents.keys():
        # Removed in the WebUI.
        config.delete(slug)
        done['forgotten'].append(slug)
    return done


def index_downloaded(torrent: dict):
    """Index a finished torrent's files, as any other download's."""
    from wrolpi.files.worker import file_worker
    content_path = pathlib.Path(torrent.get('content_path') or torrent['save_path'])
    try:
        content_path.relative_to(get_media_directory())
    except ValueError:
        logger.warning(f'Not indexing torrent {torrent["name"]}: it is outside the media directory')
        return
    file_worker.queue_refresh([content_path], expand_stems=True)


async def sync_torrents(client: QBittorrent = None) -> Optional[dict]:
    """One pass: qBittorrent's preferences, and the config; None when qBittorrent cannot be reached."""
    client = client or QBittorrent()
    try:
        await client.version()
    except QBittorrentUnavailable:
        return None
    vpn_status = await get_vpn_status()
    await enforce_preferences(client, vpn_status)
    return await reconcile(client, wrol_mode_enabled())


@perpetual_signal(sleep=SYNC_SECONDS)
async def torrents_worker():
    if PYTEST or not flags.media_mounted.is_set() or not get_torrents_config().successful_import:
        return
    try:
        done = await sync_torrents()
    except (QBittorrentError, QBittorrentUnavailable, OSError) as e:
        logger.warning(f'Could not sync torrents with qBittorrent: {e}')
        return
    if done and any(done.values()):
        logger.info(f'Synced torrents with qBittorrent: { {k: v for k, v in done.items() if v} }')


async def get_torrents_status(client: QBittorrent = None) -> dict:
    """qBittorrent's state, the VPN's, and every torrent, for the API."""
    client = client or QBittorrent()
    vpn_status = await get_vpn_status()
    try:
        transfer, torrents = await asyncio.gather(client.transfer_info(), client.torrents())
    except (QBittorrentUnavailable, QBittorrentError) as e:
        return dict(running=False, error=str(e), vpn=vpn_status, torrents=[])
    return dict(
        running=True,
        error=None,
        vpn=vpn_status,
        # connected (peers can reach this WROLPi), firewalled, or disconnected.
        connection_status=transfer.get('connection_status'),
        upload_speed=transfer.get('up_info_speed'),
        download_speed=transfer.get('dl_info_speed'),
        torrents=[dict(hash=t['hash'], name=t['name'], size=t.get('size'), progress=t.get('progress'),
                       state=t.get('state'), ratio=t.get('ratio'), upload_speed=t.get('upspeed'),
                       download_speed=t.get('dlspeed'), peers=t.get('num_leechs'), seeds=t.get('num_seeds'),
                       save_path=config_save_path(t.get('save_path') or ''))
                  for t in torrents],
    )
