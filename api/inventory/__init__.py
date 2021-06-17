from .api import api_bp
from .common import DEFAULT_CATEGORIES, DEFAULT_INVENTORIES
from .inventory import logger
from .main import PRETTY_NAME, init_parser
from .models import Item, Inventory
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

    with get_db_context(commit=True) as (engine, session):
        if session.query(Item).count() == 0:
            for subcategory, category in DEFAULT_CATEGORIES:
                item = Item(subcategory=subcategory, category=category)
                session.add(item)

        if session.query(Inventory).count() == 0:
            for name in DEFAULT_INVENTORIES:
                inv = Inventory(name=name)
                session.add(inv)

    INVENTORY_INITIALIZED = True
