"""Tests for DomainsConfig functionality."""
import json
import pathlib
from http import HTTPStatus

import pytest
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
        domain1 = Collection.from_config(test_session, {'name': 'example.com', 'kind': 'domain'})
        domain2 = Collection.from_config(test_session, {'name': 'test.org', 'kind': 'domain'})
        channel = Collection.from_config(test_session, {'name': 'My Channel', 'kind': 'channel'})
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
        domain1 = Collection.from_config(test_session, {'name': 'example.com', 'kind': 'domain'})
        domain2 = Collection.from_config(test_session, {'name': 'test.org', 'kind': 'domain'})
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
        domain = Collection.from_config(test_session, {
            'name': 'example.com',
            'kind': 'domain',
            'description': 'Original description',
        })
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

    def test_domains_config_import_many_collections(self, test_session: Session, test_directory: pathlib.Path,
                                                    async_client):
        """Importing well over 1000 domains must not fail.

        Regression test for the 10.0.0.9 upgrade: `Collection.batch_from_config` OR'd a
        (name = ? AND kind = ?) pair per collection, and 1,670 domains exceeded SQLite's
        expression-tree depth limit of 1000 ("Expression tree is too large")."""
        config_file = test_directory / 'domains.yaml'
        config_data = {
            'version': 0,
            'collections': [{'name': f'domain{i}.example.com', 'kind': 'domain'} for i in range(1200)],
        }
        config_file.write_text(yaml.dump(config_data))

        config = DomainsConfig()
        config.import_config(file=config_file)

        assert config.successful_import is True
        assert test_session.query(Collection).filter_by(kind='domain').count() == 1200

        # Re-import (the update path) must also survive the pre-fetch query.
        config.import_config(file=config_file)
        assert test_session.query(Collection).filter_by(kind='domain').count() == 1200

    def test_domains_config_global_instance(self):
        """Test that the global domains_config instance exists."""
        assert domains_config is not None
        assert isinstance(domains_config, DomainsConfig)
        assert domains_config.file_name == 'domains.yaml'

    def test_collection_to_config_uses_relative_directory(self, test_session, test_directory, async_client):
        """Collection.to_config() should export directory as relative path for portability."""
        directory = test_directory / 'archive' / 'example.com'
        directory.mkdir(parents=True)

        collection = Collection.from_config(test_session, {
            'name': 'example.com',
            'kind': 'domain',
            'directory': str(directory),
        })
        test_session.commit()

        config = collection.to_config()

        # Directory should be relative, not absolute
        assert not config['directory'].startswith('/'), \
            f"Expected relative path but got absolute: {config['directory']}"
        assert config['directory'] == 'archive/example.com'


@pytest.mark.asyncio
async def test_domain_changes_wait_for_config_import(test_session: Session, test_directory: pathlib.Path,
                                                     async_client):
    """Until domains.yaml is imported (e.g. while WROLPi starts), domains cannot be changed through the API; the
    import would undo the change (or delete a new domain)."""
    domain = Collection.from_config(test_session, {'name': 'kept.com', 'kind': 'domain'})
    test_session.commit()
    domains_config.dump_config()
    assert domains_config.get_file().is_file()
    domains_config.successful_import = False

    did = domain.id
    requests = [
        ('post', '/api/collections', dict(name='new.com', kind='domain')),
        ('put', f'/api/collections/{did}', dict(description='changed')),
        ('post', f'/api/collections/{did}/tag', dict(tag_name='Tagged', directory='archive/Tagged/kept.com')),
        ('delete', f'/api/collections/{did}', None),
    ]
    for method, url, body in requests:
        kwargs = dict(content=json.dumps(body)) if body else {}
        request, response = await getattr(async_client, method)(url, **kwargs)
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE, (method, url, response.json)
        assert response.json['code'] == 'CONFIG_NOT_IMPORTED'

    test_session.expire_all()
    domain = test_session.query(Collection).one()
    assert domain.name == 'kept.com'
    assert domain.description is None
    assert domain.tag is None
    assert domain.directory is None

    # Once imported, domains can change again.
    domains_config.import_config()
    request, response = await async_client.put(f'/api/collections/{did}', content=json.dumps(dict(description='x')))
    assert response.status_code == HTTPStatus.OK, response.json


@pytest.mark.asyncio
async def test_import_keeps_domains_with_archives(test_session: Session, test_directory: pathlib.Path, async_client,
                                                  archive_factory):
    """A domain missing from domains.yaml is deleted by the import, unless it has Archives.  Archives create their
    domain (e.g. an upload or refresh while WROLPi starts, before domains.yaml is imported), and deleting it would
    delete its Archives."""
    from modules.archive.models import Archive
    archive_factory(domain='kept.com', url='https://kept.com/1')
    Collection.from_config(test_session, {'name': 'empty.com', 'kind': 'domain'})
    test_session.commit()
    domains_config.dump_config()
    domains_config.successful_import = False

    # Created before the import.
    archive_factory(domain='new.com', url='https://new.com/1')
    Collection.from_config(test_session, {'name': 'unused.com', 'kind': 'domain'})
    test_session.commit()
    assert test_session.query(Archive).count() == 2

    domains_config.import_config()
    test_session.expire_all()
    assert {i.name for i in test_session.query(Collection)} == {'kept.com', 'empty.com', 'new.com'}
    assert {i.collection.name for i in test_session.query(Archive)} == {'kept.com', 'new.com'}
    assert domains_config.successful_import

    # A domain with Archives which was removed from the config (by hand) is kept too.
    config = yaml.safe_load(domains_config.get_file().read_text())
    config['collections'] = [i for i in config['collections'] if i['name'] != 'kept.com']
    domains_config.get_file().write_text(yaml.dump(config))
    domains_config.import_config()
    test_session.expire_all()
    assert {i.name for i in test_session.query(Collection)} == {'kept.com', 'empty.com', 'new.com'}
    assert test_session.query(Archive).count() == 2
