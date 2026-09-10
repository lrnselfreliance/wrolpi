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
async def test_ai_get_archive(async_client, test_session, archive_factory):
    """A single archive can be fetched with its history of snapshots."""
    archive_factory(domain='example.com', url='https://example.com/a', title='first', contents='one')
    archive = archive_factory(domain='example.com', url='https://example.com/a', title='second', contents='two')
    test_session.commit()

    request, response = await async_client.get(f'/api/ai/archives/{archive.file_group_id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['kind'] == 'archive'
    assert response.json['link'] == f'/archives/{archive.file_group_id}'
    # History holds the OTHER snapshots of the URL, not the archive itself.
    assert [i['title'] for i in response.json['history']] == ['first']

    request, response = await async_client.get('/api/ai/archives/123456')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_ai_get_video_comments(async_client, test_session, video_factory):
    """Video comments render as paged author lines."""
    info_json = dict(duration=5, comments=[
        dict(author='alice', text='great video'),
        dict(author='bob', text='thanks'),
    ])
    video = video_factory(title='commented', with_info_json=info_json)
    test_session.commit()

    request, response = await async_client.get(f'/api/ai/videos/{video.file_group_id}/comments')
    assert response.status_code == HTTPStatus.OK
    assert 'alice: great video' in response.json['content']
    assert 'bob: thanks' in response.json['content']

    # No comments is an empty page, not an error.
    no_comments = video_factory(title='quiet')
    test_session.commit()
    request, response = await async_client.get(f'/api/ai/videos/{no_comments.file_group_id}/comments')
    assert response.status_code == HTTPStatus.OK
    assert response.json['content'] == ''


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


@pytest.mark.asyncio
async def test_ai_search_suggestions(async_client, test_session, video_factory, archive_factory, channel_factory,
                                     tag_factory):
    """Suggestions name the channels/domains/authors/subjects matching a term and estimate result counts."""
    channel = channel_factory(name='Wild Cooking')
    video_factory(channel_id=channel.id, title='cooking rice')
    archive_factory(domain='cooking.example.com', title='cooking beans', contents='beans')
    tag = await tag_factory('recipes')
    test_session.commit()

    content = dict(search_str='cooking')
    request, response = await async_client.post('/api/ai/search/suggestions', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    ch, = response.json['channels']
    assert ch['name'] == 'Wild Cooking' and ch['id'] == channel.id and ch['link'].startswith('/videos/channel/')
    dom, = response.json['domains']
    assert dom['name'] == 'cooking.example.com'
    assert response.json['authors'] == [] and response.json['subjects'] == []
    assert response.json['estimates']['file_groups'] == 2
    assert 'file_groups_deep' in response.json['estimates']
    assert response.json['estimates']['zims'] == []

    # Tag names narrow the estimate.
    content = dict(search_str='cooking', tag_names=[tag.name])
    request, response = await async_client.post('/api/ai/search/suggestions', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['estimates']['file_groups'] == 0

    # Something to search for is required.
    request, response = await async_client.post('/api/ai/search/suggestions', content=json.dumps({}))
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_ai_format_download_error_tail():
    """Download errors are tracebacks; the model gets the end (the exception message), not the start."""
    from modules.ai.api import _format_download, DOWNLOAD_ERROR_LENGTH
    error = 'Traceback (most recent call last):\n' + ('  File "x.py"\n' * 100) + 'ValueError: the real reason'
    formatted = _format_download(dict(id=1, url='https://example.com', status='failed', error=error))
    assert formatted['error'].endswith('ValueError: the real reason')
    assert len(formatted['error']) == DOWNLOAD_ERROR_LENGTH + 1
    assert 'error' not in _format_download(dict(id=2, url='https://example.com', status='new', error=None))
