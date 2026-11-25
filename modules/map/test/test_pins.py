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


def test_replace_targets(test_pins_config):
    """The targets given are saved in place of those loaded: kept ones keep their id and date, new ones
    get ids, removed ones are gone, and plain pins are left be."""
    home = test_pins_config.add_pin(0, 0, 'Home')
    a = test_pins_config.add_pin(1, 1, 'A', kind='target', weapon='yars')
    b = test_pins_config.add_pin(2, 2, 'B', kind='target', weapon='yars')
    saved = test_pins_config.replace_targets([
        {'id': a['id'], 'lat': 1, 'lon': 1, 'label': 'A', 'weapon': 'custom', 'yield_kt': 20, 'fission_fraction': 1},
        {'lat': 3.1234567, 'lon': -3, 'label': ' C ', 'weapon': 'w88'},
    ], loaded_ids=[a['id'], b['id']])
    assert [(t['id'], t['label']) for t in saved] == [(a['id'], 'A'), (4, 'C')]
    assert saved[0]['created'] == a['created'] and saved[0]['yield_kt'] == 20
    assert saved[1] == dict(id=4, lat=3.123457, lon=-3, label='C', color='red', created=saved[1]['created'],
                            kind='target', weapon='w88')
    assert test_pins_config.pins == [home] + saved


def test_replace_targets_refused(test_pins_config):
    """Nothing is saved over targets the user did not load, or which changed since; nor bad targets."""
    a = test_pins_config.add_pin(1, 1, 'A', kind='target')
    before = test_pins_config.pins
    with pytest.raises(pins.TargetsChanged):
        test_pins_config.replace_targets([{'lat': 2, 'lon': 2, 'label': 'B'}], loaded_ids=[])
    test_pins_config.add_pin(2, 2, 'B', kind='target')
    with pytest.raises(pins.TargetsChanged):
        test_pins_config.replace_targets([], loaded_ids=[a['id']])
    assert test_pins_config.pins[:1] == before
    loaded = [p['id'] for p in test_pins_config.pins]
    for bad in ({'lat': 1, 'lon': 1, 'label': ' '}, {'lat': 91, 'lon': 1, 'label': 'X'},
                {'lat': 1, 'lon': 1, 'label': 'X', 'yield_kt': -1}):
        with pytest.raises(ValueError):
            test_pins_config.replace_targets([bad], loaded_ids=loaded)
    with pytest.raises(ValueError):
        test_pins_config.replace_targets([{'id': a['id'], 'lat': 1, 'lon': 1, 'label': 'A'}] * 2, loaded_ids=loaded)
    assert len(test_pins_config.pins) == 2


def test_replace_targets_with_none_saved(test_pins_config):
    """With no saved targets there is nothing to load first."""
    saved = test_pins_config.replace_targets([{'lat': 1, 'lon': 1, 'label': 'A'}], loaded_ids=[])
    assert [t['label'] for t in saved] == ['A']


@pytest.mark.asyncio
async def test_targets_api(async_client, test_pins_config):
    for i in range(20):
        test_pins_config.add_pin(i, i, f'Base {i}', kind='target', weapon='yars')
    loaded = [p['id'] for p in test_pins_config.pins]
    one = {'id': loaded[0], 'lat': 0, 'lon': 0, 'label': 'Base 0', 'weapon': 'w76-1', 'fission_fraction': 0.5}
    # Not loaded: refused.
    request, response = await async_client.put('/api/map/pins/targets',
                                               content=json.dumps({'targets': [one], 'loaded_ids': []}))
    assert response.status_code == HTTPStatus.CONFLICT
    assert 'load them again' in response.json['error']
    request, response = await async_client.put('/api/map/pins/targets',
                                               content=json.dumps({'targets': [one], 'loaded_ids': loaded}))
    assert response.status_code == HTTPStatus.OK
    assert [t['weapon'] for t in response.json['targets']] == ['w76-1']
    request, response = await async_client.get('/api/map/pins')
    assert [p['label'] for p in response.json['pins']] == ['Base 0']
    request, response = await async_client.put('/api/map/pins/targets', content=json.dumps(
        {'targets': [{'lat': 0, 'lon': 0, 'label': ''}], 'loaded_ids': [loaded[0]]}))
    assert response.status_code == HTTPStatus.BAD_REQUEST
