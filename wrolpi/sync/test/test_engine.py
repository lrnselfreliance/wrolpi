import os
import pathlib
from collections import namedtuple

import pytest
import yaml

from wrolpi.common import get_wrolpi_config, set_test_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import InvalidConfig
from wrolpi.files.models import FileGroup
from wrolpi.sync import lib
from wrolpi.sync.config import get_sync_config
from wrolpi.sync.conftest import manifest_page
from wrolpi.sync.status import get_sync_status, update_sync_status
from wrolpi.tags import get_tags_config, Tag, TagFile


@pytest.mark.parametrize('path, allowed', [
    ('videos/channel/video.mp4', True),
    ('a.txt', True),
    ('../escape.txt', False),
    ('videos/../../escape.txt', False),
    ('/etc/passwd', False),
    ('videos/.hidden/video.mp4', False),
    ('.hidden.txt', False),
    ('config/wrolpi.db', False),
    ('config/tags.yaml', False),
    ('tags/one/video.mp4', False),
    # A drive that ignores case (exFAT, NTFS, macOS) would write these into the real config and tags folders.
    ('Config/wrolpi.db', False),
    ('CONFIG/tags.yaml', False),
    ('Tags/one/video.mp4', False),
    ('videos\\video.mp4', False),
    ('', False),
])
def test_resolve_destination(test_directory, path, allowed):
    destination = lib.resolve_destination(test_directory, path)
    if allowed:
        assert destination == test_directory / path
    else:
        assert destination is None


def test_resolve_destination_refuses_symlinks(test_directory):
    """A sync never writes through a symlink; it could point outside the media directory."""
    outside = test_directory / 'outside'
    outside.mkdir()
    (test_directory / 'videos').symlink_to(outside)
    assert lib.resolve_destination(test_directory, 'videos/video.mp4') is None

    (test_directory / 'docs').mkdir()
    (test_directory / 'docs/link.txt').symlink_to(outside / 'target.txt')
    assert lib.resolve_destination(test_directory, 'docs/link.txt') is None


def test_needs_download(test_directory):
    path = test_directory / 'a.txt'
    file = lib.ManifestFile('a.txt', 5, 1_700_000_000.0)
    assert lib.needs_download(path, file), 'a missing file is downloaded'

    path.write_text('12345')
    os.utime(path, (file.mtime, file.mtime))
    assert not lib.needs_download(path, file)

    os.utime(path, (file.mtime + 1.5, file.mtime + 1.5))
    assert not lib.needs_download(path, file), 'within the 2 second tolerance of exFAT'

    os.utime(path, (file.mtime + 3, file.mtime + 3))
    assert lib.needs_download(path, file), 'a different modification time is downloaded'

    os.utime(path, (file.mtime, file.mtime))
    path.write_text('1234')
    os.utime(path, (file.mtime, file.mtime))
    assert lib.needs_download(path, file), 'a different size is downloaded'


Primary = namedtuple('Primary', 'directory url state')


@pytest.fixture
def primary(test_directory, secondary_directory, primary_media_server) -> Primary:
    """A primary whose media is `test_directory`, served like Caddy."""
    url, state = primary_media_server(test_directory)
    return Primary(test_directory, url, state)


def write_primary_file(primary: Primary, path: str, content: bytes, mtime: float = 1_700_000_000.0) \
        -> lib.ManifestFile:
    file = primary.directory / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    os.utime(file, (mtime, mtime))
    return lib.ManifestFile(path, len(content), mtime)


@pytest.mark.asyncio
async def test_download_file(primary, secondary_directory):
    """A downloaded file has the primary's bytes and modification time, and no partial is left."""
    file = write_primary_file(primary, 'videos/channel/video name.mp4', b'video bytes' * 1000)
    destination = secondary_directory / file.path

    async with lib.PrimaryClient(primary.url) as client:
        received = await lib.download_file(client, file, destination)

    assert received == file.size
    assert destination.read_bytes() == (primary.directory / file.path).read_bytes()
    assert destination.stat().st_mtime == file.mtime
    assert not lib.partial_path(destination).exists()
    assert not lib.needs_download(destination, file)


@pytest.mark.asyncio
async def test_download_file_resumes(primary, secondary_directory):
    """A partial left by an interrupted download is resumed with a Range request."""
    content = bytes(range(256)) * 400
    file = write_primary_file(primary, 'big.bin', content)
    destination = secondary_directory / file.path
    lib.partial_path(destination).write_bytes(content[:30_000])

    async with lib.PrimaryClient(primary.url) as client:
        received = await lib.download_file(client, file, destination)

    assert received == len(content) - 30_000
    assert ('/media/big.bin', 'bytes=30000-') in primary.state['requests']
    assert destination.read_bytes() == content


@pytest.mark.asyncio
async def test_download_file_restarts_without_range(primary, secondary_directory):
    """A server that ignores Range sends the whole file; the partial is replaced, not appended to."""
    primary.state['honor_range'] = False
    content = b'abcdefghij' * 100
    file = write_primary_file(primary, 'a.bin', content)
    destination = secondary_directory / file.path
    lib.partial_path(destination).write_bytes(content[:500])

    async with lib.PrimaryClient(primary.url) as client:
        await lib.download_file(client, file, destination)

    assert destination.read_bytes() == content


@pytest.mark.asyncio
async def test_download_file_changed_on_primary(primary, secondary_directory):
    """A file whose size changed after the manifest was read is not written; the next sync gets it."""
    file = write_primary_file(primary, 'a.txt', b'old')
    (primary.directory / 'a.txt').write_bytes(b'new and longer')
    destination = secondary_directory / file.path

    async with lib.PrimaryClient(primary.url) as client:
        with pytest.raises(lib.SyncError):
            await lib.download_file(client, file, destination)

    assert not destination.exists()


@pytest.mark.asyncio
async def test_download_file_larger_than_manifest(primary, secondary_directory):
    """A primary that sends more bytes than its manifest said (no Content-Length to catch it) is not written past
    the manifest's size, which is what the free-space check allowed for."""
    primary.state['omit_length'] = True
    write_primary_file(primary, 'a.bin', b'x' * 5 * lib.DOWNLOAD_CHUNK_SIZE)
    file = lib.ManifestFile('a.bin', 3000, 1_700_000_000.0)
    destination = secondary_directory / file.path

    async with lib.PrimaryClient(primary.url) as client:
        with pytest.raises(lib.SyncError, match='larger than the primary said'):
            await lib.download_file(client, file, destination)

    assert not destination.exists()
    assert not lib.partial_path(destination).exists()


@pytest.mark.asyncio
async def test_download_file_disk_full(primary, secondary_directory, monkeypatch):
    """A file that would leave less than the minimum free space is not downloaded; its partial is kept."""
    file = write_primary_file(primary, 'a.bin', b'x' * 1000)
    destination = secondary_directory / file.path
    destination.parent.mkdir(parents=True, exist_ok=True)
    lib.partial_path(destination).write_bytes(b'x' * 10)

    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr(lib.shutil, 'disk_usage', lambda _: usage(10, 10, lib.MIN_FREE_BYTES))

    async with lib.PrimaryClient(primary.url) as client:
        with pytest.raises(lib.SyncDiskFull):
            await lib.download_file(client, file, destination)

    assert lib.partial_path(destination).read_bytes() == b'x' * 10
    assert primary.state['requests'] == []


def capture_manifest() -> list:
    pages = list()
    after_id = 0
    with get_db_session() as session:
        while True:
            page = lib.build_manifest_page(session, after_id, limit=2)
            pages.append(page)
            if page['next_after_id'] is None:
                return pages
            after_id = page['next_after_id']


@pytest.mark.asyncio
async def test_run_sync(async_client, test_session, primary, secondary_directory, make_secondary, fake_primary_api,
                        refresh_files, tag_factory, test_tags_config, events_fixture, await_switches):
    """A secondary gets the primary's files, then its tags.yaml, and its FileGroups are tagged like the primary's."""
    write_primary_file(primary, 'docs/notes.txt', b'some notes', mtime=1_700_000_001.0)
    write_primary_file(primary, 'docs/more notes.txt', b'more notes', mtime=1_700_000_002.0)
    write_primary_file(primary, 'videos/channel/video.mp4', b'not really a video', mtime=1_700_000_003.0)
    write_primary_file(primary, 'videos/channel/video.info.json', b'{}', mtime=1_700_000_004.0)
    await refresh_files()

    tag = await tag_factory('one')
    notes = test_session.query(FileGroup).filter_by(primary_path=primary.directory / 'docs/notes.txt').one()
    notes.add_tag(test_session, tag.id)
    test_session.commit()
    get_tags_config().dump_config()
    await await_switches()
    primary_tags = (primary.directory / 'config/tags.yaml').read_bytes()
    assert b'docs/notes.txt' in primary_tags

    pages = capture_manifest()
    assert len(pages) >= 2, 'the manifest is paged'
    fake_primary_api(pages, primary.directory)

    # The secondary is another machine with its own (empty) database.
    test_session.query(TagFile).delete()
    test_session.query(Tag).delete()
    test_session.query(FileGroup).delete()
    test_session.commit()

    # This WROLPi becomes the secondary; it has its own (empty) tags.yaml.
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)
    (secondary_directory / 'config/tags.yaml').write_text('tags: {}\ntag_files: []\nversion: 1\n')

    status = await lib.run_sync()

    assert status['state'] == 'idle', status['last_error']
    assert status['files_failed'] == 0
    assert status['files_downloaded'] == 4
    assert status['last_success_at']
    for path in ('docs/notes.txt', 'docs/more notes.txt', 'videos/channel/video.mp4',
                 'videos/channel/video.info.json'):
        copy = secondary_directory / path
        assert copy.read_bytes() == (primary.directory / path).read_bytes()
        assert copy.stat().st_mtime == (primary.directory / path).stat().st_mtime

    # The secondary's own tags.yaml is kept in today's backup.
    backups = list((secondary_directory / 'config/backup').glob('tags-*.yaml'))
    assert len(backups) == 1 and b'docs/notes.txt' not in backups[0].read_bytes()

    # The primary's tags.yaml is copied byte for byte, and imported.
    assert (secondary_directory / 'config/tags.yaml').read_bytes() == primary_tags
    assert 'tags.yaml' in status['configs_imported']
    with get_db_session() as session:
        copy = session.query(FileGroup).filter_by(primary_path=secondary_directory / 'docs/notes.txt').one()
        assert copy.tag_names == ['one']
        # Files of a group arrive together, and are grouped again on the secondary.
        video = session.query(FileGroup).filter_by(directory=secondary_directory / 'videos/channel').one()
        assert {pathlib.Path(i['path']).name for i in video.files} == {'video.mp4', 'video.info.json'}

    events_fixture.assert_has_event('sync_completed')

    # Nothing changed, so nothing is downloaded or imported again.
    primary.state['requests'].clear()
    status = await lib.run_sync()
    assert status['files_to_download'] == 0
    assert status['configs_imported'] == []
    assert not [i for i in primary.state['requests'] if not i[0].startswith('/media/config/')]


@pytest.mark.asyncio
async def test_run_sync_refuses_unsafe_paths(async_client, primary, secondary_directory, make_secondary,
                                             fake_primary_api):
    """A manifest cannot make a secondary write outside its library, or over its configs and database."""
    good = write_primary_file(primary, 'good.txt', b'good')
    write_primary_file(primary, 'config/wrolpi.db', b'not a database')
    pages = [manifest_page(
        (good.path, good.size, good.mtime),
        ('config/wrolpi.db', 14, 1_700_000_000.0),
        ('../escape.txt', 4, 1_700_000_000.0),
        ('tags/one/good.txt', 4, 1_700_000_000.0),
    )]
    fake_primary_api(pages, primary.directory)
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    status = await lib.run_sync()

    assert status['files_failed'] == 3
    assert (secondary_directory / 'good.txt').read_bytes() == b'good'
    assert not (secondary_directory / 'config/wrolpi.db').exists()
    assert not (secondary_directory.parent / 'escape.txt').exists()
    assert not (secondary_directory / 'tags').exists()


@pytest.mark.asyncio
async def test_run_sync_excluded_directories(async_client, primary, secondary_directory, make_secondary,
                                             fake_primary_api):
    """A secondary never downloads files inside its excluded folders, and keeps what it already has in them."""
    wanted = [write_primary_file(primary, i, b'wanted') for i in ('Movies2/a.mp4', 'docs/Movies/b.txt', 'c.txt')]
    excluded = [write_primary_file(primary, i, b'excluded') for i in ('Movies/a.mp4', 'Movies/deep/b.mp4',
                                                                      'Movies [HD]/c.mp4')]
    pages = [manifest_page(*((i.path, i.size, i.mtime) for i in wanted + excluded))]
    fake_primary_api(pages, primary.directory)
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)
    get_sync_config()._config['sync_excluded_directories'] = ['Movies', 'Movies [HD]']
    # Copied before the folder was excluded.
    (secondary_directory / 'Movies').mkdir()
    (secondary_directory / 'Movies/old.mp4').write_bytes(b'old')

    status = await lib.run_sync()

    assert status['last_error'] is None
    assert status['files_excluded'] == 3
    assert status['files_downloaded'] == 3
    for file in wanted:
        assert (secondary_directory / file.path).read_bytes() == b'wanted'
    for file in excluded:
        assert not (secondary_directory / file.path).exists()
    assert (secondary_directory / 'Movies/old.mp4').read_bytes() == b'old', 'nothing is deleted'


@pytest.mark.parametrize('values, expected', [
    ([], []),
    (['Movies'], ['Movies']),
    (['/Movies/', ' Movies ', 'Movies//'], ['Movies']),
    (['videos/Movies', 'videos'], ['videos']),
    (['Movies', 'Movies2', 'Movies/deep'], ['Movies', 'Movies2']),
    (['a//b'], ['a/b']),
    (['Movies [HD]'], ['Movies [HD]']),
])
def test_normalize_excluded_directories(values, expected):
    assert lib.normalize_excluded_directories(values) == expected


@pytest.mark.parametrize('value', ['', '/', '..', 'a/../b', '../a', 'a/./b', '.hidden', 'a/.hidden', 'config',
                                   'config/x', 'tags', 'Config', 'TAGS/x', 'a\\b', None])
def test_normalize_excluded_directories_rejects(value):
    with pytest.raises(InvalidConfig):
        lib.normalize_excluded_directories([value])


def test_is_excluded():
    assert lib.is_excluded('Movies/a.mp4', {'Movies'})
    assert lib.is_excluded('Movies', {'Movies'})
    assert not lib.is_excluded('Movies2/a.mp4', {'Movies'})
    assert not lib.is_excluded('docs/Movies/a.mp4', {'Movies'})
    assert lib.is_excluded('docs/Movies/a.mp4', {'docs/Movies'})


def test_list_local_directories(test_directory):
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden', 'zims', 'lost+found', 'Tags'):
        try:
            (test_directory / i).mkdir(parents=True)
        except FileExistsError:
            pass  # 'Tags' is 'tags' on a filesystem that ignores case.
    (test_directory / 'file.txt').write_text('a file')
    (test_directory / 'link').symlink_to(test_directory / 'Movies')

    assert lib.list_local_directories('') == [
        dict(name='Movies', path='Movies'), dict(name='videos', path='videos'), dict(name='zims', path='zims')]
    assert lib.list_local_directories('/videos/') == [dict(name='channel', path='videos/channel')]
    for path in ('../', 'videos/../..', 'file.txt', 'missing', 'link'):
        with pytest.raises(InvalidConfig):
            lib.list_local_directories(path)


@pytest.mark.asyncio
async def test_list_primary_directories(primary, secondary_directory, make_secondary):
    for i in ('Movies', 'videos/channel', 'config', 'tags', '.hidden', 'lost+found'):
        (primary.directory / i).mkdir(parents=True)
    (primary.directory / 'file.txt').write_text('a file')
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    assert await lib.list_primary_directories('') == [
        dict(name='Movies', path='Movies'), dict(name='videos', path='videos')]
    assert await lib.list_primary_directories('videos') == [dict(name='channel', path='videos/channel')]
    with pytest.raises(InvalidConfig):
        await lib.list_primary_directories('../etc')


@pytest.mark.asyncio
async def test_run_sync_only_on_a_secondary(async_client, test_wrolpi_config, fake_primary_api):
    status = await lib.run_sync()
    assert status['state'] == 'idle'
    assert status['last_skip_reason'] == 'This WROLPi is not a secondary'
    assert status['started_at'] is None


@pytest.mark.asyncio
async def test_run_sync_refuses_a_secondary_primary(async_client, primary, secondary_directory, make_secondary,
                                                    fake_primary_api):
    """Secondaries do not chain; a secondary's library may be stale."""
    fake_primary_api([manifest_page()], primary.directory, role='secondary')
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    status = await lib.run_sync()
    assert status['state'] == 'error'
    assert 'is not a primary' in status['last_error']


@pytest.mark.asyncio
async def test_run_sync_cancel(async_client, primary, secondary_directory, make_secondary, fake_primary_api):
    """A cancelled sync stops between pages; the files of finished pages stay."""
    first = write_primary_file(primary, 'first.txt', b'first')
    second = write_primary_file(primary, 'second.txt', b'second')
    pages = [manifest_page((first.path, first.size, first.mtime), next_after_id=1, max_id=2),
             manifest_page((second.path, second.size, second.mtime), max_id=2)]
    fake_primary_api(pages, primary.directory)
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    original = lib._refresh

    async def refresh_then_cancel(paths):
        await original(paths)
        lib.request_sync_cancel()

    lib._refresh = refresh_then_cancel
    try:
        status = await lib.run_sync()
    finally:
        lib._refresh = original

    assert status['last_error'] == 'The sync was cancelled'
    assert status['state'] == 'idle'
    assert (secondary_directory / 'first.txt').exists()
    assert not (secondary_directory / 'second.txt').exists()


@pytest.mark.asyncio
async def test_sync_configs_wrolpi_yaml(async_client, primary, secondary_directory, make_secondary):
    """Only the library settings of the primary's wrolpi.yaml are applied; the secondary keeps its own role, hotspot,
    and the like."""
    primary_config = dict(
        videos_destination='my videos/%(channel_name)s',
        ignored_directories=['config', 'tags', str(primary.directory / 'private'), '/elsewhere/directory'],
        hotspot_ssid='primary hotspot',
        role='primary',
        nav_color='red',
        version=12,
    )
    (primary.directory / 'config').mkdir(exist_ok=True)
    (primary.directory / 'config/wrolpi.yaml').write_text(yaml.dump(primary_config))
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    async with lib.PrimaryClient(primary.url) as client:
        await lib.sync_configs(client, str(primary.directory), reimport=False)

    config = get_wrolpi_config()
    assert config.videos_destination == 'my videos/%(channel_name)s'
    assert config.ignored_directories == ['config', 'tags', 'private']
    assert get_sync_config().role == 'secondary', 'the role is in sync.yaml, which is never synced'
    assert config.hotspot_ssid == 'WROLPi'
    assert config.nav_color == 'violet'


@pytest.mark.asyncio
async def test_sync_configs_inventories(async_client, primary, secondary_directory, make_secondary):
    """Inventories are a directory of configs; each one is copied."""
    from modules.inventory.common import get_inventory_configs

    inventory_directory = primary.directory / 'config/inventory'
    inventory_directory.mkdir(parents=True)
    pantry = dict(version=3, slug='pantry', name='Pantry', type='food', fields=[], items=[])
    (inventory_directory / 'pantry.yaml').write_text(yaml.dump(pantry))
    (inventory_directory / '.hidden.yaml').write_text('ignored')
    set_test_media_directory(secondary_directory)
    make_secondary(primary.url)

    async with lib.PrimaryClient(primary.url) as client:
        changed = await lib._sync_inventory_directory(client)

    assert changed
    copy = get_inventory_configs().get_directory() / 'pantry.yaml'
    assert yaml.safe_load(copy.read_text())['name'] == 'Pantry'
    assert not (copy.parent / '.hidden.yaml').exists()


@pytest.mark.asyncio
async def test_sync_tick(async_client, test_wrolpi_config, make_secondary, monkeypatch):
    """A requested sync runs; WROL Mode drops the request."""
    calls = list()

    async def fake_run_sync(force=False):
        calls.append(force)

    monkeypatch.setattr(lib, 'run_sync', fake_run_sync)

    await lib.sync_tick()
    assert calls == [], 'a primary never syncs'

    make_secondary()
    await lib.sync_tick()
    assert calls == [], 'nothing requested, no window'

    lib.request_sync(force=True)
    await lib.sync_tick()
    assert calls == [True]
    assert get_sync_status()['requested'] is False

    get_wrolpi_config()._config['wrol_mode'] = True
    lib.request_sync()
    await lib.sync_tick()
    assert calls == [True]
    assert get_sync_status()['requested'] is False
    assert get_sync_status()['last_skip_reason'] == 'WROL Mode is enabled'


def test_request_sync_cancel(async_client):
    update_sync_status(state='running')
    lib.request_sync_cancel()
    assert get_sync_status()['cancel_requested'] is True

    update_sync_status(state='idle', cancel_requested=False, requested=True)
    lib.request_sync_cancel()
    assert get_sync_status()['requested'] is False
    assert get_sync_status()['cancel_requested'] is False


def test_partial_path():
    assert lib.partial_path(pathlib.Path('/a/b/video.mp4')) == pathlib.Path('/a/b/.video.mp4.partial')
