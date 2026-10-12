"""Read-only SQL access to the WROLPi database, for advanced users and agents (the WROLPi MCP).

Disabled unless `allow_database_query: true` is set in wrolpi.yaml; there is no UI for this setting.

A query can never change the database:
    * The connection is opened with `mode=ro`, so SQLite itself refuses every write.
    * An authorizer permits only reads (SELECT, CTEs, functions, and introspection PRAGMAs), so a statement
      cannot ATTACH another file, create TEMP objects, or change a PRAGMA.
A query cannot monopolize the device:
    * A progress handler interrupts it after `QUERY_TIMEOUT` seconds (this also bounds how long it pins a
      WAL snapshot).
    * SQLite refuses to build a value longer than `MAX_VALUE_LENGTH`, or a row wider than `MAX_COLUMNS`.
    * Rows are read one at a time; long values are cut to `MAX_CELL_LENGTH`, and rows stop at `MAX_LIMIT` or once
      the response holds `MAX_RESPONSE_LENGTH` characters.
"""
import asyncio
import contextlib
import sqlite3
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import List, Optional

from sanic import Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import json_response
from wrolpi.common import logger, get_wrolpi_config
from wrolpi.db import get_db_file
from wrolpi.errors import DatabaseQueryDisabled, InvalidDatabaseQuery
from wrolpi.schema import JSONErrorResponse

logger = logger.getChild(__name__)

DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
MAX_CELL_LENGTH = 10_000
MAX_RESPONSE_LENGTH = 5_000_000
# Larger than any value WROLPi stores (a document's text), far smaller than SQLite's 1 GB default.
MAX_VALUE_LENGTH = 32 * 1024 * 1024
MAX_COLUMNS = 100
QUERY_TIMEOUT = 10.0
# How many SQLite VM instructions run between timeout checks.
PROGRESS_INTERVAL = 10_000

ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}
# PRAGMAs which only read, whatever their argument.  Every other PRAGMA (e.g. `PRAGMA foreign_keys=OFF`) is refused.
ALLOWED_PRAGMAS = {
    # FTS5 reads this when it opens a table, through the authorizer, on SQLite 3.46 (Debian 13).
    'data_version',
    'foreign_key_list',
    'index_info',
    'index_list',
    'index_xinfo',
    'table_info',
    'table_list',
    'table_xinfo',
}
DENIED_FUNCTIONS = {'load_extension'}


def _authorizer(action: int, arg1: Optional[str], arg2: Optional[str], _db: Optional[str], _trigger: Optional[str]):
    if action == sqlite3.SQLITE_PRAGMA:
        if arg1 and arg1.lower() in ALLOWED_PRAGMAS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and arg2 and arg2.lower() in DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    if action in ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


@contextlib.contextmanager
def read_only_connection(timeout: float = QUERY_TIMEOUT):
    """A connection to the WROLPi database which can only read, and which interrupts any statement still running
    `timeout` seconds after the connection was opened."""
    conn = sqlite3.connect(f'file:{get_db_file()}?mode=ro', uri=True, timeout=5, check_same_thread=False)
    try:
        deadline = time.monotonic() + timeout
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), PROGRESS_INTERVAL)
        conn.set_authorizer(_authorizer)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_LENGTH)
        conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, MAX_COLUMNS)
        yield conn
    finally:
        conn.close()


def _cell(value):
    if isinstance(value, bytes):
        return f'<blob {len(value)} bytes>'
    if isinstance(value, str) and len(value) > MAX_CELL_LENGTH:
        return value[:MAX_CELL_LENGTH] + f'... <truncated {len(value) - MAX_CELL_LENGTH} characters>'
    return value


def _cell_length(value) -> int:
    return len(value) if isinstance(value, str) else 8


def _raise_query_error(e: sqlite3.Error):
    message = str(e)
    if isinstance(e, sqlite3.OperationalError) and message == 'interrupted':
        message = f'Query exceeded the {QUERY_TIMEOUT:g} second time limit'
    elif 'not authorized' in message or 'authorization denied' in message:
        message = 'Only read-only queries (SELECT) are allowed'
    elif 'too big' in message:
        message = f'A value is too large (over {MAX_VALUE_LENGTH} bytes)'
    raise InvalidDatabaseQuery(message) from e


def run_query(sql: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Run one read-only statement, return at most `limit` rows."""
    if not sql or not sql.strip():
        raise InvalidDatabaseQuery('Query is empty')
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    start = time.monotonic()
    rows, truncated, response_length = [], False, 0
    with read_only_connection() as conn:
        try:
            curs = conn.execute(sql)
            columns = [i[0] for i in curs.description or []]
            # One row at a time, so only the kept (truncated) values are held.
            for row in curs:
                if len(rows) >= limit or response_length >= MAX_RESPONSE_LENGTH:
                    truncated = True
                    break
                row = [_cell(i) for i in row]
                response_length += sum(_cell_length(i) for i in row)
                rows.append(row)
        except sqlite3.Error as e:
            _raise_query_error(e)
        except sqlite3.Warning as e:
            # Python refuses more than one statement.
            raise InvalidDatabaseQuery(str(e)) from e

    return dict(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed=round(time.monotonic() - start, 3),
    )


def _is_fts_shadow_table(name: str, virtual_tables: List[str]) -> bool:
    return any(name.startswith(f'{i}_') for i in virtual_tables)


def get_schema() -> List[dict]:
    """Describe every table and view (but not SQLite internals or FTS5's shadow tables), with the foreign key each
    column references."""
    with read_only_connection() as conn:
        objects = conn.execute(
            "SELECT name, type, sql FROM sqlite_master"
            " WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        virtual_tables = [name for name, _, sql in objects if sql and sql.upper().startswith('CREATE VIRTUAL TABLE')]

        tables = []
        for name, type_, sql in objects:
            if _is_fts_shadow_table(name, virtual_tables):
                continue
            is_virtual = name in virtual_tables
            # How this table joins to others, e.g. {'channel_id': 'channel.id'}.
            references = {
                from_: f'{table}.{to}' for _, _, table, from_, to, *_ in conn.execute(
                    'SELECT * FROM pragma_foreign_key_list(?)', (name,)).fetchall()
            }
            columns = [
                dict(name=col_name, type=col_type, not_null=bool(not_null), primary_key=bool(pk),
                     references=references.get(col_name))
                for _, col_name, col_type, not_null, _, pk in conn.execute(
                    'SELECT * FROM pragma_table_info(?)', (name,)).fetchall()
            ]
            indexes = []
            if type_ == 'table' and not is_virtual:
                for _, index_name, unique, *_ in conn.execute(
                        'SELECT * FROM pragma_index_list(?)', (name,)).fetchall():
                    index_columns = [i[2] for i in conn.execute(
                        'SELECT * FROM pragma_index_info(?)', (index_name,)).fetchall()]
                    indexes.append(dict(name=index_name, unique=bool(unique), columns=index_columns))
            table = dict(
                name=name,
                type='virtual' if is_virtual else type_,
                columns=columns,
                indexes=indexes,
            )
            if is_virtual or type_ == 'view':
                # The definition explains an FTS5 table's tokenizer and content table, or a view's query.
                table['sql'] = sql
            tables.append(table)
    return tables


def check_database_query_allowed():
    if not get_wrolpi_config().allow_database_query:
        raise DatabaseQueryDisabled()


db_query_bp = Blueprint('DatabaseQuery', url_prefix='/api/db')


@dataclass
class DatabaseQueryRequest:
    sql: str
    limit: Optional[int] = DEFAULT_LIMIT


@dataclass
class DatabaseQueryResponse:
    columns: List[str]
    rows: List[list]
    row_count: int
    truncated: bool
    elapsed: float


@dataclass
class DatabaseSchemaResponse:
    tables: List[dict] = field(default_factory=list)


@db_query_bp.post('/query')
@openapi.definition(
    description='Run one read-only SQL statement (SELECT) against the WROLPi database.  Requires'
                ' `allow_database_query: true` in wrolpi.yaml.',
    body=DatabaseQueryRequest,
)
@openapi.response(HTTPStatus.OK, DatabaseQueryResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, JSONErrorResponse)
@openapi.response(HTTPStatus.FORBIDDEN, JSONErrorResponse)
@validate(DatabaseQueryRequest)
async def post_query(_: Request, body: DatabaseQueryRequest):
    check_database_query_allowed()
    result = await asyncio.to_thread(run_query, body.sql, body.limit)
    return json_response(result)


@db_query_bp.get('/schema')
@openapi.definition(
    description='Describe the tables, columns, and indexes of the WROLPi database.  Requires'
                ' `allow_database_query: true` in wrolpi.yaml.',
)
@openapi.response(HTTPStatus.OK, DatabaseSchemaResponse)
@openapi.response(HTTPStatus.FORBIDDEN, JSONErrorResponse)
async def get_schema_request(_: Request):
    check_database_query_allowed()
    tables = await asyncio.to_thread(get_schema)
    return json_response(dict(tables=tables))
