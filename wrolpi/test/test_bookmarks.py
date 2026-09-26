import yaml

from wrolpi.bookmarks import get_bookmarks_config
from wrolpi.common import get_media_directory
from wrolpi.errors import ValidationError


def read_config():
    return yaml.safe_load((get_media_directory() / 'config/bookmarks.yaml').read_text())


async def test_bookmarks_tree_api(async_client, test_directory):
    """Bookmarks and directories can be added, edited, moved and deleted, and are persisted to YAML."""
    request, response = await async_client.get('/api/bookmarks')
    assert response.status == 200
    assert response.json['bookmarks'] == []

    # A top-level bookmark; new_tab defaults to false.
    request, response = await async_client.post('/api/bookmarks', json=dict(name='Videos', url='/videos'))
    assert response.status == 201, response.json
    videos = response.json['bookmark']
    assert videos == dict(id=1, name='Videos', url='/videos', new_tab=False)

    # A directory, then a bookmark inside it that opens in a new tab.
    request, response = await async_client.post('/api/bookmarks/directory', json=dict(name='Services'))
    assert response.status == 201
    services = response.json['bookmark']
    assert services == dict(id=2, name='Services', children=[])
    request, response = await async_client.post('/api/bookmarks',
                                                json=dict(name='Jellyfin', url=':8096/', new_tab=True,
                                                          parent_id=services['id']))
    assert response.status == 201
    jellyfin = response.json['bookmark']
    assert jellyfin['id'] == 3 and jellyfin['new_tab'] is True

    request, response = await async_client.get('/api/bookmarks')
    assert response.json['bookmarks'] == [
        dict(id=1, name='Videos', url='/videos', new_tab=False),
        dict(id=2, name='Services', children=[
            dict(id=3, name='Jellyfin', url=':8096/', new_tab=True),
        ]),
    ]
    # The tree was written to the config file.
    assert read_config()['bookmarks'] == response.json['bookmarks']

    # Rename and re-point a bookmark.
    request, response = await async_client.put('/api/bookmarks/3', json=dict(name='Movies', url='http://:8096/web'))
    assert response.status == 200
    assert response.json['bookmark'] == dict(id=3, name='Movies', url='http://:8096/web', new_tab=True)

    # A directory cannot take a URL.
    request, response = await async_client.put('/api/bookmarks/2', json=dict(url='/videos'))
    assert response.status == 400

    # Move the top-level bookmark into the directory, at the front.
    request, response = await async_client.post('/api/bookmarks/1/move', json=dict(parent_id=2, position=0))
    assert response.status == 200
    request, response = await async_client.get('/api/bookmarks')
    assert [i['id'] for i in response.json['bookmarks']] == [2]
    assert [i['id'] for i in response.json['bookmarks'][0]['children']] == [1, 3]

    # Move it back to the top level, at the end.
    request, response = await async_client.post('/api/bookmarks/1/move', json=dict(parent_id=None))
    assert response.status == 200
    request, response = await async_client.get('/api/bookmarks')
    assert [i['id'] for i in response.json['bookmarks']] == [2, 1]

    # Deleting a directory deletes its contents.
    request, response = await async_client.delete('/api/bookmarks/2')
    assert response.status == 204
    request, response = await async_client.get('/api/bookmarks')
    assert response.json['bookmarks'] == [dict(id=1, name='Videos', url='/videos', new_tab=False)]
    request, response = await async_client.post('/api/bookmarks', json=dict(name='Docs', url='/docs'))
    assert response.json['bookmark']['id'] == 2
    assert read_config()['bookmarks'] == [
        dict(id=1, name='Videos', url='/videos', new_tab=False),
        dict(id=2, name='Docs', url='/docs', new_tab=False),
    ]

    # Unknown nodes are 400s, not crashes.
    request, response = await async_client.delete('/api/bookmarks/999')
    assert response.status == 400
    request, response = await async_client.put('/api/bookmarks/999', json=dict(name='x'))
    assert response.status == 400


async def test_bookmarks_validation(async_client, test_directory):
    """Names are required and URLs must be a path, a port, or an absolute URL."""
    for url in ('', 'videos', 'ftp://example.com', 'javascript:alert(1)', '8096/'):
        request, response = await async_client.post('/api/bookmarks', json=dict(name='x', url=url))
        assert response.status == 400, url
    for url in ('/videos', ':8096/', ':8096', 'http://:8096/web', 'https://example.com', 'HTTP://EXAMPLE.COM'):
        request, response = await async_client.post('/api/bookmarks', json=dict(name='x', url=url))
        assert response.status == 201, url

    request, response = await async_client.post('/api/bookmarks', json=dict(name='  ', url='/videos'))
    assert response.status == 400
    request, response = await async_client.post('/api/bookmarks/directory', json=dict(name=''))
    assert response.status == 400

    # Whitespace is trimmed.
    request, response = await async_client.post('/api/bookmarks', json=dict(name='  Map ', url=' /map '))
    assert response.json['bookmark'] == dict(id=7, name='Map', url='/map', new_tab=False)


async def test_bookmarks_move_guards(async_client, test_directory):
    """A directory cannot be moved into itself or a descendant, and only directories hold children."""
    config = get_bookmarks_config()
    outer = config.add_directory('Outer')
    inner = config.add_directory('Inner', parent_id=outer['id'])
    leaf = config.add_bookmark('Leaf', '/files', parent_id=inner['id'])

    request, response = await async_client.post(f'/api/bookmarks/{outer["id"]}/move', json=dict(parent_id=outer['id']))
    assert response.status == 400
    request, response = await async_client.post(f'/api/bookmarks/{outer["id"]}/move', json=dict(parent_id=inner['id']))
    assert response.status == 400
    # A bookmark is not a directory.
    request, response = await async_client.post(f'/api/bookmarks/{inner["id"]}/move', json=dict(parent_id=leaf['id']))
    assert response.status == 400
    request, response = await async_client.post('/api/bookmarks', json=dict(name='x', url='/x', parent_id=leaf['id']))
    assert response.status == 400

    # The failed moves left the tree untouched.
    assert [i['id'] for i, _, _ in __import__('wrolpi.bookmarks', fromlist=['walk']).walk(config.bookmarks)] == \
           [outer['id'], inner['id'], leaf['id']]


def test_bookmarks_config_import(test_directory, test_wrolpi_config):
    """A hand-edited bookmarks.yaml is imported as-is, including nested directories."""
    config_file = test_directory / 'config/bookmarks.yaml'
    config_file.parent.mkdir(exist_ok=True)
    config_file.write_text(yaml.dump(dict(version=0, bookmarks=[
        dict(id=1, name='Radio', children=[
            dict(id=2, name='OpenWebRX', url=':8073/', new_tab=True),
        ]),
    ])))

    config = get_bookmarks_config()
    config.initialize()
    config.import_config()
    assert config.successful_import is True
    assert config.bookmarks[0]['children'][0]['name'] == 'OpenWebRX'

    # Later additions continue the id sequence past the hand-written ids.
    node = config.add_bookmark('Docs', '/docs')
    assert node['id'] == 3
