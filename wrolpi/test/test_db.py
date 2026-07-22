import sqlite3

from wrolpi.conftest import production_like_sessions
from wrolpi.db import get_db_session, get_immediate_db_session


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
