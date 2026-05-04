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
async def test_docs_search_multi_word(async_client, test_session, test_directory, example_epub, refresh_files):
    """Docs search handles multi-word queries without tsquery syntax errors."""
    await refresh_files()

    # Multi-word search should not raise a syntax error.
    content = dict(search_str='primitive fire starting friction methods')
    request, response = await async_client.post('/api/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_get_doc(async_client, test_session, test_directory, example_epub, refresh_files):
    """Single doc endpoint returns the doc."""
    await refresh_files()

    doc = test_session.query(Doc).first()
    assert doc

    request, response = await async_client.get(f'/api/docs/{doc.file_group_id}')
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
    """Docs can be deleted, including their on-disk files and FileGroup row."""
    from wrolpi.files.models import FileGroup
    await refresh_files()

    doc = test_session.query(Doc).first()
    assert doc
    file_group_id = doc.file_group_id
    paths = list(doc.file_group.my_paths())
    assert paths and all(p.is_file() for p in paths)

    body = json.dumps({'file_group_ids': [file_group_id]})
    request, response = await async_client.post('/api/files/delete_groups', content=body)
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Doc, FileGroup, and on-disk files all removed.
    assert test_session.query(Doc).filter_by(file_group_id=file_group_id).one_or_none() is None
    assert test_session.query(FileGroup).filter_by(id=file_group_id).one_or_none() is None
    assert all(not p.exists() for p in paths)


@pytest.mark.asyncio
async def test_delete_doc_tagged_requires_force(async_client, test_session, doc_factory, tag_factory,
                                                await_switches):
    """The unified delete endpoint returns 409 for tagged docs until force=true is passed."""
    from wrolpi.files.models import FileGroup
    tag = await tag_factory()
    doc = doc_factory()
    doc.file_group.add_tag(test_session, tag.name)
    test_session.commit()
    file_group_id = doc.file_group_id
    paths = list(doc.file_group.my_paths())

    body = json.dumps({'file_group_ids': [file_group_id]})
    request, response = await async_client.post('/api/files/delete_groups', content=body)
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json['code'] == 'FILE_GROUP_IS_TAGGED'
    assert len(response.json['file_groups']) == 1
    assert response.json['file_groups'][0]['id'] == file_group_id
    assert tag.name in response.json['file_groups'][0]['tags']
    # Nothing was deleted.
    assert all(p.is_file() for p in paths)
    assert test_session.query(Doc).count() == 1

    # With force=true, the Doc is deleted.
    body = json.dumps({'file_group_ids': [file_group_id], 'force': True})
    request, response = await async_client.post('/api/files/delete_groups', content=body)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert all(not p.exists() for p in paths)
    assert test_session.query(Doc).count() == 0
    assert test_session.query(FileGroup).filter_by(id=file_group_id).one_or_none() is None
    await await_switches()


@pytest.mark.asyncio
async def test_delete_doc_atomic_when_some_tagged(async_client, test_session, doc_factory, tag_factory):
    """When deleting multiple Docs and any are tagged, NONE are deleted until force=true."""
    untagged = doc_factory()
    tagged = doc_factory()
    tag = await tag_factory()
    tagged.file_group.add_tag(test_session, tag.name)
    test_session.commit()
    untagged_paths = list(untagged.file_group.my_paths())
    tagged_paths = list(tagged.file_group.my_paths())

    body = json.dumps({'file_group_ids': [untagged.file_group_id, tagged.file_group_id]})
    request, response = await async_client.post('/api/files/delete_groups', content=body)
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json['code'] == 'FILE_GROUP_IS_TAGGED'
    returned_ids = {fg['id'] for fg in response.json['file_groups']}
    assert returned_ids == {tagged.file_group_id}
    # Nothing was deleted.
    assert all(p.is_file() for p in untagged_paths)
    assert all(p.is_file() for p in tagged_paths)
    assert test_session.query(Doc).count() == 2
