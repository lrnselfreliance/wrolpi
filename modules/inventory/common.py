"""Config-only inventory backend.

Each inventory is a single YAML file at ``config/inventory/<slug>.yaml`` and is the source-of-truth (no database).
All files are loaded into one shared, cross-worker dict keyed by slug.  Unit math/aggregation happens in the
frontend (mathjs), so this module treats item field values as opaque strings/numbers.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from wrolpi.common import logger, MultiFileConfig
from wrolpi.errors import ValidationError
from .defaults import (DEFAULT_INVENTORIES, FIELD_TYPES, default_fields, slugify)

MY_DIR: Path = Path(__file__).parent

logger = logger.getChild(__name__)


@dataclass
class InventoryConfigValidator:
    version: int = None
    slug: str = None
    name: str = None
    type: str = None
    created_at: str = None
    viewed_at: str = None
    fields: list = field(default_factory=list)
    items: list = field(default_factory=list)


def _validate_fields(fields_: list):
    """Validate a field schema list.  Raises ValidationError on bad input."""
    if not isinstance(fields_, list):
        raise ValidationError('fields must be a list')
    seen = set()
    for f in fields_:
        if not isinstance(f, dict) or not f.get('key') or not f.get('type'):
            raise ValidationError(f'Invalid field definition: {f}')
        if f['type'] not in FIELD_TYPES:
            raise ValidationError(f'Unknown field type: {f["type"]}')
        if f['key'] in seen:
            raise ValidationError(f'Duplicate field key: {f["key"]}')
        seen.add(f['key'])


def _allowed_item_keys(fields_: list) -> set:
    """Keys an item may contain, derived from the field schema (quantity fields add a companion `<key>_unit`)."""
    keys = set()
    for f in fields_:
        keys.add(f['key'])
        if f.get('type') == 'quantity':
            keys.add(f'{f["key"]}_unit')
    return keys


def _normalize_items(items: list, fields_: list) -> list:
    """Filter each item to the schema's allowed keys and assign stable ids (fresh id for any missing/duplicate)."""
    if not isinstance(items, list):
        raise ValidationError('items must be a list')
    allowed = _allowed_item_keys(fields_)
    counter = max((i.get('id') for i in items if isinstance(i.get('id'), int)), default=0)
    used = set()
    normalized = []
    for raw in items:
        clean = {k: v for k, v in raw.items() if k in allowed}
        item_id = raw.get('id')
        if not isinstance(item_id, int) or item_id in used:
            counter += 1
            item_id = counter
        used.add(item_id)
        clean['id'] = item_id
        normalized.append(clean)
    return normalized


# Slugs reserved in the config/inventory/ directory that are NOT inventories.  The shared food catalog lives at
# config/inventory/catalog.yaml, so it must be excluded from inventory discovery (and from new-inventory slugs).
RESERVED_SLUGS = {'catalog'}


class InventoriesConfig(MultiFileConfig):
    subdirectory = 'inventory'
    name = 'inventory'
    validator = InventoryConfigValidator
    default_entity = dict(version=0, slug=None, name=None, type='food', created_at=None, viewed_at=None,
                          fields=[], items=[])

    def discover(self) -> List[str]:
        # Exclude reserved files (e.g. catalog.yaml) that share the directory but are not inventories.
        return [slug for slug in super().discover() if slug not in RESERVED_SLUGS]

    def all_inventories(self) -> List[dict]:
        """Return every inventory in full (fields + items), sorted by name.

        The frontend loads this once and derives everything (selected items, summary, locations, ration data)
        client-side, then persists whole inventories via `save_inventory` — so there are no granular item/field
        endpoints.
        """
        return sorted(self.all(), key=lambda i: (i.get('name') or '').lower())

    def get_inventory(self, slug: str) -> Optional[dict]:
        return self.get(slug)

    def create_inventory(self, name: str, inventory_type: str) -> dict:
        from wrolpi.dates import now
        name = (name or '').strip()
        if not name:
            raise ValidationError('Inventory name is required')
        slug = slugify(name)
        # Slug is a stable identifier; dedupe it so two same-named inventories don't collide on disk, and never
        # let a user-created inventory claim a reserved slug (e.g. naming an inventory "Catalog").
        taken = lambda s: s in self._configs or s in RESERVED_SLUGS
        if taken(slug):
            suffix = 2
            while taken(f'{slug}-{suffix}'):
                suffix += 1
            slug = f'{slug}-{suffix}'
        created = now().isoformat()
        self.create(slug, dict(
            slug=slug,
            name=name,
            type=inventory_type,
            created_at=created,
            viewed_at=created,
            fields=default_fields(inventory_type),
            items=[],
        ))
        return self.get(slug)

    def delete_inventory(self, slug: str):
        if slug not in self._configs:
            raise ValidationError(f'No inventory: {slug}')
        self.delete(slug)

    def save_inventory(self, slug: str, data: dict, expected_version: int = None) -> dict:
        """Replace an inventory's editable parts (name / fields / items) in one write.

        `slug` is a stable id and is never changed by a save (only the display `name` changes).  Item ids are
        normalized server-side (any item missing/duplicating an id gets a fresh one).  When `expected_version` is
        given and does not match the stored version, an `InventoryConflict` is raised so a stale client (e.g. a
        second browser tab) cannot silently clobber a newer save.
        """
        from wrolpi.dates import now
        from .errors import InventoryConflict

        if slug not in self._configs:
            raise ValidationError(f'No inventory: {slug}')

        # Hold the save lock for the whole read-check-mutate-persist cycle so two concurrent saves of the same
        # inventory can't both pass the version check and clobber each other (lost write).
        with self.save_lock():
            current = dict(self._configs[slug])
            stored_version = current.get('version')
            if expected_version is not None and stored_version is not None and stored_version != expected_version:
                raise InventoryConflict(
                    f'Inventory {slug} changed since it was loaded (stored {stored_version} != {expected_version})')

            if 'name' in data:
                name = (data['name'] or '').strip()
                if not name:
                    raise ValidationError('Inventory name is required')
                current['name'] = name
            if data.get('type'):
                current['type'] = data['type']
            if 'fields' in data:
                fields_ = data['fields']
                _validate_fields(fields_)
                for index, f in enumerate(fields_):
                    f['order'] = index
                current['fields'] = fields_
            if 'items' in data:
                current['items'] = _normalize_items(data['items'], current.get('fields') or [])

            current['viewed_at'] = now().isoformat()
            self._configs[slug] = current
            # Persist synchronously (lock already held) so the version bump is immediate and returned to the client.
            self._persist_slug(slug)
        return self.get(slug)

    def seed_defaults(self):
        """Create the default example inventories if the directory is empty."""
        if self._configs:
            return
        for default in DEFAULT_INVENTORIES:
            try:
                self.create_inventory(default['name'], default['type'])
            except Exception as e:
                logger.warning(f'Failed to seed default inventory {default}: {e}')


INVENTORIES_CONFIG: InventoriesConfig = InventoriesConfig()
TEST_INVENTORIES_CONFIG: Optional[InventoriesConfig] = None


def get_inventory_configs() -> InventoriesConfig:
    if isinstance(TEST_INVENTORIES_CONFIG, InventoriesConfig):
        return TEST_INVENTORIES_CONFIG
    return INVENTORIES_CONFIG


# Backwards-compatible alias used by some call sites.
get_inventories_config = get_inventory_configs


def set_test_inventories_config(enabled: bool):
    global TEST_INVENTORIES_CONFIG
    if enabled:
        TEST_INVENTORIES_CONFIG = InventoriesConfig()
    else:
        TEST_INVENTORIES_CONFIG = None


def import_inventories_config():
    """Migrate any legacy inventories.yaml, load per-inventory files, seed defaults, and load the food catalog."""
    from .migrate import migrate_legacy_inventory
    config = get_inventory_configs()
    try:
        migrate_legacy_inventory(config)
    except Exception as e:
        logger.error('Failed to migrate legacy inventories', exc_info=e)
    config.import_all()
    config.seed_defaults()

    # Load the shared food catalog and merge in any new shipped defaults.
    try:
        from .catalog import import_catalog_config
        import_catalog_config()
    except Exception as e:
        logger.error('Failed to import food catalog', exc_info=e)
