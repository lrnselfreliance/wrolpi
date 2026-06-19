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


def test_reimport_picks_up_and_drops_files(food_inventory_factory, test_inventory_configs):
    from modules.inventory.defaults import default_fields
    from wrolpi.common import write_config_data
    config = test_inventory_configs
    food_inventory_factory(name='Food Storage')

    # A file copied onto disk by hand is not in memory until a reimport.
    new_file = config.get_file('tools-box')
    write_config_data(dict(version=1, slug='tools-box', name='Tools Box', type='tool',
                           fields=default_fields('tool'), items=[]), new_file)
    assert config.get('tools-box') is None
    config.reimport()
    assert config.get('tools-box') is not None

    # Deleting the file on disk and re-importing drops it from memory (memory matches disk).
    new_file.unlink()
    config.reimport()
    assert config.get('tools-box') is None
    assert 'food-storage' in config.slugs


def test_get_backup_dates(food_inventory_factory, test_inventory_configs):
    from modules.inventory.defaults import default_fields
    from wrolpi.common import write_config_data
    config = test_inventory_configs
    slug = food_inventory_factory(name='Food Storage')
    assert config.get_backup_dates(slug) == []

    for date in ('20260101', '20260115'):
        backup = config._get_backup_file(slug, date)
        backup.parent.mkdir(parents=True, exist_ok=True)
        write_config_data(dict(version=1, slug=slug, name='Food Storage', type='food',
                               fields=default_fields('food'), items=[]), backup)
    # Newest first.
    assert config.get_backup_dates(slug) == ['20260115', '20260101']
    # A different slug that merely shares this slug's prefix is not matched (slug 'food' vs 'food-storage-...').
    assert config.get_backup_dates('food') == []
