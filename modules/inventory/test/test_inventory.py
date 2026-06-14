import pytest

from modules.inventory import common as inventory_common
from modules.inventory.defaults import slugify, default_fields
from modules.inventory.errors import InventoryConflict


def test_slugify():
    assert slugify('Food Storage') == 'food-storage'
    assert slugify('  Tools & Stuff!! ') == 'tools-stuff'
    assert slugify('') == 'inventory'


def test_default_fields():
    food = default_fields('food')
    assert [f['key'] for f in food][:2] == ['brand', 'name']
    # Unknown type falls back to food.
    assert default_fields('nonexistent')[0]['key'] == 'brand'
    # The size field defaults to a mathjs-valid unit (lb, not pound).
    size = next(f for f in food if f['key'] == 'item_size')
    assert size['type'] == 'quantity'
    assert size['unit'] == 'lb'


def test_create_and_list_inventory(test_inventory_configs):
    config = test_inventory_configs
    inventory = config.create_inventory('Food Storage', 'food')
    assert inventory['slug'] == 'food-storage'

    inventories = config.all_inventories()
    assert len(inventories) == 1
    assert inventories[0]['name'] == 'Food Storage'
    assert inventories[0]['type'] == 'food'
    # all_inventories returns full inventories (fields + items), not summaries.
    assert [f['key'] for f in inventories[0]['fields']] == [f['key'] for f in default_fields('food')]
    assert inventories[0]['items'] == []


def test_create_inventory_unique_slug(test_inventory_configs):
    config = test_inventory_configs
    first = config.create_inventory('Tools', 'tool')
    second = config.create_inventory('Tools', 'tool')
    assert first['slug'] == 'tools'
    assert second['slug'] == 'tools-2'
    assert len(config.all_inventories()) == 2


def test_save_inventory_items(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory()

    # Whole-inventory save: add two items.  Ids are assigned server-side.
    saved = config.save_inventory(slug, dict(items=[
        dict(brand='Ocean', name='Salt', item_size='25', item_size_unit='lb', count='8', bogus='nope'),
        dict(name='Rice', count='4'),
    ]))
    items = saved['items']
    assert {i['name'] for i in items} == {'Salt', 'Rice'}
    assert all(isinstance(i['id'], int) for i in items)
    assert len({i['id'] for i in items}) == 2
    # Unknown keys not in the field schema are dropped.
    assert all('bogus' not in i for i in items)

    # Saving again with one item removed persists the deletion.
    keep = [i for i in items if i['name'] == 'Rice']
    saved = config.save_inventory(slug, dict(items=keep))
    assert [i['name'] for i in saved['items']] == ['Rice']


def test_save_inventory_fields(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory()
    new_fields = [
        dict(key='name', label='Name', type='text'),
        dict(key='location', label='Location', type='location'),
    ]
    saved = config.save_inventory(slug, dict(fields=new_fields))
    assert [f['key'] for f in saved['fields']] == ['name', 'location']
    # Order is normalized to list order.
    assert [f['order'] for f in saved['fields']] == [0, 1]


def test_save_inventory_rename_keeps_slug(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory(name='Food Storage')
    saved = config.save_inventory(slug, dict(name='Pantry'))
    # Slug is a stable id; only the display name changes.
    assert saved['slug'] == slug
    assert saved['name'] == 'Pantry'
    assert config.get_file(slug).is_file()


def test_save_inventory_version_conflict(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory()
    current = config.get_inventory(slug)
    version = current['version']

    # A save with the matching version succeeds and bumps the version.
    saved = config.save_inventory(slug, dict(name='First'), expected_version=version)
    assert saved['version'] == version + 1

    # A stale client (still on the old version) is rejected rather than clobbering.
    with pytest.raises(InventoryConflict):
        config.save_inventory(slug, dict(name='Stale'), expected_version=version)


def test_delete_inventory(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory()
    assert config.get_file(slug).is_file()
    config.delete_inventory(slug)
    assert not config.get_file(slug).is_file()
    assert config.all_inventories() == []


def test_config_round_trip(food_inventory_factory, test_inventory_configs):
    """Saving to per-inventory YAML and re-importing preserves fields and items."""
    config = test_inventory_configs
    slug = food_inventory_factory(name='Food Storage', items=[
        dict(brand='Ocean', name='Salt', item_size='25', item_size_unit='lb', count='8'),
        dict(brand='Ricey', name='Rice', item_size='10', item_size_unit='lb', count='4'),
    ])
    assert config.get_file(slug).is_file()

    # A fresh config instance re-reads the directory from disk.
    fresh = inventory_common.InventoriesConfig()
    fresh.initialize()
    restored = fresh.get_inventory(slug)
    assert restored is not None
    assert restored['name'] == 'Food Storage'
    assert {i['name'] for i in restored['items']} == {'Salt', 'Rice'}
    assert [f['key'] for f in restored['fields']] == [f['key'] for f in default_fields('food')]
