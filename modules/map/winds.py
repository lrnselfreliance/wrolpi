"""The winds aloft over a place, from a weather forecast, for the fallout simulator.

Fallout falls from a cloud kilometers high through winds which change with height, so the simulator
needs the wind at every height, hour by hour, not only the wind at the ground.  Open-Meteo
(https://open-meteo.com) forecasts the wind at nineteen pressure levels, from about 100 m up to
about 24 km, free and without an API key.

A forecast is fetched only when the user asks for one (it needs the Internet), and is kept so the
simulator can use it offline.  The place is rounded to a whole degree before it is sent: the winds
aloft hardly differ across a degree, and the forecast service is not told where the user is.
"""
import json
from pathlib import Path
from typing import Optional
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
TIMEOUT = 30


class WindsError(Exception):
    """A forecast could not be fetched, or was not understood."""


def round_place(lat: float, lon: float) -> tuple:
    """The whole degrees nearest `lat`, `lon`: the place a forecast is fetched for."""
    lat = max(-90, min(90, round(lat)))
    lon = ((round(lon) + 180) % 360) - 180
    return lat, lon


def forecast_url(lat: int, lon: int) -> str:
    hourly = ['wind_speed_10m', 'wind_direction_10m', 'precipitation']
    for level in PRESSURE_LEVELS:
        hourly += [f'wind_speed_{level}hPa', f'wind_direction_{level}hPa', f'geopotential_height_{level}hPa']
    query = dict(latitude=lat, longitude=lon, hourly=','.join(hourly), forecast_days=FORECAST_DAYS,
                 wind_speed_unit='ms', timezone='GMT')
    return f'{OPEN_METEO_URL}?{urlencode(query)}'


def parse_forecast(data: dict) -> dict:
    """An Open-Meteo forecast as the simulator reads it:

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
            winds.append([elevation + 10, speed, direction])
        for level in PRESSURE_LEVELS:
            height = at(f'geopotential_height_{level}hPa', i)
            speed, direction = at(f'wind_speed_{level}hPa', i), at(f'wind_direction_{level}hPa', i)
            if None in (height, speed, direction) or height <= elevation + 10:
                continue
            winds.append([height, speed, direction])
        if not winds:
            continue
        winds.sort(key=lambda w: w[0])
        hours.append(dict(time=f'{time}Z', precipitation=at('precipitation', i) or 0, winds=winds))
    if not hours:
        raise WindsError('The forecast had no winds')
    return dict(elevation=elevation, hours=hours)


def winds_directory() -> Path:
    """Where forecasts are kept: a hidden directory, which the file lists and search skip."""
    directory = get_map_directory() / '.fallout-winds'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def winds_path(lat: int, lon: int) -> Path:
    return winds_directory() / f'{lat}_{lon}.json'


def cached_winds(lat: float, lon: float) -> Optional[dict]:
    """The forecast last fetched for the degree around `lat`, `lon`, or None."""
    path = winds_path(*round_place(lat, lon))
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning(f'Could not read the winds kept in {path}', exc_info=e)
        return None


async def request_forecast(url: str) -> dict:
    async with aiohttp_get(url, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise WindsError(f'The forecast service answered HTTP {response.status}')
        return await response.json()


async def fetch_winds(lat: float, lon: float) -> dict:
    """Fetch the forecast for the degree around `lat`, `lon`, keep it, and return it (as
    parse_forecast gives it, with the place it is for, where from, and when it was fetched)."""
    lat, lon = round_place(lat, lon)
    try:
        data = await request_forecast(forecast_url(lat, lon))
    except WindsError:
        raise
    except Exception as e:
        raise WindsError(f'Could not reach the forecast service: {e}') from e
    winds = dict(lat=lat, lon=lon, source='Open-Meteo', fetched_at=now().isoformat(), **parse_forecast(data))
    path = winds_path(lat, lon)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(winds))
    temporary.replace(path)
    return winds
