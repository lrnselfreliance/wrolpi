import json
from http import HTTPStatus
from unittest import mock

import pytest

from wrolpi import db_query
from wrolpi.common import get_wrolpi_config
from wrolpi.db import get_db_file


@pytest.fixture
def allow_database_query(test_wrolpi_config):
    get_wrolpi_config().allow_database_query = True
    yield
    get_wrolpi_config().allow_database_query = False


async def post_query(async_client, sql: str, **kwargs):
    body = dict(sql=sql, **kwargs)
    return await async_client.post('/api/db/query', content=json.dumps(body))


@pytest.mark.asyncio
async def test_database_query_disabled_by_default(test_session, async_client, test_wrolpi_config):
    """Both endpoints refuse until the setting is enabled in wrolpi.yaml."""
    assert get_wrolpi_config().allow_database_query is False

    request, response = await post_query(async_client, 'SELECT 1')
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json['code'] == 'DATABASE_QUERY_DISABLED'

    request, response = await async_client.get('/api/db/schema')
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json['code'] == 'DATABASE_QUERY_DISABLED'


@pytest.mark.asyncio
async def test_database_query_enabled_by_config_import(test_session, async_client, test_wrolpi_config):
    """An advanced user enables queries by editing wrolpi.yaml and importing it; there is no UI for it."""
    config = get_wrolpi_config()
    config.dump_config()
    contents = test_wrolpi_config.read_text()
    assert 'allow_database_query: false' in contents
    test_wrolpi_config.write_text(contents.replace('allow_database_query: false', 'allow_database_query: true'))

    request, response = await async_client.post('/api/config/import',
                                                 content=json.dumps(dict(file_name='wrolpi.yaml')))
    assert response.status_code == HTTPStatus.NO_CONTENT
    try:
        request, response = await post_query(async_client, 'SELECT 1 AS one')
        assert response.status_code == HTTPStatus.OK, response.json
        assert response.json['rows'] == [[1]]
    finally:
        config.allow_database_query = False


@pytest.mark.asyncio
async def test_database_query_select(test_session, async_client, allow_database_query, tag_factory):
    """A SELECT returns committed rows, with column names."""
    await tag_factory('one')
    await tag_factory('two')
    test_session.commit()

    request, response = await post_query(async_client, 'SELECT name FROM tag ORDER BY name')
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['columns'] == ['name']
    assert response.json['rows'] == [['one'], ['two']]
    assert response.json['row_count'] == 2
    assert response.json['truncated'] is False

    # CTEs (including recursive ones) are reads.
    sql = 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 3) SELECT x FROM n'
    request, response = await post_query(async_client, sql)
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['rows'] == [[1], [2], [3]]


@pytest.mark.asyncio
@pytest.mark.parametrize('sql', [
    "INSERT INTO tag (name, color) VALUES ('evil', '#000000')",
    "UPDATE tag SET name = 'evil'",
    'DELETE FROM tag',
    'DROP TABLE tag',
    'CREATE TABLE evil (id INTEGER)',
    'CREATE TEMP TABLE evil (id INTEGER)',
    "ATTACH DATABASE ':memory:' AS evil",
    'PRAGMA journal_mode=DELETE',
    'PRAGMA foreign_keys=OFF',
    'BEGIN',
    'VACUUM',
    "SELECT load_extension('evil')",
    "SELECT 1; DELETE FROM tag",
])
async def test_database_query_refuses_writes(test_session, async_client, allow_database_query, tag_factory, sql):
    """Anything other than a read is refused, and the database is unchanged."""
    await tag_factory('one')
    test_session.commit()

    request, response = await post_query(async_client, sql)
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.json
    assert response.json['code'] == 'INVALID_DATABASE_QUERY'

    request, response = await post_query(async_client, 'SELECT name FROM tag')
    assert response.json['rows'] == [['one']]


@pytest.mark.asyncio
async def test_database_query_connection_is_read_only(test_session, allow_database_query):
    """Even without the authorizer, SQLite refuses to write through the connection."""
    with db_query.read_only_connection() as conn:
        conn.set_authorizer(None)
        with pytest.raises(Exception, match='readonly'):
            conn.execute("INSERT INTO tag (name, color) VALUES ('evil', '#000000')")


@pytest.mark.asyncio
async def test_database_query_introspection_pragmas(test_session, async_client, allow_database_query):
    """Schema-describing PRAGMAs are allowed, both as statements and as table-valued functions."""
    request, response = await post_query(async_client, 'PRAGMA table_info(tag)')
    assert response.status_code == HTTPStatus.OK, response.json
    assert 'name' in [row[1] for row in response.json['rows']]

    request, response = await post_query(async_client, "SELECT name FROM pragma_table_info('tag')")
    assert response.status_code == HTTPStatus.OK, response.json
    assert ['name'] in response.json['rows']


@pytest.mark.asyncio
async def test_database_query_errors(test_session, async_client, allow_database_query):
    request, response = await post_query(async_client, 'SELECT * FROM no_such_table')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'no such table' in response.json['error']

    request, response = await post_query(async_client, '   ')
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['code'] == 'INVALID_DATABASE_QUERY'


@pytest.mark.asyncio
async def test_database_query_limits(test_session, async_client, allow_database_query):
    """Rows are capped by `limit` (and MAX_LIMIT), long text is truncated, and blobs are summarized."""
    sql = 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 20) SELECT x FROM n'
    request, response = await post_query(async_client, sql, limit=5)
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['rows'] == [[1], [2], [3], [4], [5]]
    assert response.json['truncated'] is True

    with mock.patch.object(db_query, 'MAX_LIMIT', 3):
        request, response = await post_query(async_client, sql, limit=1000)
    assert response.json['row_count'] == 3
    assert response.json['truncated'] is True

    request, response = await post_query(
        async_client, f"SELECT printf('%.*c', {db_query.MAX_CELL_LENGTH + 5}, 'a'), zeroblob(16)")
    text, blob = response.json['rows'][0]
    assert text.startswith('a' * db_query.MAX_CELL_LENGTH + '...')
    assert text.endswith('<truncated 5 characters>')
    assert blob == '<blob 16 bytes>'


@pytest.mark.asyncio
async def test_database_query_timeout(test_session, async_client, allow_database_query):
    """A query that runs too long is interrupted."""
    sql = 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT count(*) FROM n'
    with mock.patch.object(db_query, 'QUERY_TIMEOUT', 0.2):
        request, response = await post_query(async_client, sql)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'time limit' in response.json['error']


@pytest.mark.asyncio
async def test_database_schema(test_session, async_client, allow_database_query):
    request, response = await async_client.get('/api/db/schema')
    assert response.status_code == HTTPStatus.OK, response.json
    tables = {i['name']: i for i in response.json['tables']}

    tag = tables['tag']
    assert tag['type'] == 'table'
    columns = {i['name']: i for i in tag['columns']}
    assert columns['id']['primary_key'] is True
    assert 'name' in columns
    assert any(i['columns'] == ['name'] for i in tag['indexes'])

    # FTS5 tables are described (with their definition), but their shadow tables are not.
    virtual = [i for i in tables.values() if i['type'] == 'virtual']
    assert virtual and all('fts5' in i['sql'].lower() for i in virtual)
    for table in virtual:
        assert f'{table["name"]}_data' not in tables
    assert not any(name.startswith('sqlite_') for name in tables)
    assert get_db_file().is_file()
