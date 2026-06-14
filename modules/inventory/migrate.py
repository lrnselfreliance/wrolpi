"""One-time migration from the legacy DB-backed / single-file inventory system to per-inventory config files.

Runs on startup (idempotent): if any ``config/inventory/*.yaml`` files already exist, it does nothing.  Otherwise it
converts the legacy ``config/inventories.yaml`` (or, as a fallback, the legacy ``inventory``/``item`` DB tables) into
per-inventory files typed ``food``, then backs up and renames the old file so it is not re-read.
"""
import shutil

from wrolpi.common import logger, read_config_data
from wrolpi.dates import now
from .defaults import default_fields, slugify

logger = logger.getChild(__name__)

# Legacy pint unit names that are not valid mathjs unit names.  Unrecognized units are kept verbatim (the item
# simply won't aggregate in the frontend until the user picks a known unit).
LEGACY_UNIT_MAP = {
    'pound': 'lb',
    'pounds': 'lb',
    'lbs': 'lb',
}

# Legacy item columns we carry over (mapped onto the default food field schema).
_LEGACY_ITEM_KEYS = ('brand', 'name', 'category', 'subcategory', 'count', 'expiration_date')


def normalize_unit(unit) -> str:
    if not unit:
        return unit
    return LEGACY_UNIT_MAP.get(str(unit).strip().lower(), unit)


def _convert_item(legacy: dict, item_id: int) -> dict:
    item = dict(id=item_id)
    for key in _LEGACY_ITEM_KEYS:
        value = legacy.get(key)
        if value is not None and value != '':
            item[key] = str(value) if not isinstance(value, str) else value
    size = legacy.get('item_size')
    if size is not None and size != '':
        item['item_size'] = str(size)
        unit = normalize_unit(legacy.get('unit'))
        if unit:
            item['item_size_unit'] = unit
    return item


def _convert_inventory(legacy: dict, fallback_name: str) -> dict:
    name = (legacy.get('name') or fallback_name or 'Inventory').strip()
    created = legacy.get('created_at') or now().isoformat()
    items = []
    for legacy_item in legacy.get('items') or []:
        # Skip soft-deleted legacy items.
        if legacy_item.get('deleted_at'):
            continue
        items.append(_convert_item(legacy_item, len(items) + 1))
    return dict(
        name=name,
        type='food',
        created_at=str(created),
        viewed_at=str(legacy.get('viewed_at') or created),
        fields=default_fields('food'),
        items=items,
    )


def _legacy_inventories_from_db() -> list:
    """Read legacy inventories/items straight from the DB if the tables still exist (pre-drop installs)."""
    from wrolpi.db import get_db_curs
    inventories = []
    try:
        with get_db_curs() as curs:
            curs.execute("SELECT to_regclass('public.inventory')")
            if curs.fetchone()[0] is None:
                return []
            curs.execute('SELECT id, name, created_at, viewed_at FROM inventory WHERE deleted_at IS NULL')
            rows = curs.fetchall()
            for row in rows:
                inv = dict(id=row[0], name=row[1], created_at=row[2], viewed_at=row[3], items=[])
                curs.execute(
                    'SELECT brand, name, item_size, unit, count, category, subcategory, expiration_date '
                    'FROM item WHERE inventory_id = %s AND deleted_at IS NULL', (row[0],))
                for item in curs.fetchall():
                    inv['items'].append(dict(
                        brand=item[0], name=item[1], item_size=item[2], unit=item[3], count=item[4],
                        category=item[5], subcategory=item[6], expiration_date=item[7],
                    ))
                inventories.append(inv)
    except Exception as e:
        logger.debug(f'No legacy inventory DB tables to migrate: {e}')
        return []
    return inventories


def migrate_legacy_inventory(config) -> bool:
    """Migrate legacy inventory data into per-inventory config files.  Returns True if a migration happened."""
    # Already migrated (per-inventory files exist).
    if config.discover():
        return False

    legacy_file = config.get_directory().parent / 'inventories.yaml'
    legacy_inventories = []
    source = None

    if legacy_file.is_file():
        try:
            data = read_config_data(legacy_file)
            legacy_inventories = data.get('inventories') or []
            source = 'file'
        except Exception as e:
            logger.error(f'Failed to read legacy inventories.yaml: {e}', exc_info=e)

    if not legacy_inventories:
        legacy_inventories = _legacy_inventories_from_db()
        if legacy_inventories:
            source = 'db'

    if not legacy_inventories:
        return False

    logger.info(f'Migrating {len(legacy_inventories)} legacy inventories from {source}')
    used_slugs = set()
    for index, legacy in enumerate(legacy_inventories):
        entity = _convert_inventory(legacy, fallback_name=f'Inventory {index + 1}')
        # Dedupe against a stable base slug with an incrementing suffix (food, food-2, food-3, ...); reassigning
        # `slug` in the loop would grow the string unboundedly and could collide with an existing config.
        base_slug = slugify(entity['name'])
        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f'{base_slug}-{suffix}'
            suffix += 1
        used_slugs.add(slug)
        entity['slug'] = slug
        try:
            config.create(slug, entity)
        except Exception as e:
            logger.error(f'Failed to migrate inventory {entity["name"]}: {e}', exc_info=e)

    # Back up and retire the legacy file so it is not migrated again.
    if legacy_file.is_file():
        try:
            backup_dir = legacy_file.parent / 'backup'
            backup_dir.mkdir(parents=True, exist_ok=True)
            date_str = now().strftime('%Y%m%d')
            shutil.copy(legacy_file, backup_dir / f'inventories-{date_str}.yaml')
            legacy_file.rename(legacy_file.with_suffix('.yaml.migrated'))
        except Exception as e:
            logger.error(f'Failed to retire legacy inventories.yaml: {e}', exc_info=e)

    return True
