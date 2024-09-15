import json
from http import HTTPStatus

import pytest

from modules.inventory import Item
from modules.inventory.inventory import save_item


def test_delete_items(test_session, init_test_inventory, test_client):
    """
    Multiple Items can be deleted in a single request.
    """
    item = dict(
        brand='Ocean',
        name='Salt',
        count='8.0',
        unit='lbs',
        item_size='25.0',
        category='cooking ingredients',
        subcategory='salt',
    )
    save_item(init_test_inventory.id, item)
    save_item(init_test_inventory.id, item)
    items = test_session.query(Item).filter(Item.brand != None).all()

    request, response = test_client.delete(f'/api/inventory/item/{items[0].id},{items[1].id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
    # Refresh all items.  Verify they were deleted.
    [test_session.refresh(i) for i in items]
    assert all([i.deleted_at for i in items])


def test_delete_item(test_session, init_test_inventory, test_client):
    """
    An item can be deleted by itself.
    """
    item = dict(
        brand='Ocean',
        name='Salt',
        count='8.0',
        unit='lbs',
        item_size='25.0',
        category='cooking ingredients',
        subcategory='salt',
    )
    save_item(init_test_inventory.id, item)
    item = test_session.query(Item).filter(Item.brand != None).one()
    assert not item.deleted_at

    request, response = test_client.delete(f'/api/inventory/item/{item.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code
    test_session.refresh(item)
    assert item.deleted_at


def test_item_api(test_session, init_test_inventory, test_client):
    """An Item can be added to an Inventory."""
    inventory_id = init_test_inventory.id
    item = {'brand': 'Salty', 'name': 'Salt', 'item_size': '1', 'unit': 'lbs', 'count': '5',
            'category': 'cooking ingredients', 'subcategory': 'salt', 'expiration_date': None}
    request, response = test_client.post(f'/api/inventory/{inventory_id}/item', content=json.dumps(item))
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code

    # Get the Item we just created.
    request, response = test_client.get(f'/api/inventory/{inventory_id}/item')
    assert response.status_code == HTTPStatus.OK
    # assert item == response.json['items'][0]
    item = response.json['items'][0]

    expiration_dates = ('1969-12-31T20:25:45.123450', None)
    for expiration_date in expiration_dates:
        item['expiration_date'] = expiration_date
        request, response = test_client.put(f'/api/inventory/item/{item["id"]}', content=json.dumps(item))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.json


@pytest.mark.asyncio
async def test_inventory_api(test_session, async_client):
    """An Inventory can be created."""
    inventory = dict(name='foo')
    request, response = await async_client.post('/api/inventory', content=json.dumps(inventory))
    assert response.status_code == HTTPStatus.CREATED, response.status_code

    request, response = await async_client.get('/api/inventory')
    assert response.status_code == HTTPStatus.OK
    inventory = response.json['inventories'][0]
    inventory_id = inventory['id']

    request, response = await async_client.get(f'/api/inventory/{inventory_id}')
    assert response.status_code == HTTPStatus.OK

    request, response = await async_client.get('/api/inventory/categories')
    assert response.status_code == HTTPStatus.OK

    request, response = await async_client.get('/api/inventory/brands')
    assert response.status_code == HTTPStatus.OK

    inventory = dict(name='new name')
    request, response = await async_client.put(f'/api/inventory/{inventory_id}', content=json.dumps(inventory))
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code

    request, response = await async_client.delete(f'/api/inventory/{inventory_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.status_code

    request, response = await async_client.get('/api/inventory')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['inventories']) == 0
