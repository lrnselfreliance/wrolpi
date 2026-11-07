"""Copy this WROLPi's media directory to a second drive (its "backup drive").

The backup drive mirrors the media directory, so if the media drive dies the backup drive can be mounted as the media
directory and WROLPi starts from it:

1. rsync copies every file that is new or changed (never `--delete`: a file deleted from the media directory stays on
   the backup drive).  The Tags Directory and the playlists directory are not copied; they are hard links that
   WROLPi rebuilds from the configs when it starts.
2. The database is not copied by rsync (a live database copied as files can be torn); SQLite's backup API writes a
   consistent snapshot instead.

A backup only reads the media directory, so the API stays usable while it runs.  It runs in the sync window, or when
the user asks.  Nothing is written unless the configured drive is mounted where it was chosen: an unplugged drive
leaves an empty directory on the system drive, which must never be filled.
"""
import asyncio
import contextlib
import os
import pathlib
import re
import shutil
import sqlite3
import time
from typing import List, Optional, Tuple

from wrolpi import flags
from wrolpi.common import logger, get_media_directory, get_wrolpi_config, wrol_mode_enabled
from wrolpi.dates import now
from wrolpi.db import get_db_file
from wrolpi.events import Events
from wrolpi.sync.config import get_sync_config
from wrolpi.sync.lib import window_is_due, PROGRESS_INTERVAL_SECONDS
from wrolpi.sync.status import get_backup_status, update_backup_status
from wrolpi.vars import DOCKERIZED, PYTEST

logger = logger.getChild(__name__)

# Within the sync window, back up again this long after the last backup finished; each backup walks the whole library.
BACKUP_REPEAT_SECONDS = 60 * 60
# rsync keeps an interrupted file here (on the backup drive) so the next backup resumes it.
PARTIAL_DIRECTORY = '.rsync-partial'
# rsync exit codes: 23 = some files could not be read, 24 = some files vanished while copying.
RSYNC_VANISHED = 24
RSYNC_PARTIAL = 23
# How often a running backup checks that its drive is still mounted.
MOUNT_CHECK_SECONDS = 5.0
PROC_MOUNTS = pathlib.Path('/proc/mounts')
# Backup drives are mounted in this directory (the Controller mounts drives here).
MOUNT_ROOT = pathlib.Path('/media')
# Mount points (in MOUNT_ROOT) that are never a backup drive.
RESERVED_MOUNT_NAMES = frozenset({'wrolpi_temp_onboarding'})

# `--info=progress2` lines: "  1234567  45%   10.5MB/s    0:01:23 (xfr#12, to-chk=100/2000)"
PROGRESS_LINE = re.compile(r'^\s*([\d,]+)\s+(\d+)%\s+\S+\s+\S+(?:\s+\(xfr#(\d+), (?:ir|to)-chk=(\d+)/(\d+)\))?')
FILES_TRANSFERRED_LINE = re.compile(r'^Number of regular files transferred: ([\d,]+)')


class BackupError(Exception):
    pass


class BackupCancelled(BackupError):
    pass


def _unescape_mount_path(path: str) -> str:
    # /proc/mounts escapes spaces and the like as octal, e.g. "\040".
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), path)


def mount_source(mount_point: str) -> Optional[str]:
    """The device mounted at `mount_point`, or None.  A path mounted twice reports the last (visible) mount."""
    try:
        lines = PROC_MOUNTS.read_text().splitlines()
    except OSError:
        return None
    source = None
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and _unescape_mount_path(parts[1]) == mount_point:
            source = parts[0]
    return source


def uuid_device(uuid: str) -> Optional[str]:
    """The device with this filesystem UUID, or None."""
    if not uuid or '/' in uuid:
        return None
    path = pathlib.Path('/dev/disk/by-uuid') / uuid
    return os.path.realpath(path) if path.exists() else None


def device_id(path) -> int:
    return os.stat(path).st_dev


def is_mount(path) -> bool:
    return os.path.ismount(path)


def find_mount_point(path: pathlib.Path) -> pathlib.Path:
    """The mount point of the filesystem that holds `path` (an existing, resolved path)."""
    while not is_mount(path) and path != path.parent:
        path = path.parent
    return path


def check_backup_target(directory: Optional[str], uuid: Optional[str]) -> Optional[str]:
    """Why `directory` must not be written as the backup, or None if it is on the drive with `uuid`, and that drive is
    mounted, and is not the media drive or the system drive.

    `directory` is the drive's mount point, or a folder on the drive.  The folder may not exist yet (the backup
    creates it); the drive is checked through its nearest existing folder, so a folder on an unplugged drive (which
    would be on the system drive) is refused."""
    if not directory or not uuid:
        return 'No backup drive is configured'
    path = pathlib.Path(directory)
    if not path.is_absolute() or any(i in ('.', '..') for i in path.parts):
        return f'{directory} is not a valid directory'
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        resolved_existing = existing.resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        return f'{directory} does not exist'
    resolved = resolved_existing.joinpath(path.relative_to(existing))
    mount_root = MOUNT_ROOT.resolve()
    if mount_root not in resolved.parents:
        return f'{directory} is not under {MOUNT_ROOT}'
    media_directory = get_media_directory().resolve()
    if resolved == media_directory or media_directory in resolved.parents or resolved in media_directory.parents:
        return 'The backup drive cannot be the media directory'
    mount_point = find_mount_point(resolved_existing)
    if mount_root not in mount_point.parents:
        # The folder is not on a drive mounted in MOUNT_ROOT; e.g. the drive is unplugged.
        return f'No drive is mounted at {directory}'
    if mount_point.parent == mount_root and mount_point.name in RESERVED_MOUNT_NAMES:
        return f'{mount_point} cannot be a backup drive'
    if device_id(mount_point) == device_id(media_directory):
        return 'The backup drive is the media drive'
    if device_id(mount_point) == device_id('/'):
        return 'The backup drive is the system drive'
    expected = uuid_device(uuid)
    source = mount_source(str(mount_point))
    if not expected or not source or os.path.realpath(source) != expected:
        return f'The chosen drive is not mounted at {mount_point}'
    if not os.access(resolved_existing, os.W_OK):
        return f'{directory} is not writable'
    return None


def rsync_literal(path: str) -> str:
    """`path` as an rsync pattern that matches only itself (rsync reads `* ? [ \\` as wildcards)."""
    return re.sub(r'([*?\[\\])', r'\\\1', path)


def build_rsync_command(source: pathlib.Path, target: pathlib.Path, playlists_destination: str = None,
                        excluded_directories: List[str] = None) -> List[str]:
    """The rsync that copies `source` (the media directory) to `target` (the backup drive), never deleting."""
    command = list()
    # The backup should not slow the WROLPi down.
    if ionice := shutil.which('ionice'):
        command.extend([ionice, '-c3'])
    if nice := shutil.which('nice'):
        command.extend([nice, '-n', '19'])
    command.extend([
        shutil.which('rsync') or 'rsync',
        '--archive',
        '--partial', f'--partial-dir={PARTIAL_DIRECTORY}',
        '--info=progress2,stats2', '--no-human-readable',
        # The database is copied as a snapshot (see `snapshot_database`).
        '--exclude=/config/wrolpi.db', '--exclude=/config/wrolpi.db-*', '--exclude=/config/.wrolpi.db.backup',
        # Hard links rebuilt from the configs when WROLPi starts.
        '--exclude=/tags/',
        # Files still being written by a sync, and rsync's own partials.
        '--exclude=.*.partial', f'--exclude={PARTIAL_DIRECTORY}/',
        # Root-only directory on every ext4 drive.
        '--exclude=/lost+found/',
    ])
    if playlists_destination and (playlists := playlists_destination.strip('/')):
        command.append(f'--exclude=/{playlists}/')
    # Folders the user chose not to back up.
    for directory in excluded_directories or []:
        if directory := directory.strip('/'):
            command.append(f'--exclude=/{rsync_literal(directory)}/')
    command.extend([f'{source}/', f'{target}/'])
    return command


def parse_progress(line: str) -> Optional[dict]:
    if match := PROGRESS_LINE.match(line):
        progress = dict(bytes_transferred=int(match.group(1).replace(',', '')), percent=int(match.group(2)))
        if match.group(3):
            progress['files_transferred'] = int(match.group(3))
            progress['files_to_check'] = int(match.group(5))
        return progress
    if match := FILES_TRANSFERRED_LINE.match(line):
        return dict(files_transferred=int(match.group(1).replace(',', '')))
    return None


def snapshot_database(target: pathlib.Path):
    """Write a consistent copy of the live database to the backup drive's config directory."""
    config_directory = target / 'config'
    config_directory.mkdir(parents=True, exist_ok=True)
    temporary = config_directory / '.wrolpi.db.backup'
    temporary.unlink(missing_ok=True)
    with contextlib.closing(sqlite3.connect(get_db_file(), timeout=60)) as source, \
            contextlib.closing(sqlite3.connect(temporary)) as destination:
        # One step: a read transaction, which writers in WAL mode do not wait for, and which never restarts.
        source.backup(destination)
    database = config_directory / 'wrolpi.db'
    # A write-ahead log left by an older copy would be applied to the new database.
    for suffix in ('-wal', '-shm'):
        database.with_name(f'wrolpi.db{suffix}').unlink(missing_ok=True)
    os.replace(temporary, database)


def backup_skip_reason() -> Optional[str]:
    """Why a backup cannot start now, or None."""
    config = get_sync_config()
    if not config.backup_directory:
        return 'No backup drive is configured'
    if DOCKERIZED:
        return 'Backup drives are not supported in Docker'
    if wrol_mode_enabled():
        return 'WROL Mode is enabled'
    if not PYTEST and not flags.db_up.is_set():
        return 'The database is not up'
    if not shutil.which('rsync'):
        return 'rsync is not installed'
    if reason := check_backup_target(config.backup_directory, config.backup_device_uuid):
        return reason
    if flags.backup_running.is_set():
        return 'A backup is already running'
    return None


def request_backup():
    update_backup_status(requested=True)


def request_backup_cancel():
    from wrolpi.api_utils import api_app
    if 'backup' not in api_app.shared_ctx.status:
        return
    status = get_backup_status()
    if status['state'] == 'running' or status['requested']:
        update_backup_status(cancel_requested=status['state'] == 'running', requested=False)


def _check_backup_cancel():
    if get_backup_status()['cancel_requested']:
        raise BackupCancelled('The backup was cancelled')
    if wrol_mode_enabled():
        raise BackupCancelled('WROL Mode was enabled')


async def _run_rsync(command: List[str], target: pathlib.Path, uuid: str) -> Tuple[int, List[str]]:
    """Run rsync, reporting its progress.  Stops it if the backup is cancelled or the drive disappears."""
    logger.info(f'Running {" ".join(command)}')
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    errors: List[str] = list()

    async def read_errors():
        async for line in process.stderr:
            errors.append(line.decode(errors='replace').rstrip())
            del errors[:-20]

    errors_task = asyncio.create_task(read_errors())
    buffer = ''
    last_report = last_mount_check = 0.0
    progress = dict()
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(65536), timeout=1)
            except asyncio.TimeoutError:
                chunk = None
            if chunk == b'':
                break
            if chunk:
                buffer += chunk.decode(errors='replace')
                *lines, buffer = re.split(r'[\r\n]', buffer)
                for line in lines:
                    if parsed := parse_progress(line):
                        progress.update(parsed)
            if time.monotonic() - last_report >= PROGRESS_INTERVAL_SECONDS and progress:
                last_report = time.monotonic()
                update_backup_status(**progress)
            if time.monotonic() - last_mount_check >= MOUNT_CHECK_SECONDS:
                last_mount_check = time.monotonic()
                if reason := check_backup_target(str(target), uuid):
                    raise BackupError(f'Stopped: {reason}')
            _check_backup_cancel()
        code = await process.wait()
    except BaseException:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=30)
            except asyncio.TimeoutError:
                process.kill()
        raise
    finally:
        await asyncio.gather(errors_task, return_exceptions=True)
    if buffer and (parsed := parse_progress(buffer)):
        progress.update(parsed)
    if progress:
        update_backup_status(**progress)
    return code, errors


async def run_backup() -> dict:
    """Copy the media directory to the backup drive.  Returns the final status."""
    if reason := backup_skip_reason():
        logger.info(f'Not backing up: {reason}')
        return update_backup_status(last_skip_reason=reason)

    config = get_sync_config()
    target = pathlib.Path(config.backup_directory)
    uuid = config.backup_device_uuid
    started_at = now()
    update_backup_status(state='running', phase='files', cancel_requested=False, started_at=started_at.isoformat(),
                         finished_at=None, last_error=None, last_skip_reason=None, directory=str(target),
                         bytes_transferred=0, percent=0, files_transferred=0, files_to_check=0)
    logger.warning(f'Backing up to {target}')
    warning = None
    try:
        with flags.backup_running:
            # A folder on the drive is created once the drive has been checked (`backup_skip_reason`).
            target.mkdir(parents=True, exist_ok=True)
            command = build_rsync_command(get_media_directory(), target, get_wrolpi_config().playlists_destination,
                                          config.backup_excluded_directories)
            code, errors = await _run_rsync(command, target, uuid)
            if code == RSYNC_PARTIAL:
                # Unreadable files; everything else was copied.
                warning = 'Some files could not be read: ' + ' '.join(errors[-3:])
                logger.warning(warning)
            elif code not in (0, RSYNC_VANISHED):
                raise BackupError(f'rsync failed ({code}): ' + ' '.join(errors[-3:]))
            _check_backup_cancel()

            update_backup_status(phase='database')
            if reason := check_backup_target(str(target), uuid):
                raise BackupError(f'Stopped: {reason}')
            await asyncio.to_thread(snapshot_database, target)
    except BackupCancelled as e:
        logger.warning(f'Backup stopped: {e}')
        return update_backup_status(state='idle', phase=None, finished_at=now().isoformat(), last_error=str(e),
                                    cancel_requested=False)
    except Exception as e:
        logger.error('Backup failed', exc_info=e)
        Events.send_backup_failed(f'Backup to {target} failed: {e}')
        return update_backup_status(state='error', phase=None, finished_at=now().isoformat(), last_error=str(e),
                                    cancel_requested=False)

    finished_at = now()
    status = get_backup_status()
    if not warning:
        get_sync_config().update({'backup_last_success_at': finished_at.isoformat()})
    message = f'Backed up {status["files_transferred"]} files to {target}'
    logger.warning(f'{message} in {(finished_at - started_at).total_seconds():.0f}s')
    if status['files_transferred'] or warning:
        Events.send_backup_completed(message + (f'; {warning}' if warning else ''))
    return update_backup_status(state='idle', phase=None, finished_at=finished_at.isoformat(),
                                last_success_at=finished_at.isoformat() if not warning else status['last_success_at'],
                                last_error=warning, percent=100,
                                # A request to stop during the database snapshot (which runs to the end) is done.
                                cancel_requested=False)


def backup_is_due(status: dict, local_now) -> bool:
    """True if the backup window is open and the last backup finished long enough ago."""
    config = get_sync_config()
    return window_is_due(status, local_now, config.backup_window_start, config.backup_window_end,
                         BACKUP_REPEAT_SECONDS)


async def backup_tick():
    """Start a backup when one was requested, or when it is due."""
    status = get_backup_status()
    if not get_sync_config().backup_directory or wrol_mode_enabled():
        if status['requested']:
            reason = 'WROL Mode is enabled' if wrol_mode_enabled() else 'No backup drive is configured'
            update_backup_status(requested=False, last_skip_reason=reason)
        return
    from wrolpi.downloader import DownloadManager
    if not status['requested'] and not backup_is_due(status, DownloadManager._get_local_now()):
        return
    update_backup_status(requested=False)
    await run_backup()
