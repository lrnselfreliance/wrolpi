"""Tests for DomainsConfig functionality."""
import pathlib

import yaml
from sqlalchemy.orm import Session

from modules.archive.lib import DomainsConfig, domains_config
from wrolpi.collections import Collection


class TestDomainsConfig:
    """Test domains.yaml config file operations."""

    def test_domains_config_import_creates_domain_collections(self, test_session: Session, test_directory: pathlib.Path,
                                                              async_client):
        """Test that importing domains.yaml creates domain collections."""
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {
                    'name': 'example.com',
                    'kind': 'domain',
                    'description': 'Archives from example.com',
                },
                {
                    'name': 'wikipedia.org',
                    'kind': 'domain',
                },
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        # Import the config
        config = DomainsConfig()
        config.import_config(file=config_file)

        # Verify collections were created
        collections = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(collections) == 2

        example = test_session.query(Collection).filter_by(name='example.com', kind='domain').first()
        assert example is not None
        assert example.description == 'Archives from example.com'
        assert example.directory is None  # Domain collections should be unrestricted

        wiki = test_session.query(Collection).filter_by(name='wikipedia.org', kind='domain').first()
        assert wiki is not None

    def test_domains_config_dump_exports_only_domain_collections(self, test_session: Session,
                                                                 test_directory: pathlib.Path, async_client):
        """Test that dumping domains.yaml only exports domain collections."""
        # Create some domain and channel collections
        domain1 = Collection.from_config({'name': 'example.com', 'kind': 'domain'}, session=test_session)
        domain2 = Collection.from_config({'name': 'test.org', 'kind': 'domain'}, session=test_session)
        channel = Collection.from_config({'name': 'My Channel', 'kind': 'channel'}, session=test_session)
        test_session.commit()

        # Dump to config
        config_file = test_directory / 'domains.yaml'
        config = DomainsConfig()
        config.dump_config(file=config_file)

        # Read and verify
        data = yaml.safe_load(config_file.read_text())
        assert 'collections' in data
        assert len(data['collections']) == 2  # Only domain collections

        names = {c['name'] for c in data['collections']}
        assert 'example.com' in names
        assert 'test.org' in names
        assert 'My Channel' not in names  # Channel should not be in domains.yaml

        # All should have kind='domain'
        for coll in data['collections']:
            assert coll['kind'] == 'domain'

    def test_domains_config_enforces_domain_validation(self, test_session: Session, test_directory: pathlib.Path,
                                                       async_client):
        """Test that importing invalid domain names skips them (logs error but doesn't fail import)."""
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {
                    'name': 'invalid-domain',  # No dot
                    'kind': 'domain',
                },
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()

        # Import should succeed but skip invalid domain (error is logged)
        config.import_config(file=config_file)

        # No collections should be created
        domains = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(domains) == 0

    def test_domains_config_forces_kind_to_domain(self, test_session: Session, test_directory: pathlib.Path,
                                                  async_client):
        """Test that DomainsConfig forces kind='domain' even if not specified."""
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {
                    'name': 'example.com',
                    # kind not specified
                },
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()
        config.import_config(file=config_file)

        # Should be created with kind='domain'
        collection = test_session.query(Collection).filter_by(name='example.com').first()
        assert collection is not None
        assert collection.kind == 'domain'

    def test_domains_config_removes_deleted_domains(self, test_session: Session, test_directory: pathlib.Path,
                                                    async_client):
        """Test that domains removed from config are deleted from database."""
        # Create two domain collections
        domain1 = Collection.from_config({'name': 'example.com', 'kind': 'domain'}, session=test_session)
        domain2 = Collection.from_config({'name': 'test.org', 'kind': 'domain'}, session=test_session)
        test_session.commit()

        # Import config with only one domain
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {'name': 'example.com', 'kind': 'domain'},
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()
        config.import_config(file=config_file)

        # test.org should be deleted
        remaining = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(remaining) == 1
        assert remaining[0].name == 'example.com'

    def test_domains_config_updates_existing_domain(self, test_session: Session, test_directory: pathlib.Path,
                                                    async_client):
        """Test that updating a domain in config updates the existing collection."""
        # Create initial domain
        domain = Collection.from_config({
            'name': 'example.com',
            'kind': 'domain',
            'description': 'Original description',
        }, session=test_session)
        test_session.commit()
        domain_id = domain.id

        # Import config with updated description
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {
                    'name': 'example.com',
                    'kind': 'domain',
                    'description': 'Updated description',
                },
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()
        config.import_config(file=config_file)

        # Should update existing, not create new
        all_domains = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(all_domains) == 1
        assert all_domains[0].id == domain_id
        assert all_domains[0].description == 'Updated description'

    def test_domains_config_skips_invalid_entries(self, test_session: Session, test_directory: pathlib.Path,
                                                  async_client):
        """Test that invalid entries are skipped but valid ones are imported."""
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [
                {'name': 'example.com', 'kind': 'domain'},  # Valid
                {'name': 'invalid', 'kind': 'domain'},  # Invalid - no dot
                {'name': 'test.org', 'kind': 'domain'},  # Valid
            ]
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()
        config.import_config(file=config_file)

        # Should have imported 2 valid domains, skipped 1 invalid
        domains = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(domains) == 2
        names = {d.name for d in domains}
        assert 'example.com' in names
        assert 'test.org' in names
        assert 'invalid' not in names

    def test_domains_config_global_instance(self):
        """Test that the global domains_config instance exists."""
        assert domains_config is not None
        assert isinstance(domains_config, DomainsConfig)
        assert domains_config.file_name == 'domains.yaml'
