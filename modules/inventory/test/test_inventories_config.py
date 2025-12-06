"""
Tests for InventoriesConfig import/upgrade scenarios.

Tests cover:
1. Onboarding (new install) - no config file exists
2. Upgrade - config file exists with data
3. Edge cases - empty config, missing config with DB data
"""
import pytest
import yaml

from modules.inventory import Inventory
from modules.inventory.common import get_inventories_config


@pytest.mark.asyncio
class TestInventoriesConfigOnboarding:
    """Tests for new install scenarios where no config file exists."""

    async def test_new_install_no_db_data(self, test_session, test_directory, async_client):
        """
        New install with empty DB and no config file.
        Should succeed with empty config.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Ensure no config file exists
        if config_path.is_file():
            config_path.unlink()

        # Ensure DB has no inventories
        assert test_session.query(Inventory).count() == 0

        # Import should succeed
        config.import_config()
        assert config.successful_import is True

    async def test_new_install_with_db_data(self, test_session, test_directory, async_client, test_inventory):
        """
        Config file missing but DB has data.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Ensure we have an inventory from the fixture
        assert test_session.query(Inventory).count() == 1

        # Remove config file to simulate missing config
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 1
        assert inventories[0].name == 'Test Inventory'


@pytest.mark.asyncio
class TestInventoriesConfigUpgrade:
    """Tests for upgrade scenarios where config file exists."""

    async def test_upgrade_config_exists_with_data(self, test_session, test_directory, async_client, test_inventory):
        """
        Upgrade with existing config containing inventory data.
        Should import and sync DB with config.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Dump to create config file
        config.dump_config()
        assert config_path.is_file()

        # Now import should succeed and preserve the inventory
        config.import_config()
        assert config.successful_import is True

        # Inventory should still exist
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 1
        assert inventories[0].name == 'Test Inventory'

    async def test_upgrade_config_exists_empty_list(self, test_session, test_directory, async_client, test_inventory):
        """
        Config exists but has empty inventories list.
        Should NOT delete existing DB inventories (never delete on empty).
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Write empty config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump({'version': 0, 'inventories': []}, f)

        # Reinitialize config to read the empty file
        config.initialize()

        # Import should succeed but NOT delete the inventory
        config.import_config()
        assert config.successful_import is True

        # Inventory should still exist (never delete on empty config)
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 1
        assert inventories[0].name == 'Test Inventory'

    async def test_upgrade_config_missing_db_has_data(self, test_session, test_directory, async_client):
        """
        Config file missing but DB has inventories.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Create inventories in DB
        for name in ['Inventory One', 'Inventory Two']:
            inventory = Inventory(name=name)
            test_session.add(inventory)
        test_session.commit()

        # Remove config file
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 2
        inventory_names = {i.name for i in inventories}
        assert 'Inventory One' in inventory_names
        assert 'Inventory Two' in inventory_names


@pytest.mark.asyncio
class TestInventoriesConfigEdgeCases:
    """Tests for edge cases in config import."""

    async def test_config_deletes_removed_items(self, test_session, test_directory, async_client):
        """
        Config removes an inventory that exists in DB.
        Should delete the inventory from DB.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Create two inventories
        for name in ['Keep This', 'Delete This']:
            inventory = Inventory(name=name)
            test_session.add(inventory)
        test_session.commit()

        # Dump to config
        config.dump_config()

        # Modify config to remove one inventory
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        config_data['inventories'] = [i for i in config_data['inventories'] if i['name'] == 'Keep This']

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Only one inventory should remain
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 1
        assert inventories[0].name == 'Keep This'

    async def test_config_adds_new_items(self, test_session, test_directory, async_client):
        """
        Config has a new inventory that doesn't exist in DB.
        Should create the inventory in DB.
        """
        config = get_inventories_config()
        config_path = config.get_file()

        # Ensure no inventories in DB
        assert test_session.query(Inventory).count() == 0

        # Write config with a new inventory
        config_data = {
            'version': 0,
            'inventories': [{
                'name': 'New Inventory',
                'id': 1,
                'created_at': None,
                'deleted_at': None,
                'items': [],
            }]
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Inventory should be created
        inventories = test_session.query(Inventory).all()
        assert len(inventories) == 1
        assert inventories[0].name == 'New Inventory'
