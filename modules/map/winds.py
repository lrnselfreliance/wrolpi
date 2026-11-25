"""The winds aloft over a region, from a weather forecast, for the fallout simulator.

Fallout falls from a cloud kilometers high, for hours, across hundreds of kilometers, through winds
which change with height, with place, and with time.  So the simulator takes a field of forecasts:
the wind at every height, hour by hour, at points on a grid over the region around the targets, and
carries each particle by the wind where it is, at the height it is, at the hour it is there.

Open-Meteo (https://open-meteo.com) forecasts the wind at nineteen pressure levels, from about 100 m
up to about 24 km, free and without an API key, for many places in one request.  When the user
subscribes (the map's Manage tab), a field around the saved nuclear targets is downloaded every day,
as a recurring Download, and kept so the simulator can use it offline.  Only the newest is kept:
a simulation is of bursts now.  Its points are on whole degrees, so the forecast service is never
told where a target is.

The free service allows 600 calls a minute and 10,000 a day, a place costing about one call for
every ten variables asked of it (here sixty).  So a field is kept to MAX_POINTS points, by spacing
them further apart over a wide region, and is fetched as a Job, BATCH places a minute: a field over
a whole country takes a few minutes.
"""
import asyncio
import json
from dataclasses import dataclass
import time
import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from modules.map.lib import get_map_directory
from modules.map.nuclear import get_map_nuclear_config
from wrolpi.common import aiohttp_get, logger
from wrolpi.dates import now
from wrolpi.downloader import Download, DownloadContext, Downloader, DownloadFrequency, DownloadResult, \
    download_manager, save_downloads_config

logger = logger.getChild(__name__)

OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'
# The pressure levels (hPa) Open-Meteo forecasts, from near the ground up.
PRESSURE_LEVELS = (1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30)
# Long enough for fallout to come down: the forecast starts at midnight UTC, and the 48 hours after a
# burst this hour must be in it until the next day's download.  Open-Meteo counts up to a week of a
# place as one call, so the extra days cost nothing.
FORECAST_DAYS = 4
# The pressure levels whose relative humidity is asked for: where a rain cloud may be, up to the tops of
# thunderstorms (about 200 hPa).
HUMIDITY_LEVELS = (1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200)
# A cloud's bottom is the lowest level at least this humid, its top the first above that is less than
# CLOUD_TOP_RH (percent): HYSPLIT's rule (Moroz et al. 2010, after Draxler and Hess 1997).
CLOUD_BOTTOM_RH = 80
CLOUD_TOP_RH = 60
TIMEOUT = 60
# How far around each target the field reaches (degrees): as far as fallout which shows is carried.
MARGIN = 6
# No more points than this in a field: up to about 4,000 of the free service's 5,000 calls an hour and
# 10,000 a day, fetched in about seven minutes.
MAX_POINTS = 540
# The spacings (degrees) a field's points may have, the closest first.
SPACINGS = (1, 2, 3, 4, 5, 6, 8, 10)
# Places asked for in one request (each costs 7.4 calls: 74 variables, a call for every ten; 600 calls
# a minute are allowed), and how long (s) from one request to the next.
BATCH = 80
BATCH_SECONDS = 61
# Fields kept on disk: only the newest, which is the one used.  It is replaced only once a newer one
# has been downloaded.
KEPT_FIELDS = 1


class WindsError(Exception):
    """A forecast could not be fetched, or was not understood."""


def field_points(places: Sequence[Tuple[float, float]], margin: float = MARGIN,
                 max_points: int = None) -> Tuple[int, List[Tuple[int, int]]]:
    """The points of a field over `places` ([(lat, lon)]): the spacing (degrees), and the points
    ([(lat, lon)], on whole multiples of the spacing) within `margin` degrees of any place, as close
    together as `max_points` allows."""
    if not places:
        raise WindsError('A field needs at least one place')
    max_points = max_points or MAX_POINTS
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
    hourly += [f'relative_humidity_{level}hPa' for level in HUMIDITY_LEVELS]
    query = dict(latitude=','.join(str(p[0]) for p in points), longitude=','.join(str(p[1]) for p in points),
                 hourly=','.join(hourly), forecast_days=FORECAST_DAYS, wind_speed_unit='ms', timezone='GMT')
    return f'{OPEN_METEO_URL}?{urlencode(query)}'


def parse_forecast(data: dict) -> dict:
    """An Open-Meteo forecast for one place as the simulator reads it:

    {elevation (m, of the forecast's ground), hours: [{time (UTC, ISO), precipitation (mm in the
    hour), cloud: [bottom, top] (m above sea level, of the cloud rain would fall from) or None,
    winds: [[height (m above sea level), speed (m/s), direction (degrees the wind blows FROM)],
    ...]}]}

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
        hours.append(dict(time=f'{time}Z', precipitation=at('precipitation', i) or 0, winds=winds,
                          cloud=cloud_layer(elevation, [(at(f'geopotential_height_{level}hPa', i),
                                                         at(f'relative_humidity_{level}hPa', i))
                                                        for level in HUMIDITY_LEVELS])))
    if not hours:
        raise WindsError('The forecast had no winds')
    return dict(elevation=elevation, hours=hours)


def cloud_layer(elevation: float, levels: Sequence[Tuple[Optional[float], Optional[float]]]) -> Optional[List[int]]:
    """The cloud rain would fall from, as [bottom, top] (m above sea level), from the (height,
    relative humidity) of each level going up; None without one.  Its bottom is the lowest level
    above the ground at least CLOUD_BOTTOM_RH humid, its top the first above that which is less than
    CLOUD_TOP_RH humid (or the highest level)."""
    known = [(h, rh) for h, rh in levels if h is not None and rh is not None and h > elevation]
    bottom = next((k for k, (_, rh) in enumerate(known) if rh >= CLOUD_BOTTOM_RH), None)
    if bottom is None:
        return None
    top = next((k for k in range(bottom + 1, len(known)) if known[k][1] < CLOUD_TOP_RH), len(known) - 1)
    return [round(known[bottom][0]), round(known[top][0])]


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


async def request_batch(url: str) -> list:
    """The forecasts of a request; asked once more, a minute later, when the service says too many
    have been asked of it."""
    for attempt in range(2):
        try:
            return await request_forecast(url)
        except WindsError as e:
            if attempt or 'HTTP 429' not in str(e):
                raise
            logger.warning('The forecast service asked us to slow down; trying again in a minute')
            await asyncio.sleep(BATCH_SECONDS)
        except Exception as e:
            raise WindsError(f'Could not reach the forecast service: {e}') from e


async def fetch_wind_field(places: Sequence[Tuple[float, float]], progress=None, cancelled=None) -> dict:
    """Fetch the field over `places` ([(lat, lon)]), keep it, and return it:

    {source, fetched_at, spacing (degrees), points: [{lat, lon, elevation}], hours: [time (UTC,
    ISO)], winds: [for each point: [for each hour: [[height (m above sea level), speed (m/s),
    direction FROM (degrees)], ...]]], rain: [for each point: [mm in each hour]], clouds: [for each
    point: [for each hour: [bottom, top] (m above sea level) or None]]}

    `progress(done, total)`, if given, hears how many points have been fetched; once `cancelled()`, if
    given, is true, it stops (WindsError) and keeps nothing."""
    spacing, points = field_points(places)
    forecasts = []
    last = None
    for start in range(0, len(points), BATCH):
        batch = points[start:start + BATCH]
        if last is not None:
            await asyncio.sleep(max(BATCH_SECONDS - (time.monotonic() - last), 0))
        if cancelled and cancelled():
            raise WindsError('Cancelled')
        last = time.monotonic()
        answered = await request_batch(forecast_url(batch))
        if len(answered) != len(batch):
            raise WindsError(f'The forecast service answered for {len(answered)} of {len(batch)} places')
        forecasts.extend(parse_forecast(f) for f in answered)
        if progress:
            progress(len(forecasts), len(points))

    # Every point has the same hours (Open-Meteo forecasts the same hours everywhere); a point which
    # is short of any is given its last.
    hours = [h['time'] for h in max(forecasts, key=lambda f: len(f['hours']))['hours']]
    winds, rain, clouds = [], [], []
    for forecast in forecasts:
        by_time = {h['time']: h for h in forecast['hours']}
        last = forecast['hours'][-1]
        winds.append([by_time.get(t, last)['winds'] for t in hours])
        rain.append([by_time.get(t, last)['precipitation'] for t in hours])
        clouds.append([by_time.get(t, last).get('cloud') for t in hours])
    field = dict(
        source='Open-Meteo',
        fetched_at=now().isoformat(),
        spacing=spacing,
        points=[dict(lat=lat, lon=lon, elevation=f['elevation']) for (lat, lon), f in zip(points, forecasts)],
        hours=hours,
        winds=winds,
        rain=rain,
        clouds=clouds,
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


def field_summary() -> Optional[dict]:
    """What the newest field is, without its winds: {fetched_at, spacing, points, first_hour, last_hour,
    size (bytes)}, or None."""
    for path in sorted(winds_directory().glob('field-*.json'), reverse=True):
        stat = path.stat()
        key = (str(path), stat.st_mtime, stat.st_size)
        if _summary_cache.get('key') != key:
            try:
                field = json.loads(path.read_text())
            except Exception as e:
                logger.warning(f'Could not read the winds kept in {path}', exc_info=e)
                continue
            _summary_cache.update(key=key, summary=dict(
                fetched_at=field['fetched_at'], spacing=field['spacing'], points=len(field['points']),
                first_hour=field['hours'][0], last_hour=field['hours'][-1], size=stat.st_size))
        return _summary_cache['summary']
    return None


_summary_cache = dict()

# The weather subscription: one recurring Download of a field around the saved targets.
WEATHER_URL = OPEN_METEO_URL
WEATHER_DOWNLOADER = 'open_meteo'


def target_places() -> List[Tuple[float, float]]:
    """The places a field is downloaded around: the saved nuclear targets."""
    return [(t['lat'], t['lon']) for t in get_map_nuclear_config().targets]


def get_weather_download(session: Session) -> Optional[Download]:
    return session.query(Download).filter_by(url=WEATHER_URL, downloader=WEATHER_DOWNLOADER).one_or_none()


def set_weather_subscription(session: Session, enabled: bool):
    """Subscribe to the weather (a Download every day, the first now), or not (no Download)."""
    download = get_weather_download(session)
    if enabled and not download:
        download = download_manager.get_or_create_download(session, WEATHER_URL, reset_attempts=True,
                                                           override_skip=True)
        download.downloader = WEATHER_DOWNLOADER
        download.frequency = DownloadFrequency.daily
        download.location = '/map/manage'
        download.settings = {}
        download.renew(reset_attempts=True)
    elif not enabled and download:
        session.delete(download)
    else:
        return
    session.commit()
    save_downloads_config.activate_switch()


def download_weather_now(session: Session) -> bool:
    """Download the weather now (it is subscribed to), rather than when it is next due."""
    download = get_weather_download(session)
    if not download:
        return False
    download.renew(reset_attempts=True)
    session.commit()
    return True


def weather_status(session: Session) -> dict:
    """The weather subscription: whether it is on, its Download, the targets it is around, and the
    field kept."""
    download = get_weather_download(session)
    places = target_places()
    spacing = points = None
    if places:
        try:
            spacing, field = field_points(places)
            points = len(field)
        except WindsError:
            pass
    return dict(
        enabled=download is not None,
        download=dict(download.__json__(), error=download.error) if download else None,
        targets=len(places),
        spacing=spacing,
        points=points,
        # About how long a download takes (s): the forecast service allows so many places a minute.
        seconds=BATCH_SECONDS * ((points - 1) // BATCH) if points else None,
        field=field_summary(),
    )


@dataclass
class PreparedWeather:
    places: List[Tuple[float, float]]


@dataclass
class ExecutedWeather:
    points: int = 0
    error: Optional[str] = None


class WeatherDownloader(Downloader):
    """Downloads the field of forecast winds aloft around the saved nuclear targets."""

    name = WEATHER_DOWNLOADER
    pretty_name = 'Open-Meteo weather'
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedWeather:
        return PreparedWeather(places=target_places())

    async def execute_download(self, prepared: PreparedWeather, ctx: DownloadContext,
                               download: Download = None) -> ExecutedWeather:
        # No targets: nothing to download around, and nothing wrong.
        if not prepared.places:
            return ExecutedWeather()
        try:
            field = await fetch_wind_field(
                prepared.places,
                progress=lambda done, total: ctx.report_progress(dict(percent=100 * done / total)),
                cancelled=ctx.is_cancelled)
        except WindsError as e:
            return ExecutedWeather(error=str(e))
        finally:
            ctx.clear_progress()
        return ExecutedWeather(points=len(field['points']))

    def finalize_download(self, session: Session, download: Download, executed: ExecutedWeather) -> DownloadResult:
        if executed.error:
            return DownloadResult(success=False, error=executed.error)
        return DownloadResult(success=True, location='/map/manage')


weather_downloader = WeatherDownloader()
