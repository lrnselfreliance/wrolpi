"""The API's side of a secondary WROLPi copying its primary.

The Controller runs a sync (controller/lib/sync.py): it stops this API, copies the primary's whole media directory
with rsync from the primary's daemon (controller/rsyncd.conf), puts the primary's database snapshot
(wrolpi.sync.snapshot) in place, and starts this API again.  What is left here:

- what a primary tells a secondary about itself (`get_sync_info`),
- the secondary's settings: its primary's address and the folders it does not copy,
- the primary's library settings, which a secondary's API takes from the primary's wrolpi.yaml when it starts
  (`apply_primary_wrolpi_config`),
- the daily window, which the backup drive uses too.
"""
import json
import os
import pathlib
import posixpath
import ssl
from datetime import datetime
from http import HTTPStatus
from typing import List, Optional
from urllib.parse import quote, urlparse

import aiohttp
import yaml
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import logger, get_media_directory, get_wrolpi_config, is_secondary
from wrolpi.dates import is_within_daily_window
from wrolpi.errors import InvalidConfig
from wrolpi.sync.config import get_sync_config
from wrolpi.vars import DEFAULT_HTTP_HEADERS
from wrolpi.version import __version__

logger = logger.getChild(__name__)

# How often a running backup reports its progress.
PROGRESS_INTERVAL_SECONDS = 2.0
# Answers and directory listings are small; never read more than this from the primary.
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024
# Enough for any real library; keeps a pasted list from growing without bound.
MAX_EXCLUDED_DIRECTORIES = 500

# Top-level folders that cannot be excluded: the configs and database, and the Tags Directory (hard links that the
# secondary rebuilds).
PROTECTED_DIRECTORIES = frozenset({'config', 'tags'})
# Top-level folders never offered for exclusion: the protected ones, and the root-only folder of every ext4 drive.
UNLISTED_DIRECTORIES = PROTECTED_DIRECTORIES | {'lost+found'}

# wrolpi.yaml keys that describe the library rather than this machine (hotspot, timezone, etc. stay local; the role
# and other sync settings are in sync.yaml, which is never synced).
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


# ---------------------------------------------------------------------------------------------------------------------
# Primary: what it tells a secondary.


def _is_protected(name: str) -> bool:
    """True if the top-level folder `name` is a protected one.  Case is ignored: on a drive that ignores case (exFAT,
    NTFS, macOS) 'Config' is the real config folder."""
    return name.casefold() in PROTECTED_DIRECTORIES


def _is_unlisted(name: str) -> bool:
    return name.casefold() in UNLISTED_DIRECTORIES


def get_sync_info(session: Session) -> dict:
    from wrolpi.files.models import FileGroup
    return dict(
        version=__version__.strip(),
        role=get_sync_config().role,
        media_directory=str(get_media_directory()),
        max_file_group_id=session.execute(select(func.max(FileGroup.id))).scalar() or 0,
        # A secondary that replaces its database with this one must run code of the same migration.
        database_revision=_database_revision(session),
        # An unmounted media directory looks like an empty library.
        media_mounted=bool(flags.media_mounted.is_set()),
    )


def _database_revision(session: Session) -> Optional[str]:
    try:
        return session.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except OperationalError:
        return None


# ---------------------------------------------------------------------------------------------------------------------
# Secondary: its primary, and the folders it does not copy.


def resolve_destination(media_directory: pathlib.Path, path: str) -> Optional[pathlib.Path]:
    """The secondary's path for a manifest path, or None if the path must not be written: outside the media directory,
    hidden, protected, or reached through a symlink."""
    if not path or path.startswith('/') or '\\' in path:
        return None
    parts = pathlib.PurePosixPath(path).parts
    if not parts or any(i in ('.', '..') or i.startswith('.') for i in parts):
        return None
    if _is_protected(parts[0]):
        return None
    media_directory = media_directory.resolve()
    destination = media_directory.joinpath(*parts)
    # A symlink anywhere on the way (or the file itself) resolves elsewhere.
    if pathlib.Path(os.path.realpath(destination)) != destination:
        return None
    return destination


def normalize_excluded_directories(values: List[str]) -> List[str]:
    """Excluded folders as '/'-separated paths relative to the media directory, without duplicates or folders that
    are already inside another excluded folder."""
    if len(values) > MAX_EXCLUDED_DIRECTORIES:
        raise InvalidConfig(f'No more than {MAX_EXCLUDED_DIRECTORIES} folders can be excluded')
    directories = set()
    for value in values:
        if not isinstance(value, str) or '\\' in value or '\x00' in value:
            raise InvalidConfig(f'Invalid folder: {value!r}')
        stripped = value.strip().strip('/')
        # Reject '..' before normalizing, which would quietly resolve it.
        parts = [i for i in stripped.split('/') if i] if stripped else []
        directory = posixpath.normpath(stripped) if stripped else ''
        if not parts or any(i.startswith('.') for i in parts):
            raise InvalidConfig(f'Invalid folder: {value!r}')
        if _is_protected(parts[0]):
            raise InvalidConfig(f'{parts[0]} is never copied')
        directories.add(directory)
    return sorted(i for i in directories if not any(is_excluded(i, {j}) for j in directories if j != i))


def is_excluded(path: str, excluded_directories) -> bool:
    """True if `path` (relative, '/'-separated) is an excluded folder or inside one."""
    return any(path == i or path.startswith(f'{i}/') for i in excluded_directories)


def list_local_directories(path: str) -> List[dict]:
    """The folders directly inside `path` (relative to the media directory) that a user may exclude."""
    media_directory = get_media_directory().resolve()
    path = (path or '').strip('/')
    directory = resolve_destination(media_directory, path) if path else media_directory
    if directory is None or not directory.is_dir():
        raise InvalidConfig(f'Not a folder: {path!r}')
    directories = list()
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name.startswith('.') or not entry.is_dir(follow_symlinks=False):
                continue
            if not path and _is_unlisted(entry.name):
                continue
            directories.append(dict(name=entry.name, path=f'{path}/{entry.name}' if path else entry.name))
    return sorted(directories, key=lambda i: i['name'].lower())


async def list_primary_directories(path: str) -> List[dict]:
    """The folders directly inside `path` in the primary's media directory (Caddy's browse listing)."""
    path = (path or '').strip('/')
    if path and resolve_destination(get_media_directory(), path) is None:
        raise InvalidConfig(f'Not a folder: {path!r}')
    async with PrimaryClient(get_sync_config().primary_url) as client:
        entries = await client.list_directory(path)
    directories = list()
    for entry in entries:
        name = (entry.get('name') or '').rstrip('/')
        if not entry.get('is_dir') or not name or name.startswith('.') or '/' in name:
            continue
        if not path and _is_unlisted(name):
            continue
        directories.append(dict(name=name, path=f'{path}/{name}' if path else name))
    return sorted(directories, key=lambda i: i['name'].lower())


def make_sync_ssl_context() -> ssl.SSLContext:
    """WROLPi serves HTTPS with its own certificate authority; on a trusted LAN (see the Bookshelf threat model) the
    primary is not verified."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def normalize_primary_url(url: str) -> str:
    """'https://host[:port]' with no path; raises ValueError otherwise."""
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
    async for chunk in response.content.iter_chunked(READ_CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > MAX_RESPONSE_BYTES:
            raise SyncError(f'{path} is larger than {MAX_RESPONSE_BYTES} bytes')
    return bytes(data)


class PrimaryClient:
    """Asks a primary WROLPi about itself (Test Connection) and lists its folders (to choose which are not copied).
    The sync itself is the Controller's, by rsync."""

    def __init__(self, url: str):
        self.url = normalize_primary_url(url)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        ssl_context = make_sync_ssl_context() if self.url.startswith('https') else False
        timeout = aiohttp.ClientTimeout(total=60, connect=30)
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context), timeout=timeout,
                                             headers=DEFAULT_HTTP_HEADERS)
        return self

    async def __aexit__(self, *exc):
        await self.session.close()

    async def get_info(self) -> dict:
        path = '/api/sync/info'
        async with self.session.get(f'{self.url}{path}') as response:
            if response.status != HTTPStatus.OK:
                raise SyncError(f'{path} returned HTTP {response.status}')
            return json.loads(await _read_limited(response, path))

    async def list_directory(self, path: str) -> List[dict]:
        """The entries of a directory in the primary's media directory (Caddy's browse listing), [] if missing."""
        url = f'{self.url}/media/{quote(path.rstrip("/") + "/")}'
        async with self.session.get(url, headers={'Accept': 'application/json'}) as response:
            if response.status == HTTPStatus.NOT_FOUND:
                return []
            if response.status != HTTPStatus.OK:
                raise SyncError(f'{path} returned HTTP {response.status}')
            return json.loads(await _read_limited(response, path))


# ---------------------------------------------------------------------------------------------------------------------
# Secondary: the primary's library settings.


def _parse_config(data: bytes, name: str) -> dict:
    config = yaml.safe_load(data)
    if not isinstance(config, dict):
        raise SyncError(f'{name} from the primary is not a config')
    return config


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


# Where the Controller's sync (controller/lib/sync.py) leaves the primary's wrolpi.yaml and /api/sync/info.
PRIMARY_WROLPI_CONFIG = 'config/.sync/primary-wrolpi.yaml'
PRIMARY_INFO = 'config/.sync/primary-info.yaml'


def apply_primary_wrolpi_config() -> List[str]:
    """A secondary's wrolpi.yaml is its own (hotspot, timezone), except for the settings that describe the library:
    those are taken from the copy of the primary's wrolpi.yaml that the last sync left.  Returns the changed keys."""
    if not is_secondary():
        return []
    media_directory = get_media_directory()
    try:
        primary_config = _parse_config((media_directory / PRIMARY_WROLPI_CONFIG).read_bytes(), 'wrolpi.yaml')
        info = yaml.safe_load((media_directory / PRIMARY_INFO).read_text()) or {}
    except (OSError, yaml.YAMLError, SyncError) as e:
        if not isinstance(e, FileNotFoundError):
            logger.error(f"Could not read the primary's wrolpi.yaml: {e}")
        return []
    changes = merge_wrolpi_config(primary_config, str(info.get('media_directory') or media_directory))
    if changes:
        logger.info(f'Applying library settings from the primary: {sorted(changes)}')
        get_wrolpi_config().update(changes)
    return sorted(changes)


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


# ---------------------------------------------------------------------------------------------------------------------
# The daily window (the backup drive's; the Controller has its own for the sync).


def window_is_due(status: dict, local_now: datetime, start: Optional[str], end: Optional[str],
                  repeat_seconds: int) -> bool:
    """True if the daily window from `start` to `end` is open and the last run (described by `status`) finished
    `repeat_seconds` ago.  No window: never (only on request)."""
    if not start or not end:
        return False
    if not is_within_daily_window(start, end, local_now.time()):
        return False
    if not status.get('finished_at'):
        return True
    finished_at = datetime.fromisoformat(status['finished_at'])
    return (local_now - finished_at).total_seconds() >= repeat_seconds


