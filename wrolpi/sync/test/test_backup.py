import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

import pytest

from wrolpi.common import get_wrolpi_config
from wrolpi.sync import backup
from wrolpi.sync.config import get_sync_config
from wrolpi.sync.status import get_backup_status, update_backup_status


def _rsync_supports_progress2() -> bool:
    """rsync 3.1+ (Raspberry Pi OS, Debian); macOS ships openrsync, which has no `--info=progress2`."""
    if not shutil.which('rsync'):
        return False
    output = subprocess.run(['rsync', '--version'], capture_output=True, text=True).stdout
    match = re.search(r'rsync\s+version\s+(\d+)\.(\d+)', output)
    return bool(match) and (int(match.group(1)), int(match.group(2))) >= (3, 1)


requires_rsync = pytest.mark.skipif(not _rsync_supports_progress2(), reason='rsync 3.1 or newer is not installed')


@pytest.fixture
def backup_drive(test_directory, test_wrolpi_config, monkeypatch):
    """A temporary directory that the target checks accept as the mounted backup drive `uuid-1`."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        drive = pathlib.Path(tmp_dir).resolve()
        monkeypatch.setattr(backup, 'check_backup_target', lambda directory, uuid: None)
        get_sync_config()._config.update(backup_directory=str(drive), backup_device_uuid='uuid-1')
        yield drive


def test_build_rsync_command(monkeypatch):
    monkeypatch.setattr(backup.shutil, 'which', lambda name: f'/usr/bin/{name}')
    command = backup.build_rsync_command(pathlib.Path('/media/wrolpi'), pathlib.Path('/media/backup'), 'playlists')
    assert command[:5] == ['/usr/bin/ionice', '-c3', '/usr/bin/nice', '-n', '19']
    assert command[-2:] == ['/media/wrolpi/', '/media/backup/'], 'trailing slashes copy the contents, not the folder'
    assert not any(i.startswith('--delete') for i in command), 'a backup never deletes'
    assert '-H' not in command and '--hard-links' not in command
    for exclude in ('/config/wrolpi.db', '/config/wrolpi.db-*', '/tags/', '/playlists/', '.*.partial',
                    '.rsync-partial/', '/lost+found/'):
        assert f'--exclude={exclude}' in command, exclude

    # ionice and nice are optional.
    monkeypatch.setattr(backup.shutil, 'which', lambda name: '/usr/bin/rsync' if name == 'rsync' else None)
    command = backup.build_rsync_command(pathlib.Path('/media/wrolpi'), pathlib.Path('/media/backup'), None)
    assert command[0] == '/usr/bin/rsync'
    assert not any(i.startswith('--exclude=/playlists') for i in command)


@pytest.mark.parametrize('line, expected', [
    ('     32,768   0%    0.00kB/s    0:00:00 (xfr#1, ir-chk=1018/1023)',
     dict(bytes_transferred=32768, percent=0, files_transferred=1, files_to_check=1023)),
    ('  1234567890  45%   10.50MB/s    0:01:23 (xfr#12, to-chk=100/2000)',
     dict(bytes_transferred=1234567890, percent=45, files_transferred=12, files_to_check=2000)),
    ('  1234567890  45%   10.50MB/s    0:01:23', dict(bytes_transferred=1234567890, percent=45)),
    ('Number of regular files transferred: 1,234', dict(files_transferred=1234)),
    ('sending incremental file list', None),
    ('', None),
])
def test_parse_progress(line, expected):
    assert backup.parse_progress(line) == expected


@pytest.fixture
def fake_mounts(test_directory, monkeypatch, tmp_path):
    """Pretend `/media/backup` is a mounted drive with UUID `uuid-1` (device /dev/sdb1)."""
    drive = tmp_path / 'backup'
    drive.mkdir()
    media = test_directory.resolve()
    real_resolve = pathlib.Path.resolve

    def resolve(self, strict=False):
        if str(self) == '/media/backup':
            return drive
        return real_resolve(self, strict=strict)

    state = dict(mounted=True, device=2, uuid_device='/dev/sdb1', source='/dev/sdb1')
    monkeypatch.setattr(pathlib.Path, 'resolve', resolve)
    monkeypatch.setattr(backup, 'is_mount', lambda path: state['mounted'] if path == drive else False)
    monkeypatch.setattr(backup, 'device_id', lambda path: state['device'] if path == drive else
                        (1 if path == media else 0))
    monkeypatch.setattr(backup, 'uuid_device', lambda uuid: state['uuid_device'] if uuid == 'uuid-1' else None)
    monkeypatch.setattr(backup, 'mount_source', lambda path: state['source'] if path == str(drive) else None)
    return state


def test_check_backup_target(test_directory, fake_mounts):
    assert backup.check_backup_target('/media/backup', 'uuid-1') is None

    assert backup.check_backup_target(None, None) == 'No backup drive is configured'
    assert backup.check_backup_target('backup', 'uuid-1') == 'backup is not under /media'
    assert backup.check_backup_target('/mnt/backup', 'uuid-1') == '/mnt/backup is not under /media'
    assert backup.check_backup_target('/media/wrolpi_temp_onboarding', 'uuid-1') \
           == '/media/wrolpi_temp_onboarding cannot be a backup drive'

    fake_mounts['mounted'] = False
    assert backup.check_backup_target('/media/backup', 'uuid-1') == 'No drive is mounted at /media/backup', \
        'an unplugged drive leaves a directory on the system drive'
    fake_mounts['mounted'] = True

    fake_mounts['device'] = 1
    assert backup.check_backup_target('/media/backup', 'uuid-1') == 'The backup drive is the media drive'
    fake_mounts['device'] = 0
    assert backup.check_backup_target('/media/backup', 'uuid-1') == 'The backup drive is the system drive'
    fake_mounts['device'] = 2

    fake_mounts['source'] = '/dev/sdc1'
    assert backup.check_backup_target('/media/backup', 'uuid-1') \
           == 'The chosen drive is not mounted at /media/backup', 'another drive mounted at the same place'
    fake_mounts['source'] = '/dev/sdb1'
    assert backup.check_backup_target('/media/backup', 'uuid-2') \
           == 'The chosen drive is not mounted at /media/backup', 'the drive is not plugged in'


def test_mount_source(monkeypatch, tmp_path):
    mounts = tmp_path / 'mounts'
    mounts.write_text('/dev/sda1 /media/wrolpi ext4 rw 0 0\n'
                      '/dev/sdb1 /media/my\\040backup ext4 rw 0 0\n'
                      '/dev/sdc1 /media/stacked ext4 rw 0 0\n'
                      '/dev/sdd1 /media/stacked ext4 rw 0 0\n')
    monkeypatch.setattr(backup, 'PROC_MOUNTS', mounts)
    assert backup.mount_source('/media/my backup') == '/dev/sdb1'
    assert backup.mount_source('/media/stacked') == '/dev/sdd1', 'the last mount is the visible one'
    assert backup.mount_source('/media/missing') is None


def test_snapshot_database(test_directory, tmp_path):
    """The snapshot is a complete, consistent database, even with writes still in the live database's WAL."""
    (test_directory / 'config').mkdir(exist_ok=True)
    live = sqlite3.connect(test_directory / 'config/wrolpi.db')
    live.execute('PRAGMA journal_mode=WAL')
    live.execute('CREATE TABLE t (v TEXT)')
    live.execute("INSERT INTO t VALUES ('in the WAL')")
    live.commit()
    assert (test_directory / 'config/wrolpi.db-wal').stat().st_size > 0

    drive = tmp_path / 'drive'
    (drive / 'config').mkdir(parents=True)
    # A stale WAL from an older copy must not be applied to the new snapshot.
    (drive / 'config/wrolpi.db-wal').write_bytes(b'stale')
    try:
        backup.snapshot_database(drive)
    finally:
        live.close()

    assert not (drive / 'config/wrolpi.db-wal').exists()
    assert not (drive / 'config/.wrolpi.db.backup').exists()
    with sqlite3.connect(drive / 'config/wrolpi.db') as copy:
        assert copy.execute('SELECT v FROM t').fetchall() == [('in the WAL',)]


@requires_rsync
@pytest.mark.asyncio
async def test_run_backup(async_client, test_directory, backup_drive, events_fixture):
    """Files and configs are copied with their modification times; the database is a snapshot; hard-link directories
    are not copied; nothing on the backup drive is deleted; a second backup copies nothing."""
    files = {
        'videos/channel/video.mp4': b'video',
        'videos/channel/video.info.json': b'{}',
        'config/tags.yaml': b'tags: {}\n',
        'tags/one/video.mp4': b'video',
        'playlists/0001_video.mp4': b'video',
        'videos/channel/.video.mp4.partial': b'vid',
    }
    for path, content in files.items():
        (test_directory / path).parent.mkdir(parents=True, exist_ok=True)
        (test_directory / path).write_bytes(content)
        os.utime(test_directory / path, (1_700_000_000, 1_700_000_000))
    with sqlite3.connect(test_directory / 'config/wrolpi.db') as db:
        db.execute('CREATE TABLE t (v TEXT)')
        db.execute("INSERT INTO t VALUES ('row')")
    # Only on the backup drive: never deleted.
    (backup_drive / 'old.txt').write_text('deleted from the media directory long ago')

    status = await backup.run_backup()

    assert status['state'] == 'idle', status['last_error']
    assert status['last_success_at']
    for path in ('videos/channel/video.mp4', 'videos/channel/video.info.json', 'config/tags.yaml'):
        assert (backup_drive / path).read_bytes() == files[path]
        assert (backup_drive / path).stat().st_mtime == 1_700_000_000
    assert not (backup_drive / 'tags').exists()
    assert not (backup_drive / 'playlists').exists()
    assert not (backup_drive / 'videos/channel/.video.mp4.partial').exists()
    assert (backup_drive / 'old.txt').exists()
    with sqlite3.connect(backup_drive / 'config/wrolpi.db') as copy:
        assert copy.execute('SELECT v FROM t').fetchall() == [('row',)]
    assert status['files_transferred'] == 3
    events_fixture.assert_has_event('backup_completed')

    status = await backup.run_backup()
    assert status['state'] == 'idle', status['last_error']
    assert status['files_transferred'] == 0


@requires_rsync
@pytest.mark.asyncio
async def test_run_backup_stops_when_drive_disappears(async_client, test_directory, backup_drive, monkeypatch):
    """A drive that is unplugged during a backup is not written to again: rsync is stopped."""
    (test_directory / 'a.txt').write_text('a')
    monkeypatch.setattr(backup, 'MOUNT_CHECK_SECONDS', 0)
    monkeypatch.setattr(backup, 'check_backup_target', lambda directory, uuid: 'No drive is mounted at /media/x')
    monkeypatch.setattr(backup, 'backup_skip_reason', lambda: None)

    status = await backup.run_backup()

    assert status['state'] == 'error'
    assert 'No drive is mounted' in status['last_error']


@pytest.mark.asyncio
async def test_run_backup_skips(async_client, test_wrolpi_config):
    status = await backup.run_backup()
    assert status['last_skip_reason'] == 'No backup drive is configured'
    assert status['started_at'] is None

    get_sync_config()._config.update(backup_directory='/media/backup', backup_device_uuid='uuid-1')
    get_wrolpi_config()._config.update(wrol_mode=True)
    status = await backup.run_backup()
    assert status['last_skip_reason'] == 'WROL Mode is enabled'


@pytest.mark.asyncio
async def test_backup_tick(async_client, test_wrolpi_config, monkeypatch):
    calls = list()

    async def fake_run_backup():
        calls.append(True)

    monkeypatch.setattr(backup, 'run_backup', fake_run_backup)

    backup.request_backup()
    await backup.backup_tick()
    assert calls == [], 'no backup drive'
    assert get_backup_status()['last_skip_reason'] == 'No backup drive is configured'

    get_sync_config()._config.update(backup_directory='/media/backup', backup_device_uuid='uuid-1')
    await backup.backup_tick()
    assert calls == [], 'nothing requested and no window'

    backup.request_backup()
    await backup.backup_tick()
    assert calls == [True]
    assert get_backup_status()['requested'] is False

    get_wrolpi_config()._config.update(wrol_mode=True)
    backup.request_backup()
    await backup.backup_tick()
    assert calls == [True]
    assert get_backup_status()['last_skip_reason'] == 'WROL Mode is enabled'


def test_backup_is_due_hourly_in_window(test_wrolpi_config):
    """Within the window, a backup repeats an hour after the last one finished."""
    from wrolpi.sync.lib import sync_is_due
    get_sync_config()._config.update(window_start='01:00', window_end='05:00')
    local_now = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
    recent = dict(finished_at=local_now.replace(hour=2, minute=30).isoformat())
    earlier = dict(finished_at=local_now.replace(hour=1, minute=55).isoformat())
    assert not sync_is_due(recent, local_now, backup.BACKUP_REPEAT_SECONDS)
    assert sync_is_due(earlier, local_now, backup.BACKUP_REPEAT_SECONDS)


def test_request_backup_cancel(async_client):
    update_backup_status(state='running')
    backup.request_backup_cancel()
    assert get_backup_status()['cancel_requested'] is True
