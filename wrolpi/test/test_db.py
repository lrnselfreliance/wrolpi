import asyncio
import sqlite3

import pytest

from wrolpi.conftest import production_like_sessions, probe_write_lock_is_held
from wrolpi.db import get_db_session, _configure_sqlite_connection


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


def test_write_session_takes_write_lock_up_front(test_session):
    """`get_db_session(commit=True)` must acquire the SQLite write lock at BEGIN.

    Regression test for `database is locked` on `UPDATE download SET last_download_attempt`:
    a deferred (read-then-write) transaction that tries to upgrade its lock while another
    connection holds the write lock gets SQLITE_BUSY *immediately* — busy_timeout is ignored
    for lock upgrades to avoid deadlock.  Taking the write lock up front (BEGIN IMMEDIATE)
    lets busy_timeout absorb the contention instead of erroring instantly.  `commit=True` is
    the declaration of write intent, so it is what arms this — no opt-in helper to forget.
    """
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with get_db_session(commit=True) as session:
            # Trigger the transaction's BEGIN with a trivial read (as the download dispatcher
            # does before writing).  This session already holds the write lock.
            session.execute('SELECT 1')
            assert probe_write_lock_is_held(db_file), \
                'immediate session did not hold the write lock after BEGIN'


def test_read_session_does_not_take_write_lock(test_session):
    """A read-only `get_db_session()` must stay deferred so WAL read-concurrency is preserved."""
    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with get_db_session() as session:
            session.execute('SELECT 1')
            assert not probe_write_lock_is_held(db_file), \
                'read-only session unexpectedly holds the write lock'


@pytest.mark.asyncio
async def test_background_task_does_not_inherit_write_intent(test_session):
    """A task spawned while a write session is open must not inherit its write intent.

    `asyncio.create_task` copies the current Context, so a ContextVar set for the duration of a
    write session is inherited by every background task the session's code starts -- permanently,
    because the parent's `reset()` cannot reach the child's copy.  `create_downloads` spawns
    `dispatch_downloads` exactly that way, so every user-created download would leave that task
    issuing BEGIN IMMEDIATE for its *read* sessions, serializing reads behind the write lock.
    """
    db_file = test_session.get_bind().url.database
    held_during_child_read = dict()

    async def child():
        with get_db_session() as session:  # A read session: it must stay deferred.
            session.execute('SELECT 1')
            held_during_child_read['held'] = probe_write_lock_is_held(db_file)

    with production_like_sessions(test_session):
        with get_db_session(commit=True) as session:
            session.execute('SELECT 1')
            task = asyncio.create_task(child())
        # The write session has committed; only the child's own session can hold the lock now.
        await task

    assert held_during_child_read['held'] is False, \
        'a read session in a spawned task took the write lock, inheriting the parent write intent'
