"""Tests for the docs API."""
import json
from http import HTTPStatus

import pytest

from modules.docs.models import Doc


@pytest.mark.asyncio
async def test_docs_statistics(async_client, test_session, test_directory, example_epub, refresh_files):
    """Doc statistics endpoint returns correct counts."""
    await refresh_files()

    request, response = await async_client.get('/api/docs/statistics')
    assert response.status_code == HTTPStatus.OK
    stats = response.json['statistics']
    assert stats['doc_count'] >= 1
    assert stats['epub_count'] >= 1


@pytest.mark.asyncio
async def test_docs_search(async_client, test_session, test_directory, example_epub, refresh_files):
    """Docs search endpoint works."""
    await refresh_files()

    content = dict(search_str='WROLPi')
    request, response = await async_client.post('/api/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert len(response.json['file_groups']) >= 1


@pytest.mark.asyncio
async def test_get_doc(async_client, test_session, test_directory, example_epub, refresh_files):
    """Single doc endpoint returns the doc."""
    await refresh_files()

    doc = test_session.query(Doc).first()
    assert doc

    request, response = await async_client.get(f'/api/docs/{doc.id}')
    assert response.status_code == HTTPStatus.OK
    assert response.json['file_group']


@pytest.mark.asyncio
async def test_docs_search_by_tag(async_client, test_session, doc_factory, tag_factory):
    """Docs can be searched by tag."""
    tag = await tag_factory()
    doc = doc_factory()
    doc.file_group.add_tag(test_session, tag.name)
    test_session.commit()

    # Search with matching tag returns the doc.
    content = dict(tag_names=[tag.name])
    request, response = await async_client.post('/api/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['totals']['file_groups'] == 1

    # Search with non-existent tag returns nothing.
    content = dict(tag_names=['nonexistent'])
    request, response = await async_client.post('/api/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['totals']['file_groups'] == 0


@pytest.mark.asyncio
async def test_delete_doc(async_client, test_session, test_directory, example_epub, refresh_files):
    """Docs can be deleted."""
    await refresh_files()

    doc = test_session.query(Doc).first()
    assert doc
    doc_id = doc.id

    request, response = await async_client.delete(f'/api/docs/{doc_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert test_session.query(Doc).filter_by(id=doc_id).one_or_none() is None
