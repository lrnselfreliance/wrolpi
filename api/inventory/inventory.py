from datetime import datetime
from typing import List, Dict, Tuple

import pint
from dictorm import Table, DictDB

from api.common import logger
from api.db import get_db_context, get_db_curs

unit_registry = pint.UnitRegistry()
logger = logger.getChild(__name__)


def get_inventories() -> List[Dict]:
    with get_db_context() as (engine, session):
        Inventory: Table = db['inventory']
        return list(Inventory.get_where(Inventory['deleted_at'].IsNull()).order_by('viewed_at DESC'))


IGNORED_INVENTORY_KEYS = {'viewed_at', 'created_at', 'deleted_at'}


def _remove_conflicting_deleted_inventory(inventory: dict, db: DictDB):
    Inventory: Table = db['inventory']
    inventory = Inventory.get_one(Inventory['deleted_at'].IsNotNull(), name=inventory['name'])
    if inventory:
        if inventory['items']:
            for item in inventory['items']:
                item.delete()
        inventory.delete()


def save_inventory(inventory):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    with get_db_context(commit=True) as (engine, session):
        _remove_conflicting_deleted_inventory(inventory, db)

        Inventory: Table = db['inventory']
        Inventory(**inventory).flush()


def update_inventory(inventory_id: int, inventory: dict):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    with get_db_context(commit=True) as (engine, session):
        _remove_conflicting_deleted_inventory(inventory, db)

        Inventory: Table = db['inventory']
        i = Inventory.get_one(id=inventory_id)
        i.update(inventory)
        i.flush()


def delete_inventory(inventory_id: int):
    with get_db_context(commit=True) as (engine, session):
        Inventory: Table = db['inventory']
        inventory = Inventory.get_one(id=inventory_id)
        inventory['deleted_at'] = datetime.now()
        inventory.flush()


def get_categories() -> List[Tuple[int, str, str]]:
    """
    Get all distinct sets of subcategory and category.
    """
    with get_db_curs() as curs:
        curs.execute('SELECT DISTINCT subcategory, category FROM item ORDER BY 1, 2')
        categories = curs.fetchall()
        # Prepend an ID to each tuple, this is because javascript sucks.
        return list(categories)


def get_brands() -> List[Tuple[int, str]]:
    with get_db_context() as (engine, session):
        curs = db_conn.cursor()
        curs.execute("SELECT DISTINCT brand FROM item WHERE brand IS NOT NULL AND brand != '' ORDER BY 1")
        brands = curs.fetchall()
        return list(brands)


def get_items(inventory_id: int) -> List[Dict]:
    with get_db_context() as (engine, session):
        Item: Table = db['item']
        return list(Item.get_where(Item['inventory_id'] == inventory_id, Item['deleted_at'].IsNull()))


def save_item(inventory_id: int, item: dict):
    with get_db_context(commit=True) as (engine, session):
        Item: Table = db['item']
        Item(inventory_id=inventory_id, **item).flush()


def update_item(item_id: int, item: dict):
    with get_db_context(commit=True) as (engine, session):
        Item: Table = db['item']
        i = Item.get_one(id=item_id)
        i.update(item)
        i.flush()


def delete_items(items_ids: List[int]):
    with get_db_context(commit=True) as (engine, session):
        curs = db_conn.cursor()
        curs.execute('UPDATE item SET deleted_at=current_timestamp WHERE id = ANY(%s)', (items_ids,))

