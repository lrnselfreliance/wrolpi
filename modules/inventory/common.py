import pathlib
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import List, Tuple

from pint import Quantity

from wrolpi.common import logger, Base, ConfigFile
from wrolpi.db import get_db_session
from .errors import NoInventories
from .inventory import get_items, get_inventories, get_unit_registry
from .models import Inventory, Item

MY_DIR: Path = Path(__file__).parent

logger = logger.getChild(__name__)


def sum_by_key(items: List[Base], key: callable):
    """
    Sum the total size of each item by the provided key function.  Returns a dict containing the key, and the total_size
    for that key.  Combine total of like units.  This means ounces and pounds will be in the same total.
    """
    unit_registry = get_unit_registry()

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
INVENTORY_UNITS: dict = None
UNIT_PRECISION = 5


def initialize_inventory_units() -> dict:
    global INVENTORY_UNITS
    if INVENTORY_UNITS:
        return INVENTORY_UNITS

    unit_registry = get_unit_registry()
    INVENTORY_UNITS = {
        ('ounce', 1): (16, unit_registry.pound),
        ('pound', 1): (2000, unit_registry.ton),
    }


def compact_unit(quantity: Quantity) -> Quantity:
    """
    Convert a Quantity to it's more readable format.  Such as 2000 pounds to 1 ton.
    """
    initialize_inventory_units()

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


def quantity_to_tuple(quantity: Quantity) -> Tuple[Decimal, Quantity]:
    unit_registry = get_unit_registry()
    decimal, (units,) = quantity.to_tuple()
    unit, _ = units
    quantity, unit = round(decimal, UNIT_PRECISION), unit_registry(unit)
    return quantity, unit


def cleanup_quantity(quantity: Quantity) -> Quantity:
    """Remove trailing zeros from a Quantity."""
    num, unit = quantity_to_tuple(quantity)
    num = round(num, UNIT_PRECISION)
    num = str(num).rstrip('0').rstrip('.')
    return Decimal(num) * unit


class InventoriesConfig(ConfigFile):
    file_name = 'inventories.yaml'
    default_config = dict(
        inventories=[],
        version=0,
    )

    @property
    def inventories(self) -> dict:
        return self._config['inventories']

    @inventories.setter
    def inventories(self, value: dict):
        self.update({'inventories': value})

    def dump_config(self, file: pathlib.Path = None):
        inventories = []
        for inventory in get_inventories():
            inventories.append(inventory.dict())

        if not inventories:
            raise NoInventories('No Inventories are in the database!')

        self._config['inventories'] = inventories
        super().dump_config(file)

    def import_config(self, file: pathlib.Path = None):
        super().import_config(file)

        try:
            with get_db_session(commit=True) as session:
                db_inventories = get_inventories(session)
                config_inventory_names = {i['name'] for i in self.inventories}
                keep_inventories_names = []
                for inventory in db_inventories:
                    if inventory.name in config_inventory_names:
                        keep_inventories_names.append(inventory.name)
                        # TODO delete missing items, add new items.
                    else:
                        # Inventory was deleted from the config file.
                        inventory.delete()
                        continue

                new_inventories = [i for i in self.inventories if i['name'] not in keep_inventories_names]
                for inventory_dict in new_inventories:
                    # New Inventory in config, copy it into the DB.
                    inventory = Inventory(
                        name=inventory_dict['name'],
                        created_at=inventory_dict['created_at'],
                        deleted_at=inventory_dict['deleted_at'],
                    )
                    session.add(inventory)
                    # Get the Inventory from the DB so we can use its ID.
                    inventory.flush()

                    for item in inventory_dict['items']:
                        del item['inventory_id']
                        item = Item(inventory_id=inventory.id, **item)
                        item.inventory_id = inventory.id
                        session.add(item)

            self.successful_import = True
        except Exception as e:
            logger.error(f'Failed to import {self.file_name}', exc_info=e)
            raise


INVENTORIES_CONFIG: InventoriesConfig = InventoriesConfig()
TEST_INVENTORIES_CONFIG: InventoriesConfig = None


def get_inventories_config():
    global TEST_INVENTORIES_CONFIG
    if isinstance(TEST_INVENTORIES_CONFIG, ConfigFile):
        return TEST_INVENTORIES_CONFIG

    global INVENTORIES_CONFIG
    return INVENTORIES_CONFIG


def set_test_inventories_config(enabled: bool):
    global TEST_INVENTORIES_CONFIG
    if enabled:
        TEST_INVENTORIES_CONFIG = InventoriesConfig()
    else:
        TEST_INVENTORIES_CONFIG = None


def save_inventories_config():
    """Write all inventories and their respective items to a WROLPi Config file."""
    get_inventories_config().background_dump.activate_switch()


def import_inventories_config():
    get_inventories_config().import_config()
