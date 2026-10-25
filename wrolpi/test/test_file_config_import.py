"""A config that keeps no database rows imports by reading and validating its file, nothing more.  The Import button
and the startup imports read files and may write the database, so they run off the event loop."""
import asyncio
from http import HTTPStatus

import pytest

from modules.archive.lib import ArchiveDownloaderConfig
from modules.map.pins import MapPinsConfig
from modules.videos.lib import VideoDownloaderConfig
from wrolpi.common import ConfigFile, WROLPiConfig
from wrolpi import common
from wrolpi.downloader import DownloadCacheConfig
from wrolpi.errors import InvalidConfig
from wrolpi.events import Events


@pytest.fixture
def pins_config(async_client):
    config = MapPinsConfig()
    config.get_file().parent.mkdir(parents=True, exist_ok=True)
    return config


def on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


@pytest.mark.asyncio
async def test_import(pins_config):
    """A valid file is applied, and the import succeeds without the subclass saying so."""
    pins_config.get_file().write_text('version: 3\npins: [one, two]\n')

    pins_config.import_config()

    assert pins_config.successful_import is True
    assert pins_config._config['pins'] == ['one', 'two']


@pytest.mark.asyncio
async def test_import_reads_once(pins_config, monkeypatch):
    """The file is parsed once, not once to validate and again to apply."""
    pins_config.get_file().write_text('version: 3\npins: [one]\n')
    reads = []
    read = ConfigFile.read_config_file
    monkeypatch.setattr(MapPinsConfig, 'read_config_file', lambda self, *a: reads.append(1) or read(self, *a))

    pins_config.import_config()

    assert len(reads) == 1


@pytest.mark.asyncio
async def test_import_missing(pins_config):
    """A missing file is imported as the defaults; the first save creates it."""
    pins_config.import_config()

    assert pins_config.successful_import is True
    assert pins_config._config['pins'] == []


@pytest.mark.asyncio
async def test_import_empty(pins_config):
    """A 0-byte file is reported as empty, and never saved over."""
    pins_config.get_file().write_text('')

    with pytest.raises(InvalidConfig, match='empty'):
        pins_config.import_config()

    assert pins_config.successful_import is False


@pytest.mark.asyncio
async def test_import_invalid(pins_config, monkeypatch):
    """An invalid file raises, is never saved over, and the Import button reports it."""
    pins_config.get_file().write_text('- not\n- a mapping\n')
    sent = []
    monkeypatch.setattr(Events, 'send_config_import_failed', lambda message: sent.append(message))

    with pytest.raises(InvalidConfig):
        pins_config.import_config(send_events=True)

    assert pins_config.successful_import is False
    assert sent == ['Failed to import config/map_pins.yaml']
    with pytest.raises(RuntimeError, match='never successfully imported'):
        pins_config.save()


@pytest.mark.asyncio
async def test_startup_imports_off_event_loop(test_wrolpi_config, monkeypatch):
    """wrolpi.yaml and the downloader settings are imported in a thread at startup."""
    imported = []

    def record(self, *args, **kwargs):
        imported.append((self.file_name, on_event_loop()))
        self.successful_import = True

    for cls in (WROLPiConfig, VideoDownloaderConfig, ArchiveDownloaderConfig, DownloadCacheConfig):
        monkeypatch.setattr(cls, 'import_config', record)

    await common.import_file_configs()

    assert imported == [
        ('wrolpi.yaml', False),
        ('videos_downloader.yaml', False),
        ('archives_downloader.yaml', False),
        ('download_cache.yaml', False),
    ]


@pytest.mark.asyncio
async def test_startup_imports_wrol_mode(test_wrolpi_config, monkeypatch):
    """No other config is imported when wrolpi.yaml failed, or while WROL mode is enabled."""
    imported = []

    def record(self, *args, **kwargs):
        imported.append(self.file_name)

    for cls in (VideoDownloaderConfig, ArchiveDownloaderConfig, DownloadCacheConfig):
        monkeypatch.setattr(cls, 'import_config', record)

    def fail(self, *args, **kwargs):
        self.successful_import = False
        raise InvalidConfig('invalid')

    monkeypatch.setattr(WROLPiConfig, 'import_config', fail)
    await common.import_file_configs()
    assert imported == []

    def wrol_mode(self, *args, **kwargs):
        self.successful_import = True
        self._config['wrol_mode'] = True

    monkeypatch.setattr(WROLPiConfig, 'import_config', wrol_mode)
    await common.import_file_configs()
    assert imported == []


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method,body', [
    ('/api/config/import', 'import_forced', dict(file_name='tags.yaml')),
    ('/api/config/dump', 'dump_config', dict(file_name='tags.yaml')),
])
async def test_api_off_event_loop(async_client, test_tags_config, monkeypatch, path, method, body):
    """The Import and Save buttons read the database and the file in a thread, not on the event loop."""
    from wrolpi.tags import TagsConfig
    calls = []
    monkeypatch.setattr(TagsConfig, method, lambda self, *args, **kwargs: calls.append(on_event_loop()))

    request, response = await async_client.post(path, json=body)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert calls == [False]


@pytest.mark.asyncio
async def test_backup_import_off_event_loop(async_client, test_tags_config, monkeypatch):
    """Importing a backup runs in a thread, not on the event loop."""
    from wrolpi.tags import TagsConfig, get_tags_config
    config = get_tags_config()
    backup = config._get_backup_file('20260101')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text('version: 1\ntags: {}\n')
    calls = []
    monkeypatch.setattr(TagsConfig, 'import_backup', lambda self, *args, **kwargs: calls.append(on_event_loop()))

    body = dict(file_name='tags.yaml', backup_date='20260101', mode='merge')
    request, response = await async_client.post('/api/config/backup/import', json=body)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert calls == [False]
