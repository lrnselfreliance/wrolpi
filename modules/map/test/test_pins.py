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


def test_target_weapon(test_pins_config):
    """A target keeps its weapon; a new weapon replaces the old one's yield and fission share."""
    target = test_pins_config.add_pin(61, -149, 'Base', kind='target', weapon='custom', yield_kt=20,
                                      fission_fraction=1.0)
    assert (target['weapon'], target['yield_kt'], target['fission_fraction']) == ('custom', 20, 1.0)
    assert test_pins_config.update_pin(target['id'], weapon='w88', fission_fraction=0.5)
    pin = test_pins_config.pins[0]
    assert pin['weapon'] == 'w88' and pin['fission_fraction'] == 0.5 and 'yield_kt' not in pin
    # A label alone leaves the weapon be.
    assert test_pins_config.update_pin(target['id'], label='Silo')
    assert test_pins_config.pins[0]['weapon'] == 'w88'


def test_target_weapon_checked(test_pins_config):
    with pytest.raises(ValueError):
        test_pins_config.add_pin(0, 0, 'Home', weapon='w88')
    with pytest.raises(ValueError):
        test_pins_config.add_pin(0, 0, 'Base', kind='target', yield_kt=0)
    with pytest.raises(ValueError):
        test_pins_config.add_pin(0, 0, 'Base', kind='target', fission_fraction=1.5)
    home = test_pins_config.add_pin(0, 0, 'Home')
    with pytest.raises(ValueError):
        test_pins_config.update_pin(home['id'], weapon='w88')


@pytest.mark.asyncio
async def test_pins_api_target_weapon(async_client, test_pins_config):
    request, response = await async_client.post('/api/map/pins', content=json.dumps(
        {'lat': 61, 'lon': -149, 'label': 'Base', 'kind': 'target', 'weapon': 'w87-0', 'fission_fraction': 0.5}))
    assert response.status_code == HTTPStatus.CREATED
    pin_id = response.json['pin']['id']
    request, response = await async_client.put(f'/api/map/pins/{pin_id}', content=json.dumps(
        {'weapon': 'custom', 'yield_kt': 15, 'fission_fraction': 1}))
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/map/pins')
    assert response.json['pins'][0]['yield_kt'] == 15
    request, response = await async_client.put(f'/api/map/pins/{pin_id}', content=json.dumps({'yield_kt': -1}))
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_set_targets_weapon(test_pins_config):
    """Every target gets the weapon at once; plain pins are left be."""
    test_pins_config.add_pin(0, 0, 'Home')
    for i in range(5):
        test_pins_config.add_pin(i, i, f'Base {i}', kind='target', weapon='custom', yield_kt=20)
    assert test_pins_config.set_targets_weapon('w88', fission_fraction=0.5) == 5
    targets = [p for p in test_pins_config.pins if p.get('kind') == 'target']
    assert all(p['weapon'] == 'w88' and 'yield_kt' not in p for p in targets)
    assert 'weapon' not in test_pins_config.pins[0]
    with pytest.raises(ValueError):
        test_pins_config.set_targets_weapon('', fission_fraction=0.5)


@pytest.mark.asyncio
async def test_targets_weapon_api(async_client, test_pins_config):
    for i in range(20):
        test_pins_config.add_pin(i, i, f'Base {i}', kind='target', weapon='yars')
    request, response = await async_client.put('/api/map/pins/targets/weapon',
                                               content=json.dumps({'weapon': 'w76-1', 'fission_fraction': 0.5}))
    assert response.status_code == HTTPStatus.OK
    assert response.json['targets'] == 20
    request, response = await async_client.get('/api/map/pins')
    assert {p['weapon'] for p in response.json['pins']} == {'w76-1'}
    request, response = await async_client.put('/api/map/pins/targets/weapon', content=json.dumps({'weapon': ''}))
    assert response.status_code == HTTPStatus.BAD_REQUEST
