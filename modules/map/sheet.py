"""The sheet an exported map is printed on: what a topographic map has around and over the map itself.

Around the map is a margin with a title, the latitude and longitude of the map's corners and of ticks along its
edges, scale bars, a diagram of the three norths (true, grid and magnetic), and notes (the projection, the grid,
where a compass points, where the map's data is from).  Over the map is a grid of
1,000 meter squares (Universal Transverse Mercator), which is how a position is read from, or found on, paper.

All of it is drawn as lines and text, in PDF layers of its own which a reader can turn off.
"""
import dataclasses
import datetime
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from modules.map import magnetic, quads

__all__ = ['Sheet', 'SheetPlan', 'plan_sheet', 'draw_sheet', 'to_utm', 'from_utm', 'utm_zone', 'map_scale',
           'format_angle', 'graticule_interval', 'SHEET_LAYER', 'GRID_LAYER', 'LegendLine', 'legend_lines',
           'legend_as_sent', 'adjoining_quads', 'mils']

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
# The bars: kilometers, meters, miles and feet.
BAR_COUNT = 4
# The room under the bars for how far apart the contour lines are.
CONTOUR_LEADING = 16
# The units contour lines are apart in, as they are written.
CONTOUR_UNITS = dict(feet='FEET', meters='METERS')
# The diagram of the quadrangles around the map: how large each of its nine squares is, how much room the
# diagram and the names beside it take under the bars, and the narrowest map which has room for it.
ADJOINING_SQUARE = 12
ADJOINING_HEIGHT = 58
ADJOINING_MIN_WIDTH = 280
ADJOINING_COLUMN = 150
# How many maps over to look for the next quadrangle: the widest of the USGS is under four maps wide.
ADJOINING_STEPS = 4
ADJOINING_GRAY = (0.75, 0.75, 0.75)
GRAY = (0.6, 0.6, 0.6)
# Where the eight are from the map, in the order they are numbered: (columns east, rows north).
ADJOINING = ((-1, 1), (0, 1), (1, 1), (-1, 0), (1, 0), (-1, -1), (0, -1), (1, -1))
# The legend: the most lines it has, how long what each is called may be, how wide and tall the room of one is,
# how long its piece of line is, and the least and the most a line is drawn wide (points).
LEGEND_LINES = 12
LEGEND_LABEL = 40
LEGEND_ITEM_WIDTH = 118
LEGEND_ITEM_HEIGHT = 13
LEGEND_SAMPLE = 30
LEGEND_WIDTHS = (0.15, 5)
LEGEND_DASHES = 6
WHITE = (1, 1, 1)
# A compass is marked in degrees, or in mils: 6,400 of them around.
MILS_PER_DEGREE = 6400 / 360
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
class LegendLine:
    """A kind of line of the map (a road, a boundary), as it is drawn there: for the legend."""
    label: str
    # Red, green and blue, each from 0 to 1.
    color: Tuple[float, float, float]
    # How wide it is, in points.
    width: float
    opacity: float = 1
    # The lengths of its dashes and of the gaps between them, in points; nothing when it is unbroken.
    dash: Tuple[float, ...] = ()
    # The line under it which is its edges: its color, and how wide it is, edges and all.
    casing_color: Optional[Tuple[float, float, float]] = None
    casing_width: float = 0


@dataclass
class Sheet:
    """What the browser says of a map, to be written around it."""
    # What the map is called.
    name: Optional[str] = None
    # Where the data of the map is from.
    credits: Sequence[str] = ()
    # When the map was made, as it is to be written.  When it is a day (2026-11-15), the sheet says where a
    # compass points on that day.
    date: Optional[str] = None
    # How far apart the map's contour lines are, and in what (one of CONTOUR_UNITS); None when it has none.
    contour_interval: Optional[float] = None
    contour_unit: Optional[str] = None
    # The lines of the map as the browser drew them, for the legend: `{"ground": [r, g, b], "lines": [{"label",
    # "color", "width", "opacity", "dash", "casing_color", "casing_width"}, ...]}` (see `LegendLine`; `ground`
    # is the color of the land they are drawn on).  It is whatever was sent: `legend_lines` makes lines of it.
    legend: Optional[dict] = None


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
    # How far east of true north (degrees) the grid's north, and a compass, point at the middle of the map.
    # None where there is no grid, and when it is not known where a compass points.
    grid_north: Optional[float] = None
    magnetic_north: Optional[float] = None
    # How far apart the contour lines are, as it is written under the scale bars; None when there are none.
    contours: Optional[str] = None
    # What the USGS calls the eight quadrangles around the map, in the order of ADJOINING (None for one it has
    # no name for); None when it has a name for none of them, and when the sheet has no room to say.
    adjoining: Optional[List[Optional[str]]] = None
    # The lines of the legend, and the color of the land they are drawn on.
    legend: List[LegendLine] = field(default_factory=list)
    legend_ground: Tuple[float, float, float] = WHITE

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


# A tick nearer an edge of the map than this part of the way to the next tick is that edge: the edges of the
# picture the browser draws are a hair outside the map it was asked for (a millionth of a degree).
TICK_CLEARANCE = 0.01


def _multiples(interval: float, low: float, high: float) -> List[float]:
    """The multiples of `interval` between `low` and `high`, and not at (or a hair from) either."""
    first = math.floor(low / interval)
    values = []
    for i in range(first, first + 100_000):
        value = i * interval
        if value >= high - interval * TICK_CLEARANCE:
            break
        if value > low + interval * TICK_CLEARANCE:
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


def _east_or_west(angle: float) -> str:
    """An angle east of north as it is said: 2°34' west.  No north is known to better than a minute."""
    return f'{format_angle(_to_the_minute(abs(angle)))} {"west" if angle < 0 else "east"}'


def mils(angle: float) -> int:
    """An angle (degrees) in the mils a compass may be marked in."""
    return round(abs(angle) * MILS_PER_DEGREE)


def _north_of_true(angle: float) -> str:
    """How far a north is from true north, as it is said: 2°34' west (46 mils)."""
    return f'{_east_or_west(angle)} ({mils(angle)} mils)'


def adjoining_quads(bounds: Sequence[float]) -> Optional[List[Optional[str]]]:
    """What the USGS calls the quadrangle on each of the eight sides of a map, in the order of ADJOINING.  None
    when it has a name for none of them: most of the world.

    A quadrangle of the USGS may be larger than the map (in Alaska they are wider), so the area the size of the
    map beside it may be more of the quadrangle the map is in.  The quadrangle on that side is the next one
    which is not: a sheet is never beside itself."""
    west, south, east, north = bounds
    width, height = east - west, north - south
    own = quads.quad_name(west, south, east, north)
    names = []
    for columns, rows in ADJOINING:
        name = None
        for step in range(1, ADJOINING_STEPS + 1):
            name = quads.quad_name(west + step * columns * width, south + step * rows * height,
                                   east + step * columns * width, north + step * rows * height)
            if name is None or own is None or (name.name, name.state) != (own.name, own.state):
                break
        else:
            name = None
        names.append(_latin(name.name) if name else None)
    return names if any(names) else None


def _number(value, least: float, most: float) -> Optional[float]:
    """A number which was sent, kept between two others; None when it is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return min(most, max(least, float(value)))


def _color(value) -> Optional[Tuple[float, float, float]]:
    """A color which was sent (red, green and blue, each from 0 to 1); None when it is not one."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    parts = tuple(_number(i, 0, 1) for i in value)
    return None if None in parts else parts


def legend_lines(legend) -> Tuple[Tuple[float, float, float], List[LegendLine]]:
    """The color of the land, and the lines, of the legend which a browser sent (see `Sheet.legend`).  What is
    not a line (it has no name, no color or no width) is left out, and a line is drawn no wider than a legend
    has room for."""
    if not isinstance(legend, dict):
        return WHITE, []
    lines = []
    raw = legend.get('lines')
    for line in (raw if isinstance(raw, list) else [])[:LEGEND_LINES]:
        if not isinstance(line, dict):
            continue
        label = _latin(str(line.get('label') or '')).strip()[:LEGEND_LABEL]
        color, width = _color(line.get('color')), _number(line.get('width'), *LEGEND_WIDTHS)
        if not label or color is None or width is None:
            continue
        dash = line.get('dash')
        dash = [_number(i, 0.1, LEGEND_SAMPLE) for i in (dash if isinstance(dash, (list, tuple)) else [])[:LEGEND_DASHES]]
        opacity = _number(line.get('opacity'), 0.05, 1)
        casing_color, casing_width = _color(line.get('casing_color')), _number(line.get('casing_width'), 0, 8)
        lines.append(LegendLine(
            label=label, color=color, width=width, opacity=1 if opacity is None else opacity,
            dash=() if None in dash else tuple(dash),
            casing_color=casing_color if casing_width else None,
            casing_width=casing_width if casing_color and casing_width else 0))
    return _color(legend.get('ground')) or WHITE, lines


def legend_as_sent(legend) -> Optional[dict]:
    """The legend which a browser sent with only what `legend_lines` makes of it, as it is sent; None when it
    has no lines."""
    ground, lines = legend_lines(legend)
    return dict(ground=list(ground), lines=[dataclasses.asdict(line) for line in lines]) if lines else None


def _legend_columns(plan: 'SheetPlan') -> int:
    """How many lines of the legend go side by side under a map as wide as this one."""
    return max(1, int((plan.map_rect[2] - plan.map_rect[0]) // LEGEND_ITEM_WIDTH))


def _legend_height(plan: 'SheetPlan') -> float:
    """The room the legend takes under the map: nothing, when it has no lines."""
    if not plan.legend:
        return 0
    rows = math.ceil(len(plan.legend) / _legend_columns(plan))
    return LABEL_SIZE + 8 + rows * LEGEND_ITEM_HEIGHT + 8


def _contours(sheet: 'Sheet') -> Optional[str]:
    """How far apart the contour lines are, as it is written: CONTOUR INTERVAL 40 FEET."""
    interval, unit = sheet.contour_interval, CONTOUR_UNITS.get(sheet.contour_unit)
    if not unit or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        return None
    return f'CONTOUR INTERVAL {interval:,.10g} {unit}'


def _to_the_minute(angle: float) -> float:
    return round(angle * 60) / 60


def _decimal_year(date: Optional[str]) -> Optional[float]:
    """A day (2026-11-15) as a year and a part of one, or None when it is not a day."""
    try:
        day = datetime.date.fromisoformat(str(date).strip()[:10])
    except ValueError:
        return None
    first = datetime.date(day.year, 1, 1)
    return day.year + (day - first).days / (datetime.date(day.year + 1, 1, 1) - first).days


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
        plan.grid_north = _grid_convergence(*middle, plan.zone, plan.south_hemisphere)
        notes.append(
            f'{_grid_meters(plan):,} meter grid: Universal Transverse Mercator, zone {plan.zone}'
            f'{"S" if plan.south_hemisphere else "N"}.  Grid north is {_north_of_true(plan.grid_north)} of true'
            f' north at the middle of the map.')
    year = _decimal_year(sheet.date)
    plan.magnetic_north = magnetic.declination(*middle, year) if year else None
    if plan.magnetic_north is not None:
        model = magnetic.load_model()
        # The shorter way around: a compass which passes due south goes from 180 west to 180 east.
        yearly = (model.declination(*middle, year + 1) - plan.magnetic_north + 180) % 360 - 180
        notes.append(
            f'Magnetic north is {_north_of_true(plan.magnetic_north)} of true north at the middle of the map on'
            f' {_latin(sheet.date)}, and moves about {_east_or_west(yearly)} each year ({model.name}).')
    names = [_latin(str(i)) for i in sheet.credits if str(i).strip()]
    if names:
        notes.append('Map data: ' + '; '.join(names))
    notes.append(f'Made with WROLPi, {_latin(sheet.date)}.' if sheet.date else 'Made with WROLPi.')
    for note in notes:
        plan.notes.extend(_wrap(note, map_width, NOTE_SIZE))
    plan.contours = _contours(sheet)
    if map_width >= ADJOINING_MIN_WIDTH:
        plan.adjoining = adjoining_quads(bounds)

    plan.legend_ground, plan.legend = legend_lines(sheet.legend)

    plan.width = map_width + 2 * MARGIN
    plan.map_rect = (MARGIN, TOP_MARGIN, MARGIN + map_width, TOP_MARGIN + map_height)
    plan.height = TOP_MARGIN + map_height + BARS_OFFSET + BAR_COUNT * BAR_SPACING \
        + (CONTOUR_LEADING if plan.contours else 0) + (ADJOINING_HEIGHT if plan.adjoining else 0) \
        + _legend_height(plan) + len(plan.notes) * NOTE_LEADING + BOTTOM_PADDING
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

    def line(self, points: Sequence[Tuple[float, float]], width: float = 0.5, color=BLACK, opacity: float = 1,
             dash: Sequence[float] = ()):
        self.shape.draw_polyline(list(points))
        dashes = f'[{" ".join(f"{i:.2f}" for i in dash)}] 0' if dash else None
        self.shape.finish(width=width, color=color, closePath=False, stroke_opacity=opacity, dashes=dashes,
                          lineCap=0, oc=self.group)

    def box(self, rect: Sequence[float], fill=None, width: float = 0.5, color=BLACK):
        self.shape.draw_rect(rect)
        self.shape.finish(width=width, color=color, fill=fill, oc=self.group)

    def polygon(self, points: Sequence[Tuple[float, float]], fill=BLACK):
        self.shape.draw_polyline(list(points))
        self.shape.finish(width=0.3, color=BLACK, fill=fill, closePath=True, oc=self.group)

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
                    available: float, number=str) -> float:
    """A bar which is `unit` points for each unit of distance, with its top at `y`.  It has one unit left of its
    zero, divided in `parts`, and as many to the right as there is room for, up to `most`.  Returns how long the
    bar is: nothing, when there is no room for it."""
    count = min(most, int(available // unit) - 1)
    if count < 1:
        return 0
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
    return (count + 1) * unit


# The diagram of the norths: how long the line to each is (points), and the least and the most it is drawn from
# straight up (degrees).  The diagram shows which side each north is on, not how far: the angles are written.
NORTH_LENGTHS = dict(true=62, magnetic=50, grid=38)
NORTH_LEAST, NORTH_MOST = 7, 30
# How wide the diagram is, with what is written beside its lines.
NORTHS_WIDTH = 100


def _north_tip(x: float, y: float, angle: float, length: float) -> Tuple[float, float]:
    """Where the line to a north ends: drawn to its side of straight up, but never so near it, or so far from it,
    that it can not be told apart."""
    shown = math.radians(math.copysign(min(NORTH_MOST, max(NORTH_LEAST, abs(angle))), angle))
    return x + length * math.sin(shown), y - length * math.cos(shown)


def _draw_norths(pen: _Pen, plan: SheetPlan, x: float, y: float):
    """Which way true north, the grid's north and a compass's north are from each other, from a point at
    (`x`, `y`), with how far each is from true north written under it."""
    top = y - NORTH_LENGTHS['true']
    pen.line([(x, y), (x, top)], width=0.6)
    # True north is at a star.
    star = [(x + r * math.sin(math.radians(36 * i)), top - 5 - r * math.cos(math.radians(36 * i)))
            for i, r in zip(range(10), (5, 2) * 5)]
    pen.polygon(star)
    below = y + LABEL_SIZE + 4
    for name, angle, length in (('MN', plan.magnetic_north, NORTH_LENGTHS['magnetic']),
                                ('GN', plan.grid_north, NORTH_LENGTHS['grid'])):
        if angle is None:
            continue
        tip_x, tip_y = _north_tip(x, y, angle, length)
        pen.line([(x, y), (tip_x, tip_y)], width=0.6)
        east = angle >= 0
        pen.text(tip_x + (3 if east else -3), tip_y + 2, name, align='left' if east else 'right')
        pen.text(x, below, f'{name} {format_angle(_to_the_minute(abs(angle)))} {"E" if east else "W"}'
                           f'  {mils(angle)} MILS', align='center')
        below += LABEL_SIZE + 2


def _draw_adjoining(pen: _Pen, plan: SheetPlan, x: float, y: float):
    """The quadrangles around the map: nine squares with the map the middle one, each of the others with a
    number, and beside them what each number is called.  Its top left is at (`x`, `y`)."""
    pen.text(x, y + LABEL_SIZE, 'ADJOINING QUADRANGLES')
    top = y + LABEL_SIZE + 5
    side = ADJOINING_SQUARE
    pen.box((x + side, top + side, x + 2 * side, top + 2 * side), fill=ADJOINING_GRAY, width=0.4)
    for i in range(4):
        pen.line([(x + i * side, top), (x + i * side, top + 3 * side)], width=0.4)
        pen.line([(x, top + i * side), (x + 3 * side, top + i * side)], width=0.4)
    # The names are in two columns: as wide as a long name, or as the room beside the squares allows.
    left = x + 3 * side + 12
    column = min(ADJOINING_COLUMN, (plan.map_rect[2] - left) / 2)
    listed = 0
    for number, ((columns, rows), name) in enumerate(zip(ADJOINING, plan.adjoining), start=1):
        if not name:
            continue
        pen.text(x + (columns + 1.5) * side, top + (1.5 - rows) * side + LABEL_SIZE / 3, str(number), align='center')
        while _text_width(f'{number}  {name}', LABEL_SIZE) > column - 6 and len(name) > 1:
            name = name[:-1]
        pen.text(left + (listed // 4) * column, top + LABEL_SIZE + (listed % 4) * (LABEL_SIZE + 2.5),
                 f'{number}  {name}')
        listed += 1


def _draw_legend(pen: _Pen, plan: SheetPlan, x: float, y: float):
    """What the lines of the map are: a piece of each as the map draws it, on the color of the map's land, with
    what it is called beside it.  Its top left is at (`x`, `y`)."""
    pen.text(x, y + LABEL_SIZE, 'LEGEND')
    top = y + LABEL_SIZE + 8
    columns = _legend_columns(plan)
    for index, line in enumerate(plan.legend):
        left = x + (index % columns) * LEGEND_ITEM_WIDTH
        row = top + (index // columns) * LEGEND_ITEM_HEIGHT
        box = (left, row, left + LEGEND_SAMPLE, row + LEGEND_ITEM_HEIGHT - 3)
        pen.box(box, fill=plan.legend_ground, width=0.3, color=GRAY)
        middle = (box[1] + box[3]) / 2
        ends = [(left + 1, middle), (left + LEGEND_SAMPLE - 1, middle)]
        if line.casing_color and line.casing_width > line.width:
            pen.line(ends, width=line.casing_width, color=line.casing_color)
        pen.line(ends, width=line.width, color=line.color, opacity=line.opacity, dash=line.dash)
        pen.text(left + LEGEND_SAMPLE + 5, middle + LABEL_SIZE / 3, line.label)


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
    bars = [
        _draw_scale_bar(pen, center, y, 1000 * meter, 'KILOMETERS', 2, 10, available),
        _draw_scale_bar(pen, center, y + BAR_SPACING, 1000 * meter, 'METERS', 2, 2, available,
                        number=lambda i: str(i * 1000)),
        _draw_scale_bar(pen, center, y + 2 * BAR_SPACING, METERS_PER_MILE * meter, 'MILES', 1, 4, available),
        _draw_scale_bar(pen, center, y + 3 * BAR_SPACING, 1000 * METERS_PER_FOOT * meter, 'FEET', 7, 2, available,
                        number=lambda i: str(i * 1000)),
    ]
    # The norths are left of the bars, where there is room for them.
    if (plan.grid_north is not None or plan.magnetic_north is not None) \
            and center - max(bars) / 2 - x0 >= NORTHS_WIDTH + 10:
        _draw_norths(pen, plan, x0 + NORTHS_WIDTH / 2, y + (BAR_COUNT - 1) * BAR_SPACING - 12)

    y += BAR_COUNT * BAR_SPACING
    if plan.contours:
        pen.text(center, y - 4, plan.contours, size=NOTE_SIZE + 1, align='center')
        y += CONTOUR_LEADING
    if plan.adjoining:
        _draw_adjoining(pen, plan, x0, y - NOTE_LEADING)
        y += ADJOINING_HEIGHT
    if plan.legend:
        _draw_legend(pen, plan, x0, y - NOTE_LEADING)
        y += _legend_height(plan)
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
