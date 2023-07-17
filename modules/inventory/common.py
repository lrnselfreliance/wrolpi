from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import List, Tuple

from pint import Quantity

from wrolpi import before_startup
from wrolpi.common import logger, Base, ConfigFile
from wrolpi.db import get_db_session
from .errors import NoInventories, InventoriesVersionMismatch
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
    """Remove trailing zeros from a Quantity."""
    num, unit = quantity_to_tuple(quantity)
    num = round(num, UNIT_PRECISION)
    num = str(num).rstrip('0').rstrip('.')
    return Decimal(num) * unit


class InventoriesConfig(ConfigFile):
    file_name = 'inventories.yaml'
    default_config = dict(
        inventories=[],
        version=1,
    )

    @property
    def inventories(self) -> dict:
        return self._config['inventories']

    @inventories.setter
    def inventories(self, value: dict):
        self.update({'inventories': value})

    @property
    def version(self) -> int:
        return self._config['version']

    @version.setter
    def version(self, value: int):
        self.update({'version': value})


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


def save_inventories_file():
    """Write all inventories and their respective items to a YAML file."""
    config = get_inventories_config()

    inventories = []
    for inventory in get_inventories():
        inventories.append(inventory.dict())

    if not inventories:
        raise NoInventories('No Inventories are in the database!')

    with increment_inventories_version() as version:
        if config.version and config.version > version:
            raise InventoriesVersionMismatch(
                f'Inventories config version is {config.version} but DB version is {get_inventories_version()}')

        config.inventories = inventories
        config.version = version
        config.save()


@before_startup
def import_inventories_file():
    config = get_inventories_config()

    inventories = get_inventories()
    inventories_names = {i.name for i in inventories}
    new_inventories = [i for i in config.inventories if i['name'] not in inventories_names]
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
