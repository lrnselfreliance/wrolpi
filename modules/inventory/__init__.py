from wrolpi.db import get_db_session
from .api import inventory_bp
from .inventory import logger, DEFAULT_CATEGORIES, DEFAULT_INVENTORIES
from .models import Item, Inventory

INVENTORY_INITIALIZED = False


def init_inventory(force=False):
    """
    Initialize inventory categories, but only if none already exist.  Initializes the inventories, but only if none
    already exist.
    """
    global INVENTORY_INITIALIZED
    if INVENTORY_INITIALIZED and force is False:
        return

    logger.info('Initializing inventory')

    with get_db_session(commit=True) as session:
        if session.query(Item).count() == 0:
            for subcategory, category in DEFAULT_CATEGORIES:
                item = Item(subcategory=subcategory, category=category)
                session.add(item)

        if session.query(Inventory).count() == 0:
            for name in DEFAULT_INVENTORIES:
                inv = Inventory(name=name)
                session.add(inv)

    INVENTORY_INITIALIZED = True
