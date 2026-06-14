import json
from http import HTTPStatus

import pytest


@pytest.mark.asyncio
async def test_inventory_lifecycle_api(test_inventory_configs, async_client):
    """Create, list (full), rename, and delete an inventory via the API."""
    request, response = await async_client.post('/api/inventory',
                                                 content=json.dumps(dict(name='Food Storage', type='food')))
    assert response.status_code == HTTPStatus.CREATED, response.status_code
    inventory = response.json['inventory']
    slug = inventory['slug']
    assert slug == 'food-storage'
    assert inventory['fields'], 'food inventory should be seeded with default fields'

    # GET / returns every inventory in full (fields + items) in one request.
    request, response = await async_client.get('/api/inventory')
    assert response.status_code == HTTPStatus.OK
    assert response.json['inventories'][0]['name'] == 'Food Storage'
    assert 'items' in response.json['inventories'][0]

    # Rename via whole-inventory PUT; slug stays stable.
    request, response = await async_client.put(f'/api/inventory/{slug}', content=json.dumps(dict(name='Pantry')))
    assert response.status_code == HTTPStatus.OK, response.status_code
    assert response.json['inventory']['name'] == 'Pantry'
    assert response.json['inventory']['slug'] == slug

    request, response = await async_client.delete(f'/api/inventory/{slug}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code

    request, response = await async_client.get('/api/inventory')
    assert len(response.json['inventories']) == 0


@pytest.mark.asyncio
async def test_save_items_and_fields_api(food_inventory_factory, async_client):
    """Items and fields are persisted with a single whole-inventory PUT."""
    slug = food_inventory_factory()

    items = [
        {'brand': 'Salty', 'name': 'Salt', 'item_size': '1', 'item_size_unit': 'lb', 'count': '5'},
        {'brand': 'Ricey', 'name': 'Rice', 'count': '4'},
    ]
    request, response = await async_client.put(f'/api/inventory/{slug}', content=json.dumps(dict(items=items)))
    assert response.status_code == HTTPStatus.OK, response.json
    saved_items = response.json['inventory']['items']
    assert {i['name'] for i in saved_items} == {'Salt', 'Rice'}
    assert all(isinstance(i['id'], int) for i in saved_items)

    # Replace the field schema in the same kind of request.
    new_fields = [
        {'key': 'name', 'label': 'Name', 'type': 'text'},
        {'key': 'location', 'label': 'Location', 'type': 'location'},
    ]
    request, response = await async_client.put(f'/api/inventory/{slug}', content=json.dumps(dict(fields=new_fields)))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [f['key'] for f in response.json['inventory']['fields']] == ['name', 'location']


@pytest.mark.asyncio
async def test_put_version_conflict_api(food_inventory_factory, async_client):
    """A stale version is rejected with 409 instead of clobbering a newer save."""
    slug = food_inventory_factory()
    request, response = await async_client.get('/api/inventory')
    inventory = next(i for i in response.json['inventories'] if i['slug'] == slug)
    version = inventory['version']

    request, response = await async_client.put(f'/api/inventory/{slug}',
                                               content=json.dumps(dict(name='First', version=version)))
    assert response.status_code == HTTPStatus.OK

    request, response = await async_client.put(f'/api/inventory/{slug}',
                                               content=json.dumps(dict(name='Stale', version=version)))
    assert response.status_code == HTTPStatus.CONFLICT, response.status_code


@pytest.mark.asyncio
async def test_missing_inventory_404(test_inventory_configs, async_client):
    request, response = await async_client.put('/api/inventory/does-not-exist', content=json.dumps(dict(name='x')))
    assert response.status_code == HTTPStatus.NOT_FOUND, response.status_code
