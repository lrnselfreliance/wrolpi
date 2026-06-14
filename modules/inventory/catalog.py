"""Shared food catalog: a single config-only YAML of known food items used to autocomplete and pre-fill the
inventory entry form.

It ships with curated defaults (``catalog_defaults.yaml``) which are merged into the user's catalog on startup:
new shipped entries are added by their default id, but a default the user has edited or deleted is never
re-added (its id stays in ``merged_default_ids``, acting as a tombstone).  `calories` is the total kcal for one
package of `item_size` (the basis the ration estimate uses).
"""
import pathlib
from copy import deepcopy
from dataclasses import dataclass, field
from typing import List

from wrolpi.common import logger, ConfigFile, read_config_data

logger = logger.getChild(__name__)

CATALOG_DEFAULTS_PATH = pathlib.Path(__file__).parent / 'catalog_defaults.yaml'

# The fields copied from a catalog entry onto an inventory item when pre-filling.
CATALOG_ENTRY_KEYS = ('name', 'category', 'subcategory', 'item_size', 'item_size_unit', 'calories')


@dataclass
class CatalogConfigValidator:
    version: int = None
    items: list = field(default_factory=list)
    merged_default_ids: list = field(default_factory=list)


class CatalogConfig(ConfigFile):
    file_name = 'inventory/catalog.yaml'
    default_config = dict(version=0, items=[], merged_default_ids=[])
    validator = CatalogConfigValidator

    @property
    def items(self) -> list:
        return self._config.get('items') or []

    @property
    def merged_default_ids(self) -> list:
        return self._config.get('merged_default_ids') or []


CATALOG_CONFIG: CatalogConfig = CatalogConfig()
TEST_CATALOG_CONFIG: CatalogConfig = None


def get_catalog_config() -> CatalogConfig:
    if isinstance(TEST_CATALOG_CONFIG, CatalogConfig):
        return TEST_CATALOG_CONFIG
    return CATALOG_CONFIG


def set_test_catalog_config(enabled: bool):
    global TEST_CATALOG_CONFIG
    TEST_CATALOG_CONFIG = CatalogConfig() if enabled else None


def load_catalog_defaults() -> List[dict]:
    """Read the shipped default catalog entries from catalog_defaults.yaml."""
    try:
        data = read_config_data(CATALOG_DEFAULTS_PATH)
        return data.get('items') or []
    except Exception as e:
        logger.error(f'Failed to read catalog defaults: {e}', exc_info=e)
        return []


def _clean_entry(raw: dict) -> dict:
    return {k: (raw.get(k) if raw.get(k) is not None else '') for k in CATALOG_ENTRY_KEYS}


def _next_id(items: list) -> int:
    return max((i.get('id') for i in items if isinstance(i.get('id'), int)), default=0) + 1


def seed_catalog_defaults(config: CatalogConfig):
    """Merge shipped defaults into the catalog: add any default whose id has not been merged before, but never
    re-add one the user edited/deleted (tracked by `merged_default_ids`)."""
    defaults = load_catalog_defaults()
    if not defaults:
        return
    merged = set(config.merged_default_ids)
    items = [deepcopy(i) for i in config.items]
    next_id = _next_id(items)
    added = 0
    for default in defaults:
        default_id = default.get('id')
        if default_id is None or default_id in merged:
            continue
        entry = _clean_entry(default)
        entry['id'] = next_id
        next_id += 1
        items.append(entry)
        merged.add(default_id)
        added += 1
    if added:
        config.update({'items': items, 'merged_default_ids': sorted(merged)})
        logger.info(f'Seeded {added} food catalog defaults')


def import_catalog_config():
    """Load the catalog from disk (if present), then merge in any new shipped defaults."""
    config = get_catalog_config()
    if config.get_file().is_file():
        config.import_config()
        config.successful_import = True
    seed_catalog_defaults(config)


def save_catalog_items(items: list) -> list:
    """Replace the catalog's items (whole-list save).  Each entry is filtered to the known keys and given a
    stable id; `merged_default_ids` is preserved so deleted defaults stay tombstoned."""
    config = get_catalog_config()
    normalized = []
    used = set()
    counter = max((i.get('id') for i in (items or []) if isinstance(i.get('id'), int)), default=0)
    for raw in (items or []):
        entry = _clean_entry(raw)
        item_id = raw.get('id')
        if not isinstance(item_id, int) or item_id in used:
            counter += 1
            item_id = counter
        used.add(item_id)
        entry['id'] = item_id
        normalized.append(entry)
    config.update({'items': normalized})
    return deepcopy(config.items)
