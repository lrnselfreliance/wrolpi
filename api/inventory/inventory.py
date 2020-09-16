from decimal import Decimal
from functools import partial
from typing import List, Dict, Tuple

from dictorm import Table

from api.db import get_db_context
from api.inventory.common import DEFAULT_CATEGORIES

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


ITEM_ORDER = 'subcategory, category'


def sum_by_key(items: List, key: callable):
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
