import json
from http import HTTPStatus


def check_results(test_client, data, ids):
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    if not response.status_code == HTTPStatus.OK:
        raise AssertionError(str(response.json))

    if ids:
        file_groups = response.json['file_groups']
        assert file_groups, f'Expected {len(ids)} archives but did not receive any'
    assert [i['id'] for i in response.json['file_groups']] == ids, \
        f'{response.json["file_groups"][0]["id"]}..{response.json["file_groups"][-1]["id"]}'


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
