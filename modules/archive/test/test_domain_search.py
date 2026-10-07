from http import HTTPStatus

import pytest

from wrolpi.collections import Collection


@pytest.mark.asyncio
async def test_search_domains(async_client, test_session, tag_factory):
    """Domains can be searched by their name and/or Tags, and the Other tab's estimate counts the same Domains."""
    tag1, tag2 = await tag_factory(), await tag_factory()
    test_session.add_all([
        Collection(name='cooking.example.com', kind='domain', tag=tag1),
        Collection(name='cooking.example.org', kind='domain'),
        Collection(name='gardening.example.com', kind='domain', tag=tag2),
        # Not a Domain.
        Collection(name='cooking channel', kind='channel', tag=tag1),
    ])
    test_session.commit()

    async def search(body):
        request, response = await async_client.post('/api/archive/domains/search', json=body)
        assert response.status_code == HTTPStatus.OK
        return sorted(i['domain'] for i in response.json['domains'])

    cases = [
        (dict(search_str='cooking'), ['cooking.example.com', 'cooking.example.org']),
        (dict(tag_names=[tag1.name]), ['cooking.example.com']),
        # Any of the Tags.
        (dict(tag_names=[tag1.name, tag2.name]), ['cooking.example.com', 'gardening.example.com']),
        # The name and the Tags must both match.
        (dict(search_str='example.com', tag_names=[tag2.name]), ['gardening.example.com']),
        (dict(search_str='cooking', tag_names=[tag2.name]), []),
        # Nothing to search by matches nothing.
        (dict(search_str=''), []),
        (dict(), []),
    ]
    for body, expected in cases:
        assert await search(body) == expected, body
        request, response = await async_client.post('/api/search_other_estimates', json=body)
        assert response.status_code == HTTPStatus.OK
        assert response.json['others']['domain_count'] == len(expected), body

    request, response = await async_client.post('/api/archive/domains/search', json=dict(tag_names=[tag1.name]))
    domain, = response.json['domains']
    assert domain['tag_name'] == tag1.name
