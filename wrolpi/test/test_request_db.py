"""An API request uses at most one SQLite connection (see `wrolpi.db.RequestDB`).

Each connection costs a connect plus WROLPi's PRAGMAs, about 3 ms on a Raspberry Pi 4.  These tests count
the connections a request opens with production's per-call sessions; the shared `test_session` hides them.
"""
from http import HTTPStatus

import pytest

from wrolpi import flags
from wrolpi.conftest import count_request_connections


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
@pytest.mark.parametrize('path', ['/api/tag', '/api/tag?tag_names={name}', '/api/tag/recent'])
async def test_tags_use_one_connection(async_client, test_session, tag_factory, path):
    """The Tags, their overlaps, and the recent Tags are read on the request's connection."""
    tag = await tag_factory()
    response, count = await count_request_connections(
        async_client, test_session, 'get', path.format(name=tag.name))
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_channel_list_uses_one_connection(async_client, test_session, simple_channel):
    response, count = await count_request_connections(async_client, test_session, 'get', '/api/videos/channels')
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_zim_estimates_use_one_connection(async_client, test_session, zim_factory):
    zim_factory('test zim')
    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/zim/search_estimates', json={'search_str': 'one'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_zim_search_uses_one_connection(async_client, test_session, zim_factory):
    """The zim's entries' tags are read on the request's connection."""
    zim_factory('test zim')
    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/zim/search', json={'search_str': 'one'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('path,body', [
    ('/api/files/search', {'search_str': 'video'}),
    ('/api/videos/search', {'search_str': 'video'}),
    ('/api/archive/search', {'search_str': 'video'}),
    ('/api/flasher/search', {}),
])
async def test_search_uses_one_connection(async_client, test_session, simple_channel, video_factory, path, body):
    """The search total, the page of ids, and the models for that page share the request's connection."""
    video_factory(title='a video', channel_id=simple_channel.id)
    response, count = await count_request_connections(async_client, test_session, 'post', path, json=body)
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_channel_uses_one_connection(async_client, test_session, simple_channel):
    """The Channel and its statistics are read on the request's connection."""
    response, count = await count_request_connections(
        async_client, test_session, 'get', f'/api/videos/channels/{simple_channel.id}')
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_zim_tag_searches_use_one_connection(async_client, test_session, test_zim, tag_factory):
    """Searching a Zim's tagged entries reads the tags on the request's connection."""
    tag = await tag_factory()
    test_zim.tag_entry(test_session, tag.name, 'one')

    response, count = await count_request_connections(
        async_client, test_session, 'post', f'/api/zim/search/{test_zim.id}', json={'tag_names': [tag.name]})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1

    response, count = await count_request_connections(
        async_client, test_session, 'post', '/api/zim/search_estimates', json={'tag_names': [tag.name]})
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['', '/description', '/captions', '/comments'])
async def test_video_reads_use_one_connection(async_client, test_session, simple_channel, video_factory, suffix):
    """A Video, its neighbors, and its details are read on the request's connection."""
    video_factory(title='first', channel_id=simple_channel.id)
    video = video_factory(title='second', channel_id=simple_channel.id)
    response, count = await count_request_connections(
        async_client, test_session, 'get', f'/api/videos/{video.file_group_id}{suffix}')
    assert response.status_code == HTTPStatus.OK, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_video_edit_uses_one_connection(async_client, test_session, simple_channel, video_factory):
    video = video_factory(title='before', channel_id=simple_channel.id)
    response, count = await count_request_connections(
        async_client, test_session, 'put', f'/api/videos/{video.file_group_id}', json={'title': 'after'})
    assert response.status_code == HTTPStatus.OK, response.body
    assert response.json['file_group']['title'] == 'after'
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,body', [
    ('get', '/api/statistics', None),
    ('post', '/api/search_file_estimates', {'search_str': 'video'}),
    ('post', '/api/search_other_estimates', {'tag_names': ['{tag}']}),
    ('post', '/api/files/bulk_tag/preview', {'paths': ['{video_dir}']}),
    ('get', '/api/download', None),
    ('post', '/api/download/retry_once', None),
    ('get', '/api/docs/statistics', None),
    ('get', '/api/videos/statistics', None),
    ('get', '/api/archive/statistics', None),
    ('post', '/api/docs/search', {'search_str': 'video'}),
])
async def test_summaries_use_one_connection(async_client, test_session, test_directory, tag_factory, simple_channel,
                                            video_factory, test_download_manager, method, path, body):
    """Statistics, estimates, previews and lists each read on the request's connection."""
    tag = await tag_factory()
    video = video_factory(title='a video', channel_id=simple_channel.id)
    video_dir = str(video.video_path.parent.relative_to(test_directory))
    if body is not None:
        body = {k: [i.format(tag=tag.name, video_dir=video_dir) for i in v] if isinstance(v, list) else v
                for k, v in body.items()}
    kwargs = dict(json=body) if body is not None else dict()
    response, count = await count_request_connections(async_client, test_session, method, path, **kwargs)
    assert response.status_code < 300, response.body
    assert count == 1


@pytest.mark.asyncio
async def test_status_uses_one_connection(async_client, test_session, test_download_manager, flags_lock):
    """The UI polls the status; its download summary is read on the request's connection."""
    flags.db_up.set()
    try:
        response, count = await count_request_connections(async_client, test_session, 'get', '/api/status')
    finally:
        flags.db_up.clear()
    assert response.status_code == HTTPStatus.OK, response.body
    assert 'pending' in response.json['downloads'], 'the download summary was not read'
    assert count == 1


@pytest.mark.asyncio
async def test_kill_download_uses_one_connection(async_client, test_session, test_downloader):
    from wrolpi.downloader import Download
    await async_client.post('/api/download', json={'urls': ['https://example.com/kill'],
                                                   'downloader': test_downloader.name})
    download = test_session.query(Download).filter_by(url='https://example.com/kill').one()

    response, count = await count_request_connections(
        async_client, test_session, 'post', f'/api/download/{download.id}/kill')
    assert response.status_code < 300, response.body
    assert count == 1
    assert test_session.query(Download).filter_by(id=download.id).one().error == 'User stopped this download'
