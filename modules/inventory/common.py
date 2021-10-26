from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import List, Tuple

import yaml
from pint import Quantity

from wrolpi import before_startup
from wrolpi.common import logger, Base
from wrolpi.db import get_db_session
from wrolpi.errors import NoInventories, InventoriesVersionMismatch
from wrolpi.vars import CONFIG_DIR
from .inventory import unit_registry, get_items, get_inventories, increment_inventories_version, \
    get_inventories_version
from .models import Inventory, Item

MY_DIR: Path = Path(__file__).parent

logger = logger.getChild(__name__)


def sum_by_key(items: List[Base], key: callable):
    """
    Sum the total size of each item by the provided key function.  Returns a dict containing the key, and the total_size
    for that key.  Combine total of like units.  This means ounces and pounds will be in the same total.
    """
    summed = dict()
    for item in items:
        k = key(item)
        item_size, count, unit = item.item_size, item.count, unit_registry(item.unit)
        key_dim = (k, unit.dimensionality)

        total_size = item_size * count * unit

        try:
            summed[key_dim] += total_size
        except KeyError:
            summed[key_dim] = total_size

    summed = {k: compact_unit(v) for k, v in summed.items()}
    return summed


def get_inventory_by_keys(keys: Tuple, inventory_id: int):
    items = get_items(inventory_id)

    summed = sum_by_key(items, lambda i: tuple(getattr(i, k) or '' for k in keys))

    inventory = []
    for key, quantity in sorted(summed.items(), key=lambda i: i[0][0]):
        quantity = cleanup_quantity(quantity)
        total_size, units = quantity.to_tuple()
        unit = units[0][0]

        d = dict(total_size=total_size, unit=unit)
        d.update(dict(zip(keys, key[0])))
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
    quantity = round(quantity, UNIT_PRECISION)
    return quantity


def quantity_to_tuple(quantity: unit_registry.Quantity) -> Tuple[Decimal, Quantity]:
    decimal, (units,) = quantity.to_tuple()
    unit, _ = units
    quantity, unit = round(decimal, UNIT_PRECISION), unit_registry(unit)
    return quantity, unit


def cleanup_quantity(quantity: Quantity) -> Quantity:
    """
    Remove trailing zeros from a Quantity.
    """
    num, unit = quantity_to_tuple(quantity)
    num = round(num, UNIT_PRECISION)
    num = str(num).rstrip('0').rstrip('.')
    return Decimal(num) * unit


DEFAULT_SAVE_PATH = CONFIG_DIR / 'inventories.yaml'


def save_inventories_file(path: str = None):
    """
    Write all inventories and their respective items to a YAML file.
    """
    path: Path = Path(path) if path else DEFAULT_SAVE_PATH

    inventories = []
    for inventory in get_inventories():
        inventories.append(inventory.dict())

    if not inventories:
        raise NoInventories('No Inventories are in the database!')

    with increment_inventories_version() as version:
        if path.is_file():
            # Check that we aren't overwriting our inventories with empty inventories.
            with open(path, 'rt') as fh:
                old = yaml.load(fh, Loader=yaml.Loader)
                if old and not inventories:
                    raise FileExistsError(f'Refusing to overwrite non-empty inventories.yaml with empty inventories.'
                                          f'  {path}')

                if old and old.get('version') > version:
                    raise InventoriesVersionMismatch(
                        f'Inventories config version is {old["version"]} but DB version is {get_inventories_version()}')

        with open(path, 'wt') as fh:
            contents = dict(
                version=version,
                inventories=inventories,
            )

            yaml.dump(contents, fh)


@before_startup
def import_inventories_file(path: str = None):
    path: Path = Path(path) if path else DEFAULT_SAVE_PATH

    if not path.is_file():
        logger.warning(f'No inventories config file at {path}')
        return

    with open(path, 'rt') as fh:
        contents = yaml.load(fh, Loader=yaml.Loader)

    if not contents or 'inventories' not in contents:
        raise ValueError('Inventories file does not contain the expected "inventories" list.')

    inventories = get_inventories()
    inventories_names = {i.name for i in inventories}
    new_inventories = [i for i in contents['inventories'] if i['name'] not in inventories_names]
    with get_db_session(commit=True) as session:
        for inventory in new_inventories:
            items = inventory['items']
            inventory = Inventory(
                name=inventory['name'],
                created_at=inventory['created_at'],
                deleted_at=inventory['deleted_at'],
            )
            session.add(inventory)
            # Get the Inventory from the DB so we can use it's ID.
            session.flush()
            session.refresh(inventory)

            for item in items:
                del item['inventory_id']
                item = Item(inventory_id=inventory.id, **item)
                item.inventory_id = inventory.id
                session.add(item)
