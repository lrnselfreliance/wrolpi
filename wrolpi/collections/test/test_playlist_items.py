"""Tests for playlist CollectionItem operations: create, add file/url items, reorder, remove."""
from http import HTTPStatus

import pytest

from wrolpi.collections.models import Collection


@pytest.mark.asyncio
async def test_create_playlist(async_client, test_session):
    """A playlist collection can be created via the API."""
    _, response = await async_client.post('/api/collections', json={'name': 'Fire Making'})
    assert response.status_code == HTTPStatus.CREATED, response.json
    data = response.json['collection']
    assert data['name'] == 'Fire Making'
    assert data['kind'] == 'playlist'
    assert data['item_count'] == 0
    assert data['items'] == []
    # Persisted to the database.
    assert test_session.query(Collection).filter_by(name='Fire Making', kind='playlist').one()


@pytest.mark.asyncio
async def test_create_playlist_rejects_blank_and_duplicate(async_client, test_session):
    _, response = await async_client.post('/api/collections', json={'name': '   '})
    assert response.status_code == HTTPStatus.BAD_REQUEST

    _, response = await async_client.post('/api/collections', json={'name': 'Dup'})
    assert response.status_code == HTTPStatus.CREATED
    _, response = await async_client.post('/api/collections', json={'name': 'Dup'})
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_add_url_item(async_client, test_session):
    """A url item (e.g. a map location) can be added and is returned in order."""
    _, response = await async_client.post('/api/collections', json={'name': 'Links'})
    cid = response.json['collection']['id']

    _, response = await async_client.post(f'/api/collections/{cid}/items', json={
        'item_kind': 'url', 'url': '/map?lat=40.76&lon=-111.89&z=12', 'title': 'Salt Lake City'})
    assert response.status_code == HTTPStatus.CREATED, response.json
    item = response.json['item']
    assert item['item_kind'] == 'url'
    assert item['url'] == '/map?lat=40.76&lon=-111.89&z=12'
    assert item['title'] == 'Salt Lake City'
    assert item['position'] == 1

    _, response = await async_client.get(f'/api/collections/{cid}')
    data = response.json['collection']
    assert data['item_count'] == 1
    assert [i['url'] for i in data['items']] == ['/map?lat=40.76&lon=-111.89&z=12']


@pytest.mark.asyncio
async def test_add_url_item_requires_url(async_client, test_session):
    _, response = await async_client.post('/api/collections', json={'name': 'Links'})
    cid = response.json['collection']['id']
    _, response = await async_client.post(f'/api/collections/{cid}/items', json={'item_kind': 'url'})
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_add_item_to_unknown_collection(async_client, test_session):
    _, response = await async_client.post('/api/collections/99999/items',
                                          json={'item_kind': 'url', 'url': '/x'})
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_add_file_item(async_client, test_session, test_directory):
    """An existing FileGroup can be added as a file item."""
    from wrolpi.files.models import FileGroup

    _, response = await async_client.post('/api/collections', json={'name': 'Mixed'})
    cid = response.json['collection']['id']

    path = test_directory / 'guide.pdf'
    path.write_bytes(b'%PDF-1.4 test')
    fg = FileGroup.from_paths(test_session, path)
    test_session.commit()

    _, response = await async_client.post(f'/api/collections/{cid}/items', json={
        'item_kind': 'file', 'file_group_id': fg.id})
    assert response.status_code == HTTPStatus.CREATED, response.json
    assert response.json['item']['item_kind'] == 'file'

    _, response = await async_client.get(f'/api/collections/{cid}')
    items = response.json['collection']['items']
    assert len(items) == 1
    assert items[0]['file_group']['id'] == fg.id


@pytest.mark.asyncio
async def test_reorder_and_remove_items(async_client, test_session):
    """Items can be reordered by id and removed, with positions kept contiguous."""
    _, response = await async_client.post('/api/collections', json={'name': 'Order'})
    cid = response.json['collection']['id']

    ids = []
    for name in ('a', 'b', 'c'):
        _, response = await async_client.post(f'/api/collections/{cid}/items', json={
            'item_kind': 'url', 'url': f'/u/{name}', 'title': name})
        ids.append(response.json['item']['id'])

    # Reverse the order.
    _, response = await async_client.put(f'/api/collections/{cid}/items/order',
                                         json={'item_ids': list(reversed(ids))})
    assert response.status_code == HTTPStatus.OK, response.json
    items = response.json['collection']['items']
    assert [i['url'] for i in items] == ['/u/c', '/u/b', '/u/a']
    assert [i['position'] for i in items] == [1, 2, 3]

    # Remove the middle item (originally 'b').
    _, response = await async_client.delete(f'/api/collections/{cid}/items/{ids[1]}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    _, response = await async_client.get(f'/api/collections/{cid}')
    items = response.json['collection']['items']
    assert [i['url'] for i in items] == ['/u/c', '/u/a']
    assert [i['position'] for i in items] == [1, 2]


@pytest.mark.asyncio
async def test_tag_playlist_without_directory(async_client, test_session):
    """A playlist can be tagged (and untagged) even though it has no directory."""
    _, response = await async_client.post('/api/collections', json={'name': 'Tagged'})
    cid = response.json['collection']['id']

    # Set a tag -- unlike domains/channels, no directory is required.
    _, response = await async_client.put(f'/api/collections/{cid}', json={'tag_name': 'Cooking'})
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['collection']['tag_name'] == 'Cooking'

    # Clearing the tag works too.
    _, response = await async_client.put(f'/api/collections/{cid}', json={'tag_name': ''})
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['collection']['tag_name'] is None


@pytest.mark.asyncio
async def test_adding_duplicate_item_is_idempotent(async_client, test_session):
    """Re-adding the same url returns the existing item with 200 (not a new 201)."""
    _, response = await async_client.post('/api/collections', json={'name': 'Dups'})
    cid = response.json['collection']['id']

    _, r1 = await async_client.post(f'/api/collections/{cid}/items',
                                    json={'item_kind': 'url', 'url': '/u/x'})
    assert r1.status_code == HTTPStatus.CREATED
    first_id = r1.json['item']['id']

    _, r2 = await async_client.post(f'/api/collections/{cid}/items',
                                    json={'item_kind': 'url', 'url': '/u/x'})
    assert r2.status_code == HTTPStatus.OK  # already existed -> not created
    assert r2.json['item']['id'] == first_id

    _, rg = await async_client.get(f'/api/collections/{cid}')
    assert rg.json['collection']['item_count'] == 1


@pytest.mark.asyncio
async def test_reorder_ignores_duplicate_ids(async_client, test_session):
    """Duplicate ids in the reorder list must not leave a position gap."""
    _, response = await async_client.post('/api/collections', json={'name': 'DupOrder'})
    cid = response.json['collection']['id']

    ids = []
    for name in ('a', 'b', 'c'):
        _, r = await async_client.post(f'/api/collections/{cid}/items',
                                       json={'item_kind': 'url', 'url': f'/u/{name}'})
        ids.append(r.json['item']['id'])

    # Pass the first id twice; positions must stay contiguous (1, 2, 3).
    _, response = await async_client.put(f'/api/collections/{cid}/items/order',
                                         json={'item_ids': [ids[0], ids[1], ids[0]]})
    assert response.status_code == HTTPStatus.OK, response.json
    positions = sorted(i['position'] for i in response.json['collection']['items'])
    assert positions == [1, 2, 3], positions


@pytest.mark.asyncio
async def test_playlist_directory_sync(async_client, test_session, test_directory):
    """Adding items materializes ordered files into the playlists directory; reorder re-prefixes."""
    from wrolpi.files.models import FileGroup

    _, response = await async_client.post('/api/collections', json={'name': 'Sync Test'})
    cid = response.json['collection']['id']

    # A real file becomes a FileGroup, added as a file item.
    path = test_directory / 'lesson.pdf'
    path.write_bytes(b'%PDF-1.4 test')
    fg = FileGroup.from_paths(test_session, path)
    test_session.commit()
    _, rf = await async_client.post(f'/api/collections/{cid}/items',
                                    json={'item_kind': 'file', 'file_group_id': fg.id})
    file_item_id = rf.json['item']['id']
    # A url item.
    _, ru = await async_client.post(f'/api/collections/{cid}/items',
                                    json={'item_kind': 'url', 'url': '/map?lat=1&lon=2&z=3', 'title': 'Map Spot'})
    url_item_id = ru.json['item']['id']

    playlist_dir = test_directory / 'playlists' / 'Sync Test'
    names = sorted(p.name for p in playlist_dir.iterdir())
    assert any(n.startswith('0001_') and n.endswith('lesson.pdf') for n in names), names
    assert any(n.startswith('0002_') and n.endswith('.html') for n in names), names
    # The file is a hard link to the source (same inode).
    link = next(p for p in playlist_dir.iterdir() if p.name.startswith('0001_'))
    assert link.stat().st_ino == path.stat().st_ino

    # Reorder so the url is first; prefixes must follow the new positions.
    await async_client.put(f'/api/collections/{cid}/items/order',
                           json={'item_ids': [url_item_id, file_item_id]})
    names = sorted(p.name for p in playlist_dir.iterdir())
    assert any(n.startswith('0001_') and n.endswith('.html') for n in names), names
    assert any(n.startswith('0002_') and n.endswith('lesson.pdf') for n in names), names

    # Removing the url item drops its stub and re-sequences the file to 0001_.
    await async_client.delete(f'/api/collections/{cid}/items/{url_item_id}')
    names = sorted(p.name for p in playlist_dir.iterdir())
    assert not any(n.endswith('.html') for n in names), names
    assert any(n.startswith('0001_') and n.endswith('lesson.pdf') for n in names), names


@pytest.mark.asyncio
async def test_url_stub_neutralizes_dangerous_scheme(async_client, test_session, test_directory):
    """A javascript: url item must not produce an executable href in its on-disk stub."""
    _, response = await async_client.post('/api/collections', json={'name': 'XSS'})
    cid = response.json['collection']['id']
    await async_client.post(f'/api/collections/{cid}/items',
                            json={'item_kind': 'url', 'url': 'javascript:alert(1)', 'title': 'evil'})

    stub = next(p for p in (test_directory / 'playlists' / 'XSS').iterdir() if p.name.endswith('.html'))
    content = stub.read_text()
    assert 'javascript:' not in content, content
    assert 'about:blank' in content


@pytest.mark.asyncio
async def test_playlists_config_round_trip(async_client, test_session, test_directory):
    """A playlist's items survive a dump -> wipe DB -> import cycle (config is source of truth)."""
    from wrolpi.collections.config import playlists_config
    from wrolpi.files.models import FileGroup

    _, r = await async_client.post('/api/collections', json={'name': 'Roundtrip'})
    cid = r.json['collection']['id']

    path = test_directory / 'a.pdf'
    path.write_bytes(b'%PDF-1.4 x')
    fg = FileGroup.from_paths(test_session, path)
    test_session.commit()
    await async_client.post(f'/api/collections/{cid}/items',
                            json={'item_kind': 'file', 'file_group_id': fg.id})
    await async_client.post(f'/api/collections/{cid}/items',
                            json={'item_kind': 'url', 'url': '/map?x=1', 'title': 'Spot'})

    # Dump to playlists.yaml, wipe playlists from the DB, then re-import from config.
    playlists_config.dump_config()
    test_session.query(Collection).filter_by(kind='playlist').delete()
    test_session.commit()
    assert test_session.query(Collection).filter_by(kind='playlist').count() == 0

    playlists_config.import_config()
    test_session.expire_all()

    collection = test_session.query(Collection).filter_by(name='Roundtrip', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['file', 'url']
    assert collection.items[0].file_group_id == fg.id
    assert collection.items[1].url == '/map?x=1'
    assert collection.items[1].title == 'Spot'
    assert [i.position for i in collection.items] == [1, 2]


@pytest.mark.asyncio
async def test_add_zim_item_end_to_end(async_client, test_session, test_directory):
    """A Zim article can be added, renders an on-disk stub, and survives a config round trip."""
    from modules.zim.models import Zim
    from wrolpi.collections.config import playlists_config
    from wrolpi.vars import PROJECT_DIR

    zim_path = test_directory / 'wikipedia.zim'
    zim_path.write_bytes((PROJECT_DIR / 'test/zim.zim').read_bytes())
    zim = Zim.from_paths(test_session, zim_path)
    test_session.commit()

    _, response = await async_client.post('/api/collections', json={'name': 'Articles'})
    cid = response.json['collection']['id']

    # An entry that does not exist in the Zim is rejected.
    _, response = await async_client.post(f'/api/collections/{cid}/items', json={
        'item_kind': 'zim', 'zim_id': zim.id, 'zim_entry': 'nonexistent-entry'})
    assert response.status_code == HTTPStatus.BAD_REQUEST, response.json

    # A real entry is added.
    _, response = await async_client.post(f'/api/collections/{cid}/items', json={
        'item_kind': 'zim', 'zim_id': zim.id, 'zim_entry': 'home', 'title': 'Home Page'})
    assert response.status_code == HTTPStatus.CREATED, response.json
    item = response.json['item']
    assert item['item_kind'] == 'zim'
    assert item['zim'] == {'id': zim.id, 'entry': 'home', 'path': str(zim_path)}

    # The on-disk stub redirects to the Zim entry API.
    stub = test_directory / 'playlists' / 'Articles' / '0001_Home Page.html'
    assert stub.is_file()
    assert f'/api/zim/{zim.id}/entry/home' in stub.read_text()

    # Config round trip: the zim item is stored by media-relative path and restored after a wipe.
    playlists_config.dump_config()
    test_session.query(Collection).filter_by(kind='playlist').delete()
    test_session.commit()
    playlists_config.import_config()
    test_session.expire_all()

    collection = test_session.query(Collection).filter_by(name='Articles', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['zim']
    assert collection.items[0].zim_id == zim.id
    assert collection.items[0].zim_entry == 'home'
    assert collection.items[0].title == 'Home Page'


@pytest.mark.asyncio
async def test_remove_unknown_item(async_client, test_session):
    _, response = await async_client.post('/api/collections', json={'name': 'Empty'})
    cid = response.json['collection']['id']
    _, response = await async_client.delete(f'/api/collections/{cid}/items/99999')
    assert response.status_code == HTTPStatus.NOT_FOUND
