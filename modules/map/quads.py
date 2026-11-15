"""What a quadrangle of the map is called.

The U.S. Geological Survey names each of its 7.5 minute quadrangles, after a town or a mountain or a lake in it
("Berthoud", Colorado).  `quads/usgs_7_5_minute.tsv.gz` is the index of those names, from the Map Indices of
The National Map (public domain); `wrolpi/scripts/build_map_quad_names.py` makes it.

Most of those quadrangles are 7.5 minutes each way, with their edges on whole multiples of 7.5 minutes.  Not all:
in Alaska a quadrangle is wider the further north it is, and around some islands they are moved to fit the land.
So a place is looked for in the quadrangle which has it, and whether that quadrangle is the one asked about is
said too.
"""
import bisect
import gzip
import pathlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

__all__ = ['QuadName', 'quad_name', 'load_index', 'INDEX_PATH']

INDEX_PATH = pathlib.Path(__file__).parent / 'quads' / 'usgs_7_5_minute.tsv.gz'
SECONDS_PER_DEGREE = 3600
# No quadrangle is taller than this (seconds of arc): how far south of a place its quadrangle may start.
TALLEST = 450
# Edges this near (seconds of arc) are the same edge.
SAME_EDGE = 1


@dataclass
class QuadName:
    name: str
    state: str
    # Whether the named quadrangle is the area which was asked about, and not a larger or a moved one which has
    # the middle of it.
    exact: bool

    def __json__(self) -> dict:
        return dict(name=self.name, state=self.state, exact=self.exact)


# The quadrangles which start at one latitude: their west edges in order, and (west, east, north, name, state) of
# each, in the same order.
Row = Tuple[List[int], List[Tuple[int, int, int, str, str]]]


@lru_cache(maxsize=None)
def load_index(path: pathlib.Path = INDEX_PATH) -> Tuple[List[int], Dict[int, str]]:
    """The index: the latitudes (seconds of arc) quadrangles start at, in order, and the lines of the quadrangles
    which start at each.

    The lines are kept as they are written (3 MB; as numbers and names they are 17 MB in each process of the API),
    and are not read until a name is asked for."""
    rows: Dict[int, List[str]] = {}
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        for line in fh:
            rows.setdefault(int(line[:line.index('\t')]), []).append(line)
    return sorted(rows), {south: ''.join(lines) for south, lines in rows.items()}


@lru_cache(maxsize=32)
def _row(south: int) -> Row:
    """The quadrangles which start at a latitude.  Those asked about one after another are near each other, so
    the few rows last read are kept."""
    wests, cells = [], []
    for line in load_index()[1][south].splitlines():
        _, west, east, north, name, state = line.split('\t')
        # The lines are in order, so these are.
        wests.append(int(west))
        cells.append((int(west), int(east), int(north), name, state))
    return wests, cells


def quad_name(west: float, south: float, east: float, north: float) -> Optional[QuadName]:
    """What the USGS calls the quadrangle between these edges (degrees), or None where it has none: most of the
    world."""
    souths, _ = load_index()
    x = (west + east) / 2 * SECONDS_PER_DEGREE
    y = (south + north) / 2 * SECONDS_PER_DEGREE
    edges = [round(i * SECONDS_PER_DEGREE) for i in (west, south, east, north)]
    # The rows which may have the middle of the area, from the nearest to start south of it.
    last = bisect.bisect_right(souths, y)
    for row_south in reversed(souths[max(0, last - 8):last]):
        if row_south < y - TALLEST * 2:
            break
        wests, cells = _row(row_south)
        index = bisect.bisect_right(wests, x) - 1
        # Quadrangles moved to fit an island lie over their neighbors a little, so the one before is looked at too.
        for cell_west, cell_east, cell_north, name, state in cells[max(0, index - 1):index + 1][::-1]:
            if cell_west <= x < cell_east and row_south <= y < cell_north:
                found = [cell_west, row_south, cell_east, cell_north]
                exact = all(abs(a - b) <= SAME_EDGE for a, b in zip(edges, found))
                return QuadName(name=name, state=state, exact=exact)
    return None
