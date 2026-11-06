"""Copy a primary WROLPi's library to a secondary WROLPi.

A secondary pulls; the primary only answers reads.  The library is the media files plus the config YAMLs, because the
database is rebuilt from both, so a sync is:

1. Walk the primary's manifest (`/api/sync/manifest`): every file of every FileGroup, paged by FileGroup id.
2. Download each file the secondary lacks, or has with a different size or modification time, from the primary's
   `/media/` (Caddy).  A file is written to a hidden partial (refresh never indexes hidden files), then renamed into
   place with the primary's modification time, so a later comparison is exact and an interrupted download resumes.
3. Refresh the downloaded files, a page at a time.
4. Copy the synced configs (`SYNCED_CONFIG_FILE_NAMES`) and import them.  Files come first so the configs never
   refer to files the secondary does not have yet.

Files deleted on the primary are never deleted on the secondary.

While a sync runs the secondary's API refuses requests (`check_sync_api_lock`), so nobody edits a library that is
being replaced.
"""
import asyncio
import contextlib
import json
import os
import pathlib
import re
import shutil
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import AsyncGenerator, List, Optional
from urllib.parse import quote

import aiohttp
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import logger, get_media_directory, get_wrolpi_config, is_secondary, wrol_mode_enabled, \
    get_config_by_file_name, SYNCED_CONFIG_FILE_NAMES
from wrolpi.dates import now, is_within_daily_window
from wrolpi.events import Events
from wrolpi.sync.status import get_sync_status, update_sync_status
from wrolpi.vars import DEFAULT_HTTP_HEADERS, PYTEST
from wrolpi.version import __version__

logger = logger.getChild(__name__)

MANIFEST_PAGE_LIMIT = 500
# Files downloaded at once.  Small files are dominated by round trips; four keeps a Pi's disk and CPU busy.
DOWNLOAD_CONCURRENCY = 4
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
# Never fill the secondary's drive; leave this much free.
MIN_FREE_BYTES = 1024 ** 3
# exFAT stores modification times in 2-second steps.
MTIME_TOLERANCE_SECONDS = 2.0
# How often a running sync reports its progress.
PROGRESS_INTERVAL_SECONDS = 2.0
# Within the sync window, sync again this long after the last sync finished (an idle sync only compares sizes).
SYNC_WINDOW_REPEAT_SECONDS = 15 * 60
REFRESH_TIMEOUT_SECONDS = 60 * 60
# Configs and directory listings are small; never read more than this from the primary.
MAX_CONFIG_BYTES = 64 * 1024 * 1024

# Top-level directories never written by a sync: the configs and database, and the Tags Directory (hard links that
# the secondary rebuilds from tags.yaml).
PROTECTED_DIRECTORIES = frozenset({'config', 'tags'})
# Files that are still being downloaded on the primary: aria2 and yt-dlp partials, and yt-dlp format files.
INCOMPLETE_FILE = re.compile(r'(\.part|\.aria2|\.ytdl|\.temp)$|\.f\d{2,4}\.[^.]+$')

# wrolpi.yaml keys that describe the library rather than this machine (hotspot, timezone, role, etc. stay local).
SYNCED_WROLPI_CONFIG_KEYS = (
    'archive_destination',
    'ignore_outdated_zims',
    'ignored_directories',
    'map_default_location',
    'map_destination',
    'playlists_destination',
    'repos_destination',
    'save_ffprobe_json',
    'tags_directory',
    'videos_destination',
    'zims_destination',
)


class SyncError(Exception):
    pass


class SyncDiskFull(SyncError):
    pass


class SyncCancelled(SyncError):
    pass


@dataclass(frozen=True)
class ManifestFile:
    path: str  # Relative to the media directory, '/' separated.
    size: int
    mtime: float


# ---------------------------------------------------------------------------------------------------------------------
# Primary: the manifest.


def build_manifest_page(session: Session, after_id: int = 0, limit: int = MANIFEST_PAGE_LIMIT) -> dict:
    """One page of the primary's library: the files of the FileGroups after `after_id`, in id order.

    Sizes and modification times come from the files themselves, not the database, which does not record them for
    every file of a group."""
    from wrolpi.files.models import FileGroup

    media_directory = get_media_directory().resolve()
    rows = session.execute(
        select(FileGroup.id, FileGroup.directory, FileGroup.files)
        .where(FileGroup.id > after_id)
        .order_by(FileGroup.id)
        .limit(limit)
    ).all()
    max_id = session.execute(select(func.max(FileGroup.id))).scalar() or 0

    groups = list()
    for id_, directory, files in rows:
        paths = list()
        for entry in files or []:
            if not isinstance(entry, dict) or not entry.get('path'):
                continue
            path = pathlib.Path(entry['path'])
            if not path.is_absolute():
                # Files are stored relative to their FileGroup's directory; older rows stored absolute paths.
                path = pathlib.Path(directory) / path
            if manifest_file := _manifest_file(media_directory, path):
                paths.append(manifest_file)
        groups.append(dict(id=id_, paths=[dict(path=i.path, size=i.size, mtime=i.mtime) for i in paths]))

    next_after_id = rows[-1][0] if len(rows) == limit else None
    return dict(groups=groups, next_after_id=next_after_id, max_id=max_id, limit=limit)


def _manifest_file(media_directory: pathlib.Path, path: pathlib.Path) -> Optional[ManifestFile]:
    try:
        relative = path.relative_to(media_directory)
    except ValueError:
        return None
    parts = relative.parts
    if not parts or any(i.startswith('.') for i in parts) or parts[0] in PROTECTED_DIRECTORIES:
        return None
    if INCOMPLETE_FILE.search(path.name):
        return None
    try:
        stat = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    if not path.is_file():
        return None
    return ManifestFile(relative.as_posix(), stat.st_size, stat.st_mtime)


def get_sync_info(session: Session) -> dict:
    from wrolpi.files.models import FileGroup
    return dict(
        version=__version__.strip(),
        role=get_wrolpi_config().role,
        media_directory=str(get_media_directory()),
        max_file_group_id=session.execute(select(func.max(FileGroup.id))).scalar() or 0,
    )


# ---------------------------------------------------------------------------------------------------------------------
# Secondary: comparing and writing files.


def resolve_destination(media_directory: pathlib.Path, path: str) -> Optional[pathlib.Path]:
    """The secondary's path for a manifest path, or None if the path must not be written: outside the media directory,
    hidden, protected, or reached through a symlink."""
    if not path or path.startswith('/') or '\\' in path:
        return None
    parts = pathlib.PurePosixPath(path).parts
    if not parts or any(i in ('.', '..') or i.startswith('.') for i in parts):
        return None
    if parts[0] in PROTECTED_DIRECTORIES:
        return None
    media_directory = media_directory.resolve()
    destination = media_directory.joinpath(*parts)
    # A symlink anywhere on the way (or the file itself) resolves elsewhere.
    if pathlib.Path(os.path.realpath(destination)) != destination:
        return None
    return destination


def needs_download(destination: pathlib.Path, file: ManifestFile) -> bool:
    try:
        stat = destination.stat()
    except FileNotFoundError:
        return True
    return stat.st_size != file.size or abs(stat.st_mtime - file.mtime) > MTIME_TOLERANCE_SECONDS


def partial_path(destination: pathlib.Path) -> pathlib.Path:
    """Hidden, so a refresh never indexes a file that is still downloading."""
    return destination.with_name(f'.{destination.name}.partial')


def _cpu_lacks_aes() -> bool:
    """True when the CPU has no AES instructions (a Raspberry Pi 4).  ChaCha20 is then about twice as fast."""
    try:
        cpuinfo = pathlib.Path('/proc/cpuinfo').read_text()
    except OSError:
        return False
    features = [i for i in cpuinfo.splitlines() if i.lower().startswith(('features', 'flags'))]
    return bool(features) and not any(' aes' in f' {i.split(":", 1)[-1]} ' for i in features)


def make_sync_ssl_context() -> ssl.SSLContext:
    """WROLPi serves HTTPS with its own certificate authority; on a trusted LAN (see the Bookshelf threat model) the
    primary is not verified.  Pinning it would load the primary's `/ca.crt` here with `load_verify_locations`."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if _cpu_lacks_aes():
        # Python cannot order TLS 1.3 ciphers, and TLS 1.3 picks AES-GCM, which a Pi 4 decrypts at half the speed.
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE+AESGCM')
    return context


def normalize_primary_url(url: str) -> str:
    """'https://host[:port]' with no path; raises ValueError otherwise."""
    from urllib.parse import urlparse
    url = (url or '').strip().rstrip('/')
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('The primary must be an http:// or https:// address')
    if parsed.username or parsed.password:
        # The address is logged and shown in the sync's status.
        raise ValueError('The primary address must not contain a user name or password')
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError('The primary address must not have a path')
    return url


async def _read_limited(response: aiohttp.ClientResponse, path: str) -> bytes:
    data = bytearray()
    async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > MAX_CONFIG_BYTES:
            raise SyncError(f'{path} is larger than {MAX_CONFIG_BYTES} bytes')
    return bytes(data)


class PrimaryClient:
    """Reads from a primary WROLPi: its sync API, and its media directory through Caddy."""

    def __init__(self, url: str):
        self.url = normalize_primary_url(url)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        ssl_context = make_sync_ssl_context() if self.url.startswith('https') else False
        connector = aiohttp.TCPConnector(ssl=ssl_context, limit=DOWNLOAD_CONCURRENCY * 2)
        # A large file takes minutes; only a stalled read is an error.
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers=DEFAULT_HTTP_HEADERS)
        return self

    async def __aexit__(self, *exc):
        await self.session.close()

    def media_url(self, path: str) -> str:
        return f'{self.url}/media/{quote(path)}'

    async def get_json(self, path: str, params: dict = None, headers: dict = None):
        async with self.session.get(f'{self.url}{path}', params=params, headers=headers) as response:
            if response.status != HTTPStatus.OK:
                raise SyncError(f'{path} returned HTTP {response.status}')
            return json.loads(await _read_limited(response, path))

    async def get_info(self) -> dict:
        return await self.get_json('/api/sync/info')

    async def iter_manifest(self, limit: int = MANIFEST_PAGE_LIMIT) -> AsyncGenerator[dict, None]:
        after_id = 0
        while True:
            page = await self.get_json('/api/sync/manifest', params=dict(after_id=after_id, limit=limit))
            yield page
            if page.get('next_after_id') is None:
                return
            after_id = page['next_after_id']

    async def get_bytes(self, path: str) -> Optional[bytes]:
        """A file in the primary's media directory, or None if it does not exist."""
        async with self.session.get(self.media_url(path)) as response:
            if response.status == HTTPStatus.NOT_FOUND:
                return None
            if response.status != HTTPStatus.OK:
                raise SyncError(f'{path} returned HTTP {response.status}')
            return await _read_limited(response, path)

    async def list_directory(self, path: str) -> List[dict]:
        """The entries of a directory in the primary's media directory (Caddy's browse listing), [] if missing."""
        url = self.media_url(path.rstrip('/') + '/')
        async with self.session.get(url, headers={'Accept': 'application/json'}) as response:
            if response.status == HTTPStatus.NOT_FOUND:
                return []
            if response.status != HTTPStatus.OK:
                raise SyncError(f'{path} returned HTTP {response.status}')
            return json.loads(await _read_limited(response, path))

    @contextlib.asynccontextmanager
    async def open_media(self, path: str, offset: int = 0):
        # Sizes and ranges count the file's bytes, so the file must not be compressed in transit.
        headers = {'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        async with self.session.get(self.media_url(path), headers=headers) as response:
            yield response


async def download_file(client: PrimaryClient, file: ManifestFile, destination: pathlib.Path,
                        on_bytes=None) -> int:
    """Download one file to `destination` with the primary's modification time.  Returns the bytes received.

    A partial file left by an earlier attempt is resumed."""
    partial = partial_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    offset = partial.stat().st_size if partial.is_file() else 0
    if offset > file.size:
        offset = 0
    remaining = file.size - offset
    if shutil.disk_usage(destination.parent).free - remaining < MIN_FREE_BYTES:
        raise SyncDiskFull(f'Not enough free space for {file.path}')

    received = 0
    if remaining > 0 or not partial.is_file():
        async with client.open_media(file.path, offset) as response:
            if response.status == HTTPStatus.PARTIAL_CONTENT and offset:
                mode = 'ab'
            elif response.status == HTTPStatus.OK:
                mode, offset = 'wb', 0
            elif response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                # The partial does not match the primary's file; start over next time.
                partial.unlink(missing_ok=True)
                raise SyncError(f'{file.path} changed on the primary')
            else:
                raise SyncError(f'{file.path} returned HTTP {response.status}')

            if response.content_length is not None and response.content_length != file.size - offset:
                # The file changed on the primary after the manifest was read; the next sync gets it.
                raise SyncError(f'{file.path} changed on the primary')

            with open(partial, mode) as fh:
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    if offset + received + len(chunk) > file.size:
                        # Never write past the size the free-space check allowed for.
                        fh.close()
                        partial.unlink(missing_ok=True)
                        raise SyncError(f'{file.path} is larger than the primary said')
                    await asyncio.to_thread(fh.write, chunk)
                    received += len(chunk)
                    if on_bytes:
                        on_bytes(len(chunk))

    if (size := partial.stat().st_size) != file.size:
        raise SyncError(f'{file.path} is {size} bytes, the primary said {file.size}')
    os.utime(partial, (file.mtime, file.mtime))
    os.replace(partial, destination)
    return received


# ---------------------------------------------------------------------------------------------------------------------
# Secondary: configs.


def _import_tags():
    from wrolpi.tags import import_tags_config
    import_tags_config()


def _import_downloads():
    from wrolpi.downloader import get_download_manager_config
    get_download_manager_config().import_config()


def _import_channels():
    from modules.videos.lib import import_channels_config
    import_channels_config()


def _import_domains():
    from modules.archive.lib import import_domains_config
    import_domains_config()


def _import_playlists():
    from wrolpi.collections.config import playlists_config
    from wrolpi.collections.sync import sync_playlists_directory
    playlists_config.import_config()
    sync_playlists_directory.activate_switch()


def _import_zims():
    from modules.zim.lib import import_zims_config
    import_zims_config()


def _import_plain(file_name: str):
    def import_():
        get_config_by_file_name(file_name).import_config()

    return import_


def _import_inventories():
    from modules.inventory.common import import_inventories_config
    import_inventories_config()


# In the order of `import_all_db_configs`: Collections refer to Tags, and link to Downloads.
SYNCED_CONFIG_IMPORTS = (
    ('tags.yaml', _import_tags),
    ('download_manager.yaml', _import_downloads),
    ('channels.yaml', _import_channels),
    ('domains.yaml', _import_domains),
    ('playlists.yaml', _import_playlists),
    ('zims.yaml', _import_zims),
    ('map_pins.yaml', _import_plain('map_pins.yaml')),
    ('bookmarks.yaml', _import_plain('bookmarks.yaml')),
    ('videos_downloader.yaml', _import_plain('videos_downloader.yaml')),
    ('archives_downloader.yaml', _import_plain('archives_downloader.yaml')),
)
INVENTORY_DIRECTORY = 'config/inventory'
assert {i for i, _ in SYNCED_CONFIG_IMPORTS} | {'inventory/catalog.yaml'} == SYNCED_CONFIG_FILE_NAMES


def _parse_config(data: bytes, name: str) -> dict:
    config = yaml.safe_load(data)
    if not isinstance(config, dict):
        raise SyncError(f'{name} from the primary is not a config')
    return config


def write_config_bytes(file: pathlib.Path, data: bytes, backup: pathlib.Path = None) -> bool:
    """Replace `file` with the primary's bytes (keeping its version).  Returns False if they are already the same.

    The replaced file is copied to `backup` first (today's config backup), unless today's backup exists: like a save,
    the first copy of the day is the one kept, so a sync can be undone with a config backup import."""
    if file.is_file() and file.read_bytes() == data:
        return False
    if backup and file.is_file() and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, backup)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(f'.{file.name}.sync')
    temporary.write_bytes(data)
    os.replace(temporary, file)
    return True


async def sync_configs(client: PrimaryClient, primary_media_directory: str, reimport: bool) -> List[str]:
    """Copy the primary's synced configs, then import those that changed (all of them when `reimport`, because newly
    downloaded files may let a config import entries it skipped before).  Returns the imported configs."""
    imported = list()
    for file_name, import_ in SYNCED_CONFIG_IMPORTS:
        data = await client.get_bytes(f'config/{file_name}')
        if data is None:
            continue
        config = get_config_by_file_name(file_name)
        _parse_config(data, file_name)
        changed = write_config_bytes(config.get_file(), data, config._get_backup_filename())
        if changed or reimport:
            logger.info(f'Importing {file_name} from the primary')
            await asyncio.to_thread(import_)
            imported.append(file_name)

    if await _sync_inventory_directory(client) or reimport:
        logger.info('Importing inventories from the primary')
        await asyncio.to_thread(_import_inventories)
        imported.append('inventory')

    await _merge_wrolpi_config(client, primary_media_directory)
    return imported


async def _sync_inventory_directory(client: PrimaryClient) -> bool:
    from modules.inventory.common import get_inventory_configs
    inventories = get_inventory_configs()
    directory = inventories.get_directory()
    changed = False
    for entry in await client.list_directory(INVENTORY_DIRECTORY):
        name = entry.get('name') or ''
        if entry.get('is_dir') or not name.endswith('.yaml') or '/' in name or name.startswith('.'):
            continue
        data = await client.get_bytes(f'{INVENTORY_DIRECTORY}/{name}')
        if data is None:
            continue
        _parse_config(data, name)
        backup = inventories._get_backup_filename(name.removesuffix('.yaml'))
        changed = write_config_bytes(directory / name, data, backup) or changed
    return changed


def merge_wrolpi_config(primary_config: dict, primary_media_directory: str) -> dict:
    """The library settings of the primary's wrolpi.yaml that differ from this WROLPi's."""
    wrolpi_config = get_wrolpi_config()
    changes = dict()
    for key in SYNCED_WROLPI_CONFIG_KEYS:
        if key not in primary_config:
            continue
        value = primary_config[key]
        if key == 'ignored_directories':
            value = _relative_directories(value or [], primary_media_directory)
        if wrolpi_config.dict().get(key) != value:
            changes[key] = value
    return changes


def _relative_directories(directories: List[str], primary_media_directory: str) -> List[str]:
    relative = list()
    for directory in directories:
        path = pathlib.PurePosixPath(directory)
        if path.is_absolute():
            try:
                path = path.relative_to(primary_media_directory)
            except ValueError:
                # Outside the primary's media directory; meaningless here.
                continue
        relative.append(str(path))
    return relative


async def _merge_wrolpi_config(client: PrimaryClient, primary_media_directory: str):
    data = await client.get_bytes('config/wrolpi.yaml')
    if data is None:
        return
    if changes := merge_wrolpi_config(_parse_config(data, 'wrolpi.yaml'), primary_media_directory):
        logger.info(f'Applying library settings from the primary: {sorted(changes)}')
        get_wrolpi_config().update(changes)


# ---------------------------------------------------------------------------------------------------------------------
# Secondary: the sync.


def sync_skip_reason() -> Optional[str]:
    """Why a sync cannot start now, or None."""
    config = get_wrolpi_config()
    if not is_secondary():
        return 'This WROLPi is not a secondary'
    if wrol_mode_enabled():
        return 'WROL Mode is enabled'
    if not config.sync_primary_url:
        return 'No primary is configured'
    if not PYTEST:
        if not flags.db_up.is_set():
            return 'The database is not up'
        if not flags.refresh_complete.is_set():
            return 'The first refresh has not finished'
        if config.require_media_mounted and not flags.media_mounted.is_set():
            return 'The media directory is not mounted'
    if flags.sync_running.is_set():
        return 'A sync is already running'
    return None


def request_sync(force: bool = False):
    update_sync_status(requested=True, force=force)


def request_sync_cancel():
    """Stop a running sync between pages, and forget a requested one."""
    from wrolpi.api_utils import api_app
    if 'sync' not in api_app.shared_ctx.status:
        return
    status = get_sync_status()
    if status['state'] == 'running' or status['requested']:
        update_sync_status(cancel_requested=status['state'] == 'running', requested=False)


def _check_cancel():
    if get_sync_status()['cancel_requested']:
        raise SyncCancelled('The sync was cancelled')
    if wrol_mode_enabled():
        raise SyncCancelled('WROL Mode was enabled')


@contextlib.contextmanager
def lock_api():
    """Refuse API requests (see `check_sync_api_lock`) while the library is replaced."""
    from wrolpi.api_utils import api_app
    with flags.sync_running:
        api_app.shared_ctx.sync_api_locked.set()
        try:
            yield
        finally:
            api_app.shared_ctx.sync_api_locked.clear()


async def run_sync(force: bool = False) -> dict:
    """Copy the primary's library to this secondary.  Returns the final status."""
    if reason := sync_skip_reason():
        logger.info(f'Not syncing: {reason}')
        return update_sync_status(last_skip_reason=reason, force=False)

    url = get_wrolpi_config().sync_primary_url
    started_at = now()
    update_sync_status(
        state='running', phase='files', force=False, cancel_requested=False, started_at=started_at.isoformat(),
        finished_at=None, last_error=None, last_skip_reason=None, primary_url=url, primary_version=None,
        groups_seen=0, max_id=0, files_checked=0, files_to_download=0, files_downloaded=0, bytes_downloaded=0,
        files_failed=0, configs_imported=[], disk_full=False,
    )
    logger.warning(f'Syncing from the primary {url}')
    try:
        with lock_api():
            async with PrimaryClient(url) as client:
                info = await client.get_info()
                if info.get('role') != 'primary':
                    raise SyncError(f'{url} is not a primary WROLPi')
                if (info.get('version') or '').strip() != __version__.strip():
                    logger.warning(f'The primary runs WROLPi {info.get("version")}, this is {__version__.strip()}')
                update_sync_status(primary_version=(info.get('version') or '').strip() or None)

                downloaded = await _sync_files(client)
                _check_cancel()

                update_sync_status(phase='configs')
                primary_media_directory = info.get('media_directory') or ''
                imported = await sync_configs(client, primary_media_directory, reimport=bool(downloaded) or force)
    except SyncCancelled as e:
        logger.warning(f'Sync stopped: {e}')
        return update_sync_status(state='idle', phase=None, finished_at=now().isoformat(), last_error=str(e),
                                  cancel_requested=False)
    except Exception as e:
        logger.error('Sync failed', exc_info=e)
        Events.send_sync_failed(f'Sync from the primary failed: {e}')
        return update_sync_status(state='error', phase=None, finished_at=now().isoformat(), last_error=str(e),
                                  cancel_requested=False)

    status = get_sync_status()
    finished_at = now()
    failed = status['files_failed']
    message = f'Synced {len(downloaded)} files from the primary'
    if failed:
        message += f'; {failed} failed'
    if status['disk_full']:
        message += '; the drive is full'
    logger.warning(f'{message} in {(finished_at - started_at).total_seconds():.0f}s')
    if downloaded or failed or imported:
        Events.send_sync_completed(message)
    last_success_at = finished_at.isoformat() if not failed and not status['disk_full'] else status['last_success_at']
    return update_sync_status(state='idle', phase=None, finished_at=finished_at.isoformat(),
                              last_success_at=last_success_at, configs_imported=imported,
                              last_error=f'{failed} files failed' if failed else None)


async def _sync_files(client: PrimaryClient) -> List[pathlib.Path]:
    """Download the files this secondary lacks, and refresh them a page at a time.  Returns the files downloaded."""
    media_directory = get_media_directory()
    downloaded = list()
    groups_seen = files_checked = files_to_download = files_failed = 0
    bytes_downloaded = 0
    disk_full = False

    last_report = 0.0

    def report(force: bool = False):
        nonlocal last_report
        if force or time.monotonic() - last_report >= PROGRESS_INTERVAL_SECONDS:
            last_report = time.monotonic()
            update_sync_status(groups_seen=groups_seen, files_checked=files_checked,
                               files_to_download=files_to_download, files_downloaded=len(downloaded),
                               bytes_downloaded=bytes_downloaded, files_failed=files_failed, disk_full=disk_full)

    def count_bytes(n: int):
        nonlocal bytes_downloaded
        bytes_downloaded += n
        report()

    async for page in client.iter_manifest():
        _check_cancel()
        wanted = list()
        for group in page['groups']:
            groups_seen += 1
            for entry in group['paths']:
                files_checked += 1
                file = ManifestFile(entry['path'], int(entry['size']), float(entry['mtime']))
                destination = resolve_destination(media_directory, file.path)
                if destination is None:
                    logger.warning(f'Refusing to sync {repr(file.path)}')
                    files_failed += 1
                    continue
                if needs_download(destination, file):
                    wanted.append((file, destination))
        files_to_download += len(wanted)
        update_sync_status(max_id=page.get('max_id') or 0)
        report(force=True)

        page_downloaded = list()
        if wanted and not disk_full:
            semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

            async def download(file_: ManifestFile, destination_: pathlib.Path):
                nonlocal disk_full
                async with semaphore:
                    if disk_full:
                        return None
                    try:
                        await download_file(client, file_, destination_, count_bytes)
                        downloaded.append(destination_)
                        return destination_
                    except SyncDiskFull as e:
                        disk_full = True
                        logger.error(str(e))
                    except Exception as e:
                        logger.error(f'Failed to sync {repr(file_.path)}: {e}')
                    return False

            results = await asyncio.gather(*(download(f, d) for f, d in wanted))
            page_downloaded = [i for i in results if i]
            files_failed += sum(1 for i in results if i is False)

        update_sync_status(max_id=page.get('max_id') or 0)
        report(force=True)

        if page_downloaded:
            await _refresh(page_downloaded)

    return downloaded


async def _refresh(paths: List[pathlib.Path]):
    from wrolpi.files.worker import file_worker, FileWorkerJobFailed
    job_id = file_worker.queue_refresh(paths, send_events=False)
    try:
        await file_worker.wait_for_job(job_id, timeout=REFRESH_TIMEOUT_SECONDS)
    except (FileWorkerJobFailed, TimeoutError) as e:
        # The files are in place; a later refresh indexes them.
        logger.error(f'Failed to refresh synced files: {e}')


def sync_is_due(status: dict, local_now: datetime) -> bool:
    """True if the sync window is open and the last sync finished long enough ago."""
    config = get_wrolpi_config()
    start, end = config.sync_window_start, config.sync_window_end
    if not start or not end:
        # No window: only "Sync now".
        return False
    if not is_within_daily_window(start, end, local_now.time()):
        return False
    if not status.get('finished_at'):
        return True
    finished_at = datetime.fromisoformat(status['finished_at'])
    return (local_now - finished_at).total_seconds() >= SYNC_WINDOW_REPEAT_SECONDS


async def sync_tick():
    """Start a sync when one was requested, or when it is due."""
    if not is_secondary():
        return
    status = get_sync_status()
    if wrol_mode_enabled():
        if status['requested']:
            update_sync_status(requested=False, last_skip_reason='WROL Mode is enabled')
        return
    from wrolpi.downloader import DownloadManager
    if not status['requested'] and not sync_is_due(status, DownloadManager._get_local_now()):
        return
    force = status['force']
    update_sync_status(requested=False)
    await run_sync(force=force)
