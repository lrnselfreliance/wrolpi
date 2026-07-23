"""Creates and migrates the SQLite database at API startup.

The database lives inside the media directory (`<media>/config/wrolpi.db`), so it may belong to
a drive that was last used by a different WROLPi:
  * no database → create it and run the migrations (the configs will then be imported and a
    refresh rebuilds the library index);
  * database older than this code → migrate it forward;
  * database NEWER than this code → refuse to write; the user must upgrade this WROLPi.
"""
import contextlib
import fcntl
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from wrolpi import flags
from wrolpi.common import logger
from wrolpi.db import get_db_file, get_db_uri
from wrolpi.vars import PROJECT_DIR, PYTEST, DOCKERIZED

logger = logger.getChild(__name__)

MINIMUM_SQLITE_VERSION = (3, 40, 0)

# WAL locking is unsafe on network filesystems; refuse to run there.
NETWORK_FS_TYPES = {'nfs', 'nfs4', 'cifs', 'smb3', 'smbfs', 'fuse.sshfs', 'fuse.rclone', '9p'}

# FAT/exFAT/NTFS drives (common when a USB drive is formatted for Windows compatibility) cannot
# support SQLite WAL: it needs mmap'd shared-memory that these filesystems do not provide.  These
# are still usable — the engine degrades to a rollback journal (see `_configure_sqlite_connection`)
# — but with reduced write-concurrency, so we warn the user to prefer ext4.
WAL_INCOMPATIBLE_FS_TYPES = {'vfat', 'exfat', 'msdos', 'ntfs', 'ntfs3', 'fuseblk'}


def _media_fs_type(path: Path) -> Optional[str]:
    """The filesystem type of the mount containing `path` (Linux only)."""
    if sys.platform != 'linux':
        return None
    try:
        mounts = Path('/proc/mounts').read_text()
    except OSError:
        return None
    best_prefix, best_type = '', None
    path_str = str(path)
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount_point, fs_type = parts[1], parts[2]
        if path_str == mount_point or path_str.startswith(mount_point.rstrip('/') + '/') or mount_point == '/':
            if len(mount_point) > len(best_prefix):
                best_prefix, best_type = mount_point, fs_type
    return best_type


def check_sqlite_environment(db_file: Path) -> Optional[str]:
    """Returns an error message when the environment cannot safely run the database, else None."""
    if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
        return f'SQLite {sqlite3.sqlite_version} is too old, WROLPi requires 3.40+'
    fs_type = _media_fs_type(db_file.parent if db_file.parent.exists() else db_file.parent.parent)
    if fs_type in NETWORK_FS_TYPES:
        return f'Refusing to use a database on a network filesystem ({fs_type}); WAL locking is unsafe there'
    if fs_type in WAL_INCOMPATIBLE_FS_TYPES:
        # Usable, but WAL is impossible here so the engine will use a slower rollback journal.
        logger.warning(f'Media filesystem is {fs_type}: SQLite WAL is unavailable, so the database will use a '
                       f'slower rollback journal with reduced write-concurrency.  Reformat the drive as ext4 '
                       f'for best performance.')
    return None


def media_directory_is_unmounted_production(media_directory: Path = None) -> bool:
    """True when this is a production host whose media directory should be a mount, but is not.

    While true, the database must not be created, migrated, or even considered "up": any file at
    the database path is on the root filesystem, shadowing the real database on the drive.  (An
    ORM connection implicitly creates an empty DB file, so file-existence checks cannot be used
    to detect this situation.)"""
    if PYTEST or DOCKERIZED or sys.platform != 'linux':
        return False
    if media_directory is None:
        from wrolpi.common import get_media_directory
        media_directory = get_media_directory()
    if not str(media_directory).startswith('/media/'):
        # A custom MEDIA_DIRECTORY (dev boxes) may legitimately not be a mount.
        return False
    try:
        return not media_directory.is_mount()
    except OSError:
        return True


def _alembic_config():
    from alembic.config import Config
    config = Config(str(PROJECT_DIR / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', get_db_uri())
    return config


def compare_db_version() -> str:
    """Compare the database's alembic version to this code's.

    Returns 'missing' (no/uninitialized DB file), 'current', 'behind' (needs migrations), or
    'ahead' (the DB was written by a newer WROLPi)."""
    from alembic.script import ScriptDirectory

    db_file = get_db_file()
    if not db_file.is_file():
        return 'missing'
    try:
        # Read-only URI probe: a plain connect would create an empty database file.
        with contextlib.closing(sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)) as conn:
            row = conn.execute('SELECT version_num FROM alembic_version').fetchone()
        current = row[0] if row else None
    except sqlite3.OperationalError:
        current = None
    if not current:
        # The file exists but was never migrated; treat like a fresh database.
        return 'missing'

    script = ScriptDirectory.from_config(_alembic_config())
    if current == script.get_current_head():
        return 'current'
    try:
        script.get_revision(current)
        return 'behind'
    except Exception:
        # This code does not know the DB's revision: the DB is from a newer WROLPi.
        return 'ahead'


def ensure_db() -> bool:
    """Create/migrate the database.  Returns True when the database is usable at head.

    Never creates the database beneath an unmounted media directory on a production host
    (that would silently start an empty library on the root filesystem)."""
    from alembic import command
    from wrolpi.common import get_media_directory
    from wrolpi.events import Events

    db_file = get_db_file()

    if error := check_sqlite_environment(db_file):
        logger.critical(error)
        with contextlib.suppress(Exception):
            Events.send_config_import_failed(error)
        return False

    media_directory = get_media_directory()
    if not media_directory.is_dir():
        logger.warning(f'Cannot create/migrate database; media directory is missing: {media_directory}')
        return False
    if media_directory_is_unmounted_production(media_directory):
        # A production media directory that is not mounted: any database created/migrated here
        # would land on the root filesystem and shadow the real database once the drive mounts.
        # (Unconditional: a worker's ORM connection may have already created an empty DB file.)
        logger.warning(f'Refusing to create/migrate database beneath unmounted media directory: {media_directory}')
        return False

    state = compare_db_version()
    if state == 'ahead':
        flags.db_version_mismatch.set()
        message = 'The database was written by a NEWER WROLPi (drive from another system?).  ' \
                  'Upgrade this WROLPi before using this drive.'
        logger.critical(message)
        with contextlib.suppress(Exception):
            Events.send_config_import_failed(message)
        return False

    flags.db_version_mismatch.clear()

    if state in ('missing', 'behind'):
        db_file.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(f'Migrating database ({state}): {db_file}')
        command.upgrade(_alembic_config(), 'head')

    return True


@contextlib.contextmanager
def bootstrap_lock():
    """A non-blocking cross-process lock; yields True when this process holds the lock.

    Multiple Sanic workers may try to bootstrap simultaneously; only one needs to."""
    lock_file = get_db_file().with_suffix('.db.lock')
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        with lock_file.open('w') as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        # Cannot create the lock file (media directory missing/read-only); let the caller try.
        yield True
