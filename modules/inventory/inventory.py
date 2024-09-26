from functools import partial
from operator import itemgetter
from typing import List, Tuple

import pint
import psycopg2
from sqlalchemy.orm import Session

from wrolpi.common import logger, Base
from wrolpi.db import get_db_session, get_db_curs, optional_session
from wrolpi.errors import APIError
from .models import Inventory, Item

logger = logger.getChild(__name__)

__all__ = [
    'DEFAULT_CATEGORIES',
    'DEFAULT_INVENTORIES',
    'delete_inventory',
    'delete_items',
    'get_brands',
    'get_categories',
    'get_inventories',
    'get_items',
    'get_unit_registry',
    'logger',
    'save_inventory',
    'save_item',
    'sort_categories',
    'update_inventory',
    'update_item',
]

UNIT_REGISTRY: pint.UnitRegistry = None


def get_unit_registry() -> pint.UnitRegistry:
    global UNIT_REGISTRY
    if UNIT_REGISTRY:
        return UNIT_REGISTRY

    UNIT_REGISTRY = pint.UnitRegistry()
    return UNIT_REGISTRY


DEFAULT_CATEGORIES = [
    ('salt', 'cooking ingredients'),
    ('dry milk', 'dairy'),
    ('evaporated milk', 'dairy'),
    ('freeze dried', 'dairy'),
    ('shortening', 'fats'),
    ('vegetable oil', 'fats'),
    ('canned', 'fruits'),
    ('dehydrated', 'fruits'),
    ('freeze-dried', 'fruits'),
    ('corn meal', 'grains'),
    ('flour', 'grains'),
    ('oats', 'grains'),
    ('pasta', 'grains'),
    ('rice', 'grains'),
    ('wheat', 'grains'),
    ('dry beans', 'legumes'),
    ('lentils', 'legumes'),
    ('canned', 'meats'),
    ('dried', 'meats'),
    ('freeze dried', 'meals'),
    ('brown sugar', 'sugars'),
    ('corn syrup', 'sugars'),
    ('honey', 'sugars'),
    ('juice mix', 'sugars'),
    ('white sugar', 'sugars'),
    ('canned', 'vegetables'),
    ('dehydrated', 'vegetables'),
    ('freeze dried', 'vegetables'),
    ('water', 'water'),
    ('bottled', 'water'),
    ('barrel', 'water'),
]

DEFAULT_INVENTORIES = [
    'Food Storage',
]

# Categories are sorted by category/sub-category.
sort_categories = partial(sorted, key=itemgetter(1, 0))


@optional_session
def get_inventories(session: Session = None) -> List[Inventory]:
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

    with get_db_session(commit=True) as session:
        _remove_conflicting_deleted_inventory(inventory, session)
        session.add(Inventory(**inventory))


def update_inventory(inventory_id: int, inventory: dict):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    # Cleanup the whitespace.
    inventory['name'] = inventory['name'].strip()

    with get_db_session(commit=True) as session:
        _remove_conflicting_deleted_inventory(inventory, session)

        i = session.query(Inventory).filter_by(id=inventory_id).one()
        for key, value in inventory.items():
            setattr(i, key, value)


def delete_inventory(inventory_id: int):
    with get_db_session(commit=True) as session:
        inventory = session.query(Inventory).filter_by(id=inventory_id).one()
        inventory.delete()


def get_categories() -> List[Tuple[str, str]]:
    """
    Get all distinct sets of subcategory and category.
    """
    categories = DEFAULT_CATEGORIES.copy()
    with get_db_curs() as curs:
        curs.execute("SELECT DISTINCT COALESCE(subcategory, ''), COALESCE(category, '') FROM item ORDER BY 1, 2")
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
    with get_db_session() as session:
        results = session.query(Item).filter(
            Item.inventory_id == inventory_id,
            Item.deleted_at == None,  # noqa
        ).all()
        return results


def save_item(inventory_id: int, item: dict):
    with get_db_session(commit=True) as session:
        item = Item(inventory_id=inventory_id, **item)
        session.add(item)


def update_item(item_id: int, item: dict):
    with get_db_session(commit=True) as session:
        i = session.query(Item).filter_by(id=item_id).one()
        del item['id']
        del item['created_at']
        for key, value in item.items():
            setattr(i, key, value)


def delete_items(items_ids: List[int]):
    with get_db_curs(commit=True) as curs:
        curs.execute('UPDATE item SET deleted_at=current_timestamp WHERE id = ANY(%s) RETURNING id', (items_ids,))
        deleted_ids = {i['id'] for i in curs.fetchall()}
        if set(items_ids) != deleted_ids:
            raise APIError('Could not delete the items')
