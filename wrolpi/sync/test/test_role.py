"""A secondary WROLPi never saves the configs it copies from its primary, and never downloads."""
from datetime import datetime, time, timezone

import pytest
import yaml

from wrolpi.common import get_wrolpi_config, SYNCED_CONFIG_FILE_NAMES, get_all_configs
from wrolpi.config_version import IMPORT, SAVE, get_config_version, set_config_version
from wrolpi.dates import is_within_daily_window
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager
from wrolpi.sync import lib
from wrolpi.sync.config import get_sync_config
from wrolpi.tags import get_tags_config


def test_synced_configs_exist(test_channels_config):
    """Every synced config name is a real config (a typo would sync nothing, and save on a secondary)."""
    assert SYNCED_CONFIG_FILE_NAMES - {'inventory/catalog.yaml'} <= set(get_all_configs())
    assert 'repos.yaml' not in SYNCED_CONFIG_FILE_NAMES, 'git clones are not synced'
    assert 'wrolpi.yaml' not in SYNCED_CONFIG_FILE_NAMES, 'wrolpi.yaml is merged, it holds local settings'
    assert 'sync.yaml' not in SYNCED_CONFIG_FILE_NAMES, "a secondary's role is its own"
    assert 'sync.yaml' in get_all_configs()


@pytest.mark.asyncio
async def test_secondary_does_not_save_synced_configs(async_client, test_session, test_tags_config, tag_factory,
                                                      make_secondary, await_switches):
    await tag_factory('one')
    get_tags_config().dump_config()
    await await_switches()
    primary_copy = test_tags_config.read_text()
    assert 'one' in primary_copy

    make_secondary()
    await tag_factory('two')
    get_tags_config().dump_config()
    await await_switches()
    assert test_tags_config.read_text() == primary_copy, 'a secondary must not save tags.yaml'

    # wrolpi.yaml holds the secondary's own settings, and is saved.
    get_wrolpi_config().update(dict(nav_color='red'))
    await await_switches()
    assert yaml.safe_load(get_wrolpi_config().get_file().read_text())['nav_color'] == 'red'


@pytest.mark.asyncio
async def test_secondary_does_not_save_inventories(async_client, test_inventory_configs, make_secondary,
                                                   await_switches):
    from modules.inventory.common import get_inventory_configs
    config = get_inventory_configs()
    slug = config.create_inventory('Pantry', 'food')['slug']
    pantry = config.get_file(slug)
    before = pantry.read_text()

    make_secondary()
    config.replace(slug, dict(name='Changed'))
    await await_switches()
    assert pantry.read_text() == before, 'a secondary must not save inventories'


def test_secondary_imports_synced_configs(async_client, test_tags_config, make_secondary):
    """A secondary's database never outranks the primary's copy of a config: every import applies the file."""
    with get_db_session(commit=True) as session:
        set_config_version(session, 'tags.yaml', 10)
    config = get_tags_config()
    assert config.version_decision(file_version=3)[0] == SAVE

    make_secondary()
    assert config.version_decision(file_version=3)[0] == IMPORT


def test_secondary_never_downloads(async_client, test_wrolpi_config, make_secondary):
    assert download_manager.blocked_download_reason() != 'secondary role'
    make_secondary()
    assert download_manager.blocked_download_reason() == 'secondary role'


@pytest.mark.parametrize('start, end, current, expected', [
    ('01:00', '05:00', time(0, 59), False),
    ('01:00', '05:00', time(1, 0), True),
    ('01:00', '05:00', time(4, 59), True),
    ('01:00', '05:00', time(5, 0), False),
    ('22:00', '06:00', time(23, 0), True),
    ('22:00', '06:00', time(3, 0), True),
    ('22:00', '06:00', time(12, 0), False),
])
def test_is_within_daily_window(start, end, current, expected):
    assert is_within_daily_window(start, end, current) is expected


def test_sync_is_due(test_wrolpi_config):
    config = get_sync_config()
    local_now = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
    never = dict(finished_at=None)
    assert not lib.sync_is_due(never, local_now), 'no window is "Sync now" only'

    config._config.update(window_start='01:00', window_end='05:00')
    assert lib.sync_is_due(never, local_now)
    assert not lib.sync_is_due(never, local_now.replace(hour=6)), 'outside the window'

    recent = dict(finished_at=local_now.replace(hour=1, minute=50).isoformat())
    assert not lib.sync_is_due(recent, local_now), 'synced 10 minutes ago'
    earlier = dict(finished_at=local_now.replace(hour=1, minute=40).isoformat())
    assert lib.sync_is_due(earlier, local_now), 'synced 20 minutes ago'
