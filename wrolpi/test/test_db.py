import sqlite3

from wrolpi.conftest import production_like_sessions
from wrolpi.db import get_db_session, get_immediate_db_session, _configure_sqlite_connection


class _FakeCursor:
    """A minimal DBAPI cursor that records executed statements and simulates WAL rejection.

    A FAT/exFAT/NTFS drive rejects WAL either by raising `disk I/O error` (`fail_wal`) or by
    silently keeping the current rollback journal — `PRAGMA journal_mode` returns the mode SQLite
    actually selected, so a WAL request can return e.g. 'delete' without raising (`wal_returns`)."""

    def __init__(self, fail_wal: bool, wal_returns: str = 'wal'):
        self.fail_wal = fail_wal
        self.wal_returns = wal_returns
        self.executed = []
        self._last_row = None

    def execute(self, statement):
        if statement == 'PRAGMA journal_mode=WAL':
            if self.fail_wal:
                raise sqlite3.OperationalError('disk I/O error')
            self._last_row = (self.wal_returns,)
        elif statement.startswith('PRAGMA journal_mode='):
            self._last_row = (statement.split('=', 1)[1].lower(),)
        else:
            self._last_row = None
        self.executed.append(statement)

    def fetchone(self):
        return self._last_row

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, fail_wal: bool, wal_returns: str = 'wal'):
        self._cursor = _FakeCursor(fail_wal, wal_returns)
        self.isolation_level = 'DEFERRED'

    def cursor(self):
        return self._cursor


def test_configure_connection_uses_wal_when_supported():
    """On a normal filesystem the connection is configured for WAL + synchronous=NORMAL."""
    conn = _FakeConnection(fail_wal=False)
    mode = _configure_sqlite_connection(conn)
    assert mode == 'WAL'
    assert conn.isolation_level is None
    assert 'PRAGMA journal_mode=WAL' in conn._cursor.executed
    assert 'PRAGMA synchronous=NORMAL' in conn._cursor.executed
    assert 'PRAGMA busy_timeout=30000' in conn._cursor.executed
    assert 'PRAGMA foreign_keys=ON' in conn._cursor.executed


def test_configure_connection_falls_back_to_rollback_journal_on_wal_failure():
    """When WAL raises `disk I/O error` (exFAT/FAT/NTFS), fall back to a crash-safe rollback journal.

    Regression test for the whole-API outage on 10.0.0.8: an exFAT media drive made
    `PRAGMA journal_mode=WAL` raise on every connection.  The connection must still come up, using
    a TRUNCATE rollback journal with synchronous=FULL (WROLPi is off-grid; power loss is expected)."""
    conn = _FakeConnection(fail_wal=True)
    mode = _configure_sqlite_connection(conn)
    assert mode == 'TRUNCATE'
    assert 'PRAGMA journal_mode=TRUNCATE' in conn._cursor.executed
    assert 'PRAGMA synchronous=FULL' in conn._cursor.executed
    # WAL's less-durable synchronous setting must NOT be applied on a rollback journal.
    assert 'PRAGMA synchronous=NORMAL' not in conn._cursor.executed
    # The connection is still fully configured.
    assert 'PRAGMA busy_timeout=30000' in conn._cursor.executed
    assert 'PRAGMA foreign_keys=ON' in conn._cursor.executed


def test_configure_connection_falls_back_when_wal_silently_refused():
    """SQLite can refuse WAL WITHOUT raising, returning the still-active rollback mode instead.

    The requested mode is not always the applied mode, so we must confirm `PRAGMA journal_mode`'s
    return value.  Here WAL 'succeeds' but reports 'delete'; that must trigger the durable fallback
    (TRUNCATE + synchronous=FULL), not cache WAL with the weaker synchronous=NORMAL."""
    conn = _FakeConnection(fail_wal=False, wal_returns='delete')
    mode = _configure_sqlite_connection(conn)
    assert mode == 'TRUNCATE'
    assert 'PRAGMA journal_mode=TRUNCATE' in conn._cursor.executed
    assert 'PRAGMA synchronous=FULL' in conn._cursor.executed
    assert 'PRAGMA synchronous=NORMAL' not in conn._cursor.executed


def test_configure_connection_does_not_reattempt_wal_once_ruled_out():
    """Once WAL is known-unavailable for an engine, later connections skip (and don't re-log) it."""
    conn = _FakeConnection(fail_wal=True)
    # `journal_mode='TRUNCATE'` is the remembered decision from a previous connection.
    mode = _configure_sqlite_connection(conn, journal_mode='TRUNCATE')
    assert mode == 'TRUNCATE'
    assert 'PRAGMA journal_mode=WAL' not in conn._cursor.executed
    assert 'PRAGMA journal_mode=TRUNCATE' in conn._cursor.executed


def _probe_write_lock_is_held(db_file: str) -> bool:
    """Return True if a competing connection cannot immediately take the write lock.

    Uses a zero busy-timeout so the probe fails instantly if another connection holds a
    RESERVED (write) lock, rather than waiting.  In WAL mode a plain reader holds no such
    lock, so this only returns True when a writer transaction is actually in progress.
    """
    probe = sqlite3.connect(db_file, timeout=0)
    try:
        probe.execute('PRAGMA busy_timeout=0')
        try:
            probe.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                return True
            raise
        probe.execute('ROLLBACK')
        return False
    finally:
        probe.close()


def test_immediate_session_takes_write_lock_up_front(test_session):
    """`get_immediate_db_session` must acquire the SQLite write lock at BEGIN.

    Regression test for `database is locked` on `UPDATE download SET last_download_attempt`:
    a deferred (read-then-write) transaction that tries to upgrade its lock while another
    connection holds the write lock gets SQLITE_BUSY *immediately* — busy_timeout is ignored
    for lock upgrades to avoid deadlock.  Taking the write lock up front (BEGIN IMMEDIATE)
    lets busy_timeout absorb the contention instead of erroring instantly.
    """
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with get_immediate_db_session() as session:
            # Trigger the transaction's BEGIN with a trivial read (as the download dispatcher
            # does before writing).  This session already holds the write lock.
            session.execute('SELECT 1')
            assert _probe_write_lock_is_held(db_file), \
                'immediate session did not hold the write lock after BEGIN'


def test_plain_write_session_stays_deferred(test_session):
    """A plain `get_db_session(commit=True)` stays deferred (no write lock until it actually writes).

    Only `get_immediate_db_session` opts into the up-front write lock, so ordinary write sessions
    keep WAL read-concurrency and don't serialize behind each other at BEGIN.
    """
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with get_db_session(commit=True) as session:
            session.execute('SELECT 1')
            assert not _probe_write_lock_is_held(db_file), \
                'plain write session unexpectedly holds the write lock before writing'


def test_read_session_does_not_take_write_lock(test_session):
    """A read-only `get_db_session()` must stay deferred so WAL read-concurrency is preserved."""
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with get_db_session() as session:
            session.execute('SELECT 1')
            assert not _probe_write_lock_is_held(db_file), \
                'read-only session unexpectedly holds the write lock'
