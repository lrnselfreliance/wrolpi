import json
from http import HTTPStatus
from unittest import mock

import pytest
import yaml

from modules.map.config import get_maps_config
from modules.map.conftest import vector_metadata
from wrolpi.api_utils import api_app
from wrolpi.common import get_all_configs
from wrolpi.conftest import production_like_sessions, write_lock_held_briefly


@pytest.mark.asyncio
async def test_get_files_empty(async_client, test_directory):
    """An empty map directory returns no files."""
    request, response = await async_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    assert response.json['files'] == []


@pytest.mark.asyncio
async def test_get_files(async_client, test_directory, make_files_structure):
    """PMTiles files in the map directory are listed."""
    make_files_structure([
        'map/usa.pmtiles',
        'map/oregon.pmtiles',
        'map/not-a-map.txt',
    ])

    request, response = await async_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    files = response.json['files']
    names = [f['name'] for f in files]
    assert 'oregon.pmtiles' in names
    assert 'usa.pmtiles' in names
    assert 'not-a-map.txt' not in names


@pytest.mark.asyncio
async def test_delete_file(async_client, test_directory, make_files_structure):
    """A PMTiles file can be deleted."""
    pmtiles_file, = make_files_structure(['map/oregon.pmtiles'])

    # File exists.
    request, response = await async_client.get('/api/map/files')
    assert len(response.json['files']) == 1

    # Delete the file.
    request, response = await async_client.delete('/api/map/files/oregon.pmtiles')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # File is gone.
    request, response = await async_client.get('/api/map/files')
    assert len(response.json['files']) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_file(async_client, test_directory):
    """Deleting a nonexistent file returns 404."""
    request, response = await async_client.delete('/api/map/files/nonexistent.pmtiles')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_delete_path_traversal(async_client, test_directory, make_files_structure):
    """Path traversal attempts are rejected."""
    request, response = await async_client.delete('/api/map/files/..%2F..%2Fetc%2Fpasswd')
    # Path traversal is blocked — either 400 (caught by validation) or 404 (file not found).
    assert response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND)


@pytest.mark.asyncio
async def test_get_subscriptions_empty(async_client, test_session, test_directory):
    """Catalog and empty subscriptions can be fetched."""
    request, response = await async_client.get('/api/map/subscribe')
    assert response.status_code == HTTPStatus.OK
    assert 'catalog' in response.json
    assert 'subscriptions' in response.json
    assert len(response.json['catalog']) > 0
    assert len(response.json['subscriptions']) == 0


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe(async_client, test_session, test_directory):
    """A map region can be subscribed to and unsubscribed from."""
    body = json.dumps({'name': 'Alaska', 'region': 'us-alaska'})
    request, response = await async_client.post('/api/map/subscribe', content=body)
    assert response.status_code == HTTPStatus.CREATED

    # Subscription appears in the list.
    request, response = await async_client.get('/api/map/subscribe')
    assert response.status_code == HTTPStatus.OK
    regions = [s['region'] for s in response.json['subscriptions']]
    assert 'us-alaska' in regions

    # Unsubscribe.
    request, response = await async_client.delete('/api/map/subscribe/us-alaska')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Subscription is gone.
    request, response = await async_client.get('/api/map/subscribe')
    assert len(response.json['subscriptions']) == 0


@pytest.mark.asyncio
async def test_subscribe_multiple_regions(async_client, test_session, test_directory):
    """Multiple regions share a single Download record."""
    body = json.dumps({'name': 'Alaska', 'region': 'us-alaska'})
    request, response = await async_client.post('/api/map/subscribe', content=body)
    assert response.status_code == HTTPStatus.CREATED

    body = json.dumps({'name': 'United States (West)', 'region': 'us-west'})
    request, response = await async_client.post('/api/map/subscribe', content=body)
    assert response.status_code == HTTPStatus.CREATED

    request, response = await async_client.get('/api/map/subscribe')
    regions = [s['region'] for s in response.json['subscriptions']]
    assert 'us-alaska' in regions
    assert 'us-west' in regions

    # Unsubscribe one — the other remains.
    request, response = await async_client.delete('/api/map/subscribe/us-alaska')
    assert response.status_code == HTTPStatus.NO_CONTENT

    request, response = await async_client.get('/api/map/subscribe')
    regions = [s['region'] for s in response.json['subscriptions']]
    assert 'us-alaska' not in regions
    assert 'us-west' in regions


@pytest.mark.asyncio
async def test_subscribe_invalid_region(async_client, test_session, test_directory):
    """Subscribing to an invalid region returns an error."""
    body = json.dumps({'name': 'Atlantis', 'region': 'atlantis'})
    request, response = await async_client.post('/api/map/subscribe', content=body)
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_map_default_location_empty(async_client, test_directory):
    """Default location is null when not set."""
    request, response = await async_client.get('/api/settings')
    assert response.status_code == HTTPStatus.OK
    assert response.json['map_default_location'] is None


@pytest.mark.asyncio
async def test_set_and_get_map_default_location(async_client, test_directory):
    """Setting a default map location persists and is returned in settings."""
    body = json.dumps({'config': {'map_default_location': {'lat': 40.7, 'lon': -111.9, 'zoom': 10.5}}})
    request, response = await async_client.post('/api/config?file_name=wrolpi.yaml', content=body)
    assert response.status_code == HTTPStatus.NO_CONTENT

    request, response = await async_client.get('/api/settings')
    assert response.status_code == HTTPStatus.OK
    loc = response.json['map_default_location']
    assert loc['lat'] == 40.7
    assert loc['lon'] == -111.9
    assert loc['zoom'] == 10.5


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['subscribe', 'unsubscribe'])
async def test_subscription_writes_wait_for_a_concurrent_writer(async_client, test_session, test_directory, step):
    """Subscribing and unsubscribing read before they write, so each must begin as a writer: SQLite fails a
    deferred transaction's lock upgrade instantly ("database is locked") if another connection wrote meanwhile."""
    if step == 'unsubscribe':
        _, response = await async_client.post('/api/map/subscribe',
                                              content=json.dumps({'name': 'Alaska', 'region': 'us-alaska'}))
        assert response.status_code == HTTPStatus.CREATED
    test_session.commit()
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        # Held past any slow work a request does before it writes.
        with write_lock_held_briefly(db_file, seconds=3):
            if step == 'subscribe':
                _, response = await async_client.post('/api/map/subscribe',
                                                      content=json.dumps({'name': 'Alaska', 'region': 'us-alaska'}))
            else:
                _, response = await async_client.delete('/api/map/subscribe/us-alaska')
        assert response.status_code in (HTTPStatus.CREATED, HTTPStatus.NO_CONTENT), response.body

        _, response = await async_client.get('/api/map/subscribe')
        regions = [i['region'] for i in response.json['subscriptions']]
        assert regions == (['us-alaska'] if step == 'subscribe' else [])


@pytest.mark.asyncio
async def test_get_files_describes_files(async_client, test_directory, make_pmtiles):
    """A file is described by its own metadata, and by how the map draws it."""
    make_pmtiles('map/usa.pmtiles')
    make_pmtiles('map/extras/features.pmtiles',
                 vector_metadata('towers', geometries=dict(towers='Point'), name='Features', description='Things'))

    request, response = await async_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    files = {i['map_path']: i for i in response.json['files']}
    assert files['usa.pmtiles']['kind'] == 'basemap'
    assert files['usa.pmtiles']['title'] == 'Protomaps Basemap'
    features = files['extras/features.pmtiles']
    assert features['kind'] == 'overlay'
    assert features['title'] == 'Features'
    assert features['description'] == 'Things'
    assert features['path'] == 'map/extras/features.pmtiles'
    assert features['visible'] is True
    assert features['vector_layers'] == [
        dict(id='towers', minzoom=0, maxzoom=8, description=None, geometry='Point')]


@pytest.mark.asyncio
async def test_delete_file_sub_directory(async_client, test_directory, make_pmtiles):
    """A file in a sub-directory can be deleted."""
    pmtiles_file = make_pmtiles('map/extras/deeper/features.pmtiles')

    request, response = await async_client.delete('/api/map/files/extras/deeper/features.pmtiles')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not pmtiles_file.exists()


@pytest.mark.asyncio
async def test_rebuild_search_index_sub_directory(async_client, test_directory, make_pmtiles):
    """The search index of a file in a sub-directory can be built."""
    pmtiles_file = make_pmtiles('map/regions/oregon.pmtiles')

    with mock.patch('modules.map.search._check_tippecanoe', return_value=True), \
            mock.patch('modules.map.search._run_build', new_callable=mock.AsyncMock) as mock_run_build:
        request, response = await async_client.post('/api/map/search/rebuild/regions/oregon.pmtiles')
    assert response.status_code == HTTPStatus.ACCEPTED
    cmd, description = mock_run_build.call_args.args
    assert str(pmtiles_file) in cmd


@pytest.mark.asyncio
async def test_file_visible(async_client, test_directory, make_pmtiles):
    """A map file can be ignored and shown again; the choice is saved to the maps config."""
    make_pmtiles('map/extras/api-ignored.pmtiles')
    config_file = test_directory / 'config/maps.yaml'

    body = dict(map_path='extras/api-ignored.pmtiles', visible=False)
    request, response = await async_client.post('/api/map/files/visible', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/map/files')
    assert [i['visible'] for i in response.json['files']] == [False]
    assert yaml.safe_load(config_file.read_text())['ignored_files'] == ['extras/api-ignored.pmtiles']

    body = dict(map_path='extras/api-ignored.pmtiles', visible=True)
    request, response = await async_client.post('/api/map/files/visible', json=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/map/files')
    assert [i['visible'] for i in response.json['files']] == [True]
    assert yaml.safe_load(config_file.read_text())['ignored_files'] == []


@pytest.mark.asyncio
async def test_file_visible_unknown_file(async_client, test_directory):
    """A file which does not exist cannot be ignored."""
    body = dict(map_path='missing.pmtiles', visible=False)
    request, response = await async_client.post('/api/map/files/visible', json=body)
    assert response.status_code == HTTPStatus.NOT_FOUND

    body = dict(map_path='../../etc/passwd', visible=False)
    request, response = await async_client.post('/api/map/files/visible', json=body)
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_maps_config_import(async_client, test_directory, make_pmtiles):
    """A maps config a person edited is applied when it is imported."""
    make_pmtiles('map/hand-edited.pmtiles')
    make_pmtiles('map/other.pmtiles')
    config = get_maps_config()
    config.get_file().parent.mkdir(parents=True, exist_ok=True)
    config.get_file().write_text(yaml.safe_dump(dict(version=1, ignored_files=['hand-edited.pmtiles'])))

    config.import_config()

    request, response = await async_client.get('/api/map/files')
    visible = {i['map_path']: i['visible'] for i in response.json['files']}
    assert visible == {'hand-edited.pmtiles': False, 'other.pmtiles': True}


def test_maps_config_is_shared(async_client):
    """The maps config lives in the context the Sanic workers share (a config which does not is saved by one
    worker and overwritten by another), and is among the configs WROLPi manages."""
    assert get_maps_config()._config is api_app.shared_ctx.maps_config
    assert get_all_configs()['maps.yaml'] is get_maps_config()


@pytest.mark.asyncio
async def test_map_file_has_no_sprite_of_its_own(async_client, test_directory, make_pmtiles):
    """The map draws its own icons on an overlay: a sprite sheet beside a map file is not served or reported."""
    make_pmtiles('map/extras/features.pmtiles', vector_metadata('towers'))
    (test_directory / 'map/extras/sprite.json').write_text('{}')
    (test_directory / 'map/extras/sprite.png').write_bytes(b'png')

    request, response = await async_client.get('/api/map/files')
    assert 'has_sprite' not in response.json['files'][0]
    request, response = await async_client.get('/api/map/files/sprite/extras/features.pmtiles.json')
    assert response.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED)
