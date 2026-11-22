import json
from http import HTTPStatus
from unittest import mock

import pytest

from modules.map import winds
from wrolpi import flags


def forecast(elevation=100.0, hours=2):
    """An Open-Meteo forecast with three pressure levels, one of them below the ground."""
    hourly = {'time': [f'2026-11-22T{h:02d}:00' for h in range(hours)],
              'wind_speed_10m': [2.0] * hours, 'wind_direction_10m': [180] * hours,
              'precipitation': [0.0, 1.5][:hours]}
    for level, height, speed, direction in [(1000, 50.0, 5.0, 190), (850, 1500.0, 10.0, 220),
                                            (500, 5600.0, 25.0, 260)]:
        hourly[f'geopotential_height_{level}hPa'] = [height] * hours
        hourly[f'wind_speed_{level}hPa'] = [speed] * hours
        hourly[f'wind_direction_{level}hPa'] = [direction] * hours
    return {'latitude': 61.0, 'longitude': -149.0, 'elevation': elevation, 'hourly': hourly}


def test_round_place():
    """A place is rounded to the whole degree it is in before it is sent."""
    assert winds.round_place(61.2, -149.3) == (61, -149)
    assert winds.round_place(-33.6, 151.5) == (-34, 152)
    assert winds.round_place(10.0, 179.8) == (10, -180)
    assert winds.round_place(89.9, 0.0) == (90, 0)


def test_forecast_url_asks_for_every_level():
    url = winds.forecast_url(61, -149)
    assert url.startswith(winds.OPEN_METEO_URL)
    assert 'latitude=61' in url and 'longitude=-149' in url
    for level in winds.PRESSURE_LEVELS:
        assert f'geopotential_height_{level}hPa' in url
    assert 'wind_speed_unit=ms' in url


def test_parse_forecast():
    """Each hour's winds go up from 10 m above the ground; a level below the ground is left out."""
    parsed = winds.parse_forecast(forecast())
    assert parsed['elevation'] == 100.0
    assert [h['time'] for h in parsed['hours']] == ['2026-11-22T00:00Z', '2026-11-22T01:00Z']
    assert parsed['hours'][0]['winds'] == [[110.0, 2.0, 180], [1500.0, 10.0, 220], [5600.0, 25.0, 260]]
    assert parsed['hours'][1]['precipitation'] == 1.5


def test_parse_forecast_skips_missing():
    data = forecast(hours=1)
    data['hourly']['wind_speed_850hPa'] = [None]
    parsed = winds.parse_forecast(data)
    assert [w[0] for w in parsed['hours'][0]['winds']] == [110.0, 5600.0]


def test_parse_forecast_rejects_nonsense():
    with pytest.raises(winds.WindsError):
        winds.parse_forecast({'error': True, 'reason': 'nope'})
    data = forecast(hours=1)
    for key in list(data['hourly']):
        if key != 'time':
            data['hourly'][key] = [None]
    with pytest.raises(winds.WindsError):
        winds.parse_forecast(data)


@pytest.mark.asyncio
async def test_fetch_winds_keeps_the_forecast(test_directory):
    """A fetched forecast is kept for the degree it is for, and found again from anywhere in it."""
    requested = []

    async def fake_request(url):
        requested.append(url)
        return forecast()

    with mock.patch('modules.map.winds.request_forecast', fake_request):
        fetched = await winds.fetch_winds(61.2, -149.3)
    assert 'latitude=61&longitude=-149' in requested[0]
    assert fetched['lat'] == 61 and fetched['lon'] == -149
    assert fetched['source'] == 'Open-Meteo'
    assert winds.cached_winds(60.8, -148.6) == fetched
    assert winds.cached_winds(10, 10) is None
    # Kept where the file lists do not look.
    assert winds.winds_path(61, -149).parent.name.startswith('.')


@pytest.mark.asyncio
async def test_fetch_winds_failure(test_directory):
    async def unreachable(url):
        raise OSError('no route to host')

    with mock.patch('modules.map.winds.request_forecast', unreachable):
        with pytest.raises(winds.WindsError):
            await winds.fetch_winds(61, -149)
    assert winds.cached_winds(61, -149) is None


@pytest.mark.asyncio
async def test_winds_api(async_client, test_directory, flags_lock):
    """The forecast is fetched on request, kept, and given back without fetching again."""
    request, response = await async_client.get('/api/map/fallout/winds?lat=61.2&lon=-149.3')
    assert response.status_code == HTTPStatus.OK
    assert response.json['winds'] is None

    async def fake_request(url):
        return forecast()

    flags.have_internet.set()
    try:
        with mock.patch('modules.map.winds.request_forecast', fake_request):
            request, response = await async_client.post('/api/map/fallout/winds',
                                                        content=json.dumps({'lat': 61.2, 'lon': -149.3}))
    finally:
        flags.have_internet.clear()
    assert response.status_code == HTTPStatus.OK
    assert response.json['winds']['hours'][0]['winds'][0] == [110.0, 2.0, 180]

    request, response = await async_client.get('/api/map/fallout/winds?lat=61.4&lon=-149.1')
    assert response.json['winds']['lat'] == 61


@pytest.mark.asyncio
async def test_winds_api_errors(async_client, test_directory, flags_lock):
    request, response = await async_client.get('/api/map/fallout/winds')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    flags.have_internet.clear()
    request, response = await async_client.post('/api/map/fallout/winds', content=json.dumps({'lat': 61, 'lon': -149}))
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert 'Internet' in response.json['error']

    async def broken(url):
        raise winds.WindsError('The forecast service answered HTTP 500')

    flags.have_internet.set()
    try:
        with mock.patch('modules.map.winds.request_forecast', broken):
            request, response = await async_client.post('/api/map/fallout/winds',
                                                        content=json.dumps({'lat': 61, 'lon': -149}))
    finally:
        flags.have_internet.clear()
    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert 'HTTP 500' in response.json['error']


@pytest.mark.asyncio
async def test_latest_winds(async_client, test_directory):
    """The forecast fetched most recently, wherever it is for, is the latest."""
    assert winds.latest_winds() is None

    async def fake_request(url):
        return forecast()

    with mock.patch('modules.map.winds.request_forecast', fake_request):
        await winds.fetch_winds(61, -149)
        second = await winds.fetch_winds(40, -105)
    assert winds.latest_winds() == second

    request, response = await async_client.get('/api/map/fallout/winds/latest')
    assert response.json['winds']['lat'] == 40
