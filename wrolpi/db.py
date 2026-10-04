"""WROLPi's database: SQLite stored inside the media directory.

The database file lives at `<media directory>/config/wrolpi.db`, next to the YAML configs it
complements, so a user's entire library (files + configs + database) travels with the drive.

Engines are created lazily (the media directory must be known first) and use NullPool with a
fresh session per use.  Every connection gets the same PRAGMAs (WAL, busy_timeout, foreign keys)
via `create_wrolpi_engine` — use that factory for any engine touching a WROLPi database.
"""
import contextvars
import functools
import pathlib
import sqlite3
import threading
import types
from contextlib import contextmanager
from typing import Tuple, List, Union, Type, Generator, Any, ContextManager

import sqlalchemy
import sqlalchemy.exc
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from wrolpi.common import logger, Base
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# Set by `get_db_session(commit=True)` while its transaction is being opened, so the engine's `begin`
# listener knows to emit `BEGIN IMMEDIATE` instead of a deferred `BEGIN`.  A ContextVar rather than a
# `threading.local` because the writers that set it include coroutines: Sanic runs every request in
# its own asyncio task on one shared thread, and a thread-local would leak the flag between
# interleaved tasks -- arming it for a reader and disarming it under a writer.  Each asyncio task
# (and each thread) gets its own copy of a ContextVar, so worker-thread callers behave as before.
_immediate_txn = contextvars.ContextVar('wrolpi_immediate_txn', default=False)


# Set while serializing (`no_db_access`).  A query then is a lazy load or an expired-attribute refresh: hidden
# per-row SQL today, and a `MissingGreenlet` error under an async Session.  Holds the name of what is serializing.
_no_db_access = contextvars.ContextVar('wrolpi_no_db_access', default=None)
# Serializers that have already logged an unexpected query in this process (see `_refuse_query_while_serializing`).
_warned_serializers = set()
# Every unexpected query during tests, as (reason, statement).  Recorded as well as raised, so code that catches
# broad exceptions around a serializer cannot hide one; see the `no_unexpected_queries` fixture.
UNEXPECTED_QUERIES = list()


class UnexpectedQuery(RuntimeError):
    """SQL ran inside `no_db_access` (while serializing)."""


@contextmanager
def no_db_access(reason: str):
    """No SQL may run inside this block: the data it reads must already be loaded.

    A query inside raises `UnexpectedQuery` during tests.  In production it is logged once per `reason` and
    allowed, so a missed eager load costs a query, not a failed request."""
    token = _no_db_access.set(reason)
    try:
        yield
    finally:
        _no_db_access.reset(token)


def serializer(method):
    """Run a model's serializer (`__json__`) inside `no_db_access`."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with no_db_access(f'{type(self).__name__}.{method.__name__}'):
            return method(self, *args, **kwargs)

    return wrapper


def _refuse_query_while_serializing(conn, cursor, statement, parameters, context, executemany):
    reason = _no_db_access.get()
    if reason is None:
        return
    if PYTEST:
        UNEXPECTED_QUERIES.append((reason, statement))
        raise UnexpectedQuery(f'{reason} ran SQL while serializing: {statement}')
    if reason not in _warned_serializers:
        _warned_serializers.add(reason)
        logger.warning(f'{reason} ran SQL while serializing: a relationship or deferred column it reads was not '
                       f'loaded, or a commit expired the object: {statement}')


def _adapt_datetime(value):
    """Store datetimes from raw SQL exactly like SQLAlchemy does: naive UTC with microseconds."""
    from datetime import timezone
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime('%Y-%m-%d %H:%M:%S.%f')


# Keep raw-SQL parameter formats identical to the ORM's storage formats.
import datetime as _datetime  # noqa: E402

sqlite3.register_adapter(_datetime.datetime, _adapt_datetime)
sqlite3.register_adapter(_datetime.date, lambda value: value.isoformat())
sqlite3.register_adapter(pathlib.PosixPath, str)
sqlite3.register_adapter(pathlib.Path, str)


def get_db_file() -> pathlib.Path:
    """The SQLite database file: `<media directory>/config/wrolpi.db`."""
    from wrolpi.common import get_media_directory
    return get_media_directory() / 'config' / 'wrolpi.db'


def get_db_uri() -> str:
    return f'sqlite:///{get_db_file()}'


def _configure_sqlite_connection(dbapi_conn, journal_mode: str = None) -> str:
    """Apply WROLPi's PRAGMAs to a raw DBAPI connection; returns the journal mode actually set.

    WAL is preferred (readers never block writers, so the Sanic workers stay concurrent).  But
    FAT/exFAT/NTFS drives — common when a USB drive is formatted for Windows compatibility —
    cannot support WAL: it needs mmap'd shared-memory those filesystems don't provide.  SQLite may
    reject WAL either by raising `disk I/O error` OR by silently keeping the current rollback
    journal (`PRAGMA journal_mode` returns the mode it actually selected, not necessarily the one
    requested), so we confirm the returned mode rather than assume the request succeeded.  When WAL
    is unavailable we fall back to a TRUNCATE rollback journal so the drive still works, at the cost
    of write-concurrency; `synchronous=FULL` keeps it crash-safe (WROLPi is off-grid, so power loss
    is expected).

    `journal_mode` is the mode chosen on a previous connection of the same engine: once WAL has
    been ruled out we skip re-attempting (and re-logging) it on every fresh NullPool connection."""
    # Driver-level autocommit; the `begin` listener emits BEGIN so SQLAlchemy's transactions still
    # work.  (pysqlite's implicit BEGIN is broken for SQLAlchemy, and PRAGMA journal_mode cannot
    # run inside a transaction.)
    dbapi_conn.isolation_level = None
    curs = dbapi_conn.cursor()
    try:
        if journal_mode != 'TRUNCATE':
            wal_ok = False
            try:
                curs.execute('PRAGMA journal_mode=WAL')
                row = curs.fetchone()
                wal_ok = bool(row) and str(row[0]).lower() == 'wal'
            except sqlite3.OperationalError:
                wal_ok = False
            if wal_ok:
                curs.execute('PRAGMA synchronous=NORMAL')
                journal_mode = 'WAL'
            else:
                logger.warning('SQLite WAL is unavailable on this filesystem (exFAT/FAT/NTFS?); '
                               'falling back to a slower TRUNCATE rollback journal with reduced '
                               'write-concurrency.  Reformat the media drive as ext4 for best performance.')
                journal_mode = 'TRUNCATE'
        if journal_mode == 'TRUNCATE':
            curs.execute('PRAGMA journal_mode=TRUNCATE')
            curs.execute('PRAGMA synchronous=FULL')
        curs.execute('PRAGMA busy_timeout=30000')
        curs.execute('PRAGMA foreign_keys=ON')
        curs.execute('PRAGMA recursive_triggers=ON')
        return journal_mode
    finally:
        curs.close()


def create_wrolpi_engine(target: Union[str, pathlib.Path]) -> sqlalchemy.engine.Engine:
    """Create a SQLAlchemy engine for a WROLPi SQLite database.

    The single place every WROLPi engine is built (production, tests, alembic) so that all
    connections get identical PRAGMAs and transactional behavior."""
    uri = str(target) if str(target).startswith('sqlite') else f'sqlite:///{target}'
    engine = sqlalchemy.create_engine(
        uri,
        poolclass=NullPool,
        # NullPool + executor threads mean connections may be closed on another thread.
        connect_args=dict(check_same_thread=False, timeout=30),
    )

    # The journal mode is decided on the first connection and reused for the engine's life, so WAL
    # is not re-attempted (and re-logged) on every fresh NullPool connection.
    journal_state = {'mode': None}

    @event.listens_for(engine, 'connect')
    def _sqlite_on_connect(dbapi_conn, _):
        journal_state['mode'] = _configure_sqlite_connection(dbapi_conn, journal_state['mode'])

    event.listen(engine, 'before_cursor_execute', _refuse_query_while_serializing)

    @event.listens_for(engine, 'begin')
    def _sqlite_do_begin(conn):
        # Write sessions (`commit=True`) take the write lock up front; read sessions stay deferred
        # so readers never block (in WAL; see `_immediate_txn`).
        if _immediate_txn.get():
            conn.execute('BEGIN IMMEDIATE')
        else:
            conn.execute('BEGIN')

    return engine


_engine_lock = threading.Lock()
_engine: sqlalchemy.engine.Engine = None
_session_maker: sessionmaker = None


def get_engine() -> sqlalchemy.engine.Engine:
    """The lazy singleton engine for the WROLPi database.

    Created on first use (the media directory must be known by then); recreated automatically if
    the media directory (and therefore the database file) changes."""
    global _engine, _session_maker
    with _engine_lock:
        db_file = get_db_file()
        if _engine is None or _engine.url.database != str(db_file):
            if _engine is not None:
                _engine.dispose()
            logger.info(f'Creating database engine: {db_file}')
            _engine = create_wrolpi_engine(db_file)
            _session_maker = sessionmaker(bind=_engine)
        return _engine


def _get_db_session():
    """
    This function allows the database to be wrapped during testing.  See: wrolpi.conftest.test_session
    """
    engine = get_engine()
    session = _session_maker()
    return engine, session


def _refuse_non_test_engine(engine: sqlalchemy.engine.Engine):
    from wrolpi.common import is_tempfile
    if PYTEST and not is_tempfile(engine.url.database or ''):
        raise ValueError(f'Running tests, but a test database is not being used!! {engine.url=}')


def get_db_context() -> Tuple[sqlalchemy.engine.Engine, Session]:
    """
    Get a DB engine and session.
    """
    local_engine, session = _get_db_session()
    _refuse_non_test_engine(local_engine)
    return local_engine, session


class RequestSession(Session):
    """A Session that keeps one connection for its whole life, opened at its first statement.

    An engine-bound Session releases its connection at every commit, and NullPool then closes it, so a
    request that commits and keeps working would reconnect (a connect plus PRAGMAs each time).  This
    Session binds itself to a single Connection, created lazily, so transactions after a commit reuse
    it.  `close()` releases the connection."""

    def __init__(self, engine: sqlalchemy.engine.Engine, **kwargs):
        super().__init__(**kwargs)
        self._request_engine = engine
        self._request_connection = None

    def get_bind(self, mapper=None, clause=None, **kwargs):
        if self._request_connection is None:
            self._request_connection = self._request_engine.connect()
        return self._request_connection

    def close(self):
        try:
            super().close()
        finally:
            if self._request_connection is not None:
                self._request_connection.close()
                self._request_connection = None


def _get_request_session() -> Tuple[sqlalchemy.engine.Engine, Session]:
    """Create the Session for one API request.

    This function allows the database to be wrapped during testing.  See: wrolpi.conftest.test_session
    """
    engine = get_engine()
    return engine, RequestSession(engine)


@contextmanager
def get_db_session(commit: bool = False) -> Generator[Session, Any, None]:
    """
    Context manager that creates a DB session.  This will automatically rollback changes, unless `commit` is True.

    `commit=True` declares write intent, so the transaction begins as a writer (`BEGIN IMMEDIATE`)
    rather than deferred.  A deferred transaction that upgrades to a writer at its first INSERT
    fails *instantly* with "database is locked" if any other connection wrote in the meantime —
    SQLite skips `busy_timeout` for lock upgrades, because waiting cannot help a snapshot that is
    already stale.  Taking the lock at BEGIN lets `busy_timeout` (30s) absorb the contention
    instead.  Rails and Django both made IMMEDIATE the default for the same reason; a per-call-site
    opt-in only works if every author remembers, and read-then-write is the normal shape of a write.

    The cost is that writers serialize from BEGIN rather than from their first write, so a write
    transaction must stay short — do the slow parts (globbing, ffprobe, indexing, big joins) in a
    read session or outside a session, then write what you computed.  Readers are unaffected: WAL
    readers never block, and `commit=False` sessions stay deferred.
    """
    _, session = get_db_context()
    if commit:
        # Open the transaction here rather than letting it begin lazily at the caller's first
        # statement.  Two reasons: the write lock is taken up front (the whole point), and the
        # `_immediate_txn` flag lives only across this synchronous call.  A flag held for the
        # session's lifetime would be copied into every task the caller spawns --
        # `asyncio.create_task` snapshots the Context -- and the parent's `reset()` cannot reach a
        # child's copy, so those tasks would issue BEGIN IMMEDIATE for their *read* sessions.
        token = _immediate_txn.set(True)
        try:
            session.connection()
        finally:
            _immediate_txn.reset(token)
    try:
        yield session
        if commit:
            session.commit()
    except sqlalchemy.exc.DatabaseError:
        session.rollback()
        raise
    finally:
        # Rollback only if a transaction hasn't been committed.
        # In tests, the test_session fixture manages the session lifecycle,
        # so we should not rollback here - that would undo other test operations.
        if not PYTEST and session.transaction.is_active:
            session.rollback()


@contextmanager
def get_db_curs(commit: bool = False) -> Generator[sqlite3.Cursor, Any, None]:
    """
    Context manager that yields a `sqlite3.Cursor` to execute raw SQL statements.

    Rows are `sqlite3.Row` (index and name access; `dict(row)` works).  SQL uses the sqlite3
    paramstyle: `?` positional, `:name` named (a statement must use only one style).
    """
    local_engine, session = get_db_context()
    if PYTEST:
        # During tests, use the session's connection to avoid lock issues.
        # The test_session is mocked to be shared, so getting a raw_connection would
        # create a new connection that blocks waiting for locks held by test_session.
        connection = session.connection().connection
        curs = connection.cursor()
        curs.row_factory = sqlite3.Row
        try:
            yield curs
            if commit:
                connection.commit()
        except sqlalchemy.exc.DatabaseError:
            session.rollback()
            raise
        # Don't rollback in finally during tests - test_session manages this
    else:
        connection = local_engine.raw_connection()
        curs = connection.cursor()
        curs.row_factory = sqlite3.Row
        try:
            if commit:
                # Take the write lock up front; busy_timeout absorbs contention.  (A deferred
                # transaction upgrading to a write mid-way can deadlock under concurrency.)
                curs.execute('BEGIN IMMEDIATE')
            yield curs
            if commit:
                connection.commit()
        except sqlalchemy.exc.DatabaseError:
            session.rollback()
            raise
        finally:
            # Rollback only if a transaction hasn't been committed.
            if connection.in_transaction:
                connection.rollback()
            connection.close()


@contextmanager
def session_curs(session: Session) -> Generator[sqlite3.Cursor, Any, None]:
    """A raw `sqlite3.Cursor` on `session`'s connection, inside the Session's transaction.

    Use it for raw SQL in code that is handed a Session, so the SQL shares that Session's connection
    instead of opening another (as `get_db_curs` does).  Pending ORM changes are flushed first, so raw
    SQL sees them.  Writes through the cursor commit or roll back with the Session.  Rows are
    `sqlite3.Row`."""
    session.flush()
    curs = session.connection().connection.cursor()
    curs.row_factory = sqlite3.Row
    try:
        yield curs
    finally:
        curs.close()


def _session_has_connection(session: Session) -> bool:
    """True if the Session's transaction has already connected (and so already emitted BEGIN)."""
    # SQLAlchemy 1.3 has no public API for this; 2.0 replaces it with `session.in_transaction()`.
    transaction = session.transaction
    return transaction is not None and bool(transaction._connections)


class RequestDB:
    """The database handle for one API request: `request.ctx.db`.

    One Session per request, and raw cursors (`curs()`) on that Session's connection, so a request
    uses at most one SQLite connection.  Creating the handle does no I/O; SQLAlchemy connects at the
    first statement, so requests that never touch the database never connect.  The response
    middleware calls `finish()`.

    Reads begin deferred, so they never take the write lock.  A handler that writes does so inside
    `write()`, which begins the transaction as a writer and commits when the block exits; the write
    lock is held only for that block, never for the rest of the handler or for background work the
    handler starts afterwards.  (See `get_db_session` for why a writer must take the lock at BEGIN.)

    Code that runs outside a request (workers, switches, perpetual loops) uses `get_db_session` and
    `get_db_curs`; they open their own connection.
    """

    def __init__(self):
        self.engine, self.session = _get_request_session()
        _refuse_non_test_engine(self.engine)

    def curs(self) -> ContextManager[sqlite3.Cursor]:
        """A raw `sqlite3.Cursor` on this request's connection (see `session_curs`).  Its writes commit or
        roll back with the request, or with the enclosing `write()` block."""
        return session_curs(self.session)

    @contextmanager
    def write(self) -> Generator[Session, Any, None]:
        """Begin a write transaction (BEGIN IMMEDIATE) on the request's connection; commit on exit.

        If the request already read, its deferred transaction is committed first: SQLite cannot upgrade
        a deferred transaction to a writer under `busy_timeout`, and its snapshot is stale for a writer
        anyway.  Any changes pending in the Session at that point are committed with it."""
        session = self.session
        if _session_has_connection(session):
            session.commit()
        token = _immediate_txn.set(True)
        try:
            session.connection()
        finally:
            _immediate_txn.reset(token)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def finish(self, ok: bool):
        """End the request: commit if `ok`, otherwise roll back; then release the connection."""
        try:
            if ok:
                self.session.commit()
            else:
                self.session.rollback()
        except Exception:
            self.session.rollback()
            raise
        finally:
            # In tests the shared `test_session` fixture owns the Session's lifecycle.
            if not PYTEST:
                self.session.close()


def get_ranked_models(ranked_primary_keys: List, model: Type[Base], session: Session) -> List[Base]:
    """Get all objects whose primary keys are in the `ranked_primary_keys`, preserve their order."""
    pkey = sqlalchemy.inspect(model).primary_key[0]
    pkey_name = pkey.name
    results = list(session.query(model).filter(pkey.in_(ranked_primary_keys)).all())
    results = sorted(results, key=lambda i: ranked_primary_keys.index(getattr(i, pkey_name)))
    return results


# SQLite's default variable limit; multi-row VALUES clauses must stay under it.
SQLITE_MAX_VARIABLES = 32_000


def values_clause(rows: Union[List, Generator]) -> Tuple[str, list]:
    """Build a multi-row VALUES clause and its flat parameter list.

    >>> values_clause([(1, 'a'), (2, 'b')])
    ('(?,?),(?,?)', [1, 'a', 2, 'b'])

    The caller must chunk `rows` so that `len(rows) * width` stays under SQLITE_MAX_VARIABLES."""
    rows = list(rows) if isinstance(rows, types.GeneratorType) else rows
    width = len(rows[0])
    if len(rows) * width > SQLITE_MAX_VARIABLES:
        raise RuntimeError(f'values_clause: too many parameters ({len(rows)} rows x {width}); chunk the rows')
    row_placeholders = '(' + ','.join(['?'] * width) + ')'
    sql = ','.join([row_placeholders] * len(rows))
    params = [value for row in rows for value in row]
    return sql, params


def named_placeholders(prefix: str, values: List, params: dict) -> str:
    """Add each value to `params` under a generated name, return the comma-joined placeholders.

    >>> params = dict()
    >>> named_placeholders('tag_name', ['one', 'two'], params)
    ':tag_name_0, :tag_name_1'
    """
    names = []
    for idx, value in enumerate(values):
        name = f'{prefix}_{idx}'
        params[name] = value
        names.append(f':{name}')
    return ', '.join(names)


def json_each_in(param_name: str) -> str:
    """An IN-clause subquery over a JSON array parameter; bind `json.dumps(list)` as the parameter.

    Immune to SQLite's variable-count limit regardless of list size."""
    return f'(SELECT value FROM json_each(:{param_name}))'


def parse_db_datetime(value: Union[str, None]):
    """Parse a datetime TEXT value read by a raw cursor into a UTC-aware datetime.

    (The ORM's TZDateTime does this automatically; raw cursors return the stored TEXT.)"""
    if not value:
        return None
    if isinstance(value, _datetime.datetime):
        return value
    try:
        parsed = _datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        parsed = _datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return parsed.replace(tzinfo=_datetime.timezone.utc)


