import contextlib
from typing import List, Tuple

import pint
import psycopg2
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from api.common import logger, Base
from api.db import get_db_context, get_db_curs
from api.inventory.models import Inventory, Item, InventoriesVersion

unit_registry = pint.UnitRegistry()
logger = logger.getChild(__name__)


def get_inventories() -> List[Base]:
    with get_db_context() as (engine, session):
        inventories = session.query(Inventory).filter(
            Inventory.deleted_at == None,  # noqa
        ).order_by(
            Inventory.viewed_at.desc(),
        ).all()
        inventories = list(inventories)
        return inventories


IGNORED_INVENTORY_KEYS = {'viewed_at', 'created_at', 'deleted_at'}


def _remove_conflicting_deleted_inventory(inventory: dict, session: Session):
    """
    Remove any Inventories that share the inventory's name, but are marked as deleted.
    """
    inventories = session.query(Inventory).filter(
        Inventory.deleted_at != None,  # noqa
        Inventory.name == inventory['name'],
    ).all()
    for i in inventories:
        session.query(Item).filter_by(inventory_id=i.id).delete()
        session.query(Inventory).filter_by(id=i.id).delete()


def save_inventory(inventory):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    # Cleanup the whitespace.
    inventory['name'] = inventory['name'].strip()

    with get_db_context(commit=True) as (engine, session):
        _remove_conflicting_deleted_inventory(inventory, session)
        session.add(Inventory(**inventory))


def update_inventory(inventory_id: int, inventory: dict):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    # Cleanup the whitespace.
    inventory['name'] = inventory['name'].strip()

    with get_db_context(commit=True) as (engine, session):
        _remove_conflicting_deleted_inventory(inventory, session)

        i = session.query(Inventory).filter_by(id=inventory_id).one()
        for key, value in inventory.items():
            setattr(i, key, value)


def delete_inventory(inventory_id: int):
    with get_db_context(commit=True) as (engine, session):
        inventory = session.query(Inventory).filter_by(id=inventory_id).one()
        inventory.delete()


def get_categories() -> List[Tuple[str, str]]:
    """
    Get all distinct sets of subcategory and category.
    """
    from api.inventory import DEFAULT_CATEGORIES
    from api.inventory.common import sort_categories

    categories = DEFAULT_CATEGORIES.copy()
    with get_db_curs() as curs:
        curs.execute('SELECT DISTINCT subcategory, category FROM item ORDER BY 1, 2')
        try:
            db_categories = curs.fetchall()
            db_categories = [tuple(i) for i in db_categories]
            categories = set(categories + db_categories)
        except psycopg2.ProgrammingError:
            # No categories in DB.
            pass

    return sort_categories(categories)


def get_brands() -> List[Tuple[int, str]]:
    with get_db_curs() as curs:
        curs.execute("SELECT DISTINCT brand FROM item WHERE brand IS NOT NULL AND brand != '' ORDER BY 1")
        try:
            brands = curs.fetchall()
        except psycopg2.ProgrammingError:
            # No brands
            return []
        return list(brands)


def get_items(inventory_id: int) -> List[Base]:
    """
    Get all Items in an Inventory, except deleted items.
    """
    with get_db_context() as (engine, session):
        results = session.query(Item).filter(
            Item.inventory_id == inventory_id,
            Item.deleted_at == None,  # noqa
        ).all()
        return results


def save_item(inventory_id: int, item: dict):
    with get_db_context(commit=True) as (engine, session):
        item = Item(inventory_id=inventory_id, **item)
        session.add(item)


def update_item(item_id: int, item: dict):
    with get_db_context(commit=True) as (engine, session):
        i = session.query(Item).filter_by(id=item_id).one()
        del item['id']
        del item['created_at']
        for key, value in item.items():
            setattr(i, key, value)


def delete_items(items_ids: List[int]):
    with get_db_curs(commit=True) as curs:
        curs.execute('UPDATE item SET deleted_at=current_timestamp WHERE id = ANY(%s)', (items_ids,))


def get_inventories_version():
    """
    The inventory_version table contains a single row with the Inventories version integer.
    """
    with get_db_context() as (engine, session):
        try:
            version = session.query(InventoriesVersion).one()
            return version.version
        except NoResultFound:
            # No version is saved yet.
            pass


def get_next_inventories_version():
    """
    Get the current inventories version, increment it if there is one.
    """
    version = get_inventories_version()
    if version:
        return version + 1
    return 1


@contextlib.contextmanager
def increment_inventories_version():
    """
    Context manager that will increment the Inventories Version by 1 when exiting.
    """
    version = get_next_inventories_version()
    yield version
    with get_db_context(commit=True) as (engine, session):
        if session.query(InventoriesVersion).count() == 0:
            session.add(InventoriesVersion(version=version))
        else:
            session.query(InventoriesVersion).one().version = version
