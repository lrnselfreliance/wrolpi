import pytest

from modules.inventory import Inventory, Item, DEFAULT_CATEGORIES, DEFAULT_INVENTORIES


@pytest.fixture
def test_inventory(test_session):
    inventory = Inventory(name='Test Inventory')
    test_session.add(inventory)
    test_session.commit()
    return inventory


@pytest.fixture
def init_test_inventory(test_session):
    for subcategory, category in DEFAULT_CATEGORIES:
        item = Item(subcategory=subcategory, category=category)
        test_session.add(item)

    for name in DEFAULT_INVENTORIES:
        inv = Inventory(name=name)
        test_session.add(inv)

    inventory = test_session.query(Inventory).filter_by(name='Food Storage').one()
    test_session.commit()
    yield inventory
