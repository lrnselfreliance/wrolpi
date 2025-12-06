"""
Tests for ChannelsConfig import/upgrade scenarios.

Tests cover:
1. Onboarding (new install) - no config file exists
2. Upgrade - config file exists with data
3. Edge cases - empty config, missing config with DB data
"""
import pytest
import yaml

from modules.videos.lib import get_channels_config
from modules.videos.models import Channel


@pytest.mark.asyncio
class TestChannelsConfigOnboarding:
    """Tests for new install scenarios where no config file exists."""

    async def test_new_install_no_db_data(self, test_session, test_directory, async_client, test_channels_config):
        """
        New install with empty DB and no config file.
        Should succeed with empty config.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Ensure no config file exists
        if config_path.is_file():
            config_path.unlink()

        # Ensure DB has no channels
        assert test_session.query(Channel).count() == 0

        # Import should succeed
        config.import_config()
        assert config.successful_import is True

    async def test_new_install_with_db_data(self, test_session, test_directory, async_client, test_channels_config,
                                            channel_factory):
        """
        Config file missing but DB has data.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create a channel in DB
        channel = channel_factory(name='Existing Channel')
        test_session.commit()

        # Remove config file to simulate missing config
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Existing Channel'


@pytest.mark.asyncio
class TestChannelsConfigUpgrade:
    """Tests for upgrade scenarios where config file exists."""

    async def test_upgrade_config_exists_with_data(self, test_session, test_directory, async_client,
                                                    test_channels_config, channel_factory):
        """
        Upgrade with existing config containing channel data.
        Should import and sync DB with config.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create a channel in DB
        channel = channel_factory(name='Config Channel')
        test_session.commit()

        # Dump to create config file
        config.dump_config()
        assert config_path.is_file()

        # Now import should succeed and preserve the channel
        config.import_config()
        assert config.successful_import is True

        # Channel should still exist
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Config Channel'

    async def test_upgrade_config_exists_empty_list(self, test_session, test_directory, async_client,
                                                     test_channels_config, channel_factory):
        """
        Config exists but has empty channels list.
        Should NOT delete existing DB channels (never delete on empty).
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create a channel in DB
        channel = channel_factory(name='Should Not Delete')
        test_session.commit()

        # Write empty config
        with open(config_path, 'w') as f:
            yaml.dump({'version': 0, 'channels': []}, f)

        # Reinitialize config to read the empty file
        config.initialize()

        # Import should succeed but NOT delete the channel
        config.import_config()
        assert config.successful_import is True

        # Channel should still exist (never delete on empty config)
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Should Not Delete'

    async def test_upgrade_config_missing_db_has_data(self, test_session, test_directory, async_client,
                                                       test_channels_config, channel_factory):
        """
        Config file missing but DB has channels.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create channels in DB
        channel1 = channel_factory(name='Channel One')
        channel2 = channel_factory(name='Channel Two')
        test_session.commit()

        # Remove config file
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        channels = test_session.query(Channel).all()
        assert len(channels) == 2
        channel_names = {c.name for c in channels}
        assert 'Channel One' in channel_names
        assert 'Channel Two' in channel_names


@pytest.mark.asyncio
class TestChannelsConfigEdgeCases:
    """Tests for edge cases in config import."""

    async def test_config_deletes_removed_items(self, test_session, test_directory, async_client, test_channels_config,
                                                 channel_factory):
        """
        Config removes a channel that exists in DB.
        Should delete the channel from DB.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create two channels
        channel1 = channel_factory(name='Keep This')
        channel2 = channel_factory(name='Delete This')
        test_session.commit()

        # Dump to config
        config.dump_config()

        # Modify config to remove one channel
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        config_data['channels'] = [c for c in config_data['channels'] if c['name'] == 'Keep This']

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Only one channel should remain
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'Keep This'

    async def test_config_adds_new_items(self, test_session, test_directory, async_client, test_channels_config):
        """
        Config has a new channel that doesn't exist in DB.
        Should create the channel in DB.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Ensure no channels in DB
        assert test_session.query(Channel).count() == 0

        # Write config with a new channel
        new_channel_dir = test_directory / 'videos' / 'New Channel'
        new_channel_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            'version': 0,
            'channels': [{
                'name': 'New Channel',
                'directory': str(new_channel_dir),
                'url': 'https://example.com/new',
                'download_frequency': 604800,
                'downloads': [],
            }]
        }

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Channel should be created
        channels = test_session.query(Channel).all()
        assert len(channels) == 1
        assert channels[0].name == 'New Channel'
        assert channels[0].url == 'https://example.com/new'

    async def test_config_updates_existing_items(self, test_session, test_directory, async_client, test_channels_config,
                                                  channel_factory):
        """
        Config updates an existing channel's URL.
        Should update the channel in DB.
        """
        config = get_channels_config()
        config_path = config.get_file()

        # Create a channel
        channel = channel_factory(name='Update Me', url='https://example.com/old')
        test_session.commit()

        # Dump to config
        config.dump_config()

        # Modify config to change URL
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        for c in config_data['channels']:
            if c['name'] == 'Update Me':
                c['url'] = 'https://example.com/new'

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Channel should be updated
        channel = test_session.query(Channel).filter_by(url='https://example.com/new').first()
        assert channel is not None
        assert channel.name == 'Update Me'
