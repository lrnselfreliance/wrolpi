"""The winds aloft over a region, from a weather forecast, for the fallout simulator.

Fallout falls from a cloud kilometers high, for hours, across hundreds of kilometers, through winds
which change with height, with place, and with time.  So the simulator takes a field of forecasts:
the wind at every height, hour by hour, at points on a grid over the region around the targets, and
carries each particle by the wind where it is, at the height it is, at the hour it is there.

Open-Meteo (https://open-meteo.com) forecasts the wind at nineteen pressure levels, from about 100 m
up to about 24 km, free and without an API key, for many places in one request.  A field is fetched
only when the user asks for one (it needs the Internet), and is kept so the simulator can use it
offline.  Its points are on whole degrees, so the forecast service is never told where a target is.

The free service allows 10,000 calls a day, a place costing about one call for every ten variables
asked of it (here sixty): a field is kept to MAX_POINTS points, by spacing them further apart over a
wide region.
"""
import json
import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlencode

from modules.map.lib import get_map_directory
from wrolpi.common import aiohttp_get, logger
from wrolpi.dates import now

logger = logger.getChild(__name__)

OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'
# The pressure levels (hPa) Open-Meteo forecasts, from near the ground up.
PRESSURE_LEVELS = (1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30)
# Long enough for fallout to come down; Open-Meteo's forecasts are hourly.
FORECAST_DAYS = 2
TIMEOUT = 60
# How far around each target the field reaches (degrees): as far as fallout which shows is carried.
MARGIN = 6
# No more points than this in a field: about 1,800 of the free service's 10,000 calls a day.
MAX_POINTS = 300
# The spacings (degrees) a field's points may have, the closest first.
SPACINGS = (1, 2, 3, 4, 5, 6, 8, 10)
# Places asked for in one request.
BATCH = 100
# Fields kept on disk; the newest is the one used.
KEPT_FIELDS = 3


class WindsError(Exception):
    """A forecast could not be fetched, or was not understood."""


def field_points(places: Sequence[Tuple[float, float]], margin: float = MARGIN,
                 max_points: int = MAX_POINTS) -> Tuple[int, List[Tuple[int, int]]]:
    """The points of a field over `places` ([(lat, lon)]): the spacing (degrees), and the points
    ([(lat, lon)], on whole multiples of the spacing) within `margin` degrees of any place, as close
    together as `max_points` allows."""
    if not places:
        raise WindsError('A field needs at least one place')
    for spacing in SPACINGS:
        points = set()
        for lat, lon in places:
            south = math.ceil(max(lat - margin, -85) / spacing) * spacing
            north = math.floor(min(lat + margin, 85) / spacing) * spacing
            west = math.ceil((lon - margin) / spacing) * spacing
            east = math.floor((lon + margin) / spacing) * spacing
            for point_lat in range(south, north + 1, spacing):
                for point_lon in range(west, east + 1, spacing):
                    # Longitudes wrap at the antimeridian.
                    points.add((point_lat, ((point_lon + 180) % 360) - 180))
        if len(points) <= max_points:
            return spacing, sorted(points)
    raise WindsError(f'The places are too spread out for a field of {max_points} points')


def forecast_url(points: Sequence[Tuple[int, int]]) -> str:
    hourly = ['wind_speed_10m', 'wind_direction_10m', 'precipitation']
    for level in PRESSURE_LEVELS:
        hourly += [f'wind_speed_{level}hPa', f'wind_direction_{level}hPa', f'geopotential_height_{level}hPa']
    query = dict(latitude=','.join(str(p[0]) for p in points), longitude=','.join(str(p[1]) for p in points),
                 hourly=','.join(hourly), forecast_days=FORECAST_DAYS, wind_speed_unit='ms', timezone='GMT')
    return f'{OPEN_METEO_URL}?{urlencode(query)}'


def parse_forecast(data: dict) -> dict:
    """An Open-Meteo forecast for one place as the simulator reads it:

    {elevation (m, of the forecast's ground), hours: [{time (UTC, ISO), precipitation (mm in the
    hour), winds: [[height (m above sea level), speed (m/s), direction (degrees the wind blows
    FROM)], ...]}]}

    Each hour's winds start with the wind 10 m above the ground and go up the pressure levels.  A
    level below the ground (high pressure over high ground) is left out, as is anything missing."""
    try:
        elevation = float(data['elevation'])
        hourly = data['hourly']
        times = hourly['time']
    except (KeyError, TypeError, ValueError) as e:
        raise WindsError(f'The forecast was not understood: {e}') from e

    def at(name, i):
        values = hourly.get(name)
        return values[i] if values and i < len(values) else None

    hours = []
    for i, time in enumerate(times):
        winds = []
        speed, direction = at('wind_speed_10m', i), at('wind_direction_10m', i)
        if speed is not None and direction is not None:
            winds.append([round(elevation + 10), round(speed, 1), round(direction)])
        for level in PRESSURE_LEVELS:
            height = at(f'geopotential_height_{level}hPa', i)
            speed, direction = at(f'wind_speed_{level}hPa', i), at(f'wind_direction_{level}hPa', i)
            if None in (height, speed, direction) or height <= elevation + 10:
                continue
            winds.append([round(height), round(speed, 1), round(direction)])
        if not winds:
            continue
        winds.sort(key=lambda w: w[0])
        hours.append(dict(time=f'{time}Z', precipitation=at('precipitation', i) or 0, winds=winds))
    if not hours:
        raise WindsError('The forecast had no winds')
    return dict(elevation=elevation, hours=hours)


def winds_directory() -> Path:
    """Where fields are kept: a hidden directory, which the file lists and search skip."""
    directory = get_map_directory() / '.fallout-winds'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def latest_field() -> Optional[dict]:
    """The field fetched most recently, or None."""
    for path in sorted(winds_directory().glob('field-*.json'), reverse=True):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as e:
            logger.warning(f'Could not read the winds kept in {path}', exc_info=e)
    return None


async def request_forecast(url: str) -> list:
    """The forecasts of a request, one for each of its places."""
    async with aiohttp_get(url, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise WindsError(f'The forecast service answered HTTP {response.status}')
        data = await response.json()
    # One place is answered with a forecast, several with a list of them.
    return data if isinstance(data, list) else [data]


async def fetch_wind_field(places: Sequence[Tuple[float, float]]) -> dict:
    """Fetch the field over `places` ([(lat, lon)]), keep it, and return it:

    {source, fetched_at, spacing (degrees), points: [{lat, lon, elevation}], hours: [time (UTC,
    ISO)], winds: [for each point: [for each hour: [[height (m above sea level), speed (m/s),
    direction FROM (degrees)], ...]]], rain: [for each point: [mm in each hour]]}"""
    spacing, points = field_points(places)
    forecasts = []
    for start in range(0, len(points), BATCH):
        batch = points[start:start + BATCH]
        try:
            answered = await request_forecast(forecast_url(batch))
        except WindsError:
            raise
        except Exception as e:
            raise WindsError(f'Could not reach the forecast service: {e}') from e
        if len(answered) != len(batch):
            raise WindsError(f'The forecast service answered for {len(answered)} of {len(batch)} places')
        forecasts.extend(parse_forecast(f) for f in answered)

    # Every point has the same hours (Open-Meteo forecasts the same hours everywhere); a point which
    # is short of any is given its last.
    hours = [h['time'] for h in max(forecasts, key=lambda f: len(f['hours']))['hours']]
    winds, rain = [], []
    for forecast in forecasts:
        by_time = {h['time']: h for h in forecast['hours']}
        last = forecast['hours'][-1]
        winds.append([by_time.get(t, last)['winds'] for t in hours])
        rain.append([by_time.get(t, last)['precipitation'] for t in hours])
    field = dict(
        source='Open-Meteo',
        fetched_at=now().isoformat(),
        spacing=spacing,
        points=[dict(lat=lat, lon=lon, elevation=f['elevation']) for (lat, lon), f in zip(points, forecasts)],
        hours=hours,
        winds=winds,
        rain=rain,
    )
    logger.info(f'Fetched a field of winds aloft: {len(points)} points every {spacing} degrees')

    directory = winds_directory()
    path = directory / f'field-{now().strftime("%Y%m%d-%H%M%S")}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(field, separators=(',', ':')))
    temporary.replace(path)
    for old in sorted(directory.glob('field-*.json'), reverse=True)[KEPT_FIELDS:]:
        old.unlink(missing_ok=True)
    return field
