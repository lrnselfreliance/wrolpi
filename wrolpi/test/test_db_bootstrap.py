"""Tests for wrolpi.db_bootstrap: DB auto-creation, migration, and the drive-portability guard."""
import sqlite3

import mock
import pytest

from wrolpi import db_bootstrap
from wrolpi.db import get_db_file


@pytest.fixture(autouse=True)
def permissive_sqlite_floor():
    """CI images may ship a SQLite older than the production floor (Ubuntu 22.04 has 3.37; the
    floor targets Debian 12's 3.40).  The functional tests here exercise creation/migration, not
    the version gate; the gate itself is tested explicitly with mocked versions below."""
    with mock.patch.object(db_bootstrap, 'MINIMUM_SQLITE_VERSION', (3, 0, 0)):
        yield


def test_ensure_db_creates_and_migrates(test_directory):
    """With no database file, ensure_db creates it and migrates to head."""
    db_file = get_db_file()
    assert not db_file.is_file()
    assert db_bootstrap.compare_db_version() == 'missing'

    assert db_bootstrap.ensure_db() is True

    assert db_file.is_file()
    assert db_bootstrap.compare_db_version() == 'current'
    with sqlite3.connect(db_file) as conn:
        version = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        assert version
        # Triggers and FTS5 tables were installed by the baseline.
        triggers = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
        assert triggers > 0
        fts_tables = {i[0] for i in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('file_group_fts', 'doc_section_fts')")}
        assert fts_tables == {'file_group_fts', 'doc_section_fts'}

    # Running again is a no-op.
    assert db_bootstrap.ensure_db() is True


def test_ensure_db_refuses_newer_database(test_directory):
    """A database from a NEWER WROLPi (unknown alembic revision) must not be written."""
    assert db_bootstrap.ensure_db() is True
    db_file = get_db_file()
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'future_revision_xyz'")
        conn.commit()

    assert db_bootstrap.compare_db_version() == 'ahead'
    assert db_bootstrap.ensure_db() is False
    # The database was not modified.
    with sqlite3.connect(db_file) as conn:
        assert conn.execute('SELECT version_num FROM alembic_version').fetchone()[0] == 'future_revision_xyz'


def test_compare_db_version_uninitialized_file(test_directory):
    """An empty/uninitialized file is treated like a fresh database."""
    db_file = get_db_file()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.touch()
    assert db_bootstrap.compare_db_version() == 'missing'
    assert db_bootstrap.ensure_db() is True
    assert db_bootstrap.compare_db_version() == 'current'


def test_bootstrap_lock(test_directory):
    """Only one process can hold the bootstrap lock."""
    with db_bootstrap.bootstrap_lock() as acquired:
        assert acquired is True
        with db_bootstrap.bootstrap_lock() as second:
            # flock is per-file-descriptor, so a second open in the same process CAN acquire it;
            # this just proves the context manager doesn't error or deadlock.
            assert second in (True, False)


def test_check_sqlite_environment_version_gate(test_directory):
    """SQLite older than the floor is refused; at/above the floor is accepted.

    Mocked versions so the test is deterministic regardless of the machine's SQLite (CI images
    have shipped 3.37 while the production floor is 3.40)."""
    with mock.patch.object(db_bootstrap, 'MINIMUM_SQLITE_VERSION', (3, 40, 0)):
        with mock.patch.object(db_bootstrap.sqlite3, 'sqlite_version_info', (3, 39, 9)), \
                mock.patch.object(db_bootstrap.sqlite3, 'sqlite_version', '3.39.9'):
            error = db_bootstrap.check_sqlite_environment(get_db_file())
            assert error and 'too old' in error
        with mock.patch.object(db_bootstrap.sqlite3, 'sqlite_version_info', (3, 40, 0)):
            assert db_bootstrap.check_sqlite_environment(get_db_file()) is None
        with mock.patch.object(db_bootstrap.sqlite3, 'sqlite_version_info', (3, 46, 1)):
            assert db_bootstrap.check_sqlite_environment(get_db_file()) is None


@pytest.mark.parametrize('fs_type', ['vfat', 'exfat', 'msdos', 'ntfs', 'fuseblk'])
def test_check_sqlite_environment_allows_wal_incompatible_fs_with_warning(test_directory, fs_type):
    """A FAT/exFAT/NTFS drive is allowed (with a warning), not refused.

    These filesystems cannot support SQLite WAL — it needs mmap shared-memory they don't provide,
    so `PRAGMA journal_mode=WAL` raises `(sqlite3.OperationalError) disk I/O error` (the failure
    seen on 10.0.0.8; the tell-tale sign was `Media directory has the wrong permissions: 0o40777`,
    since these filesystems can't store Unix permission bits).  Rather than crash the whole API,
    the engine degrades to a rollback journal, so the environment check must NOT refuse the drive
    — it only warns that performance is reduced."""
    with mock.patch.object(db_bootstrap, '_media_fs_type', return_value=fs_type), \
            mock.patch.object(db_bootstrap.logger, 'warning') as mock_warning:
        assert db_bootstrap.check_sqlite_environment(get_db_file()) is None
    assert mock_warning.call_count == 1
    assert 'WAL is unavailable' in mock_warning.call_args.args[0], 'expected a WAL-unavailable warning'


@pytest.mark.parametrize('fs_type', ['ext4', 'btrfs', 'xfs', 'f2fs'])
def test_check_sqlite_environment_allows_wal_compatible_fs(test_directory, fs_type):
    """Ordinary Linux filesystems support WAL and must not be refused."""
    with mock.patch.object(db_bootstrap, '_media_fs_type', return_value=fs_type):
        assert db_bootstrap.check_sqlite_environment(get_db_file()) is None


@pytest.mark.parametrize('fs_type', ['nfs', 'nfs4', 'cifs', 'fuse.sshfs'])
def test_check_sqlite_environment_refuses_network_fs(test_directory, fs_type):
    """Network filesystems remain refused: their locking is unsafe and no journal mode fixes it."""
    with mock.patch.object(db_bootstrap, '_media_fs_type', return_value=fs_type):
        error = db_bootstrap.check_sqlite_environment(get_db_file())
    assert error and fs_type in error


def test_unmounted_production_guard(test_directory):
    """An unmounted production media directory blocks DB creation/migration and db_up.

    Regression test for the shadow-database bug found on 10.0.0.8: after the media drive was
    unmounted, a worker's ORM connection created an empty wrolpi.db on the root filesystem and
    the bootstrap migrated it — because the old guard only refused when NO file existed."""
    import pathlib

    fake_media = mock.MagicMock(spec=pathlib.Path)
    fake_media.__str__ = lambda self: '/media/wrolpi'
    fake_media.is_mount.return_value = False
    fake_media.is_dir.return_value = True

    with mock.patch.object(db_bootstrap, 'PYTEST', False), \
            mock.patch.object(db_bootstrap, 'DOCKERIZED', False), \
            mock.patch.object(db_bootstrap.sys, 'platform', 'linux'):
        # Unmounted /media/* on a production linux host: guarded.
        assert db_bootstrap.media_directory_is_unmounted_production(fake_media) is True
        # Mounted: fine.
        fake_media.is_mount.return_value = True
        assert db_bootstrap.media_directory_is_unmounted_production(fake_media) is False
        # Custom (non-/media) directories are exempt (dev boxes).
        fake_media.is_mount.return_value = False
        fake_media.__str__ = lambda self: '/home/user/media'
        assert db_bootstrap.media_directory_is_unmounted_production(fake_media) is False

    # The guard must refuse ensure_db EVEN IF a database file already exists (an ORM connection
    # creates an empty file implicitly, so file-existence cannot be the condition).
    assert db_bootstrap.ensure_db() is True  # create a real DB in the test directory first
    with mock.patch.object(db_bootstrap, 'media_directory_is_unmounted_production', return_value=True):
        assert db_bootstrap.ensure_db() is False
