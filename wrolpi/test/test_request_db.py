"""An API request uses at most one SQLite connection (see `wrolpi.db.RequestDB`).

Each connection costs a connect plus WROLPi's PRAGMAs, about 3 ms on a Raspberry Pi 4.  These tests count
the connections a request opens with production's per-call sessions; the shared `test_session` hides them.
"""
from http import HTTPStatus

import pytest

from wrolpi.conftest import count_request_connections

# Library functions these endpoints call still open their own cursor or session, instead of using the
# request's.  Remove an endpoint's mark when its count reaches one (strict: an unexpected pass fails).
OPENS_OWN_CONNECTION = pytest.mark.xfail(
    strict=True, reason='a library function opens its own connection instead of using the request session')


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,body', [
    ('post', '/api/echo', {}),
    ('get', '/api/settings', None),
])
async def test_requests_without_database_work_open_no_connection(async_client, test_session, method, path, body):
    kwargs = dict(json=body) if body is not None else dict()
    response, count = await count_request_connections(async_client, test_session, method, path, **kwargs)
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 0


@pytest.mark.asyncio
async def test_collection_item_writes_use_one_connection(async_client, test_session):
    """The item endpoints read, then write in `RequestDB.write()`; both use the request's connection."""
    _, response = await async_client.post('/api/collections', json={'name': 'One Connection'})
    cid = response.json['collection']['id']

    response, count = await count_request_connections(
        async_client, test_session, 'post', f'/api/collections/{cid}/items',
        json={'item_kind': 'url', 'url': '/u/a', 'title': 'a'})
    assert response.status_code == HTTPStatus.CREATED, response.body
    assert count == 1
    item_id = response.json['item']['id']

    response, count = await count_request_connections(
        async_client, test_session, 'put', f'/api/collections/{cid}/items/order', json={'item_ids': [item_id]})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1

    response, count = await count_request_connections(
        async_client, test_session, 'delete', f'/api/collections/{cid}/items/{item_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_create_download_uses_one_connection(async_client, test_session, test_downloader):
    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/download',
        json={'urls': ['https://example.com/one-connection'], 'downloader': test_downloader.name})
    assert response.status_code == HTTPStatus.CREATED, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_tags_use_one_connection(async_client, test_session, tag_factory):
    await tag_factory()
    response, count = await count_request_connections(async_client, test_session, 'get', '/api/tag')
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_zim_estimates_use_one_connection(async_client, test_session, zim_factory):
    zim_factory('test zim')
    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/zim/search_estimates', json={'search_str': 'one'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@OPENS_OWN_CONNECTION
@pytest.mark.asyncio
async def test_zim_search_uses_one_connection(async_client, test_session, zim_factory):
    """`get_all_entries_tags` opens a cursor of its own."""
    zim_factory('test zim')
    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/zim/search', json={'search_str': 'one'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@OPENS_OWN_CONNECTION
@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/api/files/search', '/api/videos/search'])
async def test_search_uses_one_connection(async_client, test_session, simple_channel, video_factory, path):
    """`count_file_groups` opens a cursor for the total (skipped when the total is cached), then
    `handle_file_group_search_results` opens another cursor and a separate session for the page."""
    video_factory(title='a video', channel_id=simple_channel.id)
    response, count = await count_request_connections(
        async_client, test_session, 'post', path, json={'search_str': 'video'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@OPENS_OWN_CONNECTION
@pytest.mark.asyncio
async def test_channel_uses_one_connection(async_client, test_session, simple_channel):
    """`get_channel` uses the request session, but `Channel.get_statistics` opens a raw cursor of its own
    (`get_db_curs`)."""
    response, count = await count_request_connections(
        async_client, test_session, 'get', f'/api/videos/channels/{simple_channel.id}')
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1
