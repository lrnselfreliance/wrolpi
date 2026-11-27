"""Drawing blocks of tiles with MapLibre Native (mapli), in a render process.

Each render process has one MapLibre renderer, made in the process (`init_process`).  It draws with the GPU when
the process may open one (/dev/dri/renderD128; on a Raspberry Pi the user must be in the `render` group), and
otherwise in software, about 20% slower: the work is mostly the CPU's.  No display is needed.
"""
import io
import os
from typing import Dict, Optional, Tuple

from PIL import Image

from tiles.blocks import BLOCK, MIN_BLOCK_ZOOM, TILE_SIZE, Block, block_center

# MapLibre Native needs an OpenGL context; without a display, only Mesa's "surfaceless" platform gives one.
os.environ.setdefault('EGL_PLATFORM', 'surfaceless')

try:
    import mapli
except ImportError:  # mapli has wheels for Linux only.
    mapli = None

# Tiles are JPEG: ATAK and iTAK decode it, it is a seventh of the size of a PNG of a dense tile, and twice as quick
# to make.  The map has no transparency to keep.
JPEG_QUALITY = 85
CONTENT_TYPE = 'image/jpeg'

_renderer = None
_registered = set()


def available() -> bool:
    return mapli is not None


def init_process():
    """Runs once in each render process."""
    global _renderer
    if mapli is None:
        raise RuntimeError('mapli is not installed; the tile service needs it (Linux only)')
    _renderer = mapli.RenderPool(workers=1)


def encode(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.convert('RGB').save(out, 'JPEG', quality=JPEG_QUALITY)
    return out.getvalue()


def blank(color: str) -> bytes:
    """A tile of one color: of nowhere the map files have anything, or when a tile could not be drawn in time."""
    return encode(Image.new('RGB', (TILE_SIZE, TILE_SIZE), color))


def render_block(style_id: str, style: Optional[dict], block: Block) -> Dict[Tuple[int, int], bytes]:
    """Draw a block, return the JPEG of each of its tiles.

    `style` is sent the first time a process is asked for `style_id`; after that it may be None."""
    if style_id not in _registered:
        if style is None:
            raise LookupError(style_id)
        _renderer.register_style(style_id, json=style)
        _registered.add(style_id)

    if block.z < MIN_BLOCK_ZOOM:
        # MapLibre cannot draw a 256 px tile at zoom 0 (its zooms count 512 px tiles), so each tile of a world of
        # fewer than 4x4 is drawn at 512 px and made smaller.
        tiles = dict()
        for x, y in block.tiles():
            raw = _renderer.render_tile(style_id, z=block.z, x=x, y=y, tile_size=TILE_SIZE * 2, output='rgba')
            image = Image.frombytes('RGBA', (TILE_SIZE * 2, TILE_SIZE * 2), raw)
            tiles[(x, y)] = encode(image.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS))
        return tiles

    side = TILE_SIZE * BLOCK
    longitude, latitude = block_center(block)
    # MapLibre's zoom z is of 512 px tiles: the zoom of 256 px tiles less one.
    raw = _renderer.render(style_id, lon=longitude, lat=latitude, zoom=block.z - 1, width=side, height=side,
                           output='rgba')
    image = Image.frombytes('RGBA', (side, side), raw)
    tiles = dict()
    for x, y in block.tiles():
        left = (x - block.x * BLOCK) * TILE_SIZE
        top = (y - block.y * BLOCK) * TILE_SIZE
        tiles[(x, y)] = encode(image.crop((left, top, left + TILE_SIZE, top + TILE_SIZE)))
    return tiles
