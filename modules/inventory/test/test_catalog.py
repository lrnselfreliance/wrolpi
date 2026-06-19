import json
from http import HTTPStatus

import pytest

from modules.inventory import catalog as catalog_module


def test_load_catalog_defaults():
    """The shipped catalog_defaults.yaml loads and is non-trivial."""
    defaults = catalog_module.load_catalog_defaults()
    assert len(defaults) > 30
    rice = next(d for d in defaults if d['name'] == 'Long Grain White Rice')
    assert rice['category'] == 'grains'
    assert rice['calories'] == '8040'


def test_seed_catalog_defaults_and_tombstone(test_catalog_config):
    config = test_catalog_config
    assert config.items == []

    # Seeding loads all shipped defaults.
    catalog_module.seed_catalog_defaults(config)
    seeded = len(config.items)
    assert seeded == len(catalog_module.load_catalog_defaults())
    assert sorted(config.merged_default_ids) == sorted(d['id'] for d in catalog_module.load_catalog_defaults())

    # Seeding again is idempotent (nothing re-added).
    catalog_module.seed_catalog_defaults(config)
    assert len(config.items) == seeded

    # A user-deleted default is NOT re-added on the next seed (tombstoned via merged_default_ids).
    remaining = [i for i in config.items if i['name'] != 'Canned Lunch Meat']
    catalog_module.save_catalog_items(remaining)
    catalog_module.seed_catalog_defaults(config)
    assert not any(i['name'] == 'Canned Lunch Meat' for i in config.items)


def test_catalog_file_is_not_loaded_as_an_inventory(test_inventory_configs, test_catalog_config):
    """catalog.yaml shares config/inventory/ but must never appear as an inventory."""
    # Seed the catalog (writes config/inventory/catalog.yaml) and an inventory.
    catalog_module.seed_catalog_defaults(test_catalog_config)
    test_inventory_configs.create_inventory('Food Storage', 'food')
    # Re-import the inventory directory; the catalog file must be excluded.
    test_inventory_configs.import_all()
    slugs = [i['slug'] for i in test_inventory_configs.all_inventories()]
    assert 'catalog' not in slugs
    assert slugs == ['food-storage']


def test_inventory_named_catalog_does_not_collide(test_inventory_configs):
    """A user inventory named 'Catalog' must not claim the reserved catalog slug."""
    inv = test_inventory_configs.create_inventory('Catalog', 'food')
    assert inv['slug'] != 'catalog'


def test_save_catalog_items_assigns_ids(test_catalog_config):
    saved = catalog_module.save_catalog_items([
        {'name': 'Test Beans', 'category': 'legumes', 'subcategory': 'dry beans',
         'item_size': '25', 'item_size_unit': 'lb', 'calories': '39200'},
        {'name': 'No Id Item', 'category': 'grains'},
    ])
    assert [i['name'] for i in saved] == ['Test Beans', 'No Id Item']
    assert all(isinstance(i['id'], int) for i in saved)
    assert len({i['id'] for i in saved}) == 2


@pytest.mark.asyncio
async def test_catalog_api(test_catalog_config, async_client):
    # Empty to start.
    request, response = await async_client.get('/api/inventory/catalog')
    assert response.status_code == HTTPStatus.OK
    assert response.json['catalog'] == []

    items = [{'name': 'White Rice', 'category': 'grains', 'subcategory': 'rice',
              'item_size': '5', 'item_size_unit': 'lb', 'calories': '8040'}]
    request, response = await async_client.put('/api/inventory/catalog', content=json.dumps(dict(items=items)))
    assert response.status_code == HTTPStatus.OK, response.status_code
    assert response.json['catalog'][0]['name'] == 'White Rice'
    assert isinstance(response.json['catalog'][0]['id'], int)

    # The static /catalog route is not shadowed by the dynamic /<slug> route.
    request, response = await async_client.get('/api/inventory/catalog')
    assert len(response.json['catalog']) == 1
