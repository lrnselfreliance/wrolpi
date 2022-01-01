import json
from http import HTTPStatus


def test_archives_search(test_session, archive_directory, archive_factory, test_client):
    """
    Archives can be searched by their title and their contents.
    """
    archive_factory('example.com', 'https://example.com/one', 'my archive', 'foo bar qux')
    archive_factory('example.com', 'https://example.com/one', 'other archive', 'foo baz qux qux')
    archive_factory('example.org', title='archive third', contents='baz qux qux qux')
    archive_factory('example.org')  # has no contents

    def check_results(data, ids):
        request, response = test_client.post('/api/archive/search', content=json.dumps(data))
        assert response.status_code == HTTPStatus.OK, response.json
        assert [i['id'] for i in response.json['archives']] == ids

    # 1 and 2 contain "foo".
    data = {'search_str': 'foo'}
    check_results(data, [1, 2])

    # 2 and 3 contain "baz".
    data = {'search_str': 'baz'}
    check_results(data, [2, 3])

    # 1 contains "bar".
    data = {'search_str': 'bar'}
    check_results(data, [1, ])

    # No archives contain "huzzah"
    data = {'search_str': 'huzzah'}
    check_results(data, [])

    # Only 3 contains "baz" and is in domain "example.org"
    data = {'search_str': 'baz', 'domain': 'example.org'}
    check_results(data, [3, ])

    # 1's title contains "my", this is ignored by Postgres.
    data = {'search_str': 'my'}
    check_results(data, [])

    # 3's title contains "third".
    data = {'search_str': 'third'}
    check_results(data, [3, ])

    # All titles contain "qux", but they contain different amounts.  They are ordered by the amount.
    data = {'search_str': 'qux'}
    check_results(data, [3, 2, 1])
