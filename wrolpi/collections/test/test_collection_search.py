from http import HTTPStatus

import pytest

from wrolpi.collections import Collection


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['domain', 'playlist'])
async def test_search_collections_other_estimate(async_client, test_session, tag_factory, kind):
    """Collections can be searched by kind, name, and/or Tags; the Other tab's estimate counts the same
    Collections."""
    tag1, tag2 = await tag_factory(), await tag_factory()
    test_session.add_all([
        Collection(name='cooking one', kind=kind, tag=tag1),
        Collection(name='cooking two', kind=kind),
        Collection(name='gardening', kind=kind, tag=tag2),
        # Another kind is never counted.
        Collection(name='cooking other', kind='channel' if kind == 'domain' else 'domain', tag=tag1),
    ])
    test_session.commit()

    async def search(body):
        request, response = await async_client.post('/api/collections/search', json=dict(body, kind=kind))
        assert response.status_code == HTTPStatus.OK
        return sorted(i['name'] for i in response.json['collections'])

    cases = [
        (dict(search_str='cooking'), ['cooking one', 'cooking two']),
        (dict(tag_names=[tag1.name]), ['cooking one']),
        # Any of the Tags.
        (dict(tag_names=[tag1.name, tag2.name]), ['cooking one', 'gardening']),
        # The name and the Tags must both match.
        (dict(search_str='garden', tag_names=[tag2.name]), ['gardening']),
        (dict(search_str='cooking', tag_names=[tag2.name]), []),
    ]
    count_key = f'{kind}_count'
    for body, expected in cases:
        assert await search(body) == expected, body
        request, response = await async_client.post('/api/search_other_estimates', json=body)
        assert response.status_code == HTTPStatus.OK
        assert response.json['others'][count_key] == len(expected), body

    # Nothing to search by: the Other tab shows none (the search endpoint lists every Collection of the kind).
    for body in (dict(search_str=''), dict(search_str='  '), dict()):
        request, response = await async_client.post('/api/search_other_estimates', json=body)
        assert response.json['others'][count_key] == 0, body
