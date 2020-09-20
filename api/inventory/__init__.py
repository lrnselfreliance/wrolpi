from dictorm import Table

from .api import api_bp
from .common import DEFAULT_CATEGORIES, DEFAULT_INVENTORIES
from .inventory import logger
from .main import PRETTY_NAME, init_parser
from ..db import get_db_context


def import_settings_config():
    pass


INVENTORY_INITIALIZED = False


def init(force=False):
    """
    Initialize inventory categories, but only if none already exist.  Initializes the inventories, but only if none
    already exist.
    """
    global INVENTORY_INITIALIZED
    if INVENTORY_INITIALIZED and force is False:
        return

    logger.info('Initializing inventory')

    with get_db_context(commit=True) as (db_conn, db):
        Item: Table = db['item']
        if Item.count() == 0:
            for subcategory, category in DEFAULT_CATEGORIES:
                Item(subcategory=subcategory, category=category).flush()

        Inventory: Table = db['inventory']
        if Inventory.count() == 0:
            for name in DEFAULT_INVENTORIES:
                Inventory(name=name).flush()

    INVENTORY_INITIALIZED = True
