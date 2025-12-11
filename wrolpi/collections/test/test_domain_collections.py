"""Tests for domain-specific Collection functionality."""
import pytest
from sqlalchemy.orm import Session

from wrolpi.collections.models import Collection


class TestDomainValidation:
    """Test domain name validation for Collections with kind='domain'."""

    def test_is_valid_domain_name_valid_domains(self):
        """Test that valid domain names are accepted."""
        assert Collection.is_valid_domain_name('example.com') is True
        assert Collection.is_valid_domain_name('sub.example.com') is True
        assert Collection.is_valid_domain_name('a.b.c') is True
        assert Collection.is_valid_domain_name('test.org') is True
        assert Collection.is_valid_domain_name('my-site.co.uk') is True

    def test_is_valid_domain_name_invalid_domains(self):
        """Test that invalid domain names are rejected."""
        # No dots
        assert Collection.is_valid_domain_name('example') is False
        assert Collection.is_valid_domain_name('localhost') is False

        # Starts or ends with dot
        assert Collection.is_valid_domain_name('.example.com') is False
        assert Collection.is_valid_domain_name('example.com.') is False
        assert Collection.is_valid_domain_name('.') is False

        # Empty or non-string
        assert Collection.is_valid_domain_name('') is False
        assert Collection.is_valid_domain_name(None) is False
        assert Collection.is_valid_domain_name(123) is False

    def test_from_config_validates_domain_kind(self, test_session: Session):
        """Test that from_config enforces domain validation when kind='domain'."""
        # Valid domain should succeed
        config = {
            'name': 'example.com',
            'kind': 'domain',
        }
        collection = Collection.from_config(test_session, config)
        assert collection.name == 'example.com'
        assert collection.kind == 'domain'
        assert collection.directory is None

        # Invalid domain should raise ValueError
        invalid_config = {
            'name': 'invalid-no-dot',
            'kind': 'domain',
        }
        with pytest.raises(ValueError, match='Invalid domain name'):
            Collection.from_config(test_session, invalid_config)

        # Domain starting with dot should fail
        invalid_config2 = {
            'name': '.example.com',
            'kind': 'domain',
        }
        with pytest.raises(ValueError, match='Invalid domain name'):
            Collection.from_config(test_session, invalid_config2)

        # Domain ending with dot should fail
        invalid_config3 = {
            'name': 'example.com.',
            'kind': 'domain',
        }
        with pytest.raises(ValueError, match='Invalid domain name'):
            Collection.from_config(test_session, invalid_config3)

    def test_from_config_allows_any_name_for_channel_kind(self, test_session: Session):
        """Test that channel kind does not enforce domain validation."""
        # Channel kind should allow any name (no domain validation)
        config = {
            'name': 'My Channel Without Dots',
            'kind': 'channel',
        }
        collection = Collection.from_config(test_session, config)
        assert collection.name == 'My Channel Without Dots'
        assert collection.kind == 'channel'

    def test_domain_collection_unrestricted_mode(self, test_session: Session):
        """Test that domain collections can be created without directory (unrestricted)."""
        config = {
            'name': 'example.org',
            'kind': 'domain',
            'description': 'Archives from example.org',
        }
        collection = Collection.from_config(test_session, config)
        test_session.commit()

        assert collection.name == 'example.org'
        assert collection.kind == 'domain'
        assert collection.directory is None
        assert collection.is_directory_restricted is False
        assert collection.description == 'Archives from example.org'

    def test_domain_collection_with_subdomain(self, test_session: Session):
        """Test that subdomains are valid domain names."""
        config = {
            'name': 'blog.example.com',
            'kind': 'domain',
        }
        collection = Collection.from_config(test_session, config)
        test_session.commit()

        assert collection.name == 'blog.example.com'
        assert collection.kind == 'domain'

    def test_update_existing_domain_collection(self, test_session: Session):
        """Test that updating a domain collection preserves validation."""
        # Create initial domain collection
        config = {
            'name': 'example.com',
            'kind': 'domain',
            'description': 'Initial description',
        }
        collection = Collection.from_config(test_session, config)
        test_session.commit()
        collection_id = collection.id

        # Update with valid domain
        updated_config = {
            'name': 'example.com',
            'kind': 'domain',
            'description': 'Updated description',
        }
        updated = Collection.from_config(test_session, updated_config)
        assert updated.id == collection_id
        assert updated.description == 'Updated description'

    def test_domain_collection_to_config(self, test_session: Session):
        """Test that domain collections export correctly to config."""
        config = {
            'name': 'test.org',
            'kind': 'domain',
            'description': 'Test domain',
        }
        collection = Collection.from_config(test_session, config)
        test_session.commit()

        exported = collection.to_config()
        assert exported['name'] == 'test.org'
        assert exported['kind'] == 'domain'
        assert exported['description'] == 'Test domain'
        assert 'directory' not in exported  # Should not have directory

    def test_get_by_name_and_kind(self, test_session: Session):
        """Test finding domain collections by name and kind."""
        # Create two collections with same name but different kinds
        domain_config = {
            'name': 'example.com',
            'kind': 'domain',
        }
        channel_config = {
            'name': 'example.com',
            'kind': 'channel',
        }

        domain_coll = Collection.from_config(test_session, domain_config)
        channel_coll = Collection.from_config(test_session, channel_config)
        test_session.commit()

        # Both should exist with different IDs
        assert domain_coll.id != channel_coll.id
        assert domain_coll.kind == 'domain'
        assert channel_coll.kind == 'channel'

        # Finding by name and kind should return the correct one
        found_domain = test_session.query(Collection).filter_by(
            name='example.com',
            kind='domain'
        ).first()
        assert found_domain.id == domain_coll.id


class TestDirectoryValidation:
    """Test that collection directories must be under media directory."""

    def test_from_config_rejects_absolute_path_outside_media_directory(self, test_session, test_directory):
        """Test that from_config rejects absolute paths outside media directory."""
        from wrolpi.errors import ValidationError

        # Try to create collection with directory outside media directory
        config = {
            'name': 'example.com',
            'kind': 'domain',
            'directory': '/opt/wrolpi/archive/example.com'  # Outside media directory!
        }

        # Should raise ValidationError
        with pytest.raises(ValidationError, match="must be under media directory"):
            Collection.from_config(test_session, config)

    def test_from_config_accepts_relative_path(self, test_session, test_directory):
        """Test that from_config converts relative paths to absolute under media directory."""
        from wrolpi.common import get_media_directory

        config = {
            'name': 'example.com',
            'kind': 'domain',
            'directory': 'archive/example.com'  # Relative path
        }

        collection = Collection.from_config(test_session, config)
        test_session.flush()

        # Should be converted to absolute path under media directory
        assert collection.directory.is_absolute()
        assert str(collection.directory).startswith(str(get_media_directory()))
        assert collection.directory.name == 'example.com'

    def test_from_config_accepts_absolute_path_under_media_directory(self, test_session, test_directory):
        """Test that from_config accepts absolute paths that are under media directory."""
        from wrolpi.common import get_media_directory

        media_dir = get_media_directory()
        valid_path = media_dir / 'archive' / 'example.com'

        config = {
            'name': 'example.com',
            'kind': 'domain',
            'directory': str(valid_path)
        }

        collection = Collection.from_config(test_session, config)
        test_session.flush()

        # Should accept the path
        assert collection.directory == valid_path
