from datetime import datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import List, Tuple

import yaml
from pint import Quantity

from api.db import get_db_context
from api.inventory.inventory import unit_registry, get_items, get_inventories
from api.vars import PROJECT_DIR

MY_DIR: Path = Path(__file__).parent

DEFAULT_CATEGORIES = [
    ('wheat', 'grains'),
    ('rice', 'grains'),
    ('flour', 'grains'),
    ('oats', 'grains'),
    ('pasta', 'grains'),
    ('corn meal', 'grains'),
    ('canned', 'meats'),
    ('dried', 'meats'),
    ('vegetable oil', 'fats'),
    ('shortening', 'fats'),
    ('dry beans', 'legumes'),
    ('lentils', 'legumes'),
    ('dry milk', 'dairy'),
    ('evaporated milk', 'dairy'),
    ('white sugar', 'sugars'),
    ('brown sugar', 'sugars'),
    ('honey', 'sugars'),
    ('corn syrup', 'sugars'),
    ('juice mix', 'sugars'),
    ('salt', 'cooking ingredients'),
    ('canned', 'fruits'),
    ('dehydrated', 'fruits'),
    ('freeze-dried', 'fruits'),
    ('canned', 'vegetables'),
    ('dehydrated', 'vegetables'),
    ('freeze-dried', 'vegetables'),
    ('water', 'water'),
]

DEFAULT_INVENTORIES = [
    'Food Storage',
]


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


DEFAULT_SAVE_PATH = PROJECT_DIR / 'inventories.yaml'


def save_inventories_file(path: str = None):
    """
    Write all inventories and their respective items to a YAML file.
    """
    path: Path = Path(path) if path else DEFAULT_SAVE_PATH

    inventories = []
    for inventory in get_inventories():
        inventory['items'] = [dict(i) for i in get_items(inventory['id'])]
        inventories.append(dict(inventory))

    if path.is_file():
        # Check that we aren't overwriting our inventories with empty inventories.
        with open(path, 'rt') as fh:
            old = yaml.load(fh, Loader=yaml.Loader)
            if old and not inventories:
                raise FileExistsError(f'Refusing to overwrite non-empty inventories.yaml with empty inventories.'
                                      f'  {path}')

    with open(path, 'wt') as fh:
        contents = dict(
            utc_time=datetime.utcnow(),
            inventories=inventories,
        )

        yaml.dump(contents, fh)


def import_inventories_file(path: str = None):
    path: Path = Path(path) if path else DEFAULT_SAVE_PATH

    with open(path, 'rt') as fh:
        contents = yaml.load(fh, Loader=yaml.Loader)

    if not contents or 'inventories' not in contents:
        raise ValueError('Inventories file does not contain the expected "inventories" list.')

    inventories = get_inventories()
    inventories_names = [i['name'] for i in inventories]
    new_inventories = [i for i in contents['inventories'] if i['name'] not in inventories_names]
    with get_db_context(commit=True) as (engine, session):
        Inventory, Item = db['inventory'], db['item']
        for inventory in new_inventories:
            # Remove the id, we will just use the new one provided.
            del inventory['id']

            items = inventory['items']
            inventory = Inventory(
                name=inventory['name'],
                created_at=inventory['created_at'],
                deleted_at=inventory['deleted_at'],
            ).flush()

            for item in items:
                del item['id']
                del item['inventory_id']
                item = Item(inventory_id=inventory['id'], **item).flush()
