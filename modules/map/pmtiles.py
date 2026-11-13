"""Read the header and metadata of a PMTiles (version 3) file.

A PMTiles file starts with a fixed 127 byte header, which says where the JSON metadata is.  Neither needs the tile
data, so describing a file is two small reads.

https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
"""
import json
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from wrolpi.common import logger

logger = logger.getChild(__name__)

__all__ = ['read_pmtiles_info', 'classify', 'describe', 'is_searchable',
           'KIND_BASEMAP', 'KIND_OVERLAY', 'KIND_TERRAIN', 'KIND_UNKNOWN']

MAGIC = b'PMTiles'
HEADER_SIZE = 127
# Metadata larger than this (as stored, or once decompressed) is not read; the file is described by its header
# alone.  A map file is something a person downloaded: a few bytes of it must not be able to fill the memory.
MAX_METADATA_SIZE = 16 * 1024 * 1024

COMPRESSION_NONE = 1
COMPRESSION_GZIP = 2

TILE_TYPES = {
    1: 'mvt',
    2: 'png',
    3: 'jpeg',
    4: 'webp',
    5: 'avif',
}

KIND_BASEMAP = 'basemap'
KIND_OVERLAY = 'overlay'
KIND_TERRAIN = 'terrain'
KIND_UNKNOWN = 'unknown'

# A terrain (elevation) file is named, its tiles are images like any other raster file.
TERRAIN_PREFIX = 'terrain-'
# Layers every Protomaps basemap has; the map's basemap theme can only draw this schema.
BASEMAP_LAYERS = frozenset({'earth', 'water', 'roads'})
# Layers the place search index is built from.
SEARCHABLE_LAYERS = frozenset({'places', 'pois'})

# (path, mtime_ns, size) -> info.  A file is only read again when it changes.
_CACHE: Dict[Tuple[str, int, int], Optional[dict]] = dict()


def _tilestats_geometries(metadata: dict) -> Dict[str, str]:
    """The geometry type of each layer, when the file's generator recorded it (tippecanoe does)."""
    tilestats = metadata.get('tilestats')
    layers = tilestats.get('layers') if isinstance(tilestats, dict) else None
    geometries = dict()
    for layer in layers if isinstance(layers, list) else []:
        if isinstance(layer, dict) and layer.get('layer') and isinstance(layer.get('geometry'), str):
            geometries[str(layer['layer'])] = layer['geometry']
    return geometries


def _vector_layers(metadata: dict) -> List[dict]:
    geometries = _tilestats_geometries(metadata)
    layers = []
    vector_layers = metadata.get('vector_layers')
    for layer in vector_layers if isinstance(vector_layers, list) else []:
        if not isinstance(layer, dict) or not layer.get('id'):
            continue
        id_ = str(layer['id'])
        layers.append(dict(
            id=id_,
            minzoom=layer.get('minzoom'),
            maxzoom=layer.get('maxzoom'),
            description=layer.get('description') or None,
            geometry=geometries.get(id_),
        ))
    return layers


def _text(value) -> Optional[str]:
    return str(value) if value not in (None, '') else None


def _gunzip(raw: bytes) -> bytes:
    """Decompress gzip data, refusing to produce more than MAX_METADATA_SIZE."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    data = decompressor.decompress(raw, MAX_METADATA_SIZE)
    if decompressor.unconsumed_tail:
        raise ValueError(f'metadata is larger than {MAX_METADATA_SIZE} bytes')
    return data


def _read(path: Path) -> Optional[dict]:
    with path.open('rb') as fh:
        header = fh.read(HEADER_SIZE)
        if len(header) < HEADER_SIZE or header[:7] != MAGIC or header[7] != 3:
            return None

        metadata_offset, metadata_length = struct.unpack_from('<QQ', header, 24)
        internal_compression, _, tile_type, min_zoom, max_zoom = struct.unpack_from('<5B', header, 97)
        min_lon, min_lat, max_lon, max_lat = (i / 10_000_000 for i in struct.unpack_from('<4i', header, 102))

        metadata = dict()
        if 0 < metadata_length <= MAX_METADATA_SIZE \
                and internal_compression in (COMPRESSION_NONE, COMPRESSION_GZIP):
            fh.seek(metadata_offset)
            raw = fh.read(metadata_length)
            try:
                if internal_compression == COMPRESSION_GZIP:
                    raw = _gunzip(raw)
                metadata = json.loads(raw)
            except (zlib.error, ValueError) as e:
                logger.warning(f'Unable to read PMTiles metadata of {path}: {e}')
            if not isinstance(metadata, dict):
                metadata = dict()

    return dict(
        tile_type=TILE_TYPES.get(tile_type, 'unknown'),
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        bounds=[min_lon, min_lat, max_lon, max_lat],
        title=_text(metadata.get('name')),
        description=_text(metadata.get('description')),
        attribution=_text(metadata.get('attribution')),
        metadata_type=_text(metadata.get('type')),
        vector_layers=_vector_layers(metadata),
    )


def read_pmtiles_info(path: Path) -> Optional[dict]:
    """Describe a PMTiles file from its header and metadata.  Returns None if the file is not a readable PMTiles
    version 3 file; never raises."""
    try:
        stat = path.stat()
    except OSError:
        return None

    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _CACHE:
        try:
            info = _read(path)
        except (OSError, struct.error) as e:
            logger.warning(f'Unable to read PMTiles file {path}: {e}')
            info = None
        # Forget what this path used to be.
        for old in [i for i in _CACHE if i[0] == key[0]]:
            del _CACHE[old]
        _CACHE[key] = info
    info = _CACHE[key]
    return dict(info, vector_layers=[dict(i) for i in info['vector_layers']]) if info else None


def _layer_ids(info: Optional[dict]) -> set:
    return {i['id'] for i in info['vector_layers']} if info else set()


def classify(name: str, info: Optional[dict]) -> str:
    """How the map draws a file: `terrain` (hillshade and contours), `basemap` (Protomaps schema, drawn with the
    basemap theme), `overlay` (anything else, vector or raster), or `unknown` (unreadable, never drawn)."""
    if name.startswith(TERRAIN_PREFIX):
        return KIND_TERRAIN
    if not info:
        return KIND_UNKNOWN
    if info['tile_type'] == 'mvt' and BASEMAP_LAYERS <= _layer_ids(info):
        return KIND_BASEMAP
    return KIND_OVERLAY


def is_searchable(path: Path) -> bool:
    """Whether a place search index can be built from this file."""
    info = read_pmtiles_info(path)
    return classify(path.name, info) == KIND_BASEMAP and bool(SEARCHABLE_LAYERS & _layer_ids(info))


EMPTY_INFO = dict(
    tile_type=None,
    min_zoom=None,
    max_zoom=None,
    bounds=None,
    title=None,
    description=None,
    attribution=None,
    metadata_type=None,
    vector_layers=[],
)


def describe(path: Path) -> dict:
    """The `kind` of a PMTiles file and what its header and metadata say, with empty values for an unreadable
    file."""
    info = read_pmtiles_info(path)
    return dict(info or EMPTY_INFO, kind=classify(path.name, info))
