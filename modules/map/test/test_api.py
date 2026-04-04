import json
from http import HTTPStatus

import pytest


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
