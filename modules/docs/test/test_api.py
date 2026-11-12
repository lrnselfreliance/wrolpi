"""Tests for the docs API."""
import json
from http import HTTPStatus
from unittest.mock import patch

import pytest

from modules.docs.models import Doc
from wrolpi.conftest import production_like_sessions
from wrolpi.db import get_db_session
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag


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
async def test_get_doc_marks_viewed(async_client, test_session, doc_factory):
    """Getting a doc marks it viewed, unless skip_viewed is requested."""
    doc = doc_factory()
    file_group_id = doc.file_group_id
    test_session.commit()

    request, response = await async_client.get(f'/api/docs/{file_group_id}?skip_viewed=true')
    assert response.status_code == HTTPStatus.OK
    test_session.expire_all()
    assert test_session.query(Doc).filter_by(file_group_id=file_group_id).one().file_group.viewed is None

    request, response = await async_client.get(f'/api/docs/{file_group_id}')
    assert response.status_code == HTTPStatus.OK
    test_session.expire_all()
    assert test_session.query(Doc).filter_by(file_group_id=file_group_id).one().file_group.viewed is not None


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
async def test_docs_search_orders(async_client, test_session, doc_factory):
    """Docs sort like the other searches: a `-` prefix is descending, and an unknown order is a 400."""
    import datetime
    utc = datetime.timezone.utc
    # Each order puts these in a different sequence than their ids, so an ignored order cannot pass.
    one = doc_factory(size=500)
    two = doc_factory(size=10)
    three = doc_factory(size=1000)
    for doc, year, title in ((one, 2022, 'mmm'), (two, 2024, 'aaa'), (three, 2020, 'zzz')):
        doc.file_group.published_datetime = datetime.datetime(year, 1, 1, tzinfo=utc)
        doc.file_group.title = doc.file_group.a_text = title
    test_session.commit()
    one, two, three = one.file_group_id, two.file_group_id, three.file_group_id

    async def search_ids(**body):
        request, response = await async_client.post('/api/docs/search', content=json.dumps(body))
        assert response.status_code == HTTPStatus.OK, response.json
        return [i['id'] for i in response.json['file_groups']]

    expected = {
        'size': [two, one, three],
        '-size': [three, one, two],
        'published_datetime': [three, one, two],
        '-published_datetime': [two, one, three],
        'title': [two, one, three],
        '-title': [three, one, two],
    }
    for order_by, ids in expected.items():
        assert await search_ids(order_by=order_by) == ids, order_by
        # A filtered search orders the same as the unfiltered browse.
        assert await search_ids(order_by=order_by, mimetype='application/pdf') == ids, order_by

    # Without an order, the newest Docs are first.
    assert await search_ids() == [two, one, three]

    request, response = await async_client.post('/api/docs/search', content=json.dumps(dict(order_by='bogus')))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_docs_search_defaults_to_rank(async_client, test_session, doc_factory):
    """A Docs search without an order puts the most relevant Docs first."""
    import datetime
    utc = datetime.timezone.utc
    strong, weak = doc_factory(), doc_factory()
    strong.file_group.published_datetime = datetime.datetime(2020, 1, 1, tzinfo=utc)
    strong.file_group.title = strong.file_group.a_text = 'foo foo foo'
    # The weak match is newer, so date order would put it first.
    weak.file_group.published_datetime = datetime.datetime(2024, 1, 1, tzinfo=utc)
    weak.file_group.title = weak.file_group.a_text = 'foo bar baz qux quux corge grault garply'
    test_session.commit()

    async def search_ids(**body):
        request, response = await async_client.post('/api/docs/search', content=json.dumps(body))
        assert response.status_code == HTTPStatus.OK, response.json
        return [i['id'] for i in response.json['file_groups']]

    best_first = [strong.file_group_id, weak.file_group_id]
    assert await search_ids(search_str='foo') == best_first
    assert await search_ids(search_str='foo', order_by='rank') == best_first
    assert await search_ids(search_str='foo', order_by='-rank') == best_first[::-1]
    assert await search_ids(search_str='foo', order_by='-published_datetime') == best_first[::-1]


@pytest.mark.asyncio
async def test_docs_search_tag_names_and_any_tag(async_client, test_session, doc_factory, tag_factory):
    """Docs tag filtering matches the other searches: `tag_names` requires every tag, `any_tag` requires some tag."""
    tag1, tag2 = await tag_factory(), await tag_factory()
    one_tag, both_tags, untagged = doc_factory(), doc_factory(), doc_factory()
    one_tag.file_group.add_tag(test_session, tag1.id)
    both_tags.file_group.add_tag(test_session, tag1.id)
    both_tags.file_group.add_tag(test_session, tag2.id)
    test_session.commit()

    async def search_ids(**body):
        request, response = await async_client.post('/api/docs/search', content=json.dumps(body))
        assert response.status_code == HTTPStatus.OK, response.json
        assert response.json['totals']['file_groups'] == len(response.json['file_groups'])
        return {i['id'] for i in response.json['file_groups']}

    assert await search_ids(tag_names=[tag1.name]) == {one_tag.file_group_id, both_tags.file_group_id}
    # Only one Doc has both Tags.
    assert await search_ids(tag_names=[tag1.name, tag2.name]) == {both_tags.file_group_id}
    # Any Tag excludes only the untagged Doc.
    assert await search_ids(any_tag=True) == {one_tag.file_group_id, both_tags.file_group_id}
    assert await search_ids(any_tag=False) == {one_tag.file_group_id, both_tags.file_group_id,
                                               untagged.file_group_id}

    # Cannot search for any_tag, and tag names.
    content = dict(tag_names=[tag1.name], any_tag=True)
    request, response = await async_client.post('/api/docs/search', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST


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


@pytest.mark.asyncio
async def test_get_doc_records_view_after_a_concurrent_write(async_client, test_session, doc_factory):
    """Viewing a doc still succeeds, and is recorded, when another connection commits during the request."""
    file_group_id = doc_factory().file_group_id
    test_session.commit()

    __json__ = FileGroup.__json__
    concurrent_writes = []

    def json_after_a_concurrent_write(self):
        # A download or refresh commits while the doc is being read.
        if not concurrent_writes:
            with get_db_session(commit=True) as session:
                session.add(Tag(name='concurrent', color='#000000'))
            concurrent_writes.append(True)
        return __json__(self)

    with production_like_sessions(test_session), \
            patch.object(FileGroup, '__json__', json_after_a_concurrent_write):
        request, response = await async_client.get(f'/api/docs/{file_group_id}')
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['file_group']['viewed']

    test_session.rollback()  # End the test's own read snapshot to see the request's commit.
    assert test_session.query(FileGroup).filter_by(id=file_group_id).one().viewed is not None
