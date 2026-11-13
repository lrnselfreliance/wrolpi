import json
import tempfile
from pathlib import Path
from typing import List, Dict

from sqlalchemy.orm import Session

from modules.map import pmtiles
from modules.map.catalog import MAP_REGIONS, MAP_REGIONS_BY_NAME, MANIFEST_URL
from modules.map.config import get_maps_config
from wrolpi.common import get_media_directory, walk, logger, get_wrolpi_config, aiohttp_get, verify_gpg_signature
from wrolpi.downloader import DownloadFrequency, Download, save_downloads_config, download_manager

logger = logger.getChild(__name__)


def get_map_directory() -> Path:
    map_directory = get_media_directory() / get_wrolpi_config().map_destination
    if not map_directory.is_dir():
        map_directory.mkdir(parents=True)
    return map_directory


def iter_map_files(suffix: str) -> List[Path]:
    """The files in the map directory (at any depth) whose name ends with `suffix`, sorted.

    Hidden directories are skipped; an unfinished download waits in one under its final name."""
    map_directory = get_map_directory()
    paths = []
    for path in walk(map_directory):
        if not path.name.endswith(suffix) or not path.is_file():
            continue
        if any(i.startswith('.') for i in path.relative_to(map_directory).parts):
            continue
        paths.append(path)
    return sorted(paths)


def get_map_path(path: Path) -> str:
    """The name of a map file in the API and the maps config: its path relative to the map directory."""
    return path.relative_to(get_map_directory()).as_posix()


def get_pmtiles_files() -> List[dict]:
    """Find all .pmtiles files in the map directory and return their metadata."""
    maps_config = get_maps_config()

    files = []
    for path in iter_map_files('.pmtiles'):
        stat = path.stat()
        map_path = get_map_path(path)
        files.append(dict(
            name=path.name,
            path=str(path.relative_to(get_media_directory())),
            map_path=map_path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            has_search_index=path.with_suffix('.search.db').is_file(),
            visible=not maps_config.is_ignored(map_path),
            **pmtiles.describe(path),
        ))

    return files


def _resolve_pmtiles_file(filename: str) -> Path | None:
    """The PMTiles file in the map directory that `filename` (relative to the map directory) names, if it exists.

    Raises ValueError if the name leads outside of the map directory."""
    map_directory = get_map_directory().resolve()
    # Prevent path traversal.
    path = (map_directory / filename).resolve()
    if not path.is_relative_to(map_directory):
        raise ValueError(f'Invalid filename: {filename}')

    if path.is_file() and path.suffix == '.pmtiles':
        return path
    return None


def delete_pmtiles_file(filename: str) -> bool:
    """Delete a PMTiles file from the map directory.  Returns True if the file was deleted.

    Also deletes the companion .search.db file if it exists."""
    path = _resolve_pmtiles_file(filename)
    if not path:
        return False

    map_path = path.relative_to(get_map_directory().resolve()).as_posix()
    path.unlink()
    logger.warning(f'Deleted PMTiles file: {path}')
    # Also delete companion search index.
    search_db = path.with_suffix('.search.db')
    if search_db.is_file():
        search_db.unlink()
        logger.warning(f'Deleted search index: {search_db}')
    # A file that is gone is not ignored; a later file of the same name starts visible.
    get_maps_config().set_ignored(map_path, False)
    return True


def set_pmtiles_file_visible(filename: str, visible: bool) -> bool:
    """Show a PMTiles file on the map, or ignore it.  Returns False if there is no such file."""
    path = _resolve_pmtiles_file(filename)
    if not path:
        return False

    map_path = path.relative_to(get_map_directory().resolve()).as_posix()
    get_maps_config().set_ignored(map_path, not visible)
    return True


def get_map_catalog() -> List[dict]:
    """Return the list of available map regions."""
    return MAP_REGIONS.copy()


def _get_map_download(session: Session) -> Download | None:
    """Find the single recurring map download, if it exists."""
    return session.query(Download).filter_by(url=MANIFEST_URL, downloader='map_catalog').one_or_none()


def _get_or_create_map_download(session: Session) -> Download:
    """Get or create the single recurring map download."""
    download = _get_map_download(session)
    if download:
        return download

    download = download_manager.get_or_create_download(session, MANIFEST_URL, reset_attempts=True,
                                                       override_skip=True)
    download.downloader = 'map_catalog'
    download.frequency = DownloadFrequency.days180
    download.settings = {'regions': []}
    download.location = '/map/manage'
    download.attempts = 0
    session.flush([download])
    return download


def get_map_subscriptions(session: Session) -> List[dict]:
    """Return the list of subscribed regions."""
    regions = []
    download = _get_map_download(session)
    if download and download.settings:
        regions.extend(download.settings.get('regions', []))
    return regions


async def subscribe(session: Session, name: str, region: str):
    """Subscribe to a map region."""
    if name not in MAP_REGIONS_BY_NAME:
        raise ValueError(f'{name!r} is not a valid map region name')

    region_info = MAP_REGIONS_BY_NAME[name]
    if region != region_info['region']:
        raise ValueError(f'Region {region!r} does not match name {name!r}')

    download = _get_or_create_map_download(session)
    regions = list(download.settings.get('regions', []))

    # Don't add duplicates.
    if any(r['region'] == region for r in regions):
        return

    entry = {'region': region}
    if region_info.get('terrain'):
        entry['terrain'] = True

    regions.append(entry)
    download.settings = {**download.settings, 'regions': regions}
    download.renew(reset_attempts=True)
    session.commit()
    save_downloads_config.activate_switch()


async def unsubscribe(session: Session, region: str):
    """Remove a region from the subscriptions."""
    download = _get_map_download(session)
    if not download:
        raise ValueError(f'No map subscriptions exist')

    regions = [r for r in download.settings.get('regions', []) if r['region'] != region]
    if regions:
        download.settings = {**download.settings, 'regions': regions}
    else:
        # No more subscriptions — delete the download.
        session.delete(download)
    session.commit()
    save_downloads_config.activate_switch()


async def fetch_manifest(url: str = None) -> dict:
    """Fetch the map manifest JSON from the CDN and verify its GPG signature."""
    url = url or MANIFEST_URL
    sig_url = f'{url}.sig'

    # Fetch manifest.
    async with aiohttp_get(url, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'Failed to fetch manifest: HTTP {response.status}')
        manifest_bytes = await response.content.read()

    # Fetch detached signature.
    try:
        async with aiohttp_get(sig_url, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f'Failed to fetch manifest signature: HTTP {response.status}')
            signature_bytes = await response.content.read()
    except Exception as e:
        logger.warning(f'Could not fetch manifest signature from {sig_url}: {e}')
        raise RuntimeError(f'Manifest signature not available: {e}')

    # Write to temp files and verify signature against on-disk files.
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / 'manifest.json'
        sig_path = Path(tmpdir) / 'manifest.json.sig'
        manifest_path.write_bytes(manifest_bytes)
        sig_path.write_bytes(signature_bytes)

        if not await verify_gpg_signature(manifest_path, sig_path):
            raise RuntimeError('Manifest GPG signature verification failed — file may be tampered with')

    logger.info('Manifest GPG signature verified successfully')
    return json.loads(manifest_bytes)
