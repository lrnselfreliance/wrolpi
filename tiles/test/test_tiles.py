import asyncio
import gzip
import io
import json
import struct
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from modules.map import pmtiles as map_pmtiles
from modules.map.conftest import PROTOMAPS_LAYERS, pmtiles_bytes, vector_metadata
from tiles import maps, render, service as tile_service
from tiles.blocks import BLOCK, Block, block_center, block_of, is_tile, tile_corner
from tiles.cache import TileCache
from tiles.service import TileService, create_app, mobac_xml
from tiles.style import SKIP_SECONDARY, background_color, basemap_layers, build_style, style_id


def write_header_only(path: Path, metadata=None, **kwargs) -> Path:
    """A PMTiles file with a header and metadata but no tiles (as modules.map's tests make)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if metadata is None and kwargs.get('tile_type', 1) == 1:
        metadata = vector_metadata(*PROTOMAPS_LAYERS)
    path.write_bytes(pmtiles_bytes(metadata, **kwargs))
    return path


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n & 0x7f, n >> 7
        out.append(byte | 0x80 if n else byte)
        if not n:
            return bytes(out)


def write_pmtiles(path: Path, metadata: dict = None) -> Path:
    """A PMTiles (version 3) file MapLibre can read: one empty vector tile, of the whole world at zoom 0."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = metadata if metadata is not None else vector_metadata(*PROTOMAPS_LAYERS)
    tile = gzip.compress(b'')
    # One entry: tile id 0, run length 1, its length, offset 0 (written as offset + 1).
    root = gzip.compress(varint(1) + varint(0) + varint(1) + varint(len(tile)) + varint(1))
    raw_metadata = gzip.compress(json.dumps(metadata).encode())
    header = bytearray(127)
    header[0:7] = b'PMTiles'
    header[7] = 3
    root_offset = 127
    metadata_offset = root_offset + len(root)
    tiles_offset = metadata_offset + len(raw_metadata)
    struct.pack_into('<QQQQQQQQ', header, 8, root_offset, len(root), metadata_offset, len(raw_metadata),
                     tiles_offset, 0, tiles_offset, len(tile))
    struct.pack_into('<QQQ', header, 72, 1, 1, 1)
    # Clustered, gzip directories, gzip tiles, vector, zoom 0 to 0.
    struct.pack_into('<6B', header, 96, 1, 2, 2, 1, 0, 0)
    struct.pack_into('<4i', header, 102, -1800000000, -850000000, 1800000000, 850000000)
    path.write_bytes(bytes(header) + root + raw_metadata + tile)
    return path


# Map files.

@pytest.mark.parametrize('name,metadata,kwargs', [
    ('basemap.pmtiles', None, dict()),
    ('uncompressed.pmtiles', None, dict(compress=False)),
    ('roads-only.pmtiles', vector_metadata('roads'), dict()),
    ('overlay.pmtiles', vector_metadata('trails', 'campsites'), dict()),
    ('raster.pmtiles', None, dict(tile_type=2)),
    ('terrain-z0-8.pmtiles', None, dict()),
    ('no-layers.pmtiles', dict(name='x'), dict()),
])
def test_is_basemap_agrees_with_the_map(tmp_path, name, metadata, kwargs):
    """The tile service decides what a basemap is without importing modules.map; both must say the same."""
    path = write_header_only(tmp_path / name, metadata, **kwargs)
    expected = map_pmtiles.classify(path.name, map_pmtiles.read_pmtiles_info(path)) == map_pmtiles.KIND_BASEMAP
    assert maps.is_basemap(path) is expected


def test_is_basemap_unreadable(tmp_path):
    (tmp_path / 'junk.pmtiles').write_bytes(b'not a map')
    (tmp_path / 'empty.pmtiles').write_bytes(b'')
    assert not maps.is_basemap(tmp_path / 'junk.pmtiles')
    assert not maps.is_basemap(tmp_path / 'empty.pmtiles')
    assert not maps.is_basemap(tmp_path / 'missing.pmtiles')


def test_is_drawable(tmp_path):
    """A file MapLibre cannot read would fail every tile, so it is left out."""
    assert maps.is_drawable(write_pmtiles(tmp_path / 'good.pmtiles'))
    # No tiles: an empty root directory.
    assert not maps.is_drawable(write_header_only(tmp_path / 'empty.pmtiles'))
    # Cut short.
    data = (tmp_path / 'good.pmtiles').read_bytes()
    (tmp_path / 'short.pmtiles').write_bytes(data[:140])
    assert not maps.is_drawable(tmp_path / 'short.pmtiles')
    # A corrupt root directory.
    (tmp_path / 'corrupt.pmtiles').write_bytes(data[:127] + b'x' * (len(data) - 127))
    assert not maps.is_drawable(tmp_path / 'corrupt.pmtiles')
    assert not maps.is_drawable(tmp_path / 'missing.pmtiles')

    (tmp_path / 'map').mkdir()
    for name in ('empty.pmtiles', 'short.pmtiles', 'corrupt.pmtiles', 'good.pmtiles'):
        (tmp_path / 'map' / name).write_bytes((tmp_path / name).read_bytes())
    assert maps.find_basemaps(tmp_path / 'map') == [tmp_path / 'map/good.pmtiles']


def test_decompression_is_bounded(tmp_path, monkeypatch):
    """Metadata or a directory which decompresses to more than MAX_METADATA_SIZE is not read."""
    monkeypatch.setattr(maps, 'MAX_METADATA_SIZE', 1000)
    bomb = gzip.compress(b'0' * 100_000)  # small, but 100 KB decompressed
    with pytest.raises(ValueError):
        maps.gunzip(bomb)
    assert maps.gunzip(gzip.compress(b'ok')) == b'ok'
    # Metadata padded past the limit.
    path = write_header_only(tmp_path / 'big.pmtiles', vector_metadata(*PROTOMAPS_LAYERS, padding='x' * 100_000))
    assert not maps.is_basemap(path)


def test_find_maps(tmp_path):
    write_pmtiles(tmp_path / 'map/b.pmtiles')
    write_pmtiles(tmp_path / 'map/region/a.pmtiles')
    write_pmtiles(tmp_path / 'map/.partial/c.pmtiles')  # an unfinished download
    write_pmtiles(tmp_path / 'map/overlay.pmtiles', vector_metadata('trails'))
    write_header_only(tmp_path / 'map/no-tiles.pmtiles')
    overview = write_pmtiles(tmp_path / 'blobs/map-overview.pmtiles')

    assert maps.find_basemaps(tmp_path / 'map') == [tmp_path / 'map/b.pmtiles', tmp_path / 'map/region/a.pmtiles']
    # The overview is under every other file.
    assert maps.find_maps(tmp_path / 'map', overview)[0] == overview
    assert maps.find_maps(tmp_path / 'map', tmp_path / 'missing.pmtiles') == maps.find_basemaps(tmp_path / 'map')


def test_get_map_directory(tmp_path):
    assert maps.get_map_directory(tmp_path) == tmp_path / 'map'
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/wrolpi.yaml').write_text('map_destination: maps/osm\n')
    assert maps.get_map_directory(tmp_path) == tmp_path / 'maps/osm'
    (tmp_path / 'config/wrolpi.yaml').write_text(': not yaml [')
    assert maps.get_map_directory(tmp_path) == tmp_path / 'map'


# Style.

def make_static(directory: Path) -> Path:
    """The map's static directory, with a font installed."""
    (directory / 'fonts/Noto Sans Regular').mkdir(parents=True)
    (directory / 'fonts/Noto Sans Regular/0-255.pbf').write_bytes(b'')
    return directory


def test_build_style_as_the_web_map(tmp_path):
    first, second = tmp_path / 'overview.pmtiles', tmp_path / 'mexico.pmtiles'
    static = make_static(tmp_path / 'static')
    style = build_style([first, second], static=static)

    assert style['sources'] == {
        '0-overview': dict(type='vector', url=f'pmtiles://file://{first}'),
        '1-mexico': dict(type='vector', url=f'pmtiles://file://{second}'),
    }
    ids = [i['id'] for i in style['layers']]
    assert len(ids) == len(set(ids)), 'layer ids must be unique'
    template = basemap_layers('x')
    # Every layer of the first file; the second file's renamed, without what would cover the first.
    assert {'background', 'earth'} <= set(ids)
    assert len(ids) == 2 * len(template) - len(SKIP_SECONDARY)
    assert not {f'1-mexico:{i}' for i in SKIP_SECONDARY} & set(ids)
    assert {i['source'] for i in style['layers'] if i['id'].startswith('1-mexico:')} == {'1-mexico'}
    # Every label is over the ground of every file.
    types = [i['type'] for i in style['layers']]
    assert types.index('symbol') > max(i for i, t in enumerate(types) if t != 'symbol')
    assert style['glyphs'] == f'file://{static}/fonts/{{fontstack}}/{{range}}.pbf'
    assert style['sprite'] == f'file://{static}/sprites/light'


def test_build_style_without_fonts(tmp_path):
    """Without the fonts MapLibre fails every tile with a label; the map is drawn without them."""
    style = build_style([tmp_path / 'a.pmtiles'], static=tmp_path / 'static')
    assert 'glyphs' not in style
    assert style['layers'] and not [i for i in style['layers'] if i['type'] == 'symbol']

    make_static(tmp_path / 'static')
    assert [i for i in build_style([tmp_path / 'a.pmtiles'], static=tmp_path / 'static')['layers']
            if i['type'] == 'symbol']


def test_build_style_without_maps():
    style = build_style([])
    assert style['sources'] == dict()
    assert [i['type'] for i in style['layers']] == ['background']
    assert background_color(style).startswith('#')


def test_style_id():
    style = build_style([Path('/a.pmtiles')])
    assert style_id(style, (('/a.pmtiles', 1, 2),)) == style_id(style, (('/a.pmtiles', 1, 2),))
    assert style_id(style, (('/a.pmtiles', 1, 2),)) != style_id(style, (('/a.pmtiles', 3, 2),))


# Blocks.

def test_blocks():
    assert block_of(15, 7361, 14583) == Block(15, 1840, 3645)
    assert list(Block(15, 1840, 3645).tiles())[0] == (7360, 14580)
    assert len(list(Block(15, 1840, 3645).tiles())) == BLOCK * BLOCK
    # Below zoom 2 the world is the block.
    assert block_of(1, 1, 1) == Block(1, 0, 0)
    assert sorted(Block(1, 0, 0).tiles()) == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert list(Block(0, 0, 0).tiles()) == [(0, 0)]
    # The center of a block is the corner its middle four tiles share.
    assert block_center(Block(15, 1840, 3645)) == tile_corner(15, 7362, 14582)
    assert tile_corner(1, 1, 1) == (0, 0)
    assert is_tile(0, 0, 0) and not is_tile(3, 8, 0) and not is_tile(-1, 0, 0) and not is_tile(30, 0, 0)


# Cache.

def test_cache(tmp_path):
    cache = TileCache(tmp_path / 'cache', max_bytes=10_000, min_free_bytes=0)
    cache.use_style('a')
    cache.put(15, {(1, 2): b'one', (1, 3): b'two'}, 'a')
    assert cache.get(15, 1, 2) == b'one' and cache.get(15, 1, 3) == b'two'
    assert cache.get(15, 9, 9) is None
    assert cache.size == 6

    # Tiles of a style no longer drawn are not kept, and a new style removes the old.
    cache.put(15, {(5, 5): b'old'}, 'gone')
    assert cache.get(15, 5, 5) is None
    cache.use_style('b')
    assert cache.get(15, 1, 2) is None
    assert not (tmp_path / 'cache/a').exists()
    assert cache.size == 0

    # A kept cache is counted again when the service starts.
    cache.put(3, {(0, 0): b'x' * 100}, 'b')
    again = TileCache(tmp_path / 'cache', 10_000, 0)
    again.use_style('b')
    assert again.size == 100


def test_cache_evicts_oldest(tmp_path):
    cache = TileCache(tmp_path / 'cache', max_bytes=1000, min_free_bytes=0)
    cache.use_style('a')
    for x in range(10):
        cache.put(10, {(x, 0): b'x' * 200}, 'a')
        time.sleep(0.01)
    assert cache.size <= 1000 * 0.8
    assert cache.get(10, 9, 0)  # the newest are kept
    assert cache.get(10, 0, 0) is None


def test_cache_disabled_or_disk_full(tmp_path):
    disabled = TileCache(tmp_path / 'off', max_bytes=0, min_free_bytes=0)
    disabled.use_style('a')
    disabled.put(1, {(0, 0): b'x'}, 'a')
    assert disabled.get(1, 0, 0) is None and not (tmp_path / 'off').exists()

    full = TileCache(tmp_path / 'full', max_bytes=1000, min_free_bytes=2 ** 62)
    full.use_style('a')
    full.put(1, {(0, 0): b'x'}, 'a')
    assert full.get(1, 0, 0) is None


# The map source file.

def test_mobac_xml():
    root = ElementTree.fromstring(mobac_xml('http://192.0.2.8:8088', 'WROLPi & Map', 17).encode())
    assert root.tag == 'customMapSource'
    assert root.findtext('name') == 'WROLPi & Map'
    assert root.findtext('url') == 'http://192.0.2.8:8088/tiles/{$z}/{$x}/{$y}.jpg'
    # ATAK requires a maxZoom.
    assert (root.findtext('minZoom'), root.findtext('maxZoom')) == ('0', '17')
    assert root.find('backgroundColor') is None


# The service, with a renderer which draws nothing.

class FakeRenderer:

    def __init__(self, delay: float = 0, fail: bool = False):
        self.delay = delay
        self.fail = fail
        self.blocks = []
        self.lock = threading.Lock()

    def __call__(self, sid, style, block):
        with self.lock:
            self.blocks.append(block)
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError('cannot draw')
        return {(x, y): f'{block.z}/{x}/{y}'.encode() for x, y in block.tiles()}


@pytest.fixture
def make_service(tmp_path, monkeypatch):
    """A TileService drawing in threads with a fake renderer."""
    services = []

    async def _(renderer: FakeRenderer = None, processes: int = 2, cache_bytes: int = 0) -> TileService:
        monkeypatch.setattr(render, 'render_block', renderer or FakeRenderer())
        write_pmtiles(tmp_path / 'map/basemap.pmtiles')
        cache = TileCache(tmp_path / 'cache', cache_bytes, 0)
        service = TileService(tmp_path / 'map', cache, processes=processes, overview=None)
        monkeypatch.setattr(service, '_new_executor', lambda: ThreadPoolExecutor(processes))
        await service.start()
        services.append(service)
        return service

    yield _
    for service in services:
        service.executor.shutdown(wait=False, cancel_futures=True)
        for task in service.tasks:
            task.cancel()


async def test_service_draws_a_block_once(make_service):
    """ATAK asks for 4 tiles at a time, all of one block; the block is drawn once."""
    renderer = FakeRenderer(delay=0.1)
    service = await make_service(renderer)
    tiles = [(x, y) for x in range(8, 12) for y in range(20, 24)]
    results = await asyncio.gather(*(service.tile(15, x, y, 'phone') for x, y in tiles))

    assert renderer.blocks == [Block(15, 2, 5)]
    assert [data for data, _ in results] == [f'15/{x}/{y}'.encode() for x, y in tiles]
    assert all(keep for _, keep in results)


async def test_service_serves_phones_in_turn(make_service):
    """A phone downloading many blocks does not keep another's tiles waiting behind all of them."""
    renderer = FakeRenderer(delay=0.05)
    service = await make_service(renderer, processes=1)
    downloading = [asyncio.create_task(service.tile(15, 4 * i, 0, 'downloading')) for i in range(10)]
    await asyncio.sleep(0)
    other = await service.tile(15, 0, 400, 'browsing')

    assert other[0] == b'15/0/400'
    assert renderer.blocks.index(Block(15, 0, 100)) <= 2
    await asyncio.gather(*downloading)


async def test_service_late_tile_is_blank(make_service, monkeypatch):
    """A tile not drawn before ATAK gives up on it is sent blank and not kept; it is drawn for the next ask."""
    monkeypatch.setattr(tile_service, 'DEADLINE', 0.05)
    service = await make_service(FakeRenderer(delay=0.3), cache_bytes=10_000)

    data, keep = await service.tile(12, 1, 1, 'phone')
    assert (data, keep) == (service.blank_tile, False)
    await asyncio.sleep(0.5)
    assert await service.tile(12, 1, 1, 'phone') == (b'12/1/1', True)
    assert service.stats['tiles_late'] == 1 and service.stats['tiles_cached'] == 1


async def test_service_failed_tile_is_blank(make_service):
    """Never an error: five failed tiles in a row stop an ATAK download."""
    service = await make_service(FakeRenderer(fail=True))
    assert await service.tile(12, 1, 1, 'phone') == (service.blank_tile, False)
    assert await service.tile(12, 99, 99, 'phone') == (service.blank_tile, False)
    assert await service.tile(3, 8, 8, 'phone') == (service.blank_tile, False)  # not a tile


async def test_service_new_map_file(make_service, tmp_path):
    service = await make_service()
    first = service.style_id
    assert not service.refresh_maps()
    write_pmtiles(tmp_path / 'map/another.pmtiles')
    assert service.refresh_maps()
    assert service.style_id != first and len(service.maps) == 2


async def test_service_drops_tiles_a_phone_gave_up_on(make_service, monkeypatch):
    monkeypatch.setattr(tile_service, 'MAX_QUEUED_PER_CLIENT', 2)
    monkeypatch.setattr(tile_service, 'DEADLINE', 1)
    service = await make_service(FakeRenderer(delay=0.2), processes=1)
    results = await asyncio.gather(*(service.tile(15, 4 * i, 0, 'phone') for i in range(5)))
    assert service.stats['blocks_dropped'] >= 1
    assert (service.blank_tile, False) in results


async def test_service_http(make_service):
    service = await make_service()
    app = create_app(service, name=f'tiles_{uuid.uuid4().hex}')
    # The service is started by the fixture.
    app.ctx.service.start = app.ctx.service.stop = lambda: asyncio.sleep(0)

    headers = {'x-forwarded-proto': 'https', 'x-forwarded-host': 'wrolpi.local', 'x-forwarded-for': '192.0.2.34'}
    _, resp = await app.asgi_client.get('/tiles/wrolpi.xml', headers=headers)
    assert resp.status == 200
    root = ElementTree.fromstring(resp.body)
    assert root.findtext('url') == 'https://wrolpi.local/tiles/{$z}/{$x}/{$y}.jpg'
    assert root.findtext('name') == 'WROLPi Map (HTTPS)'
    assert 'wrolpi-map-https.xml' in resp.headers['content-disposition']

    _, resp = await app.asgi_client.get('/tiles/10/5/6.jpg', headers=headers)
    assert resp.status == 200 and resp.body == b'10/5/6'
    assert resp.headers['content-type'] == 'image/jpeg'
    assert 'max-age' in resp.headers['cache-control']

    _, resp = await app.asgi_client.get('/tiles/10/5/6.png')
    assert resp.status == 404

    _, resp = await app.asgi_client.get('/tiles/status')
    assert resp.status == 200
    assert resp.json['clients'][0]['client'] == '192.0.2.34'
    assert resp.json['stats']['blocks_drawn'] >= 1


# Real drawing.  mapli has wheels for Linux only: everywhere WROLPi runs.

@pytest.mark.skipif(sys.platform != 'linux', reason='mapli is Linux-only')
def test_render_block(tmp_path):
    render.init_process()
    style = build_style([write_pmtiles(tmp_path / 'overview.pmtiles'), write_pmtiles(tmp_path / 'basemap.pmtiles')])
    tiles = render.render_block('test', style, Block(15, 1840, 3645))
    assert set(tiles) == set(Block(15, 1840, 3645).tiles())
    image = Image.open(io.BytesIO(tiles[(7360, 14580)]))
    assert image.format == 'JPEG' and image.size == (256, 256)
    # The files have no features: every tile is the background.
    expected = tuple(int(background_color(style)[i:i + 2], 16) for i in (1, 3, 5))
    assert all(abs(a - b) <= 3 for a, b in zip(image.getpixel((128, 128)), expected))

    world = render.render_block('test', style, Block(1, 0, 0))
    assert len(world) == 4 and Image.open(io.BytesIO(world[(1, 1)])).size == (256, 256)

    # Without map files, the background alone.
    empty = render.render_block('empty', build_style([]), Block(0, 0, 0))
    assert Image.open(io.BytesIO(empty[(0, 0)])).size == (256, 256)
