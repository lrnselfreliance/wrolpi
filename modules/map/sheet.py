"""The sheet an exported map is printed on: what a topographic map has around and over the map itself.

Around the map is a margin with a title, the latitude and longitude of the map's corners and of ticks along its
edges, scale bars, and notes (the projection, the grid, where the map's data is from).  Over the map is a grid of
1,000 meter squares (Universal Transverse Mercator), which is how a position is read from, or found on, paper.

All of it is drawn as lines and text, in PDF layers of its own which a reader can turn off.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

__all__ = ['Sheet', 'SheetPlan', 'plan_sheet', 'draw_sheet', 'to_utm', 'from_utm', 'utm_zone', 'map_scale',
           'format_angle', 'graticule_interval', 'SHEET_LAYER', 'GRID_LAYER']

# The names of the sheet's PDF layers.
SHEET_LAYER = 'Sheet'
GRID_LAYER = 'UTM grid'

# The WGS 84 ellipsoid.
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)

# Universal Transverse Mercator.
UTM_SCALE = 0.9996
UTM_FALSE_EASTING = 500_000.0
UTM_FALSE_NORTHING_SOUTH = 10_000_000.0
# Where UTM is used: nearer the poles than this, positions are given another way.
UTM_SOUTH, UTM_NORTH = -80.0, 84.0
GRID_METERS = 1000
# More lines than this across a map are too many to read; the squares are made ten times larger until there are
# fewer.
GRID_MAX_LINES = 60

POINTS_PER_INCH = 72
METERS_PER_POINT = 0.0254 / POINTS_PER_INCH
METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048

# The sizes of the sheet, in points.
MARGIN = 54
TOP_MARGIN = 64
FONT = 'helv'
BOLD = 'hebo'
TITLE_SIZE = 13
# Between two lines of the title, and the least there is between the name and the scale on one line.
TITLE_LEADING = 18
TITLE_GAP = 18
LABEL_SIZE = 6.5
NOTE_SIZE = 7
NOTE_LEADING = 9.5
BAR_HEIGHT = 4
BAR_SPACING = 27
# From the bottom of the map to the first scale bar, and from the last note to the bottom of the page.
BARS_OFFSET = 52
BOTTOM_PADDING = 36
TICK_LENGTH = 7
CROSS_LENGTH = 5
BLACK = (0, 0, 0)
GRID_COLOR = (0.1, 0.2, 0.55)

# The spacings a map's ticks of latitude and longitude may have, in seconds of arc.
GRATICULE_INTERVALS = (36000, 18000, 3600, 1800, 900, 450, 300, 150, 60, 30, 15, 5, 1)


@dataclass
class Sheet:
    """What the browser says of a map, to be written around it."""
    # What the map is called.
    name: Optional[str] = None
    # Where the data of the map is from.
    credits: Sequence[str] = ()
    # When the map was made, as it is to be written.
    date: Optional[str] = None


@dataclass
class SheetPlan:
    """Where everything on a sheet goes.  Lengths are points; `y` is down the page from its top."""
    width: float
    height: float
    # The rectangle of the page the map is in: left, top, right, bottom.
    map_rect: Tuple[float, float, float, float]
    # The west, south, east and north edges of the map.
    bounds: Tuple[float, float, float, float]
    # How many times larger the ground is than the map, at the middle of the map.
    scale: float
    name: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    # The UTM zone the map's grid is of, or None where there is no grid.
    zone: Optional[int] = None

    @property
    def south_hemisphere(self) -> bool:
        return (self.bounds[1] + self.bounds[3]) / 2 < 0

    def point(self, latitude: float, longitude: float) -> Tuple[float, float]:
        """Where on the page a place is.  The map is Web Mercator."""
        x0, y0, x1, y1 = self.map_rect
        west, south, east, north = self.bounds
        top, bottom = _mercator_y(north), _mercator_y(south)
        return (x0 + (longitude - west) / (east - west) * (x1 - x0),
                y0 + (top - _mercator_y(latitude)) / (top - bottom) * (y1 - y0))


def _mercator_y(latitude: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))


def _middle_latitude(south: float, north: float) -> float:
    """The latitude half way up a Web Mercator map."""
    y = (_mercator_y(south) + _mercator_y(north)) / 2
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


def map_scale(width: float, bounds: Sequence[float]) -> float:
    """How many times larger the ground is than a map `width` points wide, at the middle of the map."""
    west, south, east, north = bounds
    latitude = math.radians(_middle_latitude(south, north))
    meters_per_degree = math.radians(1) * WGS84_A * math.cos(latitude) \
        / math.sqrt(1 - WGS84_E2 * math.sin(latitude) ** 2)
    return meters_per_degree * (east - west) / (width * METERS_PER_POINT)


# Universal Transverse Mercator, by the series of Krüger (as Karney gives them), which is good to well under a
# millimeter within a zone.
_N = WGS84_F / (2 - WGS84_F)
_RADIUS = WGS84_A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16, 13 * _N ** 2 / 48 - 3 * _N ** 3 / 5, 61 * _N ** 3 / 240)
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480)
_DELTA = (2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15)


def utm_zone(longitude: float) -> int:
    """The UTM zone (1 to 60) a longitude is in.  The zones are six degrees wide, everywhere: those which are
    made wider around Norway and Svalbard are not."""
    return min(60, int((longitude + 180) // 6) + 1)


def _central_meridian(zone: int) -> float:
    return math.radians(zone * 6 - 183)


def to_utm(latitude: float, longitude: float, zone: int, south: bool = False) -> Tuple[float, float]:
    """The easting and northing (meters) of a place, in a UTM zone of WGS 84."""
    phi = math.radians(latitude)
    lam = math.radians(longitude) - _central_meridian(zone)
    c = 2 * math.sqrt(_N) / (1 + _N)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    northing = xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    easting = eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    return (UTM_FALSE_EASTING + UTM_SCALE * _RADIUS * easting,
            (UTM_FALSE_NORTHING_SOUTH if south else 0) + UTM_SCALE * _RADIUS * northing)


def from_utm(easting: float, northing: float, zone: int, south: bool = False) -> Tuple[float, float]:
    """The latitude and longitude (degrees of WGS 84) of a place in a UTM zone."""
    xi = (northing - (UTM_FALSE_NORTHING_SOUTH if south else 0)) / (UTM_SCALE * _RADIUS)
    eta = (easting - UTM_FALSE_EASTING) / (UTM_SCALE * _RADIUS)
    xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    chi = math.asin(math.sin(xi_) / math.cosh(eta_))
    phi = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, 1))
    lam = _central_meridian(zone) + math.atan2(math.sinh(eta_), math.cos(xi_))
    return math.degrees(phi), math.degrees(lam)


def format_angle(degrees: float, positive: str = '', negative: str = '', short: bool = False) -> str:
    """An angle in degrees, minutes and seconds, as a sheet has it: 61°07'30".  The seconds are left out when
    there are none.  `short` leaves the degrees out too (07'30"), as the ticks between a map's corners do."""
    seconds = round(abs(degrees) * 3600)
    d, m, s = seconds // 3600, seconds // 60 % 60, seconds % 60
    text = f"{m:02d}'" if short else f"{d}°{m:02d}'"
    if s:
        text += f'{s:02d}"'
    return text + (negative if degrees < 0 else positive)


def graticule_interval(span: float) -> float:
    """How far apart (degrees) the ticks of latitude and longitude are on a map `span` degrees across: the
    largest spacing which divides it in three or more.  A 7.5 minute map has a tick every 2.5 minutes."""
    for seconds in GRATICULE_INTERVALS:
        if seconds * 3 <= round(span * 3600):
            return seconds / 3600
    return GRATICULE_INTERVALS[-1] / 3600


def _multiples(interval: float, low: float, high: float) -> List[float]:
    """The multiples of `interval` between `low` and `high`, and not at either."""
    first = math.floor(low / interval) + 1
    values = []
    for i in range(first, first + 100_000):
        value = i * interval
        if value >= high - interval * 1e-6:
            break
        if value > low + interval * 1e-6:
            values.append(value)
    return values


def _latin(text: str) -> str:
    """Text as the sheet's font can write it."""
    for old, new in (('′', "'"), ('″', '"'), ('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'), ('–', '-'),
                     ('—', '-'), (' ', ' ')):
        text = text.replace(old, new)
    text = ' '.join(text.split())
    return text.encode('latin-1', 'replace').decode('latin-1')


def _text_width(text: str, size: float, font: str = FONT) -> float:
    # Not imported at module level: see build_layered_pdf.
    import pymupdf
    return pymupdf.get_text_length(text, fontname=font, fontsize=size)


def _wrap(text: str, width: float, size: float) -> List[str]:
    """The lines of `text`, none wider than `width`."""
    lines, line = [], ''
    for word in text.split():
        longer = f'{line} {word}' if line else word
        if line and _text_width(longer, size) > width:
            lines.append(line)
            line = word
        else:
            line = longer
    return lines + [line] if line else lines


def _grid_convergence(latitude: float, longitude: float, zone: int, south: bool) -> float:
    """How far east of true north (degrees) the grid's north is at a place."""
    easting, northing = to_utm(latitude, longitude, zone, south)
    lat, lon = from_utm(easting, northing + 1000, zone, south)
    return math.degrees(math.atan2(math.radians(lon - longitude) * math.cos(math.radians(latitude)),
                                   math.radians(lat - latitude)))


def _format_scale(scale: float) -> str:
    """1:24,000.  A map's scale is not known closer than three figures."""
    digits = max(0, math.floor(math.log10(scale)) - 2)
    return f'1:{round(scale / 10 ** digits) * 10 ** digits:,}'


def _grid_meters(plan: 'SheetPlan') -> int:
    """How far apart the lines of the map's grid are."""
    (low_e, high_e), (low_n, high_n) = _utm_extent(plan)
    meters = GRID_METERS
    while (high_e - low_e) / meters > GRID_MAX_LINES or (high_n - low_n) / meters > GRID_MAX_LINES:
        meters *= 10
    return meters


def _utm_extent(plan: 'SheetPlan') -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """The least and greatest easting, and northing, on the map."""
    west, south, east, north = plan.bounds
    places = [to_utm(lat, lon, plan.zone, plan.south_hemisphere)
              for lat in (south, (south + north) / 2, north) for lon in (west, (west + east) / 2, east)]
    eastings, northings = [i[0] for i in places], [i[1] for i in places]
    return (min(eastings), max(eastings)), (min(northings), max(northings))


def plan_sheet(map_width: float, map_height: float, bounds: Sequence[float], sheet: Sheet) -> SheetPlan:
    """Where a map of `map_width` by `map_height` points, between `bounds` (west, south, east, north), goes on a
    sheet, and what is written under it."""
    west, south, east, north = bounds
    plan = SheetPlan(width=0, height=0, map_rect=(0, 0, 0, 0), bounds=(west, south, east, north),
                     scale=map_scale(map_width, bounds), name=_latin(sheet.name) if sheet.name else None)
    middle = _middle_latitude(south, north), (west + east) / 2
    if south >= UTM_SOUTH and north <= UTM_NORTH:
        plan.zone = utm_zone(middle[1])

    notes = [f'Scale {_format_scale(plan.scale)} at the middle of the map.  Projection: Web Mercator.'
             f'  Datum: WGS 84.  True north is up the page.']
    if plan.zone:
        convergence = _grid_convergence(*middle, plan.zone, plan.south_hemisphere)
        notes.append(
            f'{_grid_meters(plan):,} meter grid: Universal Transverse Mercator, zone {plan.zone}'
            f'{"S" if plan.south_hemisphere else "N"}.  Grid north is {format_angle(abs(convergence))}'
            f' {"west" if convergence < 0 else "east"} of true north at the middle of the map.')
    names = [_latin(str(i)) for i in sheet.credits if str(i).strip()]
    if names:
        notes.append('Map data: ' + '; '.join(names))
    notes.append(f'Made with WROLPi, {_latin(sheet.date)}.' if sheet.date else 'Made with WROLPi.')
    for note in notes:
        plan.notes.extend(_wrap(note, map_width, NOTE_SIZE))

    plan.width = map_width + 2 * MARGIN
    plan.height = TOP_MARGIN + map_height + BARS_OFFSET + 3 * BAR_SPACING + len(plan.notes) * NOTE_LEADING \
        + BOTTOM_PADDING
    plan.map_rect = (MARGIN, TOP_MARGIN, MARGIN + map_width, TOP_MARGIN + map_height)
    return plan


def _clip(points: Sequence[Tuple[float, float]], rect: Sequence[float]) -> List[List[Tuple[float, float]]]:
    """The parts of a line (through `points`) which are in a rectangle."""
    x0, y0, x1, y1 = rect
    pieces, piece = [], []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        # Liang-Barsky: the part of the way from a to b which is inside.
        start, end = 0.0, 1.0
        dx, dy = bx - ax, by - ay
        inside = True
        for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
            if p == 0:
                inside = inside and q >= 0
            elif p < 0:
                start = max(start, q / p)
            else:
                end = min(end, q / p)
        if not inside or start > end:
            if piece:
                pieces.append(piece)
            piece = []
            continue
        a, b = (ax + start * dx, ay + start * dy), (ax + end * dx, ay + end * dy)
        if not piece or start > 0:
            if piece:
                pieces.append(piece)
            piece = [a]
        piece.append(b)
        if end < 1:
            pieces.append(piece)
            piece = []
    if piece:
        pieces.append(piece)
    return [i for i in pieces if len(i) > 1]


class _Pen:
    """Draws the lines and text of one PDF layer."""

    def __init__(self, page, group: int):
        self.shape = page.new_shape()
        self.group = group

    def line(self, points: Sequence[Tuple[float, float]], width: float = 0.5, color=BLACK, opacity: float = 1):
        self.shape.draw_polyline(list(points))
        self.shape.finish(width=width, color=color, closePath=False, stroke_opacity=opacity, oc=self.group)

    def box(self, rect: Sequence[float], fill=None, width: float = 0.5):
        self.shape.draw_rect(rect)
        self.shape.finish(width=width, color=BLACK, fill=fill, oc=self.group)

    def text(self, x: float, y: float, text: str, size: float = LABEL_SIZE, align: str = 'left', font: str = FONT,
             color=BLACK):
        """Write `text` with its baseline at `y`: starting at, ending at, or centered on `x`."""
        if align != 'left':
            width = _text_width(text, size, font)
            x -= width if align == 'right' else width / 2
        self.shape.insert_text((x, y), text, fontsize=size, fontname=font, color=color, oc=self.group)

    def commit(self):
        self.shape.commit()


def _draw_graticule(pen: _Pen, plan: SheetPlan):
    """The edge of the map, the coordinates of its corners, and ticks of latitude and longitude between them."""
    x0, y0, x1, y1 = plan.map_rect
    west, south, east, north = plan.bounds
    pen.box(plan.map_rect, width=0.75)

    above, below, beside = y0 - 4, y1 + LABEL_SIZE + 3, LABEL_SIZE * 0.35
    # The corners.
    for longitude, x, align in ((west, x0, 'left'), (east, x1, 'right')):
        label = format_angle(longitude, 'E', 'W')
        pen.text(x, above, label, align=align)
        pen.text(x, below, label, align=align)
    for latitude, y in ((north, y0), (south, y1)):
        label = format_angle(latitude, 'N', 'S')
        pen.text(x0 - 3, y + beside, label, align='right')
        pen.text(x1 + 3, y + beside, label)

    longitudes = _multiples(graticule_interval(east - west), west, east)
    latitudes = _multiples(graticule_interval(north - south), south, north)
    for longitude in longitudes:
        x = plan.point(north, longitude)[0]
        pen.line([(x, y0), (x, y0 + TICK_LENGTH)])
        pen.line([(x, y1), (x, y1 - TICK_LENGTH)])
        label = format_angle(longitude, short=True)
        pen.text(x, above, label, align='center')
        pen.text(x, below, label, align='center')
    for latitude in latitudes:
        y = plan.point(latitude, west)[1]
        pen.line([(x0, y), (x0 + TICK_LENGTH, y)])
        pen.line([(x1, y), (x1 - TICK_LENGTH, y)])
        label = format_angle(latitude, short=True)
        pen.text(x0 - 3, y + beside, label, align='right')
        pen.text(x1 + 3, y + beside, label)
    # A cross where a tick of latitude meets one of longitude.
    for latitude in latitudes:
        for longitude in longitudes:
            x, y = plan.point(latitude, longitude)
            pen.line([(x - CROSS_LENGTH, y), (x + CROSS_LENGTH, y)])
            pen.line([(x, y - CROSS_LENGTH), (x, y + CROSS_LENGTH)])


def _graticule_labels(plan: SheetPlan) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Where along the top and bottom (x), and the sides (y), the margin is taken by a coordinate: each a
    (low, high) the grid's labels keep out of."""
    x0, y0, x1, y1 = plan.map_rect
    west, south, east, north = plan.bounds
    corner = _text_width(format_angle(-179.875, 'E', 'W'), LABEL_SIZE) + 4
    tick = _text_width(format_angle(0.125, short=True), LABEL_SIZE) / 2 + 3
    across = [(x0 - 1, x0 + corner), (x1 - corner, x1 + 1)]
    for longitude in _multiples(graticule_interval(east - west), west, east):
        x = plan.point(north, longitude)[0]
        across.append((x - tick, x + tick))
    up = [(y0 - LABEL_SIZE, y0 + LABEL_SIZE), (y1 - LABEL_SIZE, y1 + LABEL_SIZE)]
    for latitude in _multiples(graticule_interval(north - south), south, north):
        y = plan.point(latitude, west)[1]
        up.append((y - LABEL_SIZE, y + LABEL_SIZE))
    return across, up


def _draw_grid(pen: _Pen, plan: SheetPlan):
    """The UTM grid over the map, and what each of its lines is in the margin."""
    x0, y0, x1, y1 = plan.map_rect
    zone, south = plan.zone, plan.south_hemisphere
    meters = _grid_meters(plan)
    (low_e, high_e), (low_n, high_n) = _utm_extent(plan)
    taken_across, taken_up = _graticule_labels(plan)
    beside = LABEL_SIZE * 0.35
    # A line of the grid is not quite straight on the map, so it is drawn through this many places.
    steps = 24

    def free(position: float, half: float, taken: List[Tuple[float, float]]) -> bool:
        return all(position + half < low or position - half > high for low, high in taken)

    # On each edge of the map the first line which is named is named in full (339000mE), and the others by their
    # kilometers (340).
    named = set()

    def label(value: int, edge: str, letter: str) -> str:
        return f'{value // 1000}' if edge in named else f'{value}m{letter}'

    for easting in range(math.ceil(low_e / meters) * meters, math.floor(high_e / meters) * meters + 1, meters):
        northings = [low_n - meters + i * (high_n - low_n + 2 * meters) / steps for i in range(steps + 1)]
        points = [plan.point(*from_utm(easting, northing, zone, south)) for northing in northings]
        for piece in _clip(points, plan.map_rect):
            pen.line(piece, width=0.4, color=GRID_COLOR, opacity=0.7)
            for x, y in (piece[0], piece[-1]):
                if abs(y - y0) > 0.01 and abs(y - y1) > 0.01:
                    continue
                edge = 'top' if abs(y - y0) <= 0.01 else 'bottom'
                text = label(easting, edge, 'E')
                if not free(x, _text_width(text, LABEL_SIZE) / 2 + 2, taken_across):
                    continue
                pen.text(x, y0 - 4 if edge == 'top' else y1 + LABEL_SIZE + 3, text, align='center',
                         color=GRID_COLOR)
                named.add(edge)

    for northing in range(math.ceil(low_n / meters) * meters, math.floor(high_n / meters) * meters + 1, meters):
        eastings = [low_e - meters + i * (high_e - low_e + 2 * meters) / steps for i in range(steps + 1)]
        points = [plan.point(*from_utm(easting, northing, zone, south)) for easting in eastings]
        for piece in _clip(points, plan.map_rect):
            pen.line(piece, width=0.4, color=GRID_COLOR, opacity=0.7)
            for x, y in (piece[0], piece[-1]):
                if abs(x - x0) > 0.01 and abs(x - x1) > 0.01 or not free(y, LABEL_SIZE / 2, taken_up):
                    continue
                edge = 'left' if abs(x - x0) <= 0.01 else 'right'
                text = label(northing, edge, 'N')
                if edge == 'left':
                    pen.text(x0 - 3, y + beside, text, align='right', color=GRID_COLOR)
                else:
                    pen.text(x1 + 3, y + beside, text, color=GRID_COLOR)
                named.add(edge)


def _draw_scale_bar(pen: _Pen, center: float, y: float, unit: float, name: str, most: int, parts: int,
                    available: float, number=str):
    """A bar which is `unit` points for each unit of distance, with its top at `y`.  It has one unit left of its
    zero, divided in `parts`, and as many to the right as there is room for, up to `most`."""
    count = min(most, int(available // unit) - 1)
    if count < 1:
        return
    left = center - (count + 1) * unit / 2
    zero = left + unit
    for i in range(parts):
        fill = BLACK if i % 2 == 0 else None
        pen.box((left + i * unit / parts, y, left + (i + 1) * unit / parts, y + BAR_HEIGHT), fill=fill, width=0.4)
    for i in range(count):
        fill = BLACK if i % 2 == 0 else None
        pen.box((zero + i * unit, y, zero + (i + 1) * unit, y + BAR_HEIGHT), fill=fill, width=0.4)
    pen.text(left, y - 2.5, number(1), align='center')
    for i in range(count + 1):
        pen.text(zero + i * unit, y - 2.5, number(i), align='center')
    pen.text(zero + count * unit + 12, y + BAR_HEIGHT, name)


def _draw_margin(pen: _Pen, plan: SheetPlan):
    """The title above the map, and the scale and the notes below it."""
    x0, y0, x1, y1 = plan.map_rect
    scale = _format_scale(plan.scale)
    title_y = y0 - 24
    if not plan.name:
        pen.text(x1, title_y, scale, size=TITLE_SIZE, font=BOLD, align='right')
    elif _text_width(plan.name, TITLE_SIZE, BOLD) + _text_width(scale, TITLE_SIZE, BOLD) + TITLE_GAP <= x1 - x0:
        pen.text(x0, title_y, plan.name, size=TITLE_SIZE, font=BOLD)
        pen.text(x1, title_y, scale, size=TITLE_SIZE, font=BOLD, align='right')
    else:
        # A map too narrow for both (a quadrangle near a pole is two inches wide) has the scale under the name.
        pen.text(x0, title_y - TITLE_LEADING, plan.name, size=TITLE_SIZE, font=BOLD)
        pen.text(x0, title_y, scale, size=TITLE_SIZE, font=BOLD)

    center = (x0 + x1) / 2
    y = y1 + BARS_OFFSET
    pen.text(center, y - 16, f'SCALE {scale}', size=NOTE_SIZE + 1, align='center')
    # The room a bar has: the map's width, less the name of its unit on each side (so it stays centered).
    available = (x1 - x0) - 2 * (_text_width('KILOMETERS', LABEL_SIZE) + 14)
    meter = 1 / (plan.scale * METERS_PER_POINT)
    _draw_scale_bar(pen, center, y, 1000 * meter, 'KILOMETERS', 2, 10, available)
    _draw_scale_bar(pen, center, y + BAR_SPACING, METERS_PER_MILE * meter, 'MILES', 1, 4, available)
    _draw_scale_bar(pen, center, y + 2 * BAR_SPACING, 1000 * METERS_PER_FOOT * meter, 'FEET', 7, 2, available,
                    number=lambda i: str(i * 1000))

    y += 3 * BAR_SPACING
    for index, note in enumerate(plan.notes):
        pen.text(x0, y + index * NOTE_LEADING, note, size=NOTE_SIZE)


def draw_sheet(doc, page, plan: SheetPlan):
    """Draw the sheet on the page of a map: the grid over the map, and everything around it."""
    if plan.zone:
        grid = _Pen(page, doc.add_ocg(GRID_LAYER, on=True))
        _draw_grid(grid, plan)
        grid.commit()
    pen = _Pen(page, doc.add_ocg(SHEET_LAYER, on=True))
    _draw_graticule(pen, plan)
    _draw_margin(pen, plan)
    pen.commit()
