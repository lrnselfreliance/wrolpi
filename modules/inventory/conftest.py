import pytest

from modules.inventory import common as inventory_common


@pytest.fixture
def test_inventory_configs(test_directory):
    """Use an isolated, config-only inventory store pointed at the test directory.

    Ensures the shared context is attached so the config's save/switch paths work even in pure-unit tests that
    do not start the app via `async_client`.
    """
    from wrolpi.api_utils import api_app
    from wrolpi.contexts import attach_shared_contexts
    if not hasattr(api_app.shared_ctx, 'switches_lock'):
        attach_shared_contexts(api_app)

    (test_directory / 'config' / 'inventory').mkdir(parents=True, exist_ok=True)
    inventory_common.set_test_inventories_config(True)
    config = inventory_common.get_inventory_configs()
    config.initialize()
    try:
        yield config
    finally:
        inventory_common.set_test_inventories_config(False)


@pytest.fixture
def test_catalog_config(test_directory):
    """Use an isolated, config-only food catalog pointed at the test directory."""
    from wrolpi.api_utils import api_app
    from wrolpi.contexts import attach_shared_contexts
    from modules.inventory import catalog as catalog_module
    if not hasattr(api_app.shared_ctx, 'switches_lock'):
        attach_shared_contexts(api_app)

    (test_directory / 'config' / 'inventory').mkdir(parents=True, exist_ok=True)
    catalog_module.set_test_catalog_config(True)
    config = catalog_module.get_catalog_config()
    config.initialize()
    try:
        yield config
    finally:
        catalog_module.set_test_catalog_config(False)


@pytest.fixture
def food_inventory_factory(test_inventory_configs):
    """Create a food inventory (optionally with items) and return its slug."""

    def _(name='Food Storage', inventory_type='food', items=None):
        inventory = test_inventory_configs.create_inventory(name, inventory_type)
        slug = inventory['slug']
        if items:
            test_inventory_configs.save_inventory(slug, dict(items=items))
        return slug

    return _
