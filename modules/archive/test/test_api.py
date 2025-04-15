import json
from http import HTTPStatus

import pytest

from modules.archive import lib, Archive
from wrolpi.test.common import skip_circleci, skip_macos


def check_results(test_client, data, ids):
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    if not response.status_code == HTTPStatus.OK:
        raise AssertionError(str(response.json))

    if ids:
        file_groups = response.json['file_groups']
        assert file_groups, f'Expected {len(ids)} archives but did not receive any'
    assert [i['id'] for i in response.json['file_groups']] == ids, \
        f'{response.json["file_groups"][0]["id"]}..{response.json["file_groups"][-1]["id"]}'


def test_archives_search_order(test_session, archive_directory, archive_factory, test_client):
    """Search using all orders."""
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    for order_by in lib.ARCHIVE_ORDERS:
        data = {'search_str': 'foo', 'order_by': order_by}
        request, response = test_client.post('/api/archive/search', content=json.dumps(data))
        if not response.status_code == HTTPStatus.OK:
            raise AssertionError(str(response.json))

        data = {'search_str': None, 'order_by': order_by}
        request, response = test_client.post('/api/archive/search', content=json.dumps(data))
        if not response.status_code == HTTPStatus.OK:
            raise AssertionError(str(response.json))


def test_archives_search(test_session, archive_directory, archive_factory, test_client):
    """Archives can be searched by their title and their contents."""
    # Search with no archives.
    check_results(test_client, {'search_str': 'foo'}, [])

    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents
    test_session.commit()

    # 1 and 2 contain "foo".
    data = {'search_str': 'foo'}
    check_results(test_client, data, [2, 1])

    # 2 and 3 contain "baz".
    data = {'search_str': 'baz'}
    check_results(test_client, data, [3, 2])

    # 1 contains "bar".
    data = {'search_str': 'bar'}
    check_results(test_client, data, [1, ])

    # No archives contain "huzzah"
    data = {'search_str': 'huzzah'}
    check_results(test_client, data, [])

    # Only 3 contains "baz" and is in domain "example.org"
    data = {'search_str': 'baz', 'domain': 'example.org'}
    check_results(test_client, data, [3, ])

    # 1's title contains "my", this is ignored by Postgres.
    data = {'search_str': 'my'}
    check_results(test_client, data, [])

    # 3's title contains "third".
    data = {'search_str': 'third'}
    check_results(test_client, data, [3, ])

    # All contents contain "qux", but they contain different amounts.  They are ordered by the amount.
    data = {'search_str': 'qux'}
    check_results(test_client, data, [3, 2, 1])

    data = {'search_str': 'qux', 'order_by': 'bad order_by'}
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_search_archive_tags(test_session, async_client, archive_factory, tag_factory):
    """Tagged Archives can be searched."""
    tag = await tag_factory()
    archive_factory(domain='example.com', tag_names=[tag.name, ])
    test_session.commit()

    content = {'search_str': '', 'domain': 'example.com', 'tag_names': [tag.name, ]}
    request, response = await async_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups']
    assert response.json['totals']['file_groups'] == 1

    content = {'search_str': '', 'domain': 'example.com', 'tag_names': ['does not exist', ]}
    request, response = await async_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_groups'] == []
    assert response.json['totals']['file_groups'] == 0


def test_archives_search_headline(test_session, archive_directory, archive_factory, test_client):
    """Headlines can be requested."""
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents
    test_session.commit()

    content = dict(search_str='foo')
    request, response = test_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK

    # Headlines are only fetched if requested.
    assert response.json['file_groups'][0]['d_headline'] is None
    assert response.json['file_groups'][1]['d_headline'] is None

    content = dict(search_str='foo', headline=True)
    request, response = test_client.post('/api/archive/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK

    # Postgresql uses <b>...</b> to highlight matching words.
    assert response.json['file_groups'][0]['d_headline'] == '<b>foo</b> baz qux qux'
    assert response.json['file_groups'][1]['d_headline'] == '<b>foo</b> bar qux'


def test_search_offset(test_session, archive_factory, test_client):
    """Archive search can be offset."""
    for i in range(500):
        archive_factory('example.com', f'https://example.com/{i}', contents='foo bar')
    test_session.commit()

    data = {'search_str': None, 'offset': 0}
    check_results(test_client, data, list(range(500, 480, -1)))
    data = {'search_str': None, 'offset': 20}
    check_results(test_client, data, list(range(480, 460, -1)))
    data = {'search_str': None, 'offset': 100}
    check_results(test_client, data, list(range(400, 380, -1)))
    data = {'search_str': None, 'offset': 200}
    check_results(test_client, data, list(range(300, 280, -1)))
    data = {'search_str': None, 'offset': 500}
    check_results(test_client, data, [])


def test_archives_search_no_query(test_session, archive_factory, test_client):
    """Archive Search API endpoint does not require data in the body."""
    # Add 100 random archives.
    for _ in range(100):
        archive_factory('example.com')
    test_session.commit()

    # All archives are returned when no `search_str` is passed.
    request, response = test_client.post('/api/archive/search', content='{}')
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == list(range(100, 80, -1))
    assert response.json['totals']['file_groups'] == 100

    # All archives are from "example.com".
    data = dict(domain='example.com')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == list(range(100, 80, -1))
    assert response.json['totals']['file_groups'] == 100

    # No archives are from "example.org".
    data = dict(domain='example.org')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['file_groups']] == []
    assert response.json['totals']['file_groups'] == 0


def test_archive_and_domain_crud(test_session, test_client, archive_factory):
    """Getting an Archive returns it's File.  Testing deleting Archives."""
    # Can get empty results.
    request, response = test_client.get(f'/api/archive/1')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'] == []

    archive1 = archive_factory(domain='example.com', url='https://example.com/1')
    archive2 = archive_factory(domain='example.com', url='https://example.com/1')
    test_session.commit()

    # Archive1 has Archive2 as history.
    request, response = test_client.get(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_group']['id'] == archive1.id
    assert response.json['history'][0]['id'] == archive2.id

    # Archive2 has Archive1 as history.
    request, response = test_client.get(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.OK
    assert archive2.id == response.json['file_group']['id']
    assert response.json['history'][0]['id'] == archive1.id

    # Only one domain.
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'][0]['domain'] == 'example.com'
    assert response.json['domains'][0]['size'] == 116

    # Deleting works.
    request, response = test_client.delete(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Trying to delete again returns NOT_FOUND.
    request, response = test_client.delete(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Can't get deleted Archive.
    request, response = test_client.get(f'/api/archive/{archive1.id}')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # Archive2 no longer has history.
    request, response = test_client.get(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_group']['id'] == archive2.id
    assert response.json['history'] == []

    # No Archives, no Domains.
    request, response = test_client.delete(f'/api/archive/{archive2.id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = test_client.get(f'/api/archive/domains')
    assert response.status_code == HTTPStatus.OK
    assert response.json['domains'] == []


@skip_macos
@skip_circleci
@pytest.mark.asyncio
async def test_archive_upload(test_session, async_client, singlefile_contents_factory, make_multipart_form,
                              await_switches, events_history):
    """Test converting a SingleFile from the SingleFile browser extension to an Archive."""
    singlefile_contents = singlefile_contents_factory(title='upload title', url='https://example.com/single-file-url')
    forms = [
        dict(name='url', value='https://example.com/form-url'),
        dict(name='singlefile_contents', value=singlefile_contents, filename='singlefile_contents')
    ]
    body = make_multipart_form(forms)
    headers = {'Content-Type': 'multipart/form-data; boundary=-----------------------------sanic'}
    request, response = await async_client.post('/api/archive/upload', content=body, headers=headers)
    assert response.status_code == HTTPStatus.OK

    await await_switches()

    archive, = test_session.query(Archive).all()
    assert archive.singlefile_path.is_file(), 'Singlefile should have been saved.'
    assert archive.readability_path.is_file(), 'Readability should be extracted.'
    assert archive.readability_json_path.is_file(), 'Readability json should be extracted.'
    assert archive.screenshot_path.is_file(), 'Screenshot should have been created'
    assert archive.file_group.title == 'upload title', 'Title was not correct'
    assert archive.file_group.url == 'https://example.com/single-file-url', 'SingleFile URL should be trusted'
    events = list(events_history)
    assert events and events[0]['event'] == 'upload_archive', 'Event should have been sent.'
