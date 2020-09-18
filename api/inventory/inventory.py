from decimal import Decimal
from functools import partial
from typing import List, Dict, Tuple

import pint
from dictorm import Table

from api.common import iterify
from api.db import get_db_context
from api.inventory.common import DEFAULT_CATEGORIES

unit_registry = pint.UnitRegistry()

CATEGORIES_INITIALIZED = False


def init_categories(force=False):
    """
    Initialize inventory categories, but only if none already exist.
    """
    global CATEGORIES_INITIALIZED
    if CATEGORIES_INITIALIZED and force is False:
        return

    with get_db_context(commit=True) as (db_conn, db):
        Category: Table = db['category']
        if Category.count() == 0:
            for subcategory, category in DEFAULT_CATEGORIES:
                Category(subcategory=subcategory, category=category).flush()

    CATEGORIES_INITIALIZED = True


def get_categories() -> List[Dict]:
    with get_db_context() as (db_conn, db):
        Category: Table = db['category']
        return list(Category.get_where())


def get_items() -> List[Dict]:
    with get_db_context() as (db_conn, db):
        Item: Table = db['item']
        return list(Item.get_where())


def save_item(item):
    with get_db_context(commit=True) as (db_conn, db):
        Item: Table = db['item']
        Item(**item).flush()


def delete_items(items_ids: List[int]):
    with get_db_context(commit=True) as (db_conn, db):
        curs = db_conn.cursor()
        curs.execute('DELETE FROM item WHERE ID = ANY(%s)', (items_ids,))


def sum_by_key(items: List, key: callable):
    """
    Sum the total size of each item by the provided key function.  Returns a dict containing the key, and the total_size
    for that key.
    """
    summed = dict()
    for item in items:
        k = key(item)
        total_size: Decimal = item['count'] * item['item_size']
        try:
            summed[k] += total_size
        except KeyError:
            summed[k] = total_size

    return summed


def get_inventory_by_keys(keys: Tuple):
    with get_db_context() as (db_conn, db):
        Item: Table = db['item']
        items = list(Item.get_where())

    summed = sum_by_key(items, lambda i: tuple(i[k] for k in keys))

    inventory = []
    for key, total_size in sorted(summed.items(), key=lambda i: i[0]):
        d = dict(total_size=total_size)
        d.update(dict(zip(keys, key)))
        inventory.append(d)

    return inventory


get_inventory_by_category = partial(get_inventory_by_keys, ('category', 'subcategory', 'unit'))
get_inventory_by_name = partial(get_inventory_by_keys, ('brand', 'name', 'unit'))

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
        return quantity

    max_quantity, next_unit = next_unit
    if number >= max_quantity:
        # Number is too high for this unit, move to the next unit.
        return compact_unit(quantity.to(next_unit))

    # No units were necessary, return as is.
    return quantity


def quantity_to_tuple(quantity: unit_registry.Quantity) -> Tuple[Decimal, str]:
    decimal, (units,) = quantity.to_tuple()
    unit, _ = units
    return round(decimal, UNIT_PRECISION).normalize(), unit


@iterify(list)
def human_units(items: List[dict], key: str) -> List[dict]:
    for item in items:
        quantity = item[key] * unit_registry(item['unit'])
        quantity = compact_unit(quantity)
        decimal, unit = quantity_to_tuple(quantity)
        if unit_registry(item['unit']) == unit_registry(unit):
            # The unit was unchanged, lets preserve the user's format
            # i.e. ounce vs oz
            unit = item['unit']
        item.update({key: decimal, 'unit': unit})
        yield item
