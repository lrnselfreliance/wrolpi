import json
from http import HTTPStatus


def check_results(test_client, data, ids):
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['archives']] == ids, \
        f'{response.json["archives"][0]["id"]}..{response.json["archives"][19]["id"]}'


def test_archives_search(test_session, archive_directory, archive_factory, test_client):
    """Archives can be searched by their title and their contents."""
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents

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

    # All titles contain "qux", but they contain different amounts.  They are ordered by the amount.
    data = {'search_str': 'qux'}
    check_results(test_client, data, [3, 2, 1])


def test_search_offset(archive_factory, test_client):
    """Archive search can be offset."""
    for i in range(500):
        archive_factory('example.com', f'https://example.com/{i}', contents='foo bar')

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


def test_archives_search_no_query(archive_factory, test_client):
    """Archive Search API endpoint does not require data in the body."""
    # Add 100 random archives.
    for _ in range(100):
        archive_factory('example.com')

    # All archives are returned when no `search_str` is passed.
    request, response = test_client.post('/api/archive/search', content='{}')
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['archives']] == list(range(100, 80, -1))
    assert response.json['totals']['archives'] == 100

    # All archives are from "example.com".
    data = dict(domain='example.com')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['archives']] == list(range(100, 80, -1))
    assert response.json['totals']['archives'] == 100

    # No archives are from "example.org".
    data = dict(domain='example.org')
    request, response = test_client.post('/api/archive/search', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK, response.json
    assert [i['id'] for i in response.json['archives']] == []
    assert response.json['totals']['archives'] == 0
