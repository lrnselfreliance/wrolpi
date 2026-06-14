"""Tests for the reusable MultiFileConfig machinery, exercised through InventoriesConfig."""
from modules.inventory import common as inventory_common
from wrolpi.dates import now


def test_discover(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    food_inventory_factory(name='Food Storage')
    food_inventory_factory(name='Tools', inventory_type='tool')
    assert set(config.discover()) == {'food-storage', 'tools'}


def test_save_creates_dated_backup(food_inventory_factory, test_inventory_configs, test_directory):
    config = test_inventory_configs
    slug = food_inventory_factory(name='Food Storage')
    # First save happened on create (no prior file → no backup).  A second save backs up the existing file.
    config.dump_all()

    backup_dir = test_directory / 'config' / 'backup' / 'inventory'
    date_str = now().strftime('%Y%m%d')
    assert (backup_dir / f'{slug}-{date_str}.yaml').is_file()


def test_initialize_loads_from_disk(food_inventory_factory, test_inventory_configs):
    config = test_inventory_configs
    food_inventory_factory(name='Food Storage')
    config.dump_all()

    # A new instance pointed at the same directory loads the existing files on initialize().
    fresh = inventory_common.InventoriesConfig()
    fresh.initialize()
    assert 'food-storage' in fresh.slugs


def test_invalid_file_is_skipped(test_inventory_configs):
    config = test_inventory_configs
    bad = config.get_directory() / 'broken.yaml'
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('this: [is, not, a, valid, inventory\n')  # malformed YAML
    # import_all must not raise; the bad file is skipped.
    config.import_all()
    assert 'broken' not in config.slugs
