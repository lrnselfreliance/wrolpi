"""Which map files the tiles are drawn from.

The tiles are of the basemap: the Protomaps files in the map directory, over the planet overview (the world at
zoom 0 to 6) as the web map draws them.  A file is a basemap by the rule of `modules.map.pmtiles.classify`, read
here without importing it (see `tiles`); a test holds the two to the same answer.
"""
import gzip
import json
import os
import struct
import zlib
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

# As `wrolpi.vars`.
MEDIA_DIRECTORY = Path(os.environ.get('MEDIA_DIRECTORY', '/media/wrolpi'))
# Raspberry Pi and Debian installs have it here; the Docker image puts it at the same path.
OVERVIEW = Path('/opt/wrolpi-blobs/map-overview.pmtiles')

PMTILES_MAGIC = b'PMTiles'
PMTILES_HEADER_SIZE = 127
PMTILES_MVT = 1
PMTILES_GZIP = 2
# Larger metadata is not read (as modules.map.pmtiles).
MAX_METADATA_SIZE = 16 * 1024 * 1024
BASEMAP_LAYERS = frozenset({'earth', 'water', 'roads'})
TERRAIN_PREFIX = 'terrain-'


def get_map_directory(media_directory: Path = None) -> Path:
    """The map directory: `map_destination` of wrolpi.yaml (default `map`) in the media directory."""
    media_directory = media_directory or MEDIA_DIRECTORY
    destination = 'map'
    try:
        config = yaml.safe_load((media_directory / 'config/wrolpi.yaml').read_text()) or dict()
        destination = config.get('map_destination') or destination
    except (OSError, yaml.YAMLError, AttributeError):
        pass
    return media_directory / destination


def is_basemap(path: Path) -> bool:
    """Whether a PMTiles file is a Protomaps basemap: vector tiles with the layers the basemap theme draws."""
    if path.name.startswith(TERRAIN_PREFIX):
        return False
    try:
        with path.open('rb') as fh:
            header = fh.read(PMTILES_HEADER_SIZE)
            if len(header) < PMTILES_HEADER_SIZE or not header.startswith(PMTILES_MAGIC) or header[7] != 3:
                return False
            offset, length = struct.unpack_from('<QQ', header, 24)
            compression, tile_type = header[97], header[99]
            if tile_type != PMTILES_MVT or not 0 < length <= MAX_METADATA_SIZE:
                return False
            fh.seek(offset)
            raw = fh.read(length)
        if compression == PMTILES_GZIP:
            raw = gzip.decompress(raw)[:MAX_METADATA_SIZE + 1]
        metadata = json.loads(raw)
        layers = metadata.get('vector_layers') if isinstance(metadata, dict) else None
        ids = {str(i['id']) for i in layers if isinstance(i, dict) and i.get('id')} if isinstance(layers, list) else set()
        return BASEMAP_LAYERS <= ids
    except (OSError, ValueError, EOFError, struct.error, gzip.BadGzipFile):
        return False


def is_drawable(path: Path) -> bool:
    """Whether MapLibre can read a PMTiles file's tiles: its root directory is there and can be decompressed.

    A file it cannot read (empty, cut short, corrupt) fails every tile drawn with it, of every place; such a file
    is left out."""
    try:
        with path.open('rb') as fh:
            header = fh.read(PMTILES_HEADER_SIZE)
            if len(header) < PMTILES_HEADER_SIZE or not header.startswith(PMTILES_MAGIC):
                return False
            offset, length = struct.unpack_from('<QQ', header, 8)
            if not 0 < length <= MAX_METADATA_SIZE:
                return False
            fh.seek(offset)
            raw = fh.read(length)
        if len(raw) != length:
            return False
        if header[97] == PMTILES_GZIP:
            raw = gzip.decompress(raw)
        return len(raw) > 0
    except (OSError, EOFError, struct.error, gzip.BadGzipFile, zlib.error):
        return False


def find_basemaps(map_directory: Path) -> List[Path]:
    """The basemap files in the map directory (at any depth), sorted.  Hidden directories are skipped: an
    unfinished download waits in one."""
    paths = []
    for root, directories, files in os.walk(map_directory):
        directories[:] = sorted(i for i in directories if not i.startswith('.'))
        for name in files:
            path = Path(root) / name
            if name.endswith('.pmtiles') and path.is_file() and is_basemap(path) and is_drawable(path):
                paths.append(path)
    return sorted(paths)


Signature = Tuple[Tuple[str, int, int], ...]


def signature(paths: List[Path]) -> Signature:
    """What changes when a map file is added, removed or replaced."""
    entries = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


def find_maps(map_directory: Path, overview: Optional[Path] = OVERVIEW) -> List[Path]:
    """The files the tiles are drawn from, in the order they are drawn: the overview, then each basemap."""
    maps = find_basemaps(map_directory)
    if overview and overview.is_file() and is_drawable(overview):
        maps.insert(0, overview)
    return maps
