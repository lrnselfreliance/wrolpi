import os

import pytest

from modules.map import pmtiles
from modules.map.conftest import pmtiles_bytes, vector_metadata, PROTOMAPS_LAYERS


def test_read_vector_overlay(test_directory, make_pmtiles):
    """The header and metadata of a vector file are read; the bulky tilestats are reduced to a geometry per layer."""
    metadata = vector_metadata(
        'power_lines', 'towers', 'flood_zones',
        geometries=dict(power_lines='LineString', towers='Point'),
        name='Features', description='Topographic features', attribution='Somebody', type='overlay',
    )
    path = make_pmtiles('map/features.pmtiles', metadata, min_zoom=2, max_zoom=9, bounds=(-125.5, 24.0, -66.0, 49.5))

    info = pmtiles.read_pmtiles_info(path)
    assert info == dict(
        tile_type='mvt',
        min_zoom=2,
        max_zoom=9,
        bounds=[-125.5, 24.0, -66.0, 49.5],
        title='Features',
        description='Topographic features',
        attribution='Somebody',
        metadata_type='overlay',
        vector_layers=[
            dict(id='power_lines', minzoom=0, maxzoom=8, description=None, geometry='LineString'),
            dict(id='towers', minzoom=0, maxzoom=8, description=None, geometry='Point'),
            dict(id='flood_zones', minzoom=0, maxzoom=8, description=None, geometry=None),
        ],
    )
    assert pmtiles.classify(path.name, info) == pmtiles.KIND_OVERLAY


def test_read_uncompressed_metadata(test_directory, make_pmtiles):
    """Metadata which is not compressed is read too."""
    path = make_pmtiles('map/plain.pmtiles', vector_metadata('roads', name='Plain'), compress=False)
    info = pmtiles.read_pmtiles_info(path)
    assert info['title'] == 'Plain'
    assert [i['id'] for i in info['vector_layers']] == ['roads']


def test_read_without_metadata(test_directory, make_pmtiles):
    """A raster file may say nothing about itself; it is described by its header."""
    path = make_pmtiles('map/satellite.pmtiles', dict(), tile_type=4, max_zoom=12)
    info = pmtiles.read_pmtiles_info(path)
    assert info['tile_type'] == 'webp'
    assert info['max_zoom'] == 12
    assert info['title'] is None
    assert info['vector_layers'] == []


@pytest.mark.parametrize('content', [
    b'',
    b'PMTiles',
    b'not a pmtiles file' * 20,
    # Version 2 has a different header.
    b'PMTiles\x02' + bytes(200),
])
def test_unreadable_file(test_directory, content):
    """A file which is not a PMTiles version 3 file is not described, and reading it does not raise."""
    path = test_directory / 'broken.pmtiles'
    path.write_bytes(content)
    assert pmtiles.read_pmtiles_info(path) is None
    assert pmtiles.read_pmtiles_info(test_directory / 'missing.pmtiles') is None
    assert pmtiles.classify(path.name, None) == pmtiles.KIND_UNKNOWN
    assert pmtiles.describe(path)['kind'] == pmtiles.KIND_UNKNOWN
    assert pmtiles.describe(path)['vector_layers'] == []


def test_broken_metadata(test_directory):
    """A file whose metadata cannot be decoded is still described by its header."""
    content = bytearray(pmtiles_bytes(vector_metadata('roads', name='Roads')))
    # Corrupt the gzip stream.
    content[127:137] = b'0123456789'
    path = test_directory / 'corrupt.pmtiles'
    path.write_bytes(bytes(content))

    info = pmtiles.read_pmtiles_info(path)
    assert info['tile_type'] == 'mvt'
    assert info['title'] is None
    assert info['vector_layers'] == []


@pytest.mark.parametrize('name,metadata,tile_type,kind', [
    ('usa.pmtiles', vector_metadata(*PROTOMAPS_LAYERS), 1, pmtiles.KIND_BASEMAP),
    # Only the Protomaps schema can be drawn by the basemap theme.
    ('openmaptiles.pmtiles', vector_metadata('water', 'transportation', 'place'), 1, pmtiles.KIND_OVERLAY),
    ('features.pmtiles', vector_metadata('towers'), 1, pmtiles.KIND_OVERLAY),
    ('satellite.pmtiles', dict(), 3, pmtiles.KIND_OVERLAY),
    # Terrain is named; its tiles are images like any raster file.
    ('terrain-planet.pmtiles', dict(), 4, pmtiles.KIND_TERRAIN),
])
def test_classify(test_directory, make_pmtiles, name, metadata, tile_type, kind):
    path = make_pmtiles(f'map/{name}', metadata, tile_type=tile_type)
    assert pmtiles.describe(path)['kind'] == kind


def test_is_searchable(test_directory, make_pmtiles):
    """A search index is built from the place layers of a basemap."""
    assert pmtiles.is_searchable(make_pmtiles('map/usa.pmtiles'))
    assert not pmtiles.is_searchable(make_pmtiles('map/bare.pmtiles', vector_metadata('earth', 'water', 'roads')))
    assert not pmtiles.is_searchable(make_pmtiles('map/features.pmtiles', vector_metadata('places', 'pois')))
    assert not pmtiles.is_searchable(make_pmtiles('map/terrain-x.pmtiles', tile_type=4))


def test_changed_file_is_read_again(test_directory, make_pmtiles):
    """A description is remembered until the file changes."""
    path = make_pmtiles('map/features.pmtiles', vector_metadata('towers', name='Before'))
    assert pmtiles.read_pmtiles_info(path)['title'] == 'Before'

    stat = path.stat()
    make_pmtiles('map/features.pmtiles', vector_metadata('towers', name='After!'))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert pmtiles.read_pmtiles_info(path)['title'] == 'After!'

    # A caller cannot change what is remembered.
    pmtiles.read_pmtiles_info(path)['vector_layers'].clear()
    assert [i['id'] for i in pmtiles.read_pmtiles_info(path)['vector_layers']] == ['towers']


def test_metadata_which_decompresses_too_large(test_directory, make_pmtiles, monkeypatch):
    """A little compressed metadata can decompress to a great deal; it is not decompressed past the limit, and the
    file is described by its header."""
    monkeypatch.setattr(pmtiles, 'MAX_METADATA_SIZE', 10_000)
    small = make_pmtiles('map/small.pmtiles', vector_metadata('roads', name='Small'))
    assert pmtiles.read_pmtiles_info(small)['title'] == 'Small'

    # Compresses to far less than the limit, and decompresses to far more.
    bomb = make_pmtiles('map/bomb.pmtiles', vector_metadata('roads', name='Bomb', padding='0' * 1_000_000))
    assert bomb.stat().st_size < 10_000
    info = pmtiles.read_pmtiles_info(bomb)
    assert info['tile_type'] == 'mvt'
    assert info['title'] is None
    assert info['vector_layers'] == []
