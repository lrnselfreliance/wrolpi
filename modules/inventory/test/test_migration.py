import threading

import pytest
import yaml

from modules.inventory import common as inventory_common
from modules.inventory.migrate import migrate_legacy_inventory, normalize_unit


def test_normalize_unit():
    assert normalize_unit('pound') == 'lb'
    assert normalize_unit('pounds') == 'lb'
    assert normalize_unit('lbs') == 'lb'
    # Already-valid mathjs units pass through unchanged.
    assert normalize_unit('oz') == 'oz'
    assert normalize_unit('gallon') == 'gallon'
    assert normalize_unit(None) is None


def _write_legacy(config, inventories):
    legacy_file = config.get_directory().parent / 'inventories.yaml'
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    with legacy_file.open('wt') as fh:
        yaml.dump(dict(version=1, inventories=inventories), fh)
    return legacy_file


def test_migrate_legacy_yaml(test_inventory_configs):
    config = test_inventory_configs
    legacy_file = _write_legacy(config, [
        dict(name='Food Storage', created_at='2024-01-01', deleted_at=None, items=[
            dict(id=1, inventory_id=1, brand='Ocean', name='Salt', item_size='25', unit='pound', count='8',
                 category='cooking ingredients', subcategory='salt', expiration_date='2030-01-01'),
            dict(id=2, inventory_id=1, brand='deleted', name='Old', item_size='1', unit='oz', count='1',
                 deleted_at='2020-01-01'),
        ]),
    ])

    assert migrate_legacy_inventory(config) is True
    config.import_all()

    inventories = config.all_inventories()
    assert len(inventories) == 1
    slug = inventories[0]['slug']
    inventory = config.get_inventory(slug)
    assert inventory['name'] == 'Food Storage'
    assert inventory['type'] == 'food'
    # The soft-deleted legacy item is dropped.
    assert len(inventory['items']) == 1
    item = inventory['items'][0]
    assert item['name'] == 'Salt'
    # Legacy pint unit 'pound' is normalized to mathjs 'lb'.
    assert item['item_size_unit'] == 'lb'

    # The legacy file is retired (renamed) and backed up so it is not migrated again.
    assert not legacy_file.is_file()
    assert legacy_file.with_suffix('.yaml.migrated').is_file()


def test_migrate_converts_epoch_expiration_dates(test_inventory_configs):
    """Legacy items stored expiration dates as epoch seconds (sometimes ``str(float)``); the migration writes
    calendar dates so no reader has to guess what an all-digit string means."""
    config = test_inventory_configs
    _write_legacy(config, [
        dict(name='Food Storage', created_at='2024-01-01', items=[
            dict(id=1, name='Salt', item_size='25', unit='lb', count='8', expiration_date=1893456000),
            dict(id=2, name='Rice', item_size='25', unit='lb', count='8', expiration_date='1893456000.0'),
            dict(id=3, name='Beans', item_size='25', unit='lb', count='8', expiration_date='2030-01-01'),
            dict(id=4, name='Odd', item_size='25', unit='lb', count='8', expiration_date='2030'),
        ]),
    ])

    assert migrate_legacy_inventory(config) is True
    config.import_all()

    inventory = config.get_inventory(config.all_inventories()[0]['slug'])
    assert [i['expiration_date'] for i in inventory['items']] == ['2030-01-01', '2030-01-01', '2030-01-01', '2030']
    # The file on disk holds calendar dates too.
    assert '1893456000' not in config.get_file(inventory['slug']).read_text()


def _write_epoch_inventory(config, version=3):
    directory = config.get_directory()
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / 'food.yaml'
    with file.open('wt') as fh:
        yaml.dump(dict(
            version=version, slug='food', name='Food', type='food', created_at='2024-01-01', viewed_at='2024-01-01',
            fields=[dict(key='name', label='Name', type='text', order=0),
                    dict(key='expiration_date', label='Expires', type='date', order=1)],
            items=[dict(id=1, name='Salt', expiration_date='1893456000'),
                   dict(id=2, name='Rice', expiration_date='2030-06-01')],
        ), fh)
    return file


def test_import_repairs_legacy_epoch_dates(test_inventory_configs):
    """Inventories migrated before dates were normalized are rewritten once by the startup import."""
    from modules.inventory.common import import_inventories_config
    config = test_inventory_configs
    file = _write_epoch_inventory(config)

    import_inventories_config()
    inventory = config.get_inventory('food')
    assert [i['expiration_date'] for i in inventory['items']] == ['2030-01-01', '2030-06-01']
    # Repaired on disk, with a version bump so stale clients notice.
    assert '1893456000' not in file.read_text()
    assert inventory['version'] == 4

    # A second import finds nothing to repair and does not rewrite the file.
    import_inventories_config()
    assert config.get_inventory('food')['version'] == 4


def test_initialize_repairs_legacy_epoch_dates_without_deadlock(test_inventory_configs):
    """`initialize()` imports while holding the non-reentrant save lock; the repair must not take it again.

    Every API process initializes the inventory store at startup, so a deadlock here hangs the whole API."""
    config = test_inventory_configs
    file = _write_epoch_inventory(config)

    thread = threading.Thread(target=config.initialize, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), 'initialize() deadlocked while repairing legacy epoch dates'

    # Repaired in memory, but not written while the lock was held.
    assert [i['expiration_date'] for i in config.get_inventory('food')['items']] == ['2030-01-01', '2030-06-01']
    assert '1893456000' in file.read_text()

    # The write happens later, outside the lock.
    config.persist_legacy_date_repairs()
    assert '1893456000' not in file.read_text()
    assert config.get_inventory('food')['version'] == 4


def test_migrate_is_idempotent(test_inventory_configs):
    config = test_inventory_configs
    _write_legacy(config, [dict(name='Food', items=[])])
    assert migrate_legacy_inventory(config) is True
    config.import_all()
    # Second run does nothing because per-inventory files now exist.
    assert migrate_legacy_inventory(config) is False
    config.import_all()
    assert len(config.all_inventories()) == 1


def test_migrate_no_legacy_data(test_inventory_configs):
    config = test_inventory_configs
    assert migrate_legacy_inventory(config) is False
    assert config.all_inventories() == []


def test_migrate_dedupes_same_named_inventories(test_inventory_configs):
    """Multiple inventories with the same name get distinct slugs (food, food-2, food-3) with no data loss."""
    config = test_inventory_configs
    _write_legacy(config, [
        dict(name='Food', items=[]),
        dict(name='Food', items=[]),
        dict(name='Food', items=[]),
    ])
    assert migrate_legacy_inventory(config) is True
    config.import_all()
    slugs = sorted(i['slug'] for i in config.all_inventories())
    assert slugs == ['food', 'food-2', 'food-3']
    assert len(config.all_inventories()) == 3  # none dropped


@pytest.mark.asyncio
async def test_import_seeds_defaults_when_empty(test_inventory_configs, async_client):
    """A fresh install with no legacy data seeds the default example inventory."""
    config = test_inventory_configs
    inventory_common.import_inventories_config()
    inventories = config.all_inventories()
    assert any(i['name'] == 'Food Storage' for i in inventories)
