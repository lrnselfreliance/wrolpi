"""Tests for the /api/ai blueprint — the LLM tool catalog."""
import json
from http import HTTPStatus

import pytest

from modules.ai import lib


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
async def test_ai_list_collections(async_client, test_session, archive_factory, channel_factory):
    """Collections are listed paged, filtered by kind, and searchable by name."""
    archive_factory(domain='example.com', title='a page', contents='contents')
    for name in ('Alpha Cooking', 'Beta Cooking', 'Gamma Woodwork'):
        channel_factory(name=name)
    test_session.commit()

    request, response = await async_client.get('/api/ai/collections?kind=domain')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 1
    assert response.json['results'][0]['name'] == 'example.com'
    assert response.json['results'][0]['kind'] == 'domain'
    assert response.json['next_offset'] is None

    # Paged, with the full total so the model knows how many there are.
    request, response = await async_client.get('/api/ai/collections?kind=channel&limit=2')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 3 and len(response.json['results']) == 2
    assert response.json['next_offset'] == 2
    request, response = await async_client.get('/api/ai/collections?kind=channel&limit=2&offset=2')
    assert [i['name'] for i in response.json['results']] == ['Gamma Woodwork']
    assert response.json['next_offset'] is None

    # Name search.
    request, response = await async_client.get('/api/ai/collections?search_str=cooking')
    assert response.status_code == HTTPStatus.OK
    assert sorted(i['name'] for i in response.json['results']) == ['Alpha Cooking', 'Beta Cooking']


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


@pytest.mark.asyncio
async def test_ai_list_files(async_client, test_directory):
    """Directories in the media directory can be listed: directories first, then files, both sorted."""
    (test_directory / 'videos/channel').mkdir(parents=True)
    (test_directory / 'videos/channel/b.mp4').write_bytes(b'x' * 10)
    (test_directory / 'videos/channel/a.mp4').write_bytes(b'x' * 20)
    (test_directory / 'videos/channel/a.en.vtt').write_text('WEBVTT')
    (test_directory / 'videos/channel/.DS_Store').write_bytes(b'\x00')  # macOS junk is hidden
    (test_directory / 'videos/other').mkdir()
    (test_directory / 'notes.txt').write_text('hi')
    (test_directory / 'lost+found').mkdir()  # hidden
    (test_directory / 'config').mkdir(exist_ok=True)  # hidden: may hold secrets

    # The root is listed when no path is given.
    request, response = await async_client.get('/api/ai/files/list')
    assert response.status_code == HTTPStatus.OK
    assert response.json['path'] == ''
    assert [i['path'] for i in response.json['directories']] == ['videos/']
    assert [i['path'] for i in response.json['files']] == ['notes.txt']
    assert response.json['total'] == 2
    assert response.json['next_offset'] is None

    request, response = await async_client.get('/api/ai/files/list?path=videos/channel')
    assert response.status_code == HTTPStatus.OK
    assert response.json['path'] == 'videos/channel/'
    assert response.json['directories'] == []
    assert [(i['path'], i['size']) for i in response.json['files']] == [
        ('videos/channel/a.en.vtt', 6),
        ('videos/channel/a.mp4', 20),
        ('videos/channel/b.mp4', 10),
    ]
    assert response.json['files'][1]['mimetype'] == 'video/mp4'

    # Trailing slashes and leading slashes are tolerated.
    request, response = await async_client.get('/api/ai/files/list?path=/videos/')
    assert response.status_code == HTTPStatus.OK
    assert [i['path'] for i in response.json['directories']] == ['videos/channel/', 'videos/other/']
    assert response.json['files'] == []

    # Missing directory, and a file rather than a directory.
    request, response = await async_client.get('/api/ai/files/list?path=nope')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = await async_client.get('/api/ai/files/list?path=notes.txt')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_list_files_paged(async_client, test_directory):
    """Big directories are paged so a single listing cannot blow the model's context."""
    from modules.ai.api import LIST_PAGE_SIZE
    (test_directory / 'big').mkdir()
    for i in range(LIST_PAGE_SIZE + 5):
        (test_directory / f'big/{i:04d}.txt').write_text('x')

    request, response = await async_client.get('/api/ai/files/list?path=big')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['files']) == LIST_PAGE_SIZE
    assert response.json['total'] == LIST_PAGE_SIZE + 5
    assert response.json['next_offset'] == LIST_PAGE_SIZE

    request, response = await async_client.get(f'/api/ai/files/list?path=big&offset={LIST_PAGE_SIZE}')
    assert response.status_code == HTTPStatus.OK
    assert [i['name'] for i in response.json['files']] == [f'{i:04d}.txt' for i in range(LIST_PAGE_SIZE, LIST_PAGE_SIZE + 5)]
    assert response.json['next_offset'] is None


@pytest.mark.asyncio
async def test_ai_list_files_refuses_escapes(async_client, test_directory):
    """Listings outside the media directory, and inside the config directory, are refused."""
    request, response = await async_client.get('/api/ai/files/list?path=../')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    (test_directory / 'config').mkdir(exist_ok=True)
    request, response = await async_client.get('/api/ai/files/list?path=config')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_ai_list_tags(async_client, test_session, tag_factory, video_factory):
    """Tags are listed with what they are applied to, plus the recently used names."""
    one = await tag_factory('one')
    await tag_factory('two')
    video = video_factory(title='tagged video')
    video.file_group.add_tag(test_session, one.id)
    test_session.commit()

    request, response = await async_client.get('/api/ai/tags')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 2
    assert [i['name'] for i in response.json['results']] == ['one', 'two']
    assert response.json['results'][0]['file_groups'] == 1
    assert response.json['results'][1]['file_groups'] == 0
    assert response.json['recent'] == ['one']


@pytest.mark.asyncio
async def test_ai_list_downloads(async_client, test_session, test_download_manager, test_downloader,
                                 test_directory):
    """The download queue is summarized with lean, relative-path entries; status can filter."""
    test_download_manager.create_download(test_session, 'https://example.com/once', test_downloader.name,
                                          destination=test_directory / 'archive/example.com')
    test_download_manager.recurring_download(test_session, 'https://example.com/feed', 86400,
                                             test_downloader.name)
    test_session.commit()

    request, response = await async_client.get('/api/ai/downloads')
    assert response.status_code == HTTPStatus.OK
    assert response.json['summary']['recurring'] == 1
    assert 'disabled' in response.json['summary']
    once, = response.json['once']
    assert once['url'] == 'https://example.com/once'
    assert once['destination'] == 'archive/example.com'
    assert once['status'] == 'new'
    assert once['downloader'] == test_downloader.name
    recurring, = response.json['recurring']
    assert recurring['url'] == 'https://example.com/feed'
    assert recurring['frequency'] == 86400

    # Filter by status.
    request, response = await async_client.get('/api/ai/downloads?status=complete')
    assert response.status_code == HTTPStatus.OK
    assert response.json['once'] == [] and response.json['recurring'] == []


@pytest.mark.asyncio
async def test_ai_map(async_client, test_session, test_directory, make_files_structure):
    """The map overview reports map files, subscriptions, pins, and search indexes; places can be searched."""
    from modules.map.pins import get_map_pins_config
    from modules.map.test.test_search import _create_test_search_db

    make_files_structure(['map/oregon.pmtiles'])
    _create_test_search_db(test_directory / 'map/oregon.search.db', [
        ('Portland', 'city', 45.5, -122.6, 6, 'places', 'city', 650000, 'Oregon'),
        ('Port Orford', 'town', 42.7, -124.5, 9, 'places', 'town', 1100, 'Oregon'),
    ])
    get_map_pins_config().add_pin(45.1, -122.2, 'Home')

    request, response = await async_client.get('/api/ai/map')
    assert response.status_code == HTTPStatus.OK
    files, = response.json['files']
    assert files['name'] == 'oregon.pmtiles' and files['has_search_index'] is True
    assert response.json['subscriptions'] == []
    pin, = response.json['pins']
    assert pin['label'] == 'Home' and pin['link'] == '/map?lat=45.1&lon=-122.2&z=12'

    request, response = await async_client.get('/api/ai/map/search?q=port')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 2
    first = response.json['results'][0]
    assert first['name'] == 'Portland'
    assert first['region'] == 'Oregon'
    assert first['link'] == '/map?lat=45.5&lon=-122.6&z=12'

    # Proximity ranking within an importance tier: equal min_zoom, nearest first.
    _create_test_search_db(test_directory / 'map/coast.search.db', [
        ('Port A', 'town', 42.0, -124.0, 9, 'places', 'town', 100, 'Oregon'),
        ('Port B', 'town', 44.0, -124.0, 9, 'places', 'town', 100, 'Oregon'),
    ])
    request, response = await async_client.get('/api/ai/map/search?q=port%20b&lat=44.0&lon=-124.0')
    assert response.status_code == HTTPStatus.OK
    assert response.json['results'][0]['name'] == 'Port B'
    request, response = await async_client.get('/api/ai/map/search?q=port&lat=42.0&lon=-124.0&limit=2')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['results']) == 2 and response.json['total'] == 4

    # q is required.
    request, response = await async_client.get('/api/ai/map/search')
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_ai_format_download_error_tail():
    """Download errors are tracebacks; the model gets the end (the exception message), not the start."""
    from modules.ai.api import _format_download, DOWNLOAD_ERROR_LENGTH
    error = 'Traceback (most recent call last):\n' + ('  File "x.py"\n' * 100) + 'ValueError: the real reason'
    formatted = _format_download(dict(id=1, url='https://example.com', status='failed', error=error))
    assert formatted['error'].endswith('ValueError: the real reason')
    assert len(formatted['error']) == DOWNLOAD_ERROR_LENGTH + 1
    assert 'error' not in _format_download(dict(id=2, url='https://example.com', status='new', error=None))


# ---------------------------------------------------------------------------
# Consolidated, kind-generic endpoints for small models.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_search_files_kinds(async_client, test_session, video_factory, archive_factory, channel_factory):
    """One search covers every kind; kind narrows it; channel accepts a name or an id."""
    channel = channel_factory(name='Wild Cooking')
    video_factory(channel_id=channel.id, title='cooking rice')
    video_factory(title='cooking beans video')
    archive_factory(domain='cooking.example.com', title='cooking beans', contents='beans')
    test_session.commit()

    async def search(**body):
        request, response = await async_client.post('/api/ai/files/search', content=json.dumps(body))
        assert response.status_code == HTTPStatus.OK, response.json
        return response.json

    data = await search(search_str='cooking')
    assert data['total'] == 3
    assert {i['kind'] for i in data['results']} == {'video', 'archive'}
    # The matching channel and domain are offered so the model can narrow without another tool.
    assert [i['name'] for i in data['matches']['channels']] == ['Wild Cooking']
    assert data['matches']['channels'][0]['id'] == channel.id
    assert [i['name'] for i in data['matches']['domains']] == ['cooking.example.com']

    data = await search(search_str='cooking', kind='video')
    assert data['total'] == 2 and all(i['kind'] == 'video' for i in data['results'])

    data = await search(search_str='cooking', kind='archive')
    assert data['total'] == 1 and data['results'][0]['kind'] == 'archive'

    # channel by exact name, partial name, and numeric id; channel implies kind=video.
    for channel_ref in ('Wild Cooking', 'wild', str(channel.id)):
        data = await search(search_str='cooking', channel=channel_ref)
        assert data['total'] == 1, channel_ref
        assert data['results'][0]['title'] == 'cooking rice'
        assert 'matches' not in data  # already narrowed to one channel

    # domain implies kind=archive.
    data = await search(domain='cooking.example.com')
    assert data['total'] == 1 and data['results'][0]['kind'] == 'archive'

    # A filter that does not apply to the kind is ignored, not fatal.
    data = await search(search_str='cooking', kind='archive', channel='Wild Cooking')
    assert data['total'] == 1 and data['results'][0]['kind'] == 'archive'

    # An unknown channel name gives no results and a hint, not an error.
    data = await search(search_str='cooking', channel='No Such Channel')
    assert data['total'] == 0 and data['results'] == []
    assert 'channel' in data['hint'].lower()

    # Listings are slim: ids, titles, links, kind; no links the model can derive.
    result = data = (await search(search_str='cooking', kind='video'))['results'][0]
    assert {'id', 'kind', 'title', 'link'} <= set(result)
    assert 'captions_link' not in result and 'size' not in result and 'mimetype' not in result

    # No filters at all browses the newest items.
    request, response = await async_client.post('/api/ai/files/search', content=json.dumps({}))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 3

    # The limit is clamped and total reports every match so the model narrows instead of paging.
    data = await search(search_str='cooking', limit=1)
    assert len(data['results']) == 1 and data['total'] == 3
    data = await search(search_str='cooking', limit=10_000)
    assert len(data['results']) == 3

    # An unknown kind is refused.
    request, response = await async_client.post('/api/ai/files/search', content=json.dumps(dict(kind='song')))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_ai_search_files_docs(async_client, test_session, test_directory, example_epub, refresh_files):
    """kind=doc searches documents; author/subject imply kind=doc."""
    await refresh_files()
    request, response = await async_client.post('/api/ai/files/search', content=json.dumps(dict(search_str='WROLPi', kind='doc')))
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] >= 1
    doc = response.json['results'][0]
    assert doc['kind'] == 'doc' and doc['link'] == f'/docs/{doc["id"]}'

    # get_file returns the doc detail through the generic route.
    request, response = await async_client.get(f'/api/ai/files/{doc["id"]}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['kind'] == 'doc' and response.json['id'] == doc['id']


@pytest.mark.asyncio
async def test_ai_get_file(async_client, test_session, video_factory, archive_factory, make_files_structure, tag_factory):
    """get_file dispatches on the file's model and carries more than the listing row."""
    tag = await tag_factory('food')
    video = video_factory(title='wood stove install', with_caption_file=True)
    video.file_group.add_tag(test_session, tag.id)
    archive_factory(domain='example.com', url='https://example.com/a', title='first', contents='one')
    archive = archive_factory(domain='example.com', url='https://example.com/a', title='second', contents='two')
    test_session.commit()

    request, response = await async_client.get(f'/api/ai/files/{video.file_group_id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['kind'] == 'video'
    assert response.json['link'] == f'/videos/{video.file_group_id}'
    assert response.json['has_captions'] is True
    assert response.json['tags'] == ['food']
    assert response.json['mimetype'].startswith('video/')
    # Fetching does not mark the video viewed.
    test_session.expire_all()
    assert video.file_group.viewed is None

    request, response = await async_client.get(f'/api/ai/files/{archive.file_group_id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['kind'] == 'archive'
    assert response.json['url'] == 'https://example.com/a'
    assert [i['title'] for i in response.json['history']] == ['first']

    # A plain file (no model) still resolves with a media link.
    from wrolpi.files.lib import upsert_file
    path, = make_files_structure({'photos/a.png': 'not really a png'})
    fg = await upsert_file(path)
    request, response = await async_client.get(f'/api/ai/files/{fg.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['link'] == '/media/photos/a.png'

    request, response = await async_client.get('/api/ai/files/123456')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_read_content(async_client, test_session, video_factory, archive_factory):
    """read_content serves captions/comments for videos and text for archives, paged."""
    info_json = dict(duration=5, comments=[dict(author='alice', text='great video')])
    video = video_factory(title='captioned', with_caption_file=True, with_info_json=info_json)
    contents = 'word ' * 2_000
    archive = archive_factory(domain='example.com', title='long read', contents=contents)
    test_session.commit()

    request, response = await async_client.get(f'/api/ai/files/{video.file_group_id}/content')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'].startswith('[00:00:0')
    assert response.json['total_chars'] > 0

    # An offset beyond the end returns an empty page, never an error.
    offset = response.json['total_chars'] + 100
    request, response = await async_client.get(f'/api/ai/files/{video.file_group_id}/content?offset={offset}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'] == '' and response.json['next_offset'] is None

    # A video without comments is an empty page, not an error.
    quiet = video_factory(title='quiet')
    test_session.commit()
    request, response = await async_client.get(f'/api/ai/files/{quiet.file_group_id}/content?part=comments')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'] == ''

    request, response = await async_client.get(f'/api/ai/files/{video.file_group_id}/content?part=comments')
    assert response.status_code == HTTPStatus.OK
    assert 'alice: great video' in response.json['content']

    request, response = await async_client.get(f'/api/ai/files/{archive.file_group_id}/content')
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['content']) == lib.PAGE_SIZE
    assert response.json['next_offset'] == lib.PAGE_SIZE
    request, response = await async_client.get(
        f'/api/ai/files/{archive.file_group_id}/content?offset={response.json["next_offset"]}')
    assert response.json['content'] == contents[lib.PAGE_SIZE:2 * lib.PAGE_SIZE]

    # An archive has no comments; the error says what the file is.
    request, response = await async_client.get(f'/api/ai/files/{archive.file_group_id}/content?part=comments')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'archive' in response.json['error'].lower()

    request, response = await async_client.get(f'/api/ai/files/{video.file_group_id}/content?part=bogus')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    request, response = await async_client.get('/api/ai/files/123456/content')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_get_inventory_optional_slug(async_client, food_inventory_factory):
    """Without a slug the inventories are listed lean; with one, the inventory is returned in full."""
    slug = food_inventory_factory(items=[dict(name='rice', count=2)])

    request, response = await async_client.get('/api/ai/inventories')
    assert response.status_code == HTTPStatus.OK
    lean = next(i for i in response.json['results'] if i['slug'] == slug)
    assert lean['item_count'] == 1 and 'items' not in lean

    request, response = await async_client.get(f'/api/ai/inventories?slug={slug}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['inventory']['items'][0]['name'] == 'rice'

    request, response = await async_client.get('/api/ai/inventories?slug=no-such-inventory')
    assert response.status_code == HTTPStatus.NOT_FOUND
