"""Tiles and the blocks they are drawn in.

ATAK and iTAK take 256 px tiles in the Web Mercator "XYZ" scheme.  A tile is drawn as part of a block of 4x4
tiles (one 1024 px image): ATAK asks for the tiles of an area in quadtree order, so 16 requests in a row are of
one block, and a block costs about a third of what its 16 tiles cost drawn alone.  Labels are whole inside a block.
"""
import math
from typing import Iterator, NamedTuple, Tuple

TILE_SIZE = 256
BLOCK = 4  # tiles on a side of a block
# Below this zoom the world is fewer than 4x4 tiles: each is drawn alone (see `render`).
MIN_BLOCK_ZOOM = 2
MAX_ZOOM = 22


class Block(NamedTuple):
    z: int
    x: int  # of the block, not of a tile
    y: int

    def tiles(self) -> Iterator[Tuple[int, int]]:
        """The x, y of each tile of the block."""
        side = BLOCK if self.z >= MIN_BLOCK_ZOOM else 2 ** self.z
        for dy in range(side):
            for dx in range(side):
                yield self.x * side + dx, self.y * side + dy


def is_tile(z: int, x: int, y: int) -> bool:
    return 0 <= z <= MAX_ZOOM and 0 <= x < 2 ** z and 0 <= y < 2 ** z


def block_of(z: int, x: int, y: int) -> Block:
    if z < MIN_BLOCK_ZOOM:
        return Block(z, 0, 0)
    return Block(z, x // BLOCK, y // BLOCK)


def tile_corner(z: int, x: float, y: float) -> Tuple[float, float]:
    """The longitude and latitude of the north-west corner of tile x, y (fractions are inside the tile)."""
    n = 2 ** z
    longitude = x / n * 360 - 180
    latitude = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return longitude, latitude


def block_center(block: Block) -> Tuple[float, float]:
    return tile_corner(block.z, block.x * BLOCK + BLOCK / 2, block.y * BLOCK + BLOCK / 2)
