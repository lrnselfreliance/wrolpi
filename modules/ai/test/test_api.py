"""Tests for the /api/ai blueprint — the LLM tool catalog."""
import json
from http import HTTPStatus

import pytest

from modules.ai import lib


@pytest.mark.asyncio
async def test_ai_search_all(async_client, test_session, video_factory, archive_factory):
    """Global search returns lean results of every kind with links and a total."""
    video_factory(title='canning tomatoes')
    archive_factory(domain='example.com', title='canning peppers', contents='all about canning peppers')
    test_session.commit()

    request, response = await async_client.post('/api/ai/search', content=json.dumps(dict(search_str='canning')))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 2
    kinds = {i['kind'] for i in response.json['results']}
    assert kinds == {'video', 'archive'}
    for result in response.json['results']:
        assert result['link']
        assert result['id']


@pytest.mark.asyncio
async def test_ai_search_all_limit(async_client, test_session, archive_factory):
    """The limit is clamped and the total reports all matches so the model narrows, not pages."""
    for i in range(3):
        archive_factory(domain='example.com', title=f'gardening {i}', contents='gardening guide')
    test_session.commit()

    content = dict(search_str='gardening', limit=1)
    request, response = await async_client.post('/api/ai/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['results']) == 1
    assert response.json['total'] == 3

    # An excessive limit is clamped to the maximum.
    content = dict(search_str='gardening', limit=10_000)
    request, response = await async_client.post('/api/ai/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_ai_search_videos(async_client, test_session, video_factory):
    """Video search returns lean video results with captions links."""
    video_factory(title='sourdough starter', with_caption_file=True)
    video_factory(title='unrelated')
    test_session.commit()

    content = dict(search_str='sourdough')
    request, response = await async_client.post('/api/ai/videos/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    result = response.json['results'][0]
    assert result['kind'] == 'video'
    assert result['link'] == f'/videos/{result["id"]}'
    assert result['captions_link'] == f'/api/ai/videos/{result["id"]}/captions'


@pytest.mark.asyncio
async def test_ai_get_video(async_client, test_session, video_factory):
    """A single video can be fetched by its FileGroup ID."""
    video = video_factory(title='wood stove install')
    test_session.commit()
    file_group_id = video.file_group_id

    request, response = await async_client.get(f'/api/ai/videos/{file_group_id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['id'] == file_group_id
    assert response.json['kind'] == 'video'
    assert response.json['link'] == f'/videos/{file_group_id}'

    # Fetching does not mark the video viewed.
    test_session.expire_all()
    assert video.file_group.viewed is None

    request, response = await async_client.get('/api/ai/videos/123456')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_get_video_captions(async_client, test_session, video_factory):
    """Captions are returned as timestamped, paged text."""
    video = video_factory(title='captioned', with_caption_file=True)
    test_session.commit()

    request, response = await async_client.get(f'/api/ai/videos/{video.file_group_id}/captions')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'].startswith('[00:00:0')
    assert response.json['total_chars'] > 0

    # An offset beyond the end returns an empty page, never an error.
    offset = response.json['total_chars'] + 100
    request, response = await async_client.get(f'/api/ai/videos/{video.file_group_id}/captions?offset={offset}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'] == ''
    assert response.json['next_offset'] is None


@pytest.mark.asyncio
async def test_ai_search_archives(async_client, test_session, archive_factory):
    """Archive search supports the domain filter and returns text links."""
    archive_factory(domain='example.com', title='pressure canning', contents='pressure canning guide')
    archive_factory(domain='other.org', title='water bath canning', contents='water bath canning guide')
    test_session.commit()

    content = dict(search_str='canning', domain='example.com')
    request, response = await async_client.post('/api/ai/archives/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    result = response.json['results'][0]
    assert result['kind'] == 'archive'
    assert result['text_link'] == f'/api/ai/archives/{result["id"]}/text'


@pytest.mark.asyncio
async def test_ai_get_archive_text(async_client, test_session, archive_factory):
    """Archive text is served from the readability text file and paged."""
    contents = 'word ' * 2_000  # 10,000 chars, more than two pages.
    archive = archive_factory(domain='example.com', title='long read', contents=contents)
    test_session.commit()
    file_group_id = archive.file_group_id

    request, response = await async_client.get(f'/api/ai/archives/{file_group_id}/text')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['content']) == lib.PAGE_SIZE
    assert response.json['next_offset'] == lib.PAGE_SIZE
    assert response.json['total_chars'] == len(contents)

    # The second page continues where the first ended.
    request, response = await async_client.get(
        f'/api/ai/archives/{file_group_id}/text?offset={response.json["next_offset"]}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'] == contents[lib.PAGE_SIZE:2 * lib.PAGE_SIZE]

    request, response = await async_client.get('/api/ai/archives/123456/text')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_search_docs(async_client, test_session, test_directory, example_epub, refresh_files):
    """Docs can be searched and fetched with links."""
    await refresh_files()

    content = dict(search_str='WROLPi')
    request, response = await async_client.post('/api/ai/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] >= 1
    result = response.json['results'][0]
    assert result['kind'] == 'doc'
    assert result['link'] == f'/docs/{result["id"]}'

    request, response = await async_client.get(f'/api/ai/docs/{result["id"]}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['id'] == result['id']
    assert response.json['kind'] == 'doc'


@pytest.mark.asyncio
async def test_ai_zims(async_client, test_session, test_zim):
    """Zims can be listed, searched, and their entries read as paged text."""
    request, response = await async_client.get('/api/ai/zims')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    zim_id = response.json['results'][0]['id']

    # Search one specific Zim.
    content = dict(search_str='item', zim_id=zim_id)
    request, response = await async_client.post('/api/ai/zims/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] >= 1
    result = response.json['results'][0]
    assert result['zim_id'] == zim_id
    assert result['link'] == f'/api/zim/{zim_id}/entry/{result["path"]}'

    # An empty search is a clear error for the model.
    request, response = await async_client.post('/api/ai/zims/search', content=json.dumps(dict()))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Read the entry the search found.
    request, response = await async_client.get(f'/api/ai/zims/{zim_id}/entry?path={result["path"]}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content']
    assert response.json['link'] == f'/api/zim/{zim_id}/entry/{result["path"]}'

    # The path is required.
    request, response = await async_client.get(f'/api/ai/zims/{zim_id}/entry')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_ai_list_collections(async_client, test_session, archive_factory):
    """Collections can be listed and filtered by kind."""
    archive_factory(domain='example.com', title='a page', contents='contents')
    test_session.commit()

    request, response = await async_client.get('/api/ai/collections?kind=domain')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    assert response.json['results'][0]['name'] == 'example.com'
    assert response.json['results'][0]['kind'] == 'domain'

    request, response = await async_client.get('/api/ai/collections?kind=channel')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 0


@pytest.mark.asyncio
async def test_ai_inventories(async_client, food_inventory_factory):
    """Inventories are listed lean, and fetched in full by slug."""
    slug = food_inventory_factory(items=[dict(name='rice', count=2)])

    request, response = await async_client.get('/api/ai/inventories')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] >= 1
    lean = next(i for i in response.json['results'] if i['slug'] == slug)
    assert lean['item_count'] == 1
    assert 'items' not in lean

    request, response = await async_client.get(f'/api/ai/inventories/{slug}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['inventory']['items'][0]['name'] == 'rice'

    request, response = await async_client.get('/api/ai/inventories/no-such-inventory')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_read_file(async_client, test_directory):
    """Text files in the media directory can be read; everything else is refused."""
    (test_directory / 'notes').mkdir()
    (test_directory / 'notes/todo.txt').write_text('buy more rice\n' * 400)  # > one page

    request, response = await async_client.get('/api/ai/files/read?path=notes/todo.txt')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'].startswith('buy more rice')
    assert response.json['next_offset'] == lib.PAGE_SIZE

    # Missing path parameter.
    request, response = await async_client.get('/api/ai/files/read')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Missing file.
    request, response = await async_client.get('/api/ai/files/read?path=notes/nope.txt')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Binary files are refused.
    (test_directory / 'notes/blob.bin').write_bytes(b'\x00\x01\x02')
    request, response = await async_client.get('/api/ai/files/read?path=notes/blob.bin')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_ai_read_file_refuses_escapes(async_client, test_directory):
    """Reads outside the media directory, and of config files, are refused."""
    # Path traversal.
    request, response = await async_client.get('/api/ai/files/read?path=../secrets.txt')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # The config directory can contain secrets.
    (test_directory / 'config').mkdir(exist_ok=True)
    (test_directory / 'config/wrolpi.yaml').write_text('secret: hunter2')
    request, response = await async_client.get('/api/ai/files/read?path=config/wrolpi.yaml')
    assert response.status_code == HTTPStatus.BAD_REQUEST
