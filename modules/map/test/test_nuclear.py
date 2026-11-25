import json
from http import HTTPStatus

import pytest

from modules.map import nuclear


@pytest.fixture
def test_nuclear_config(test_directory, async_client, monkeypatch):
    (test_directory / 'config').mkdir(exist_ok=True)
    config = nuclear.MapNuclearConfig()
    config.initialize()
    monkeypatch.setattr(nuclear, 'TEST_MAP_NUCLEAR_CONFIG', config)
    yield config


def saved(config, *targets):
    """`targets` ({lat, lon, label, ...}) saved in place of none."""
    return config.replace_targets(list(targets), loaded_ids=[t['id'] for t in config.targets])


def test_replace_targets(test_nuclear_config):
    """The targets given are saved in place of those loaded: kept ones keep their id and date, new ones
    get ids, and removed ones are gone."""
    a, b = saved(test_nuclear_config, {'lat': 1, 'lon': 1, 'label': 'A', 'weapon': 'yars'},
                 {'lat': 2, 'lon': 2, 'label': 'B', 'weapon': 'yars'})
    assert (a['id'], b['id']) == (1, 2)
    kept = test_nuclear_config.replace_targets([
        {'id': a['id'], 'lat': 1, 'lon': 1, 'label': 'A', 'weapon': 'custom', 'yield_kt': 20, 'fission_fraction': 1},
        {'lat': 3.1234567, 'lon': -3, 'label': ' C ', 'weapon': 'w88'},
    ], loaded_ids=[a['id'], b['id']])
    assert [(t['id'], t['label']) for t in kept] == [(1, 'A'), (3, 'C')]
    assert kept[0]['created'] == a['created'] and kept[0]['yield_kt'] == 20
    assert kept[1] == dict(id=3, lat=3.123457, lon=-3, label='C', created=kept[1]['created'], weapon='w88')
    assert test_nuclear_config.targets == kept


def test_replace_targets_refused(test_nuclear_config):
    """Nothing is saved over targets the user did not load, or which changed since; nor bad targets."""
    a, = saved(test_nuclear_config, {'lat': 1, 'lon': 1, 'label': 'A'})
    with pytest.raises(nuclear.TargetsChanged):
        test_nuclear_config.replace_targets([{'lat': 2, 'lon': 2, 'label': 'B'}], loaded_ids=[])
    with pytest.raises(nuclear.TargetsChanged):
        test_nuclear_config.replace_targets([], loaded_ids=[a['id'], 99])
    for bad in ({'lat': 1, 'lon': 1, 'label': ' '}, {'lat': 91, 'lon': 1, 'label': 'X'},
                {'lat': 'north', 'lon': 1, 'label': 'X'}, {'lat': 1, 'lon': 1, 'label': 'X', 'yield_kt': -1},
                {'lat': 1, 'lon': 1, 'label': 'X', 'fission_fraction': 2}, {'lat': 1, 'lon': 1, 'label': 'X', 'weapon': ''}):
        with pytest.raises(ValueError):
            test_nuclear_config.replace_targets([bad], loaded_ids=[a['id']])
    with pytest.raises(ValueError):
        test_nuclear_config.replace_targets([{'id': a['id'], 'lat': 1, 'lon': 1, 'label': 'A'}] * 2,
                                            loaded_ids=[a['id']])
    assert test_nuclear_config.targets == [a]


def test_replace_targets_with_none_saved(test_nuclear_config):
    """With no saved targets there is nothing to load first."""
    assert [t['label'] for t in saved(test_nuclear_config, {'lat': 1, 'lon': 1, 'label': 'A'})] == ['A']


def test_delete_target(test_nuclear_config):
    a, b = saved(test_nuclear_config, {'lat': 1, 'lon': 1, 'label': 'A'}, {'lat': 2, 'lon': 2, 'label': 'B'})
    assert test_nuclear_config.delete_target(a['id']) is True
    assert test_nuclear_config.delete_target(a['id']) is False
    assert test_nuclear_config.targets == [b]


@pytest.mark.asyncio
async def test_targets_api(async_client, test_nuclear_config):
    for i in range(20):
        saved(test_nuclear_config, *test_nuclear_config.targets, {'lat': i, 'lon': i, 'label': f'Base {i}',
                                                                  'weapon': 'yars'})
    request, response = await async_client.get('/api/map/nuclear/targets')
    assert response.status_code == HTTPStatus.OK
    loaded = [t['id'] for t in response.json['targets']]
    assert len(loaded) == 20
    one = {'id': loaded[0], 'lat': 0, 'lon': 0, 'label': 'Base 0', 'weapon': 'w76-1', 'fission_fraction': 0.5}
    # Not loaded: refused.
    request, response = await async_client.put('/api/map/nuclear/targets',
                                               content=json.dumps({'targets': [one], 'loaded_ids': []}))
    assert response.status_code == HTTPStatus.CONFLICT
    assert 'load them again' in response.json['error']
    request, response = await async_client.put('/api/map/nuclear/targets',
                                               content=json.dumps({'targets': [one], 'loaded_ids': loaded}))
    assert response.status_code == HTTPStatus.OK
    assert [t['weapon'] for t in response.json['targets']] == ['w76-1']
    request, response = await async_client.put('/api/map/nuclear/targets', content=json.dumps(
        {'targets': [{'lat': 0, 'lon': 0, 'label': ''}], 'loaded_ids': [loaded[0]]}))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    request, response = await async_client.delete(f'/api/map/nuclear/targets/{loaded[0]}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.delete(f'/api/map/nuclear/targets/{loaded[0]}')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = await async_client.get('/api/map/nuclear/targets')
    assert response.json['targets'] == []


@pytest.mark.asyncio
async def test_targets_apart_from_pins(async_client, test_nuclear_config, test_directory):
    """Targets are kept in their own config, and the pins hold none."""
    saved(test_nuclear_config, {'lat': 1, 'lon': 1, 'label': 'A'})
    test_nuclear_config.save()
    assert 'label: A' in (test_directory / 'config/map_nuclear.yaml').read_text()
    request, response = await async_client.get('/api/map/pins')
    assert all(p['label'] != 'A' for p in response.json['pins'])
