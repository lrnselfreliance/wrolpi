"""
Tests for cross-config disaster recovery scenarios.

These tests verify that WROLPi's config system handles disaster recovery correctly
by using the actual `import_all_db_configs()` function from main.py startup.

Config Dependencies:
- WROLPi (wrolpi.yaml): Foundation, must succeed first
- Tags (tags.yaml): No dependencies
- Downloads (download_manager.yaml): No dependencies
- Channels (channels.yaml): Uses Tags (tag_name), linked to Downloads post-import
- Domains (domains.yaml): Uses Tags (tag_name), linked to Downloads post-import
- Inventories (inventories.yaml): No dependencies

Import Order (from import_all_db_configs):
1. Tags
2. Downloads
3. Channels (uses both downloads and tags)
4. Domains
5. Inventories
"""
import pathlib
import shutil

import pytest
import yaml

from modules.archive.lib import get_domains_config
from modules.videos.lib import get_channels_config
from modules.videos.models import Channel
from wrolpi.collections import Collection
from wrolpi.common import import_all_db_configs
from wrolpi.downloader import Download, get_download_manager_config
from wrolpi.tags import Tag

# Path to fixture config files
FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures' / 'configs'


def copy_fixture_config(fixture_name: str, dest_path: pathlib.Path) -> pathlib.Path:
    """Copy a fixture config file to the destination path."""
    fixture_path = FIXTURES_DIR / fixture_name
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_path, dest_path)
    return dest_path


@pytest.mark.asyncio
class TestRealisticFullRecovery:
    """Tests for full recovery from configs with empty database using import_all_db_configs()."""

    async def test_full_recovery_from_backup_configs(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Simulates: User ran reset_api_db.sh with backup configs present.
        Expected: All data restored from configs.

        This test uses the exact code path from main.py startup.
        """
        # Create required directories for the fixture configs
        channel_dir = test_directory / 'videos' / 'test_channel'
        channel_dir.mkdir(parents=True)

        # Copy fixture configs to test directory
        copy_fixture_config('tags_basic.yaml', test_tags_config)
        copy_fixture_config('channels_basic.yaml', test_channels_config)

        # Downloads config needs absolute path fix for destination
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        download_config_path.parent.mkdir(parents=True, exist_ok=True)
        download_config_path.write_text(yaml.dump({
            'version': 0,
            'skip_urls': [],
            'downloads': [{
                'url': 'https://example.com/channel',
                'downloader': 'video',
                'destination': str(channel_dir),
                'frequency': 604800,
                'last_successful_download': None,
                'next_download': None,
                'status': 'new',
                'sub_downloader': None,
                'settings': None,
                'tag_names': ['news'],
            }]
        }))

        # Domains config
        config_dir = test_directory / 'config'
        domains_config_path = config_dir / 'domains.yaml'
        copy_fixture_config('domains_basic.yaml', domains_config_path)

        # Verify DB is empty
        assert test_session.query(Tag).count() == 0
        assert test_session.query(Download).count() == 0
        assert test_session.query(Channel).count() == 0
        assert test_session.query(Collection).filter_by(kind='domain').count() == 0

        # Run the exact startup import sequence
        results = await import_all_db_configs()

        # Verify all imports succeeded
        assert results['tags'] is True, f'Tags import failed: {results}'
        assert results['downloads'] is True, f'Downloads import failed: {results}'
        assert results['channels'] is True, f'Channels import failed: {results}'
        assert results['domains'] is True, f'Domains import failed: {results}'

        # Verify tags restored
        assert test_session.query(Tag).count() == 2
        tag_names = {t.name for t in test_session.query(Tag).all()}
        assert 'news' in tag_names
        assert 'tech' in tag_names

        # Verify downloads restored
        assert test_session.query(Download).count() == 1
        download = test_session.query(Download).first()
        assert download.url == 'https://example.com/channel'

        # Verify channel restored with tag
        assert test_session.query(Channel).count() == 1
        channel = test_session.query(Channel).first()
        assert channel.name == 'Test Channel'
        assert channel.collection.tag.name == 'news'

        # Verify domain restored with tag
        assert test_session.query(Collection).filter_by(kind='domain').count() == 1
        domain = test_session.query(Collection).filter_by(kind='domain').first()
        assert domain.name == 'example.com'
        assert domain.tag.name == 'tech'

    async def test_import_returns_results_dict(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Verify import_all_db_configs() returns a dict with success status for each config.
        """
        # Create empty but valid configs
        test_tags_config.write_text(yaml.dump({'version': 0, 'tags': {}}))

        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        download_config_path.parent.mkdir(parents=True, exist_ok=True)
        download_config_path.write_text(yaml.dump({
            'version': 0, 'skip_urls': [], 'downloads': []
        }))

        test_channels_config.write_text(yaml.dump({'version': 0, 'channels': []}))

        config_dir = test_directory / 'config'
        domains_config_path = config_dir / 'domains.yaml'
        domains_config_path.write_text(yaml.dump({'version': 0, 'collections': []}))

        results = await import_all_db_configs()

        # All should succeed even with empty configs
        assert isinstance(results, dict)
        assert 'tags' in results
        assert 'downloads' in results
        assert 'channels' in results
        assert 'domains' in results
        assert 'inventories' in results


@pytest.mark.asyncio
class TestRealisticPartialRecovery:
    """Tests for partial recovery when some configs are missing."""

    async def test_partial_recovery_missing_downloads(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Simulates: downloads.yaml missing but channels.yaml exists.
        Expected: Channels import without links to downloads.
        """
        # Create channel directory
        channel_dir = test_directory / 'videos' / 'test_channel'
        channel_dir.mkdir(parents=True)

        # Set up tags and channels config (no downloads)
        copy_fixture_config('tags_basic.yaml', test_tags_config)
        test_channels_config.write_text(yaml.dump({
            'version': 0,
            'channels': [{
                'name': 'Channel Without Download',
                'directory': str(channel_dir),
                'url': 'https://example.com/channel',
                'tag_name': 'news',
            }]
        }))

        # Ensure downloads config doesn't exist
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        if download_config_path.is_file():
            download_config_path.unlink()

        results = await import_all_db_configs()

        # Tags and channels should succeed, downloads too (empty import)
        assert results['tags'] is True
        assert results['channels'] is True

        # Channel should exist
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Channel Without Download'
        assert channels[0].collection.tag.name == 'news'

        # No downloads should exist
        assert test_session.query(Download).count() == 0

    async def test_partial_recovery_missing_tags(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Simulates: tags.yaml missing but channels.yaml references tags.
        Expected: Channels import with null tags (graceful degradation).
        """
        # Create channel directory
        channel_dir = test_directory / 'videos' / 'test_channel'
        channel_dir.mkdir(parents=True)

        # Ensure tags config is empty (no tags)
        test_tags_config.write_text(yaml.dump({'version': 0, 'tags': {}}))

        # Channels config references non-existent tag
        test_channels_config.write_text(yaml.dump({
            'version': 0,
            'channels': [{
                'name': 'Channel With Missing Tag',
                'directory': str(channel_dir),
                'url': 'https://example.com/channel',
                'tag_name': 'nonexistent_tag',
            }]
        }))

        results = await import_all_db_configs()

        assert results['tags'] is True
        assert results['channels'] is True

        # Channel should exist but without tag
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Channel With Missing Tag'
        assert channels[0].collection.tag is None  # Tag doesn't exist


@pytest.mark.asyncio
class TestRealisticEdgeCases:
    """Tests for edge cases like minimal configs and corrupted files."""

    async def test_recovery_with_minimal_required_fields(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Simulates: Config file with minimal but complete required fields.
        Expected: Import succeeds with null/empty values for optional fields.
        """
        test_tags_config.write_text(yaml.dump({'version': 0, 'tags': {}}))

        # Use minimal downloads config - has all required fields with null values
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        download_config_path.parent.mkdir(parents=True, exist_ok=True)
        copy_fixture_config('downloads_minimal.yaml', download_config_path)

        results = await import_all_db_configs()

        # Should succeed
        assert results['downloads'] is True

        # Verify download was created with defaults
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/minimal'
        assert downloads[0].downloader == 'video'
        assert downloads[0].frequency == 604800

    async def test_one_corrupt_config_doesnt_block_others(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, async_client):
        """
        Simulates: One config is invalid YAML.
        Expected: Other configs still import successfully.
        """
        # Valid tags config
        copy_fixture_config('tags_basic.yaml', test_tags_config)

        # Corrupted downloads config (invalid YAML)
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        download_config_path.parent.mkdir(parents=True, exist_ok=True)
        download_config_path.write_text('invalid: yaml: syntax: [[[')

        # Empty but valid channels config
        test_channels_config.write_text(yaml.dump({'version': 0, 'channels': []}))

        results = await import_all_db_configs()

        # Tags should succeed, downloads may fail due to corrupt config
        assert results['tags'] is True
        # Channels should still succeed regardless of downloads status
        assert results['channels'] is True

        # Tags should be imported
        assert test_session.query(Tag).count() == 2


@pytest.mark.asyncio
class TestDBPreservation:
    """Tests for scenarios where configs are missing but DB has data."""

    async def test_empty_configs_preserve_db_data(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, channel_factory, async_client):
        """
        Simulates: Configs empty/missing, DB already has data.
        Expected: Never delete on empty config (data preservation).
        """
        # Create data in DB first
        tag = Tag(name='preserve_tag', color='#123456')
        test_session.add(tag)
        test_session.flush([tag])

        # Create a channel using factory
        channel = channel_factory(name='Preserved Channel', tag_name='preserve_tag')

        # Create a domain collection
        domain = Collection(name='preserved.com', kind='domain')
        test_session.add(domain)

        # Create a download
        download = Download(
            url='https://preserved.com/video',
            downloader='video',
            frequency=604800,
            status='new',
        )
        test_session.add(download)
        test_session.commit()

        # Verify initial state
        assert test_session.query(Channel).count() == 1
        assert test_session.query(Collection).filter_by(kind='domain').count() == 1
        assert test_session.query(Download).count() >= 1
        assert test_session.query(Tag).count() == 1

        # Remove all config files
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        if download_config_path.is_file():
            download_config_path.unlink()

        channels_config = get_channels_config()
        channels_config_path = channels_config.get_file()
        if channels_config_path.is_file():
            channels_config_path.unlink()

        domains_config = get_domains_config()
        domains_config_path = domains_config.get_file()
        if domains_config_path.is_file():
            domains_config_path.unlink()

        if test_tags_config.is_file():
            test_tags_config.unlink()

        # Run import with missing configs
        await import_all_db_configs()

        # All DB data should be preserved
        assert test_session.query(Channel).count() == 1
        assert test_session.query(Channel).first().name == 'Preserved Channel'

        assert test_session.query(Collection).filter_by(kind='domain').count() == 1
        assert test_session.query(Collection).filter_by(kind='domain').first().name == 'preserved.com'

        preserved_download = test_session.query(Download).filter_by(
            url='https://preserved.com/video'
        ).first()
        assert preserved_download is not None

        assert test_session.query(Tag).count() == 1
        assert test_session.query(Tag).first().name == 'preserve_tag'

    async def test_configs_with_new_data_add_to_existing(
            self, test_session, test_directory, test_download_manager_config,
            test_channels_config, test_tags_config, channel_factory, async_client):
        """
        Simulates: DB has some data, configs have new data.
        Expected: New data imported from config. Config is source of truth for tags.
        """
        # Create existing tag in DB
        existing_tag = Tag(name='existing_tag', color='#AAAAAA')
        test_session.add(existing_tag)
        test_session.commit()

        assert test_session.query(Tag).count() == 1

        # Config has both the existing tag and a new one
        # Config is source of truth, so we need to include existing_tag
        test_tags_config.write_text(yaml.dump({
            'version': 0,
            'tags': {
                'existing_tag': {'color': '#AAAAAA'},
                'new_tag': {'color': '#BBBBBB'}
            }
        }))

        await import_all_db_configs()

        # Both tags should exist
        test_session.expire_all()
        tags_in_db = test_session.query(Tag).all()
        tag_names = {t.name for t in tags_in_db}
        assert 'existing_tag' in tag_names
        assert 'new_tag' in tag_names


@pytest.mark.asyncio
class TestMissingDownloadConfig:
    """Tests for scenarios where download_manager.yaml is missing."""

    async def test_channels_import_without_downloads_config(
            self, test_session, test_directory, test_channels_config, test_tags_config, async_client):
        """
        Channels config exists, download_manager.yaml missing.
        Expected: Channels import successfully, no downloads linked.
        """
        # Create channel directory
        channel_dir = test_directory / 'videos' / 'test_channel'
        channel_dir.mkdir(parents=True)

        copy_fixture_config('tags_basic.yaml', test_tags_config)

        test_channels_config.write_text(yaml.dump({
            'version': 0,
            'channels': [{
                'name': 'Test Channel',
                'directory': str(channel_dir),
                'url': 'https://example.com/channel',
                'tag_name': 'news',
            }]
        }))

        # Ensure download_manager.yaml does not exist
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        if download_config_path.is_file():
            download_config_path.unlink()

        # Run using import_all_db_configs
        results = await import_all_db_configs()

        assert results['tags'] is True
        assert results['channels'] is True

        # Verify channels imported successfully
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Test Channel'
        assert channels[0].collection.tag is not None
        assert channels[0].collection.tag.name == 'news'

        # Verify no downloads created
        assert test_session.query(Download).count() == 0

    async def test_domains_import_without_downloads_config(
            self, test_session, test_directory, test_tags_config, async_client):
        """
        Domains config exists, download_manager.yaml missing.
        Expected: Domains import successfully, no downloads linked.
        """
        copy_fixture_config('tags_basic.yaml', test_tags_config)

        # Create domains config
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)
        domains_config_path = config_dir / 'domains.yaml'
        copy_fixture_config('domains_basic.yaml', domains_config_path)

        # Ensure download_manager.yaml does not exist
        download_config = get_download_manager_config()
        download_config_path = download_config.get_file()
        if download_config_path.is_file():
            download_config_path.unlink()

        results = await import_all_db_configs()

        assert results['tags'] is True
        assert results['domains'] is True

        # Verify domains imported successfully
        domains = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(domains) == 1
        assert domains[0].name == 'example.com'
        assert domains[0].tag is not None
        assert domains[0].tag.name == 'tech'

        # Verify no downloads created
        assert test_session.query(Download).count() == 0


@pytest.mark.asyncio
class TestMissingTagsConfig:
    """Tests for scenarios where tags.yaml is missing but channels/domains reference tags."""

    async def test_channels_import_with_tag_reference_no_tags_config(
            self, test_session, test_directory, test_channels_config, test_tags_config, async_client):
        """
        Channels config has tag_name, tags.yaml missing.
        Expected: Channels import, tag references resolve to None with warning.
        """
        # Create channel directory
        channel_dir = test_directory / 'videos' / 'tagged_channel'
        channel_dir.mkdir(parents=True)

        # Create channels config with tag reference
        test_channels_config.write_text(yaml.dump({
            'version': 0,
            'channels': [{
                'name': 'Tagged Channel',
                'directory': str(channel_dir),
                'url': 'https://example.com/tagged_channel',
                'tag_name': 'nonexistent_tag',
            }]
        }))

        # Empty tags config
        test_tags_config.write_text(yaml.dump({'version': 0, 'tags': {}}))

        results = await import_all_db_configs()

        assert results['tags'] is True
        assert results['channels'] is True

        # Verify channel imported successfully
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Tagged Channel'
        # Tag reference should resolve to None
        assert channels[0].collection.tag is None

    async def test_domains_import_with_tag_reference_no_tags_config(
            self, test_session, test_directory, test_tags_config, async_client):
        """
        Domains config has tag_name, tags.yaml missing.
        Expected: Domains import, tag references resolve to None with warning.
        """
        # Create domains config with tag reference
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)
        domains_config_path = config_dir / 'domains.yaml'
        domains_config_path.write_text(yaml.dump({
            'version': 0,
            'collections': [{
                'name': 'tagged-domain.com',
                'kind': 'domain',
                'tag_name': 'missing_tag',
            }]
        }))

        # Empty tags config
        test_tags_config.write_text(yaml.dump({'version': 0, 'tags': {}}))

        results = await import_all_db_configs()

        assert results['tags'] is True
        assert results['domains'] is True

        # Verify domain imported successfully
        domains = test_session.query(Collection).filter_by(kind='domain').all()
        assert len(domains) == 1
        assert domains[0].name == 'tagged-domain.com'
        # Tag reference should resolve to None
        assert domains[0].tag is None
