"""
Tests for DomainsConfig import/upgrade scenarios.

Tests cover:
1. Onboarding (new install) - no config file exists
2. Upgrade - config file exists with data
3. Edge cases - empty config, missing config with DB data
"""
import pytest
import yaml

from modules.archive.lib import get_domains_config
from wrolpi.collections import Collection


@pytest.mark.asyncio
class TestDomainsConfigOnboarding:
    """Tests for new install scenarios where no config file exists."""

    async def test_new_install_no_db_data(self, test_session, test_directory, async_client):
        """
        New install with empty DB and no config file.
        Should succeed with empty config.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Ensure no config file exists
        if config_path.is_file():
            config_path.unlink()

        # Ensure DB has no domain collections
        assert test_session.query(Collection).filter_by(kind='domain').count() == 0

        # Import should succeed
        config.import_config()
        assert config.successful_import is True

    async def test_new_install_with_db_data(self, test_session, test_directory, async_client):
        """
        Config file missing but DB has data.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create a domain collection in DB
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=None,
        )
        test_session.add(collection)
        test_session.commit()

        # Remove config file to simulate missing config
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 1
        assert collections[0].name == 'example.com'


@pytest.mark.asyncio
class TestDomainsConfigUpgrade:
    """Tests for upgrade scenarios where config file exists."""

    async def test_upgrade_config_exists_with_data(self, test_session, test_directory, async_client):
        """
        Upgrade with existing config containing collection data.
        Should import and sync DB with config.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create a collection in DB
        collection = Collection(
            name='test.org',
            kind='domain',
            directory=None,
        )
        test_session.add(collection)
        test_session.commit()

        # Dump to create config file
        config.dump_config()
        assert config_path.is_file()

        # Now import should succeed and preserve the collection
        config.import_config()
        assert config.successful_import is True

        # Collection should still exist
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 1
        assert collections[0].name == 'test.org'

    async def test_upgrade_config_exists_empty_list(self, test_session, test_directory, async_client):
        """
        Config exists but has empty collections list.
        Should NOT delete existing DB collections (never delete on empty).
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create a collection in DB
        collection = Collection(
            name='preserve.me',
            kind='domain',
            directory=None,
        )
        test_session.add(collection)
        test_session.commit()

        # Write empty config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump({'version': 0, 'collections': []}, f)

        # Reinitialize config to read the empty file
        config.initialize()

        # Import should succeed but NOT delete the collection
        config.import_config()
        assert config.successful_import is True

        # Collection should still exist (never delete on empty config)
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 1
        assert collections[0].name == 'preserve.me'

    async def test_upgrade_config_missing_db_has_data(self, test_session, test_directory, async_client):
        """
        Config file missing but DB has domain collections.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create collections in DB
        for name in ['domain1.com', 'domain2.org']:
            collection = Collection(
                name=name,
                kind='domain',
                directory=None,
            )
            test_session.add(collection)
        test_session.commit()

        # Remove config file
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 2
        collection_names = {c.name for c in collections}
        assert 'domain1.com' in collection_names
        assert 'domain2.org' in collection_names


@pytest.mark.asyncio
class TestDomainsConfigEdgeCases:
    """Tests for edge cases in config import."""

    async def test_config_deletes_removed_items(self, test_session, test_directory, async_client):
        """
        Config removes a collection that exists in DB.
        Should delete the collection from DB.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create two collections
        for name in ['keep.this', 'delete.this']:
            collection = Collection(
                name=name,
                kind='domain',
                directory=None,
            )
            test_session.add(collection)
        test_session.commit()

        # Dump to config
        config.dump_config()

        # Modify config to remove one collection
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        config_data['collections'] = [c for c in config_data['collections'] if c['name'] == 'keep.this']

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Only one collection should remain
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 1
        assert collections[0].name == 'keep.this'

    async def test_config_adds_new_items(self, test_session, test_directory, async_client):
        """
        Config has a new collection that doesn't exist in DB.
        Should create the collection in DB.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Ensure no collections in DB
        assert test_session.query(Collection).filter_by(kind='domain').count() == 0

        # Write config with a new collection
        config_data = {
            'version': 0,
            'collections': [{
                'name': 'new.domain',
                'kind': 'domain',
            }]
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Collection should be created
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 1
        assert collections[0].name == 'new.domain'

    async def test_config_updates_existing_items(self, test_session, test_directory, async_client):
        """
        Config updates an existing collection's description.
        Should update the collection in DB.
        """
        config = get_domains_config()
        config_path = config.get_file()

        # Create a collection
        collection = Collection(
            name='update.me',
            kind='domain',
            directory=None,
            description='Old description',
        )
        test_session.add(collection)
        test_session.commit()

        # Dump to config
        config.dump_config()

        # Modify config to change description
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        for c in config_data['collections']:
            if c['name'] == 'update.me':
                c['description'] = 'New description'

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Collection should be updated
        collection = test_session.query(Collection).filter_by(name='update.me').first()
        assert collection is not None
        assert collection.description == 'New description'
