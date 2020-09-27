from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import List, Dict, Tuple

import pint
from dictorm import Table, DictDB
from pint import Quantity

from api.common import logger
from api.db import get_db_context

unit_registry = pint.UnitRegistry()
logger = logger.getChild(__name__)


def get_inventories() -> List[Dict]:
    with get_db_context() as (db_conn, db):
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

    with get_db_context(commit=True) as (db_conn, db):
        _remove_conflicting_deleted_inventory(inventory, db)

        Inventory: Table = db['inventory']
        Inventory(**inventory).flush()


def update_inventory(inventory_id: int, inventory: dict):
    inventory = {k: v for k, v in inventory.items() if k not in IGNORED_INVENTORY_KEYS}

    with get_db_context(commit=True) as (db_conn, db):
        _remove_conflicting_deleted_inventory(inventory, db)

        Inventory: Table = db['inventory']
        i = Inventory.get_one(id=inventory_id)
        i.update(inventory)
        i.flush()


def delete_inventory(inventory_id: int):
    with get_db_context(commit=True) as (db_conn, db):
        Inventory: Table = db['inventory']
        inventory = Inventory.get_one(id=inventory_id)
        inventory['deleted_at'] = datetime.now()
        inventory.flush()


def get_categories() -> List[Tuple[int, str, str]]:
    """
    Get all distinct sets of subcategory and category.
    """
    with get_db_context() as (db_conn, db):
        curs = db_conn.cursor()
        curs.execute('SELECT DISTINCT subcategory, category FROM item ORDER BY 1, 2')
        categories = curs.fetchall()
        # Prepend an ID to each tuple, this is because javascript sucks.
        return list(categories)


def get_brands() -> List[Tuple[int, str]]:
    with get_db_context() as (db_conn, db):
        curs = db_conn.cursor()
        curs.execute("SELECT DISTINCT brand FROM item WHERE brand IS NOT NULL AND brand != '' ORDER BY 1")
        brands = curs.fetchall()
        return list(brands)


def get_items(inventory_id: int) -> List[Dict]:
    with get_db_context() as (db_conn, db):
        Item: Table = db['item']
        return list(Item.get_where(Item['inventory_id'] == inventory_id, Item['deleted_at'].IsNull()))


def save_item(inventory_id: int, item: dict):
    with get_db_context(commit=True) as (db_conn, db):
        Item: Table = db['item']
        Item(inventory_id=inventory_id, **item).flush()


def update_item(item_id: int, item: dict):
    with get_db_context(commit=True) as (db_conn, db):
        Item: Table = db['item']
        i = Item.get_one(id=item_id)
        i.update(item)
        i.flush()


def delete_items(items_ids: List[int]):
    with get_db_context(commit=True) as (db_conn, db):
        curs = db_conn.cursor()
        curs.execute('UPDATE item SET deleted_at=current_timestamp WHERE id = ANY(%s)', (items_ids,))


def sum_by_key(items: List, key: callable):
    """
    Sum the total size of each item by the provided key function.  Returns a dict containing the key, and the total_size
    for that key.  Combine total of like units.  This means ounces and pounds will be in the same total.
    """
    summed = dict()
    for item in items:
        k = key(item)
        item_size, count, unit = item['item_size'], item['count'], unit_registry(item['unit'])
        key_dim = (k, unit.dimensionality)

        total_size = item_size * count * unit

        try:
            summed[key_dim] += total_size
        except KeyError:
            summed[key_dim] = total_size

    summed = {k[0]: compact_unit(v) for k, v in summed.items()}
    return summed


def get_inventory_by_keys(keys: Tuple, inventory_id: int):
    items = get_items(inventory_id)

    summed = sum_by_key(items, lambda i: tuple(i[k] or '' for k in keys))

    inventory = []
    for key, quantity in sorted(summed.items(), key=lambda i: i[0]):
        quantity = cleanup_quantity(quantity)
        total_size, units = quantity.to_tuple()
        unit = units[0][0]

        d = dict(total_size=total_size, unit=unit)
        d.update(dict(zip(keys, key)))
        inventory.append(d)

    return inventory


get_inventory_by_category = partial(get_inventory_by_keys, ('category',))
get_inventory_by_subcategory = partial(get_inventory_by_keys, ('category', 'subcategory'))
get_inventory_by_name = partial(get_inventory_by_keys, ('brand', 'name'))

INVENTORY_UNITS = {
    ('ounce', 1): (16, unit_registry.pound),
    ('pound', 1): (2000, unit_registry.ton),
}

UNIT_PRECISION = 5


def compact_unit(quantity: unit_registry.Quantity) -> unit_registry.Quantity:
    """
    Convert a Quantity to it's more readable format.  Such as 2000 pounds to 1 ton.
    """
    number, (units,) = quantity.to_tuple()
    next_unit = INVENTORY_UNITS.get(units)
    if not next_unit:
        # No units after this one, return as is.
        return round(quantity, UNIT_PRECISION)

    max_quantity, next_unit = next_unit
    if number >= max_quantity:
        # Number is too high for this unit, move to the next unit.
        return compact_unit(quantity.to(next_unit))

    # No units were necessary, return as is.
    return round(quantity, UNIT_PRECISION)


def quantity_to_tuple(quantity: unit_registry.Quantity) -> Tuple[Decimal, Quantity]:
    decimal, (units,) = quantity.to_tuple()
    unit, _ = units
    return round(decimal, UNIT_PRECISION).normalize(), unit_registry(unit)


def cleanup_quantity(quantity: Quantity) -> Quantity:
    """
    Remove trailing zeros from a Quantity.
    """
    num, unit = quantity_to_tuple(quantity)
    num = round(num, UNIT_PRECISION)
    num = str(num).rstrip('0').rstrip('.')
    return Decimal(num) * unit
