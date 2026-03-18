"""Tests for the backup config import feature."""
import pathlib
from http import HTTPStatus

import pytest
import yaml

from wrolpi.common import get_media_directory


def _write_yaml(path: pathlib.Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wt') as fh:
        yaml.dump(data, fh)


def _make_backup(test_directory, file_name, backup_date, data):
    stem = pathlib.Path(file_name).stem
    suffix = pathlib.Path(file_name).suffix
    backup_dir = test_directory / 'config' / 'backup'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f'{stem}-{backup_date}{suffix}'
    _write_yaml(backup_file, data)
    return backup_file


class TestGetBackupDates:

    def test_get_backup_dates(self, test_directory, test_tags_config):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        # No backup directory yet
        assert config.get_backup_dates() == []

        # Create some backups
        backup_dir = test_directory / 'config' / 'backup'
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / 'tags-20260101.yaml').write_text('tags: {}\nversion: 1')
        (backup_dir / 'tags-20260305.yaml').write_text('tags: {}\nversion: 2')
        (backup_dir / 'tags-20260201.yaml').write_text('tags: {}\nversion: 3')
        # Other config backup should be ignored
        (backup_dir / 'channels-20260101.yaml').write_text('channels: []\nversion: 1')

        dates = config.get_backup_dates()
        assert dates == ['20260305', '20260201', '20260101']

    def test_get_backup_dates_empty_dir(self, test_directory, test_tags_config):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()
        (test_directory / 'config' / 'backup').mkdir(parents=True, exist_ok=True)
        assert config.get_backup_dates() == []


class TestTagsBackupImport:

    def test_preview_merge(self, test_directory, test_tags_config):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        # Write current config
        current = dict(
            tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
            tag_files=[['news', 'videos/ep1.mp4', '2026-01-01T00:00:00']],
            tag_zims=[['news', 'wiki.zim', '/A/Test', '2026-01-01T00:00:00']],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        # Write backup with extra items
        backup = dict(
            tags={'news': {'color': '#0000FF'}, 'survival': {'color': '#AABB00'}},
            tag_files=[
                ['news', 'videos/ep1.mp4', '2026-01-01T00:00:00'],
                ['survival', 'videos/ep2.mp4', '2026-02-01T00:00:00'],
            ],
            tag_zims=[
                ['news', 'wiki.zim', '/A/Test', '2026-01-01T00:00:00'],
                ['survival', 'wiki.zim', '/A/Other', '2026-02-01T00:00:00'],
            ],
            version=1,
        )
        _make_backup(test_directory, 'tags.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'merge')
        assert preview['mode'] == 'merge'
        assert len(preview['add']) == 3  # tag:survival, tag_file:survival/ep2, tag_zim:survival/Other
        assert preview['remove'] == []
        assert preview['unchanged'] == 3  # tag:news, tag_file:news/ep1, tag_zim:news/wiki/Test

        # Verify specific items
        add_types = {(i['type'], i.get('name', i.get('tag', ''))) for i in preview['add']}
        assert ('tag', 'survival') in add_types
        assert ('tag_file', 'survival') in add_types
        assert ('tag_zim', 'survival') in add_types

    def test_preview_overwrite(self, test_directory, test_tags_config):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        current = dict(
            tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
            tag_files=[],
            tag_zims=[],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            tags={'news': {'color': '#0000FF'}},
            tag_files=[],
            tag_zims=[],
            version=1,
        )
        _make_backup(test_directory, 'tags.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'overwrite')
        assert preview['mode'] == 'overwrite'
        assert preview['add'] == []
        assert len(preview['remove']) == 1  # tech tag removed
        assert preview['remove'][0] == {'type': 'tag', 'name': 'tech'}
        assert preview['unchanged'] == 1  # news

    @pytest.mark.asyncio
    async def test_import_merge(self, test_directory, test_tags_config, test_session, async_client):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        # Write current config with one tag
        current = dict(tags={'news': {'color': '#FF0000'}}, tag_files=[], tag_zims=[], version=1)
        _write_yaml(config.get_file(), current)

        # Write backup with two tags
        backup = dict(
            tags={'news': {'color': '#0000FF'}, 'survival': {'color': '#AABB00'}},
            tag_files=[], tag_zims=[], version=1,
        )
        _make_backup(test_directory, 'tags.yaml', '20260301', backup)

        config.import_backup('20260301', 'merge')

        # Read the merged config file - should have both tags
        merged = config.read_config_file()
        assert 'news' in merged['tags']
        assert 'survival' in merged['tags']
        # Merge doesn't change existing tag colors
        assert merged['tags']['news']['color'] == '#FF0000'

    @pytest.mark.asyncio
    async def test_import_overwrite(self, test_directory, test_tags_config, test_session, async_client):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        # Write current config with two tags
        current = dict(
            tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
            tag_files=[], tag_zims=[], version=1,
        )
        _write_yaml(config.get_file(), current)

        # Write backup with only one tag
        backup = dict(tags={'news': {'color': '#0000FF'}}, tag_files=[], tag_zims=[], version=1)
        _make_backup(test_directory, 'tags.yaml', '20260301', backup)

        config.import_backup('20260301', 'overwrite')

        # Config file should be exact copy of backup
        overwritten = config.read_config_file()
        assert list(overwritten['tags'].keys()) == ['news']
        assert overwritten['tags']['news']['color'] == '#0000FF'


class TestDownloadsBackupImport:

    def test_preview_overwrite(self, test_directory, test_download_manager_config):
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        current = dict(
            downloads=[
                dict(url='http://existing.com/feed', downloader='rss', frequency=86400, status='complete'),
                dict(url='http://other.com/feed', downloader='video_channel', frequency=2592000, status='new'),
            ],
            skip_urls=['http://skip.com'],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            downloads=[
                dict(url='http://existing.com/feed', downloader='rss', frequency=86400, status='complete'),
            ],
            skip_urls=[],
            version=1,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'overwrite')
        assert preview['mode'] == 'overwrite'
        assert len(preview['remove']) == 1
        assert preview['remove'][0]['url'] == 'http://other.com/feed'
        assert preview['unchanged'] == 1
        assert preview['add'] == []

    def test_import_overwrite(self, test_directory, test_download_manager_config, async_client):
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        _dl = lambda url, freq=None, **kw: dict(
            url=url, downloader='rss', frequency=freq, status='new',
            destination=None, sub_downloader=None, settings=None,
            tag_names=None, last_successful_download=None, next_download=None, **kw,
        )

        current = dict(
            downloads=[_dl('http://existing.com/feed', 86400), _dl('http://other.com/feed', 2592000)],
            skip_urls=['http://skip.com'],
            version=5,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            downloads=[_dl('http://existing.com/feed', 86400)],
            skip_urls=[],
            version=3,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260301', backup)

        config.import_backup('20260301', 'overwrite')

        overwritten = config.read_config_file()
        assert len(overwritten['downloads']) == 1
        assert overwritten['downloads'][0]['url'] == 'http://existing.com/feed'
        assert overwritten['skip_urls'] == []

    def test_preview_merge_skips_once_downloads(self, test_directory, test_download_manager_config):
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        current = dict(downloads=[], skip_urls=[], version=1)
        _write_yaml(config.get_file(), current)

        backup = dict(
            downloads=[
                dict(url='http://example.com/feed', downloader='rss', frequency=86400, status='complete'),
                dict(url='http://example.com/once', downloader='archive', status='complete'),
            ],
            skip_urls=[], version=1,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'merge')
        # Only the recurring download should show
        assert len(preview['add']) == 1
        assert preview['add'][0]['url'] == 'http://example.com/feed'

    @pytest.mark.asyncio
    async def test_import_merge(self, test_directory, test_download_manager_config, async_client):
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        _dl = lambda url, freq=None, **kw: dict(
            url=url, downloader='rss', frequency=freq, status='new',
            destination=None, sub_downloader=None, settings=None,
            tag_names=None, last_successful_download=None, next_download=None, **kw,
        )

        current = dict(downloads=[_dl('http://existing.com', 86400)], skip_urls=[], version=1)
        _write_yaml(config.get_file(), current)

        backup = dict(
            downloads=[
                _dl('http://new.com/feed', 86400),
                _dl('http://once.com'),
            ],
            skip_urls=['http://skip.com'], version=1,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260301', backup)

        config.import_backup('20260301', 'merge')

        merged = config.read_config_file()
        urls = [dl['url'] for dl in merged['downloads']]
        assert 'http://existing.com' in urls
        assert 'http://new.com/feed' in urls
        # Once-download should not be merged
        assert 'http://once.com' not in urls
        assert 'http://skip.com' in merged['skip_urls']


class TestChannelsBackupImport:

    def test_preview_overwrite(self, test_directory, test_channels_config):
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[
                dict(name='Channel A', directory='videos/channel_a', download_frequency=86400),
                dict(name='Channel B', directory='videos/channel_b', download_frequency=86400),
            ],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            channels=[dict(name='Channel A', directory='videos/channel_a', download_frequency=86400)],
            version=1,
        )
        _make_backup(test_directory, 'channels.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'overwrite')
        assert preview['mode'] == 'overwrite'
        assert len(preview['remove']) == 1
        assert preview['remove'][0]['directory'] == 'videos/channel_b'
        assert preview['unchanged'] == 1
        assert preview['add'] == []

    def test_import_overwrite(self, test_directory, test_channels_config, async_client, test_download_manager_config):
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[
                dict(name='Channel A', directory='videos/channel_a', download_frequency=86400),
                dict(name='Channel B', directory='videos/channel_b', download_frequency=86400),
            ],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            channels=[dict(name='Channel A', directory='videos/channel_a', download_frequency=86400)],
            version=1,
        )
        _make_backup(test_directory, 'channels.yaml', '20260301', backup)

        config.import_backup('20260301', 'overwrite')

        overwritten = config.read_config_file()
        assert len(overwritten['channels']) == 1
        assert overwritten['channels'][0]['directory'] == 'videos/channel_a'

    def test_preview_merge(self, test_directory, test_channels_config):
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[dict(name='Channel A', directory='videos/channel_a', download_frequency=86400)],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            channels=[
                dict(name='Channel A', directory='videos/channel_a', download_frequency=86400),
                dict(name='Channel B', directory='videos/channel_b', download_frequency=86400),
            ],
            version=1,
        )
        _make_backup(test_directory, 'channels.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'merge')
        assert len(preview['add']) == 1
        assert preview['add'][0]['directory'] == 'videos/channel_b'
        assert preview['unchanged'] == 1

    @pytest.mark.asyncio
    async def test_import_merge(self, test_directory, test_channels_config, async_client, test_download_manager_config):
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[dict(name='Channel A', directory='videos/channel_a', download_frequency=86400)],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            channels=[
                dict(name='Channel B', directory='videos/channel_b', download_frequency=86400),
            ],
            version=1,
        )
        _make_backup(test_directory, 'channels.yaml', '20260301', backup)

        config.import_backup('20260301', 'merge')

        merged = config.read_config_file()
        dirs = [ch['directory'] for ch in merged['channels']]
        assert 'videos/channel_a' in dirs
        assert 'videos/channel_b' in dirs


class TestDomainsBackupImport:

    def test_preview_merge(self, test_directory):
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[dict(name='example.com', kind='domain')],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            collections=[
                dict(name='example.com', kind='domain'),
                dict(name='newsite.org', kind='domain'),
            ],
            version=1,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'merge')
        assert preview['mode'] == 'merge'
        assert len(preview['add']) == 1
        assert preview['add'][0]['name'] == 'newsite.org'
        assert preview['remove'] == []
        assert preview['unchanged'] == 1

    @pytest.mark.asyncio
    async def test_import_merge(self, test_directory, test_session, async_client):
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[dict(name='example.com', kind='domain')],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            collections=[
                dict(name='example.com', kind='domain'),
                dict(name='newsite.org', kind='domain'),
            ],
            version=1,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260301', backup)

        config.import_backup('20260301', 'merge')

        merged = config.read_config_file()
        names = [c['name'] for c in merged['collections']]
        assert 'example.com' in names
        assert 'newsite.org' in names

    @pytest.mark.asyncio
    async def test_import_overwrite(self, test_directory, test_session, async_client):
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[
                dict(name='example.com', kind='domain'),
                dict(name='test.org', kind='domain'),
            ],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            collections=[dict(name='example.com', kind='domain')],
            version=1,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260301', backup)

        config.import_backup('20260301', 'overwrite')

        overwritten = config.read_config_file()
        assert len(overwritten['collections']) == 1
        assert overwritten['collections'][0]['name'] == 'example.com'

    def test_preview_overwrite(self, test_directory):
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[
                dict(name='example.com', kind='domain'),
                dict(name='test.org', kind='domain'),
            ],
            version=1,
        )
        config_file = config.get_file()
        _write_yaml(config_file, current)

        backup = dict(
            collections=[dict(name='example.com', kind='domain')],
            version=1,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'overwrite')
        assert len(preview['remove']) == 1
        assert preview['remove'][0]['name'] == 'test.org'
        assert preview['unchanged'] == 1


class TestInventoriesBackupImport:

    def test_preview_overwrite(self, test_directory):
        from modules.inventory.common import get_inventories_config
        config = get_inventories_config()

        current = dict(
            inventories=[
                dict(name='Food', created_at='2026-01-01', deleted_at=None, items=[]),
                dict(name='Tools', created_at='2026-01-01', deleted_at=None, items=[]),
            ],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            inventories=[dict(name='Food', created_at='2026-01-01', deleted_at=None, items=[])],
            version=1,
        )
        _make_backup(get_media_directory(), 'inventories.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'overwrite')
        assert preview['mode'] == 'overwrite'
        assert len(preview['remove']) == 1
        assert preview['remove'][0]['name'] == 'Tools'
        assert preview['unchanged'] == 1
        assert preview['add'] == []

    @pytest.mark.asyncio
    async def test_import_merge(self, test_directory, test_session, async_client):
        from modules.inventory.common import get_inventories_config
        config = get_inventories_config()

        current = dict(
            inventories=[dict(id=1, name='Food', created_at='2026-01-01', deleted_at=None, items=[])],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            inventories=[
                dict(id=1, name='Food', created_at='2026-01-01', deleted_at=None, items=[]),
                dict(id=2, name='Medical', created_at='2026-01-01', deleted_at=None, items=[]),
            ],
            version=1,
        )
        _make_backup(get_media_directory(), 'inventories.yaml', '20260301', backup)

        config.import_backup('20260301', 'merge')

        merged = config.read_config_file()
        names = [inv['name'] for inv in merged['inventories']]
        assert 'Food' in names
        assert 'Medical' in names

    @pytest.mark.asyncio
    async def test_import_overwrite(self, test_directory, test_session, async_client):
        from modules.inventory.common import get_inventories_config
        config = get_inventories_config()

        current = dict(
            inventories=[
                dict(id=1, name='Food', created_at='2026-01-01', deleted_at=None, items=[]),
                dict(id=2, name='Tools', created_at='2026-01-01', deleted_at=None, items=[]),
            ],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            inventories=[dict(id=1, name='Food', created_at='2026-01-01', deleted_at=None, items=[])],
            version=1,
        )
        _make_backup(get_media_directory(), 'inventories.yaml', '20260301', backup)

        config.import_backup('20260301', 'overwrite')

        overwritten = config.read_config_file()
        assert len(overwritten['inventories']) == 1
        assert overwritten['inventories'][0]['name'] == 'Food'

    def test_preview_merge(self, test_directory):
        from modules.inventory.common import get_inventories_config
        config = get_inventories_config()

        current = dict(
            inventories=[dict(name='Food', created_at='2026-01-01', deleted_at=None, items=[])],
            version=1,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            inventories=[
                dict(name='Food', created_at='2026-01-01', deleted_at=None, items=[]),
                dict(name='Medical', created_at='2026-01-01', deleted_at=None, items=[]),
            ],
            version=1,
        )
        _make_backup(get_media_directory(), 'inventories.yaml', '20260301', backup)

        preview = config.preview_backup_import('20260301', 'merge')
        assert len(preview['add']) == 1
        assert preview['add'][0]['name'] == 'Medical'
        assert preview['unchanged'] == 1


class TestImportBackupPreservesCurrentConfig:
    """Restoring a backup should preserve the current config as today's backup so the user can undo the restore."""

    @pytest.mark.asyncio
    async def test_import_preserves_current_config(self, test_directory, test_tags_config, test_session, async_client):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        current = dict(
            tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
            tag_files=[], tag_zims=[], version=5,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(tags={'news': {'color': '#0000FF'}}, tag_files=[], tag_zims=[], version=3)
        _make_backup(test_directory, 'tags.yaml', '20260101', backup)

        todays_backup = config._get_backup_filename()
        assert not todays_backup.is_file()

        # Overwrite should create today's backup with the original config.
        config.import_backup('20260101', 'overwrite')
        assert todays_backup.is_file()
        preserved = yaml.safe_load(todays_backup.read_text())
        assert 'tech' in preserved['tags']
        assert preserved['version'] == 5

        # A second import should not clobber today's backup.
        backup2 = dict(tags={'survival': {'color': '#AABB00'}}, tag_files=[], tag_zims=[], version=1)
        _make_backup(test_directory, 'tags.yaml', '20260102', backup2)
        config.import_backup('20260102', 'overwrite')
        preserved = yaml.safe_load(todays_backup.read_text())
        assert 'tech' in preserved['tags'], 'Today\'s backup should still contain the original config'
        assert preserved['version'] == 5


class TestConfigStatusIncludesBackupInfo:

    def test_db_config_has_backup_info(self, test_directory, test_tags_config):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()
        status = config.config_status()
        assert status['has_backup_import'] is True
        assert 'backup_dates' not in status

    def test_non_db_config_no_backup_info(self, test_directory, test_wrolpi_config):
        from wrolpi.common import get_wrolpi_config
        config = get_wrolpi_config()
        status = config.config_status()
        assert status['has_backup_import'] is False
        assert 'backup_dates' not in status


class TestNotImplementedForNonDBConfigs:

    def test_preview_raises(self, test_directory, test_wrolpi_config):
        from wrolpi.common import get_wrolpi_config
        config = get_wrolpi_config()
        with pytest.raises(NotImplementedError):
            config.preview_backup_import('20260301', 'merge')

    def test_import_raises(self, test_directory, test_wrolpi_config):
        from wrolpi.common import get_wrolpi_config
        config = get_wrolpi_config()
        with pytest.raises(NotImplementedError):
            config.import_backup('20260301', 'merge')


@pytest.mark.asyncio
class TestBackupAPIEndpoints:

    async def test_get_backups(self, async_client, test_directory, test_tags_config):
        backup_dir = test_directory / 'config' / 'backup'
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / 'tags-20260301.yaml').write_text('tags: {}\nversion: 1')

        request, response = await async_client.get('/api/config/backups?file_name=tags.yaml')
        assert response.status_code == HTTPStatus.OK
        assert '20260301' in response.json['dates']

    async def test_preview_endpoint(self, async_client, test_directory, test_tags_config):
        # Write current config
        from wrolpi.tags import get_tags_config
        config = get_tags_config()
        _write_yaml(config.get_file(), dict(tags={'news': {'color': '#FF0000'}}, tag_files=[], tag_zims=[], version=1))

        # Write backup
        _make_backup(test_directory, 'tags.yaml', '20260301',
                     dict(tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
                          tag_files=[], tag_zims=[], version=1))

        body = dict(file_name='tags.yaml', backup_date='20260301', mode='merge')
        request, response = await async_client.post('/api/config/backup/preview', json=body)
        assert response.status_code == HTTPStatus.OK
        assert 'preview' in response.json
        assert len(response.json['preview']['add']) == 1

    async def test_import_endpoint(self, async_client, test_directory, test_tags_config, test_session):
        from wrolpi.tags import get_tags_config
        config = get_tags_config()
        _write_yaml(config.get_file(), dict(tags={'news': {'color': '#FF0000'}}, tag_files=[], tag_zims=[], version=1))
        _make_backup(test_directory, 'tags.yaml', '20260301',
                     dict(tags={'news': {'color': '#FF0000'}, 'tech': {'color': '#00FF00'}},
                          tag_files=[], tag_zims=[], version=1))

        body = dict(file_name='tags.yaml', backup_date='20260301', mode='merge')
        request, response = await async_client.post('/api/config/backup/import', json=body)
        assert response.status_code == HTTPStatus.NO_CONTENT

    async def test_invalid_mode(self, async_client, test_directory, test_tags_config):
        body = dict(file_name='tags.yaml', backup_date='20260301', mode='invalid')
        request, response = await async_client.post('/api/config/backup/preview', json=body)
        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_non_db_config_rejected(self, async_client, test_directory, test_wrolpi_config):
        body = dict(file_name='wrolpi.yaml', backup_date='20260301', mode='merge')
        request, response = await async_client.post('/api/config/backup/preview', json=body)
        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_missing_backup_rejected(self, async_client, test_directory, test_tags_config):
        body = dict(file_name='tags.yaml', backup_date='99990101', mode='merge')
        request, response = await async_client.post('/api/config/backup/preview', json=body)
        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_config_status_includes_backup_fields(self, async_client, test_directory, test_tags_config):
        request, response = await async_client.get('/api/config')
        assert response.status_code == HTTPStatus.OK
        tags_status = response.json['configs']['tags.yaml']
        assert 'has_backup_import' in tags_status
        assert 'backup_dates' not in tags_status


class TestPreviewWithRealisticData:
    """Test preview logic with data modeled after real production backup files."""

    def test_tags_merge_old_backup_no_tag_files(self, test_directory, test_tags_config):
        """Old backup has same tags but no tag_files/tag_zims. Merge should show no changes."""
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        tag_defs = {'News': {'color': '#FF0000'}, 'Tech': {'color': '#00FF00'}, 'Medical': {'color': '#0000FF'}}

        current = dict(
            tags=tag_defs,
            tag_files=[['News', 'file1.mp4', '2026-01-01T00:00:00'], ['Tech', 'file2.mp4', '2026-01-01T00:00:00']],
            tag_zims=[['News', 'wiki.zim', 'home', '2026-01-01T00:00:00']],
            version=41,
        )
        _write_yaml(config.get_file(), current)

        # Old backup: same tags, empty tag_files/tag_zims (like tags-20251120)
        backup = dict(tags=tag_defs, tag_files=[], tag_zims=[], version=1)
        _make_backup(test_directory, 'tags.yaml', '20251120', backup)

        preview = config.preview_backup_import('20251120', 'merge')
        assert preview['mode'] == 'merge'
        assert preview['add'] == []  # Backup has nothing new
        assert preview['remove'] == []  # Merge never removes
        assert preview['unchanged'] == 3  # 3 tags match

    def test_tags_overwrite_old_backup_removes_tag_files(self, test_directory, test_tags_config):
        """Overwrite with old backup should remove tag_files and tag_zims that only exist in current."""
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        tag_defs = {'News': {'color': '#FF0000'}, 'Tech': {'color': '#00FF00'}}
        current = dict(
            tags=tag_defs,
            tag_files=[['News', 'file1.mp4', '2026-01-01T00:00:00'], ['Tech', 'file2.mp4', '2026-01-01T00:00:00']],
            tag_zims=[['News', 'wiki.zim', 'home', '2026-01-01T00:00:00']],
            version=41,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(tags=tag_defs, tag_files=[], tag_zims=[], version=1)
        _make_backup(test_directory, 'tags.yaml', '20251120', backup)

        preview = config.preview_backup_import('20251120', 'overwrite')
        assert preview['add'] == []
        assert len(preview['remove']) == 3  # 2 tag_files + 1 tag_zim
        assert preview['unchanged'] == 2  # 2 tags match

        remove_types = [r['type'] for r in preview['remove']]
        assert remove_types.count('tag_file') == 2
        assert remove_types.count('tag_zim') == 1

    def test_tags_identical_backup(self, test_directory, test_tags_config):
        """Recent identical backup should show no changes in either mode."""
        from wrolpi.tags import get_tags_config
        config = get_tags_config()

        data = dict(
            tags={'News': {'color': '#FF0000'}},
            tag_files=[['News', 'file1.mp4', '2026-01-01T00:00:00']],
            tag_zims=[['News', 'wiki.zim', 'home', '2026-01-01T00:00:00']],
            version=41,
        )
        _write_yaml(config.get_file(), data)
        _make_backup(test_directory, 'tags.yaml', '20260307', data)

        for mode in ('merge', 'overwrite'):
            preview = config.preview_backup_import('20260307', mode)
            assert preview['add'] == [], f'{mode}: unexpected adds'
            assert preview['remove'] == [], f'{mode}: unexpected removes'
            assert preview['unchanged'] == 3, f'{mode}: wrong unchanged count'

    def test_domains_overwrite_removes_new_domain(self, test_directory):
        """Backup missing a domain that was recently added. Overwrite shows it as removal."""
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[
                dict(name='crosswalk.com', kind='domain', directory='archive/crosswalk.com'),
                dict(name='wrolpi.org', kind='domain', directory='archive/wrolpi.org'),
                dict(name='zerohedge.com', kind='domain', directory='archive/zerohedge.com'),
            ],
            version=32,
        )
        _write_yaml(config.get_file(), current)

        # Backup from before zerohedge was added
        backup = dict(
            collections=[
                dict(name='crosswalk.com', kind='domain', directory='archive/crosswalk.com'),
                dict(name='wrolpi.org', kind='domain', directory='archive/wrolpi.org'),
            ],
            version=31,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260218', backup)

        preview = config.preview_backup_import('20260218', 'overwrite')
        assert preview['add'] == []
        assert len(preview['remove']) == 1
        assert preview['remove'][0]['name'] == 'zerohedge.com'
        assert preview['unchanged'] == 2

    def test_domains_merge_no_changes(self, test_directory):
        """Merge with backup that is a subset of current should show no changes."""
        from modules.archive.lib import get_domains_config
        config = get_domains_config()

        current = dict(
            collections=[
                dict(name='crosswalk.com', kind='domain', directory='archive/crosswalk.com'),
                dict(name='wrolpi.org', kind='domain', directory='archive/wrolpi.org'),
                dict(name='zerohedge.com', kind='domain', directory='archive/zerohedge.com'),
            ],
            version=32,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            collections=[
                dict(name='crosswalk.com', kind='domain', directory='archive/crosswalk.com'),
                dict(name='wrolpi.org', kind='domain', directory='archive/wrolpi.org'),
            ],
            version=31,
        )
        _make_backup(get_media_directory(), 'domains.yaml', '20260218', backup)

        preview = config.preview_backup_import('20260218', 'merge')
        assert preview['add'] == []
        assert preview['remove'] == []
        assert preview['unchanged'] == 2

    def test_download_manager_merge_skips_once_downloads(self, test_directory, test_download_manager_config):
        """Merge mode skips once-downloads (no frequency). Like backup 20260308 vs current."""
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        current = dict(
            downloads=[
                dict(url='https://example.com', downloader='video', frequency=None, status='failed'),
                dict(url='https://youtube.com/channel/ABC', downloader='video_channel', frequency=2592000,
                     status='complete'),
            ],
            skip_urls=['https://skip1.com'],
            version=260,
        )
        _write_yaml(config.get_file(), current)

        # Backup has same 2 + an extra once-download
        backup = dict(
            downloads=[
                dict(url='https://example.com', downloader='video', frequency=None, status='failed'),
                dict(url='https://youtube.com/channel/ABC', downloader='video_channel', frequency=2592000,
                     status='complete'),
                dict(url='https://youtube.com/watch?v=TEST', downloader='video', frequency=None, status='new'),
            ],
            skip_urls=['https://skip1.com'],
            version=259,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260308', backup)

        preview = config.preview_backup_import('20260308', 'merge')
        assert preview['add'] == []  # Once-download skipped in merge
        assert preview['remove'] == []
        # Only the recurring download is counted (once-downloads are skipped entirely)
        assert preview['unchanged'] == 1

    def test_download_manager_overwrite_shows_extra_download(self, test_directory, test_download_manager_config):
        """Overwrite mode includes once-downloads. Extra backup download should appear as add."""
        from wrolpi.downloader import get_download_manager_config
        config = get_download_manager_config()

        current = dict(
            downloads=[
                dict(url='https://example.com', downloader='video', frequency=None, status='failed'),
                dict(url='https://youtube.com/channel/ABC', downloader='video_channel', frequency=2592000,
                     status='complete'),
            ],
            skip_urls=[],
            version=260,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            downloads=[
                dict(url='https://example.com', downloader='video', frequency=None, status='failed'),
                dict(url='https://youtube.com/channel/ABC', downloader='video_channel', frequency=2592000,
                     status='complete'),
                dict(url='https://youtube.com/watch?v=TEST', downloader='video', frequency=None, status='new'),
            ],
            skip_urls=[],
            version=259,
        )
        _make_backup(test_directory, 'download_manager.yaml', '20260308', backup)

        preview = config.preview_backup_import('20260308', 'overwrite')
        assert len(preview['add']) == 1
        assert preview['add'][0]['url'] == 'https://youtube.com/watch?v=TEST'
        assert preview['remove'] == []
        assert preview['unchanged'] == 2

    def test_channels_case_sensitive_directory(self, test_directory, test_channels_config):
        """Directory comparison is case-sensitive. 'videos/wrolpi' != 'videos/WROLPi'."""
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[
                dict(name='WROLPi', directory='videos/WROLPi', download_frequency=2592000),
                dict(name="Maker's Muse", directory="videos/Maker's Muse"),
            ],
            version=42,
        )
        _write_yaml(config.get_file(), current)

        # Old backup used lowercase directory
        backup = dict(
            channels=[dict(name='WROLPi', directory='videos/wrolpi', download_frequency=604800)],
            version=1,
        )
        _make_backup(test_directory, 'channels.yaml', '20251120', backup)

        preview = config.preview_backup_import('20251120', 'merge')
        # Case difference means backup channel is treated as new
        assert len(preview['add']) == 1
        assert preview['add'][0]['directory'] == 'videos/wrolpi'
        assert preview['unchanged'] == 0

        preview = config.preview_backup_import('20251120', 'overwrite')
        assert len(preview['add']) == 1  # backup's videos/wrolpi
        assert len(preview['remove']) == 2  # current's videos/WROLPi + Maker's Muse
        assert preview['unchanged'] == 0

    def test_channels_merge_backup_is_subset(self, test_directory, test_channels_config):
        """When backup channels are already in current, merge shows no changes."""
        from modules.videos.lib import get_channels_config
        config = get_channels_config()

        current = dict(
            channels=[
                dict(name='WROLPi', directory='videos/WROLPi'),
                dict(name='Talking Sasquach', directory='videos/Talking Sasquach'),
                dict(name="Maker's Muse", directory="videos/Maker's Muse"),
            ],
            version=42,
        )
        _write_yaml(config.get_file(), current)

        backup = dict(
            channels=[
                dict(name='WROLPi', directory='videos/WROLPi'),
                dict(name='Talking Sasquach', directory='videos/Talking Sasquach'),
            ],
            version=41,
        )
        _make_backup(test_directory, 'channels.yaml', '20260222', backup)

        preview = config.preview_backup_import('20260222', 'merge')
        assert preview['add'] == []
        assert preview['remove'] == []
        assert preview['unchanged'] == 2


class TestWriteConfigData:

    def test_rejects_python_objects(self, test_directory, test_tags_config):
        """write_config_data raises ValueError when config contains Python objects (e.g. Enums)."""
        from enum import Enum
        from wrolpi.tags import get_tags_config

        class Frequency(int, Enum):
            weekly = 604800

        config = get_tags_config()
        config_file = config.get_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValueError, match='Python object'):
            config.write_config_data({'tags': [{'frequency': Frequency.weekly}]}, config_file)

    def test_converts_decimal_to_str(self, test_directory, test_tags_config):
        """write_config_data converts Decimal values to strings."""
        from decimal import Decimal
        from wrolpi.tags import get_tags_config

        config = get_tags_config()
        config_file = config.get_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)

        config.write_config_data({'count': Decimal('22.3')}, config_file)

        data = config.read_config_file(config_file)
        assert data['count'] == '22.3'
        assert isinstance(data['count'], str)
