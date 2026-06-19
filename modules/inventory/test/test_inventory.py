import pytest

from modules.inventory import common as inventory_common
from modules.inventory.defaults import (slugify, default_fields, recommended_food_storage_items,
                                         RECOMMENDED_ONE_YEAR_FOOD_COUNTS)
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


def test_save_inventory_fields_preserve_compute_metadata(food_inventory_factory, test_inventory_configs):
    """A field's extra `compute` metadata (e.g. count-by-weight) must round-trip through save and re-import."""
    config = test_inventory_configs
    slug = food_inventory_factory()
    compute = {'kind': 'count_by_weight', 'total': 'total_weight', 'unit': 'unit_weight'}
    saved = config.save_inventory(slug, dict(fields=[
        dict(key='name', label='Name', type='text'),
        dict(key='unit_weight', label='Unit Weight', type='quantity', unit='g'),
        dict(key='total_weight', label='Total Weight', type='quantity', unit='g'),
        dict(key='count', label='Count', type='number', compute=compute),
    ]))
    assert next(f for f in saved['fields'] if f['key'] == 'count')['compute'] == compute

    # A fresh config instance re-reads from disk; the metadata persists.
    fresh = inventory_common.InventoriesConfig()
    fresh.initialize()
    restored = fresh.get_inventory(slug)
    assert next(f for f in restored['fields'] if f['key'] == 'count')['compute'] == compute


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


def test_recommended_food_storage_items():
    """The example supply joins the shipped food catalog (per-package nutrition) with the recommended counts."""
    items = recommended_food_storage_items()
    # One item per recommended count, all resolved against the catalog.
    assert len(items) == len(RECOMMENDED_ONE_YEAR_FOOD_COUNTS)
    # Kept generic: no brand names.
    assert all(not item.get('brand') for item in items)
    # Counts are positive strings; the per-package calorie basis comes from the catalog.
    assert all(item['count'] and int(item['count']) > 0 for item in items)
    rice = next(i for i in items if i['name'] == 'Long Grain White Rice')
    assert rice['count'] == '14'
    assert rice['calories'] == '8040'
    assert rice['item_size'] == '5' and rice['item_size_unit'] == 'lb'
    # Total stored calories approximate one adult-year at ~3,000 kcal/day.
    total = sum(int(i['calories']) * int(i['count']) for i in items if i.get('calories'))
    assert 1_000_000 < total < 1_300_000


def test_seed_defaults_populates_food_storage(test_inventory_configs):
    config = test_inventory_configs
    config.seed_defaults()
    inventories = config.all_inventories()
    assert len(inventories) == 1
    inv = inventories[0]
    assert inv['name'] == 'Food Storage'
    assert inv['type'] == 'food'
    # Seeded with the full recommended one-adult/one-year supply, with server-assigned ids.
    assert len(inv['items']) == len(RECOMMENDED_ONE_YEAR_FOOD_COUNTS)
    assert all(isinstance(i['id'], int) for i in inv['items'])


def test_seed_defaults_idempotent(test_inventory_configs):
    config = test_inventory_configs
    config.seed_defaults()
    config.seed_defaults()
    assert len(config.all_inventories()) == 1


def _write_backup(config, slug, date, items, name='Food Storage'):
    """Write a dated backup file for an inventory (as the daily save would)."""
    from wrolpi.common import write_config_data
    backup = config._get_backup_file(slug, date)
    backup.parent.mkdir(parents=True, exist_ok=True)
    write_config_data(dict(version=9, slug=slug, name=name, type='food',
                           fields=default_fields('food'), items=items), backup)
    return backup


def test_restore_overwrite_replaces_inventory(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory(items=[dict(id=1, name='Rice', count='4'), dict(id=2, name='Beans', count='2')])
    _write_backup(config, slug, '20260101', name='Old Name',
                  items=[dict(id=1, name='Rice', count='99'), dict(id=3, name='Oats', count='5')])

    preview = config.preview_restore(slug, '20260101', 'overwrite')
    assert {i['id'] for i in preview['add']} == {3}      # Oats only in the backup
    assert {i['id'] for i in preview['remove']} == {2}   # Beans only in the current inventory
    assert preview['unchanged'] == 1                     # Rice (id 1) is in both

    restored = config.apply_restore(slug, '20260101', 'overwrite')
    assert restored['name'] == 'Old Name'
    assert {i['name'] for i in restored['items']} == {'Rice', 'Oats'}
    # Overwrite takes the backup's value for the shared item.
    assert next(i for i in restored['items'] if i['name'] == 'Rice')['count'] == '99'


def test_restore_merge_unions_items_by_id(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    slug = food_inventory_factory(items=[dict(id=1, name='Rice', count='4')])
    _write_backup(config, slug, '20260101',
                  items=[dict(id=1, name='Rice', count='99'), dict(id=2, name='Beans', count='2')])

    preview = config.preview_restore(slug, '20260101', 'merge')
    assert {i['id'] for i in preview['add']} == {2}      # only Beans is new; id 1 already present
    assert preview['remove'] == []

    restored = config.apply_restore(slug, '20260101', 'merge')
    assert {i['name'] for i in restored['items']} == {'Rice', 'Beans'}
    # Merge keeps the existing item untouched (does NOT take the backup's count=99 for id 1).
    assert next(i for i in restored['items'] if i['name'] == 'Rice')['count'] == '4'


def test_restore_rejects_bad_mode_and_missing_backup(food_inventory_factory, test_inventory_configs):
    from wrolpi.errors import ValidationError
    config = test_inventory_configs
    slug = food_inventory_factory()
    with pytest.raises(ValidationError):
        config.preview_restore(slug, '20260101', 'bogus')
    with pytest.raises(ValidationError):
        config.preview_restore(slug, '20260101', 'overwrite')  # no such backup file
    # A non-YYYYMMDD backup_date must be rejected (path-traversal guard), not used to build a path.
    with pytest.raises(ValidationError):
        config.preview_restore(slug, '../../../../etc/passwd', 'overwrite')


def test_restore_overwrite_rejects_corrupt_fields(food_inventory_factory, test_inventory_configs):
    """A backup with a malformed field (no 'key') is rejected with a 400, not a 500 inside the save lock."""
    from wrolpi.common import write_config_data
    from wrolpi.errors import ValidationError
    config = test_inventory_configs
    slug = food_inventory_factory(items=[dict(id=1, name='Rice', count='4')])
    backup = config._get_backup_file(slug, '20260101')
    backup.parent.mkdir(parents=True, exist_ok=True)
    write_config_data(dict(version=9, slug=slug, name='Food Storage', type='food',
                           fields=[dict(label='Broken', type='text')],  # missing 'key'
                           items=[]), backup)
    with pytest.raises(ValidationError):
        config.apply_restore(slug, '20260101', 'overwrite')


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
