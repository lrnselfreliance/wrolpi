import json
from datetime import datetime, timedelta
from http import HTTPStatus
from unittest import mock

import aiohttp
import pytest

from modules.map import winds
from wrolpi import flags
from wrolpi.conftest import make_test_ctx
from wrolpi.downloader import Download, DownloadFrequency


@pytest.fixture(autouse=True)
def unpaced():
    """Requests are not a minute apart in tests, and a field is fetched in one."""
    with mock.patch('modules.map.winds.BATCH_SECONDS', 0), mock.patch('modules.map.winds.BATCH', 1000):
        yield


def forecast(lat=61.0, lon=-149.0, elevation=100.0, hours=2):
    """An Open-Meteo forecast for one place, with three pressure levels, one of them below the ground."""
    hourly = {'time': [f'2026-11-22T{h:02d}:00' for h in range(hours)],
              'wind_speed_10m': [2.0] * hours, 'wind_direction_10m': [180] * hours,
              'precipitation': [0.0, 1.5][:hours]}
    for level, height, speed, direction in [(1000, 50.0, 5.0, 190), (850, 1500.0, 10.0, 220),
                                            (500, 5600.0, 25.0, 260)]:
        hourly[f'geopotential_height_{level}hPa'] = [height] * hours
        hourly[f'wind_speed_{level}hPa'] = [speed] * hours
        hourly[f'wind_direction_{level}hPa'] = [direction] * hours
    # Humid from 925 to 700 hPa (a cloud from about 800 m to 3,000 m), dry above.
    for level, height, rh in [(1000, 50.0, 70), (975, 300.0, 75), (950, 550.0, 78), (925, 800.0, 85),
                              (900, 1000.0, 90), (850, 1500.0, 95), (800, 2000.0, 90), (700, 3000.0, 82),
                              (600, 4200.0, 55), (500, 5600.0, 40), (400, 7200.0, 30), (300, 9200.0, 20)]:
        hourly[f'relative_humidity_{level}hPa'] = [rh] * hours
        hourly.setdefault(f'geopotential_height_{level}hPa', [height] * hours)
    return {'latitude': lat, 'longitude': lon, 'elevation': elevation, 'hourly': hourly}


def fake_service(requested):
    """A forecast service which answers every place asked of it, and keeps the URLs asked."""

    async def request(url):
        requested.append(url)
        query = dict(part.split('=', 1) for part in url.split('?', 1)[1].split('&'))
        lats = query['latitude'].replace('%2C', ',').split(',')
        lons = query['longitude'].replace('%2C', ',').split(',')
        return [forecast(float(a), float(b)) for a, b in zip(lats, lons)]

    return request


def test_field_points_around_one_place():
    """Close together around one place: every whole degree within the margin."""
    spacing, points = winds.field_points([(61.2, -149.3)])
    assert spacing == 1
    assert (61, -149) in points and (55, -155) not in points and (56, -155) in points
    assert all(abs(lat - 61.2) <= winds.MARGIN and abs(lon + 149.3) <= winds.MARGIN for lat, lon in points)
    assert len(points) <= winds.MAX_POINTS


def test_field_points_spread_out():
    """Over a country, further apart, to stay within MAX_POINTS; points of nearby places are shared."""
    places = [(40.6, -75.4), (33.6, -84.4), (47.4, -122.3), (25.8, -80.3), (61.2, -149.9), (19.7, -155.0)]
    spacing, points = winds.field_points(places)
    assert spacing > 1
    assert len(points) <= winds.MAX_POINTS
    assert all(lat % spacing == 0 and lon % spacing == 0 for lat, lon in points)
    assert len(set(points)) == len(points)


def test_field_points_wrap():
    """Around the antimeridian, longitudes wrap."""
    spacing, points = winds.field_points([(52.0, 179.0)])
    assert all(-180 <= lon < 180 for _, lon in points)
    assert any(lon < -170 for _, lon in points) and any(lon > 170 for _, lon in points)


def test_forecast_url_asks_for_every_place_and_level():
    url = winds.forecast_url([(61, -149), (60, -150)])
    assert url.startswith(winds.OPEN_METEO_URL)
    assert 'latitude=61%2C60' in url and 'longitude=-149%2C-150' in url
    for level in winds.PRESSURE_LEVELS:
        assert f'geopotential_height_{level}hPa' in url
    for level in winds.HUMIDITY_LEVELS:
        assert f'relative_humidity_{level}hPa' in url
    assert 'wind_speed_unit=ms' in url
    # The forecast starts at midnight UTC: a third day covers the 48 hours after a burst this hour.
    assert f'forecast_days={winds.FORECAST_DAYS}' in url and winds.FORECAST_DAYS >= 3


def test_parse_forecast():
    """Each hour's winds go up from 10 m above the ground; a level below the ground is left out."""
    parsed = winds.parse_forecast(forecast())
    assert parsed['elevation'] == 100.0
    assert [h['time'] for h in parsed['hours']] == ['2026-11-22T00:00Z', '2026-11-22T01:00Z']
    assert parsed['hours'][0]['winds'] == [[110, 2.0, 180], [1500, 10.0, 220], [5600, 25.0, 260]]
    assert parsed['hours'][1]['precipitation'] == 1.5
    # The cloud rain falls from: from the first level at least 80% humid to the first above it below 60%.
    assert parsed['hours'][0]['cloud'] == [800, 4200]


def test_cloud_layer():
    assert winds.cloud_layer(0, [(100, 50), (1000, 70)]) is None
    # Levels below the ground are left out; humid to the top: the top is the highest level.
    assert winds.cloud_layer(500, [(100, 95), (1000, 85), (2000, 90)]) == [1000, 2000]
    assert winds.cloud_layer(0, [(100, 85), (1000, None), (2000, 59), (3000, 90)]) == [100, 2000]


def test_parse_forecast_rejects_nonsense():
    with pytest.raises(winds.WindsError):
        winds.parse_forecast({'error': True, 'reason': 'nope'})


@pytest.mark.asyncio
async def test_fetch_wind_field(test_directory):
    """A field is fetched in batches, kept, and found again as the latest."""
    requested, heard, slept = [], [], []

    async def sleep(seconds):
        slept.append(seconds)

    places = [(61.2, -149.3), (40.6, -75.4)]
    with mock.patch('modules.map.winds.request_forecast', fake_service(requested)), \
            mock.patch('modules.map.winds.BATCH', 50), mock.patch('modules.map.winds.BATCH_SECONDS', 61), \
            mock.patch('modules.map.winds.asyncio.sleep', sleep):
        field = await winds.fetch_wind_field(places, lambda done, total: heard.append((done, total)))
    spacing, points = winds.field_points(places)
    assert len(requested) == -(-len(points) // 50)
    # Each request after the first waits out the rest of a minute from the one before it.
    assert len(slept) == len(requested) - 1 and all(50 < s <= 61 for s in slept)
    assert heard[-1] == (len(points), len(points)) and len(heard) == len(requested)
    assert field['spacing'] == spacing
    assert [(p['lat'], p['lon']) for p in field['points']] == points
    assert len(field['winds']) == len(points) and len(field['winds'][0]) == len(field['hours']) == 2
    assert field['winds'][0][0][0] == [110, 2.0, 180]
    assert field['rain'][0] == [0.0, 1.5]
    assert field['clouds'][0] == [[800, 4200], [800, 4200]]
    assert winds.latest_field() == field
    # Kept where the file lists do not look.
    assert winds.winds_directory().name.startswith('.')


@pytest.mark.asyncio
async def test_fetch_wind_field_keeps_the_newest(test_directory):
    """Only the newest field is kept: a simulation is of bursts now."""
    assert winds.KEPT_FIELDS == 1
    with mock.patch('modules.map.winds.request_forecast', fake_service([])), \
            mock.patch('modules.map.winds.now') as fake_now:
        from datetime import datetime, timezone
        for minute in range(3):
            fake_now.return_value = datetime(2026, 11, 22, 0, minute, tzinfo=timezone.utc)
            await winds.fetch_wind_field([(10, 10)])
    kept = sorted(winds.winds_directory().glob('field-*.json'))
    assert len(kept) == 1
    assert winds.latest_field()['fetched_at'].startswith('2026-11-22T00:02')


@pytest.mark.asyncio
async def test_fetch_wind_field_cancelled(test_directory):
    """Cancelled between requests, nothing is kept, and the field before stays."""
    with mock.patch('modules.map.winds.request_forecast', fake_service([])):
        before = await winds.fetch_wind_field([(10, 10)])
    asked = []
    with mock.patch('modules.map.winds.request_forecast', fake_service(asked)), \
            mock.patch('modules.map.winds.BATCH', 1):
        with pytest.raises(winds.WindsError, match='Cancelled'):
            await winds.fetch_wind_field([(61, -149)], cancelled=lambda: bool(asked))
    assert len(asked) == 1
    assert winds.latest_field() == before


@pytest.mark.asyncio
async def test_fetch_wind_field_failure(test_directory):
    async def unreachable(url):
        raise OSError('no route to host')

    with mock.patch('modules.map.winds.request_forecast', unreachable):
        with pytest.raises(winds.WindsError):
            await winds.fetch_wind_field([(61, -149)])
    assert winds.latest_field() is None

    async def short(url):
        return [forecast()]

    with mock.patch('modules.map.winds.request_forecast', short):
        with pytest.raises(winds.WindsError):
            await winds.fetch_wind_field([(61, -149)])


@pytest.mark.asyncio
async def test_fetch_wind_field_says_why(test_directory):
    """A request which takes too long, or fails without a message, still says why."""
    import asyncio

    async def slow(url):
        raise asyncio.TimeoutError()

    with mock.patch('modules.map.winds.request_forecast', slow):
        with pytest.raises(winds.WindsError, match=f'did not answer within {winds.TIMEOUT} seconds'):
            await winds.fetch_wind_field([(61, -149)])

    async def silent(url):
        raise ConnectionResetError()

    with mock.patch('modules.map.winds.request_forecast', silent):
        with pytest.raises(winds.WindsError, match='ConnectionResetError'):
            await winds.fetch_wind_field([(61, -149)])
    assert winds.TIMEOUT >= 120


@pytest.mark.asyncio
async def test_fetch_wind_field_slows_down(test_directory):
    """Told too many have been asked of it, the service is asked again a minute later, once."""
    answers = [winds.WindsError('The forecast service answered HTTP 429')]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    service = fake_service([])

    async def busy_then_fine(url):
        if answers:
            raise answers.pop()
        return await service(url)

    with mock.patch('modules.map.winds.request_forecast', busy_then_fine), \
            mock.patch('modules.map.winds.asyncio.sleep', sleep):
        field = await winds.fetch_wind_field([(10, 10)])
    assert len(slept) == 1 and field['points']

    async def always_busy(url):
        raise winds.WindsError('The forecast service answered HTTP 429')

    with mock.patch('modules.map.winds.request_forecast', always_busy), \
            mock.patch('modules.map.winds.asyncio.sleep', sleep):
        with pytest.raises(winds.WindsError, match='429'):
            await winds.fetch_wind_field([(10, 10)])


@pytest.mark.asyncio
async def test_fetch_wind_field_reconnects(test_directory):
    """A request which cannot connect is asked again a minute later, once, rather than losing the
    batches already fetched."""
    unreachable = aiohttp.ClientConnectorError(mock.Mock(host='api.open-meteo.com', port=443, ssl='default'),
                                               OSError('Connect call failed'))
    answers = [unreachable]
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    service = fake_service([])

    async def unreachable_then_fine(url):
        if answers:
            raise answers.pop()
        return await service(url)

    with mock.patch('modules.map.winds.request_forecast', unreachable_then_fine), \
            mock.patch('modules.map.winds.asyncio.sleep', sleep):
        field = await winds.fetch_wind_field([(10, 10)])
    assert slept == [winds.BATCH_SECONDS] and field['points']

    async def always_unreachable(url):
        raise unreachable

    slept.clear()
    with mock.patch('modules.map.winds.request_forecast', always_unreachable), \
            mock.patch('modules.map.winds.asyncio.sleep', sleep):
        with pytest.raises(winds.WindsError, match='Could not reach the forecast service'):
            await winds.fetch_wind_field([(10, 10)])
    assert slept == [winds.BATCH_SECONDS]


@pytest.mark.asyncio
async def test_latest_winds_api(async_client, test_directory):
    request, response = await async_client.get('/api/map/fallout/winds/latest')
    assert response.status_code == HTTPStatus.OK
    assert response.json['winds'] is None
    with mock.patch('modules.map.winds.request_forecast', fake_service([])):
        await winds.fetch_wind_field([(61.2, -149.3)])
    request, response = await async_client.get('/api/map/fallout/winds/latest')
    assert response.json['winds']['points'][0]['elevation'] == 100.0


@pytest.mark.asyncio
async def test_weather_subscription(async_client, test_session, test_directory, test_nuclear_config):
    """Subscribing makes one daily Download of the weather, due now; unsubscribing deletes it."""
    request, response = await async_client.get('/api/map/weather')
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(enabled=False, download=None, targets=0, spacing=None, points=None, seconds=None,
                                 field=None)

    test_nuclear_config.replace_targets([{'lat': 61.2, 'lon': -149.3, 'label': 'A'}], loaded_ids=[])
    request, response = await async_client.put('/api/map/weather', content=json.dumps({'enabled': True}))
    assert response.status_code == HTTPStatus.OK
    assert response.json['enabled'] is True and response.json['targets'] == 1
    assert response.json['spacing'] == 1 and response.json['points'] > 0
    download, = test_session.query(Download).all()
    assert (download.url, download.downloader, download.frequency, download.status) == \
           (winds.WEATHER_URL, 'open_meteo', DownloadFrequency.daily, 'new')
    # Subscribing again changes nothing.
    request, response = await async_client.put('/api/map/weather', content=json.dumps({'enabled': True}))
    assert test_session.query(Download).count() == 1

    # Downloaded now, though not due.
    download.status = 'complete'
    test_session.commit()
    request, response = await async_client.post('/api/map/weather/download')
    assert response.status_code == HTTPStatus.OK
    test_session.expire_all()
    assert test_session.query(Download).one().status == 'new'

    request, response = await async_client.put('/api/map/weather', content=json.dumps({'enabled': False}))
    assert response.json['enabled'] is False
    assert test_session.query(Download).count() == 0
    request, response = await async_client.post('/api/map/weather/download')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.parametrize('finished,expected', [
    ('2026-11-27T00:07:30+00:00', '2026-11-28T00:23:00+00:00'),
    ('2026-11-27T14:00:11+00:00', '2026-11-28T14:23:00+00:00'),
    ('2026-11-27T14:59:59+00:00', '2026-11-28T14:23:00+00:00'),
])
def test_weather_downloader_avoids_the_hour(finished, expected):
    """The next day's download is at WEATHER_MINUTE past an hour, when the forecast service is not
    busy with requests made on the hour."""
    with mock.patch('modules.map.winds.now', lambda: datetime.fromisoformat(finished)):
        result = winds.weather_downloader.finalize_download(None, None, winds.ExecutedWeather(points=1))
    assert result.success is True
    assert datetime.fromisoformat(finished) + timedelta(seconds=result.retry_seconds) \
           == datetime.fromisoformat(expected)


@pytest.mark.asyncio
async def test_weather_downloader(test_session, test_directory, test_nuclear_config):
    """The downloader fetches a field around the saved targets, telling how far it has got."""
    downloader = winds.weather_downloader
    # No targets: nothing to download, and nothing wrong.
    prepared = downloader.prepare_download(test_session, None)
    assert prepared.places == []
    executed = await downloader.execute_download(prepared, make_test_ctx())
    assert downloader.finalize_download(test_session, None, executed).success is True
    assert winds.latest_field() is None

    test_nuclear_config.replace_targets([{'lat': 61.2, 'lon': -149.3, 'label': 'A'},
                                         {'lat': 40.6, 'lon': -75.4, 'label': 'B'}], loaded_ids=[])
    prepared = downloader.prepare_download(test_session, None)
    assert prepared.places == [(61.2, -149.3), (40.6, -75.4)]
    heard, cleared = [], []
    with mock.patch('modules.map.winds.request_forecast', fake_service([])), mock.patch('modules.map.winds.BATCH', 50):
        executed = await downloader.execute_download(prepared, make_test_ctx(
            report_progress=heard.append, clear_progress=lambda: cleared.append(True)))
    result = downloader.finalize_download(test_session, None, executed)
    assert result.success is True and result.location == '/map/manage'
    assert heard[-1] == dict(percent=100) and cleared == [True]
    summary = winds.field_summary()
    assert summary['points'] == executed.points == len(winds.latest_field()['points'])
    assert summary['first_hour'] < summary['last_hour'] and summary['size'] > 0

    async def broken(url):
        raise winds.WindsError('The forecast service answered HTTP 500')

    with mock.patch('modules.map.winds.request_forecast', broken):
        executed = await downloader.execute_download(prepared, make_test_ctx())
    result = downloader.finalize_download(test_session, None, executed)
    assert result.success is False and 'HTTP 500' in result.error
    # The field before stays.
    assert winds.field_summary() == summary
