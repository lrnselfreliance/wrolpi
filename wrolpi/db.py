"""WROLPi's database: SQLite stored inside the media directory.

The database file lives at `<media directory>/config/wrolpi.db`, next to the YAML configs it
complements, so a user's entire library (files + configs + database) travels with the drive.

Engines are created lazily (the media directory must be known first) and use NullPool with a
fresh session per use.  Every connection gets the same PRAGMAs (WAL, busy_timeout, foreign keys)
via `create_wrolpi_engine` — use that factory for any engine touching a WROLPi database.
"""
import pathlib
import sqlite3
import threading
import types
from contextlib import contextmanager
from typing import Tuple, List, Union, Type, Generator, Any

import sqlalchemy
import sqlalchemy.exc
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from wrolpi.common import logger, Base
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# Toggled only by `get_immediate_db_session()` (below) while such a session is open on this thread,
# so the engine's `begin` listener knows to emit `BEGIN IMMEDIATE` instead of a deferred `BEGIN`.
_immediate_txn = threading.local()


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
    cannot support WAL: it needs mmap'd shared-memory those filesystems don't provide, so
    `PRAGMA journal_mode=WAL` raises `disk I/O error`.  There we fall back to a TRUNCATE rollback
    journal so the drive still works, at the cost of write-concurrency; `synchronous=FULL` keeps
    it crash-safe (WROLPi is off-grid, so power loss is expected).

    `journal_mode` is the mode chosen on a previous connection of the same engine: once WAL has
    been ruled out we skip re-attempting (and re-logging) it on every fresh NullPool connection."""
    # Driver-level autocommit; the `begin` listener emits BEGIN so SQLAlchemy's transactions still
    # work.  (pysqlite's implicit BEGIN is broken for SQLAlchemy, and PRAGMA journal_mode cannot
    # run inside a transaction.)
    dbapi_conn.isolation_level = None
    curs = dbapi_conn.cursor()
    try:
        if journal_mode != 'TRUNCATE':
            try:
                curs.execute('PRAGMA journal_mode=WAL')
                curs.execute('PRAGMA synchronous=NORMAL')
                journal_mode = 'WAL'
            except sqlite3.OperationalError:
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

    @event.listens_for(engine, 'begin')
    def _sqlite_do_begin(conn):
        # `get_immediate_db_session()` sessions take the write lock up front; everything else stays
        # deferred so readers never block (in WAL; see `_immediate_txn`).
        if getattr(_immediate_txn, 'active', False):
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


def get_db_context() -> Tuple[sqlalchemy.engine.Engine, Session]:
    """
    Get a DB engine and session.
    """
    from wrolpi.common import is_tempfile
    local_engine, session = _get_db_session()
    if PYTEST and not is_tempfile(local_engine.url.database or ''):
        raise ValueError(f'Running tests, but a test database is not being used!! {local_engine.url=}')
    return local_engine, session


@contextmanager
def get_db_session(commit: bool = False) -> Generator[Session, Any, None]:
    """
    Context manager that creates a DB session.  This will automatically rollback changes, unless `commit` is True.
    """
    _, session = get_db_context()
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
def get_immediate_db_session() -> Generator[Session, Any, None]:
    """A committing session that takes the SQLite write lock up front (`BEGIN IMMEDIATE`).

    Use this for read-then-write transactions (read some rows, then UPDATE/INSERT them).  A plain
    `get_db_session(commit=True)` begins *deferred* and only upgrades to a writer at its first
    write; if another connection holds the write lock at that moment, SQLite returns "database is
    locked" *immediately* — `busy_timeout` is skipped for lock upgrades to avoid deadlock.  Taking
    the write lock at BEGIN instead lets `busy_timeout` (30s) absorb the contention.

    The `_immediate_txn` flag is read by the engine's `begin` listener when the transaction opens
    (on the caller's first statement), so keep queries inside this `with` block.
    """
    previous = getattr(_immediate_txn, 'active', False)
    _immediate_txn.active = True
    try:
        with get_db_session(commit=True) as session:
            yield session
    finally:
        _immediate_txn.active = previous


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


