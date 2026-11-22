import json
from http import HTTPStatus
from unittest import mock

import pytest

from modules.map import winds
from wrolpi import flags
from wrolpi.jobs import COMPLETE, FAILED, wait_for_job


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
    assert 'wind_speed_unit=ms' in url


def test_parse_forecast():
    """Each hour's winds go up from 10 m above the ground; a level below the ground is left out."""
    parsed = winds.parse_forecast(forecast())
    assert parsed['elevation'] == 100.0
    assert [h['time'] for h in parsed['hours']] == ['2026-11-22T00:00Z', '2026-11-22T01:00Z']
    assert parsed['hours'][0]['winds'] == [[110, 2.0, 180], [1500, 10.0, 220], [5600, 25.0, 260]]
    assert parsed['hours'][1]['precipitation'] == 1.5


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
    assert winds.latest_field() == field
    # Kept where the file lists do not look.
    assert winds.winds_directory().name.startswith('.')


@pytest.mark.asyncio
async def test_fetch_wind_field_keeps_a_few(test_directory):
    with mock.patch('modules.map.winds.request_forecast', fake_service([])), \
            mock.patch('modules.map.winds.now') as fake_now:
        from datetime import datetime, timezone
        for minute in range(winds.KEPT_FIELDS + 2):
            fake_now.return_value = datetime(2026, 11, 22, 0, minute, tzinfo=timezone.utc)
            await winds.fetch_wind_field([(10, 10)])
    kept = sorted(winds.winds_directory().glob('field-*.json'))
    assert len(kept) == winds.KEPT_FIELDS
    assert winds.latest_field()['fetched_at'].startswith(f'2026-11-22T00:0{winds.KEPT_FIELDS + 1}')


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
async def test_winds_api(async_client, test_directory, flags_lock):
    """The field is fetched by a Job on request, kept, and given back without fetching again."""
    request, response = await async_client.get('/api/map/fallout/winds/latest')
    assert response.status_code == HTTPStatus.OK
    assert response.json['winds'] is None

    flags.have_internet.set()
    try:
        with mock.patch('modules.map.winds.request_forecast', fake_service([])):
            request, response = await async_client.post('/api/map/fallout/winds',
                                                        content=json.dumps({'places': [[61.2, -149.3], [61, -150]]}))
            assert response.status_code == HTTPStatus.ACCEPTED
            assert response.json['spacing'] == 1 and response.json['seconds'] == 0
            job = await wait_for_job(response.json['job_id'], timeout=10)
    finally:
        flags.have_internet.clear()
    assert job['status'] == COMPLETE and job['progress'] == 100
    assert job['result']['spacing'] == 1

    request, response = await async_client.get('/api/map/fallout/winds/latest')
    assert response.json['winds']['points'][0]['elevation'] == 100.0


@pytest.mark.asyncio
async def test_winds_api_errors(async_client, test_directory, flags_lock):
    flags.have_internet.clear()
    request, response = await async_client.post('/api/map/fallout/winds', content=json.dumps({'places': [[61, -149]]}))
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert 'Internet' in response.json['error']

    flags.have_internet.set()
    try:
        request, response = await async_client.post('/api/map/fallout/winds',
                                                    content=json.dumps({'places': [['north', 1]]}))
        assert response.status_code == HTTPStatus.BAD_REQUEST

        async def broken(url):
            raise winds.WindsError('The forecast service answered HTTP 500')

        # Too spread out for a field.
        with mock.patch('modules.map.winds.MAX_POINTS', 5):
            places = [[0, lon] for lon in range(-180, 180, 30)]
            request, response = await async_client.post('/api/map/fallout/winds', content=json.dumps({'places': places}))
        assert response.status_code == HTTPStatus.BAD_REQUEST

        with mock.patch('modules.map.winds.request_forecast', broken):
            request, response = await async_client.post('/api/map/fallout/winds',
                                                        content=json.dumps({'places': [[61, -149]]}))
            job = await wait_for_job(response.json['job_id'], timeout=10)
        assert job['status'] == FAILED and 'HTTP 500' in job['error']
    finally:
        flags.have_internet.clear()
