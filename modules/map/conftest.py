import gzip
import json
import struct
from pathlib import Path
from typing import Callable

import pytest

PROTOMAPS_LAYERS = ('boundaries', 'buildings', 'earth', 'landcover', 'landuse', 'places', 'pois', 'roads', 'water')


def pmtiles_bytes(metadata: dict = None, tile_type: int = 1, min_zoom: int = 0, max_zoom: int = 8,
                  bounds: tuple = (-180.0, -85.0, 180.0, 85.0), compress: bool = True) -> bytes:
    """A PMTiles version 3 file with a header and metadata, but no tiles."""
    raw = json.dumps(metadata if metadata is not None else dict()).encode()
    if compress:
        raw = gzip.compress(raw)
    header = bytearray(127)
    header[0:7] = b'PMTiles'
    header[7] = 3
    # Root directory (empty), then the metadata.
    struct.pack_into('<QQ', header, 8, 127, 0)
    struct.pack_into('<QQ', header, 24, 127, len(raw))
    # Clustered, internal compression, tile compression, tile type, zooms.
    struct.pack_into('<6B', header, 96, 1, 2 if compress else 1, 2, tile_type, min_zoom, max_zoom)
    struct.pack_into('<4i', header, 102, *(int(i * 10_000_000) for i in bounds))
    return bytes(header) + raw


def vector_metadata(*layer_ids: str, geometries: dict = None, **metadata) -> dict:
    """PMTiles metadata of a vector file with these layers.  `geometries` are recorded as tippecanoe does."""
    metadata['vector_layers'] = [dict(id=i, fields=dict(name='String'), minzoom=0, maxzoom=8) for i in layer_ids]
    if geometries:
        metadata['tilestats'] = dict(layers=[dict(layer=k, geometry=v, count=1) for k, v in geometries.items()])
    return metadata


@pytest.fixture
def make_pmtiles(test_directory) -> Callable[..., Path]:
    """Create a readable PMTiles file in the media directory.  A file is a Protomaps basemap unless `metadata` (or a
    raster `tile_type`) says otherwise."""

    def _(path: str, metadata: dict = None, **kwargs) -> Path:
        path = test_directory / path
        path.parent.mkdir(parents=True, exist_ok=True)
        if metadata is None and kwargs.get('tile_type', 1) == 1:
            metadata = vector_metadata(*PROTOMAPS_LAYERS, name='Protomaps Basemap', type='baselayer')
        path.write_bytes(pmtiles_bytes(metadata, **kwargs))
        return path

    return _
