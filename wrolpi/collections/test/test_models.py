import pytest

from wrolpi.collections import Collection
from wrolpi.errors import UnknownCollection


def test_collection_get_by_id(test_session, test_directory):
    """Collection.get_by_id should accept session as first argument, id as second."""
    collection = Collection(name='test collection', directory=test_directory / 'test_collection')
    test_session.add(collection)
    test_session.flush()

    # Session must be first argument (session-first pattern)
    found = Collection.get_by_id(test_session, collection.id)
    assert found is not None
    assert found.id == collection.id

    # Non-existent ID should return None
    not_found = Collection.get_by_id(test_session, 99999)
    assert not_found is None


def test_collection_find_by_id(test_session, test_directory):
    """Collection.find_by_id should accept session as first argument, id as second."""
    collection = Collection(name='test collection', directory=test_directory / 'test_collection')
    test_session.add(collection)
    test_session.flush()

    # Session must be first argument (session-first pattern)
    found = Collection.find_by_id(test_session, collection.id)
    assert found is not None
    assert found.id == collection.id

    # Non-existent ID should raise UnknownCollection
    with pytest.raises(UnknownCollection):
        Collection.find_by_id(test_session, 99999)
