"""
Tests for DownloadManagerConfig import/upgrade scenarios.

Tests cover:
1. Onboarding (new install) - no config file exists
2. Upgrade - config file exists with data
3. Edge cases - empty config, missing config with DB data
"""
import pytest
import yaml

from wrolpi.downloader import Download, get_download_manager_config


@pytest.mark.asyncio
class TestDownloadManagerConfigOnboarding:
    """Tests for new install scenarios where no config file exists."""

    async def test_new_install_no_db_data(self, test_session, test_directory, async_client, test_download_manager_config):
        """
        New install with empty DB and no config file.
        Should succeed with empty config.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Ensure no config file exists
        if config_path.is_file():
            config_path.unlink()

        # Ensure DB has no downloads
        assert test_session.query(Download).count() == 0

        # Import should succeed
        config.import_config()
        assert config.successful_import is True

    async def test_new_install_with_db_data(self, test_session, test_directory, async_client,
                                            test_download_manager_config):
        """
        Config file missing but DB has data.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Create a download in DB
        download = Download(
            url='https://example.com/video',
            downloader='video',
            frequency=604800,
            status='new',
        )
        test_session.add(download)
        test_session.commit()

        # Remove config file to simulate missing config
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/video'


@pytest.mark.asyncio
class TestDownloadManagerConfigUpgrade:
    """Tests for upgrade scenarios where config file exists."""

    async def test_upgrade_config_exists_with_data(self, test_session, test_directory, async_client,
                                                    test_download_manager_config):
        """
        Upgrade with existing config containing download data.
        Should import and sync DB with config.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Create a download in DB
        download = Download(
            url='https://example.com/download',
            downloader='video',
            frequency=604800,
            status='new',
        )
        test_session.add(download)
        test_session.commit()

        # Write config file directly (dump_config uses async background switches)
        config_data = {
            'version': 0,
            'skip_urls': [],
            'downloads': [{
                'url': 'https://example.com/download',
                'downloader': 'video',
                'destination': None,
                'frequency': 604800,
                'last_successful_download': None,
                'next_download': None,
                'status': 'new',
                'sub_downloader': None,
                'settings': None,
                'tag_names': [],
            }]
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        assert config_path.is_file()

        # Now import should succeed and preserve the download
        config.import_config()
        assert config.successful_import is True

        # Download should still exist
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/download'

    async def test_upgrade_config_exists_empty_list(self, test_session, test_directory, async_client,
                                                     test_download_manager_config):
        """
        Config exists but has empty downloads list.
        Should NOT delete existing DB downloads (never delete on empty).
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Create a download in DB
        download = Download(
            url='https://example.com/preserve',
            downloader='video',
            frequency=604800,
            status='new',
        )
        test_session.add(download)
        test_session.commit()

        # Write empty config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump({'version': 0, 'downloads': [], 'skip_urls': []}, f)

        # Reinitialize config to read the empty file
        config.initialize()

        # Import should succeed but NOT delete the download
        config.import_config()
        assert config.successful_import is True

        # Download should still exist (never delete on empty config)
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/preserve'

    async def test_upgrade_config_missing_db_has_data(self, test_session, test_directory, async_client,
                                                       test_download_manager_config):
        """
        Config file missing but DB has downloads.
        Import should succeed (nothing to import), DB data preserved.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Create downloads in DB
        for url in ['https://example.com/one', 'https://example.com/two']:
            download = Download(
                url=url,
                downloader='video',
                frequency=604800,
                status='new',
            )
            test_session.add(download)
        test_session.commit()

        # Remove config file
        if config_path.is_file():
            config_path.unlink()

        # Import should succeed (nothing to import)
        config.import_config()
        assert config.successful_import is True

        # DB data should be preserved
        downloads = test_session.query(Download).all()
        assert len(downloads) == 2
        download_urls = {d.url for d in downloads}
        assert 'https://example.com/one' in download_urls
        assert 'https://example.com/two' in download_urls


@pytest.mark.asyncio
class TestDownloadManagerConfigEdgeCases:
    """Tests for edge cases in config import."""

    async def test_config_deletes_removed_items(self, test_session, test_directory, async_client,
                                                 test_download_manager_config):
        """
        Config removes a download that exists in DB.
        Should delete the download from DB.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Create two downloads
        for url in ['https://example.com/keep', 'https://example.com/delete']:
            download = Download(
                url=url,
                downloader='video',
                frequency=604800,
                status='new',
            )
            test_session.add(download)
        test_session.commit()

        # Write config file directly with only one download (dump_config uses async background switches)
        config_data = {
            'version': 0,
            'skip_urls': [],
            'downloads': [{
                'url': 'https://example.com/keep',
                'downloader': 'video',
                'destination': None,
                'frequency': 604800,
                'last_successful_download': None,
                'next_download': None,
                'status': 'new',
                'sub_downloader': None,
                'settings': None,
                'tag_names': [],
            }]
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Only one download should remain
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/keep'

    async def test_config_adds_new_items(self, test_session, test_directory, async_client,
                                         test_download_manager_config):
        """
        Config has a new download that doesn't exist in DB.
        Should create the download in DB.
        """
        config = get_download_manager_config()
        config_path = config.get_file()

        # Ensure no downloads in DB
        assert test_session.query(Download).count() == 0

        # Write config with a new download
        config_data = {
            'version': 0,
            'skip_urls': [],
            'downloads': [{
                'url': 'https://example.com/new',
                'downloader': 'video',
                'destination': None,
                'frequency': 604800,
                'last_successful_download': None,
                'next_download': None,
                'status': 'new',
                'sub_downloader': None,
                'settings': None,
                'tag_names': [],
            }]
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Reinitialize and import
        config.initialize()
        config.import_config()
        assert config.successful_import is True

        # Download should be created
        downloads = test_session.query(Download).all()
        assert len(downloads) == 1
        assert downloads[0].url == 'https://example.com/new'
