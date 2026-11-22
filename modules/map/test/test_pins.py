import json
from http import HTTPStatus

import pytest

from modules.map import pins


@pytest.fixture
def test_pins_config(test_directory, async_client, monkeypatch):
    (test_directory / 'config').mkdir(exist_ok=True)
    config = pins.MapPinsConfig()
    config.initialize()
    monkeypatch.setattr(pins, 'TEST_MAP_PINS_CONFIG', config)
    yield config


def test_add_pin_kinds(test_pins_config):
    """A pin is a plain pin unless it is a target; a plain pin is written as pins always were."""
    plain = test_pins_config.add_pin(61.2, -149.9, 'Home')
    target = test_pins_config.add_pin(61.25, -149.8, 'Base', kind='target')
    assert 'kind' not in plain
    assert target['kind'] == 'target'
    assert [p['id'] for p in test_pins_config.pins] == [1, 2]
    with pytest.raises(ValueError):
        test_pins_config.add_pin(0, 0, 'Nope', kind='bunker')


@pytest.mark.asyncio
async def test_pins_api_targets(async_client, test_pins_config):
    request, response = await async_client.post('/api/map/pins', content=json.dumps(
        {'lat': 61.25, 'lon': -149.8, 'label': 'Base', 'kind': 'target'}))
    assert response.status_code == HTTPStatus.CREATED
    assert response.json['pin']['kind'] == 'target'

    request, response = await async_client.post('/api/map/pins', content=json.dumps(
        {'lat': 61.2, 'lon': -149.9, 'label': 'Home'}))
    assert response.status_code == HTTPStatus.CREATED
    assert 'kind' not in response.json['pin']

    request, response = await async_client.post('/api/map/pins', content=json.dumps(
        {'lat': 0, 'lon': 0, 'label': 'Nope', 'kind': 'bunker'}))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    request, response = await async_client.get('/api/map/pins')
    assert [p.get('kind', 'pin') for p in response.json['pins']] == ['target', 'pin']
