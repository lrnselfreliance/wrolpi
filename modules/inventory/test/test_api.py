from http import HTTPStatus

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
