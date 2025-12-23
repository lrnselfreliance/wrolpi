import pytest

from wrolpi.collections import Collection
from wrolpi.collections.errors import UnknownCollection
from wrolpi.common import get_wrolpi_config


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


def test_collection_format_destination_channel(test_session, test_directory):
    """Collection.format_destination formats path for channel collections."""
    collection = Collection(name='My Channel', kind='channel')
    test_session.add(collection)
    test_session.flush()

    destination = collection.format_destination()
    # Should use videos_destination template: videos/%(channel_tag)s/%(channel_name)s
    assert destination == test_directory / 'videos' / 'My Channel'

    # With tag
    destination_with_tag = collection.format_destination(tag_name='News')
    assert destination_with_tag == test_directory / 'videos' / 'News' / 'My Channel'


def test_collection_format_destination_domain(test_session, test_directory):
    """Collection.format_destination formats path for domain collections."""
    collection = Collection(name='example.com', kind='domain')
    test_session.add(collection)
    test_session.flush()

    destination = collection.format_destination()
    # Should use archive_destination template: archive/%(domain)s
    assert destination == test_directory / 'archive' / 'example.com'

    # With tag - default template doesn't include %(domain_tag)s, so tag has no effect
    destination_with_tag = collection.format_destination(tag_name='Tech')
    # Default archive_destination is 'archive/%(domain)s' (no tag placeholder)
    assert destination_with_tag == test_directory / 'archive' / 'example.com'


@pytest.mark.asyncio
async def test_collection_format_destination_domain_with_tag_template(async_client, test_session, test_directory,
                                                                       test_wrolpi_config):
    """Collection.format_destination uses tag when template includes %(domain_tag)s."""
    # Update config to include tag in template
    config = get_wrolpi_config()
    config.update({'archive_destination': 'archive/%(domain_tag)s/%(domain)s'})

    collection = Collection(name='example.com', kind='domain')
    test_session.add(collection)
    test_session.flush()

    # With tag - template now includes %(domain_tag)s
    destination_with_tag = collection.format_destination(tag_name='Tech')
    assert destination_with_tag == test_directory / 'archive' / 'Tech' / 'example.com'

    # Without tag - empty tag component
    destination_no_tag = collection.format_destination()
    assert destination_no_tag == test_directory / 'archive' / 'example.com'


def test_collection_get_or_set_directory_existing(test_session, test_directory):
    """Collection.get_or_set_directory returns existing directory without modifying it."""
    existing_dir = test_directory / 'existing/path'
    collection = Collection(name='example.com', kind='domain', directory=existing_dir)
    test_session.add(collection)
    test_session.commit()

    result = collection.get_or_set_directory(test_session)

    assert result == existing_dir
    # Directory should not have changed
    assert collection.directory == existing_dir


@pytest.mark.asyncio
async def test_collection_get_or_set_directory_new(async_client, test_session, test_directory):
    """Collection.get_or_set_directory formats and saves directory on first use."""
    collection = Collection(name='example.com', kind='domain')
    test_session.add(collection)
    test_session.commit()

    # Initially no directory
    assert collection.directory is None

    result = collection.get_or_set_directory(test_session)

    # Should have set the directory
    assert collection.directory is not None
    assert result == test_directory / 'archive' / 'example.com'
    # Directory should end with the relative path structure
    assert str(collection.directory).endswith('archive/example.com')


@pytest.mark.asyncio
async def test_collection_get_or_set_directory_with_tag(async_client, test_session, test_directory, tag_factory,
                                                        test_wrolpi_config):
    """Collection.get_or_set_directory uses collection's tag when formatting."""
    # Update config to include tag in template
    config = get_wrolpi_config()
    config.update({'archive_destination': 'archive/%(domain_tag)s/%(domain)s'})

    tag = await tag_factory('News')
    collection = Collection(name='example.com', kind='domain', tag=tag)
    test_session.add(collection)
    test_session.commit()

    result = collection.get_or_set_directory(test_session)

    # Should include tag in path (config has %(domain_tag)s)
    assert result == test_directory / 'archive' / 'News' / 'example.com'
    # Directory should end with the relative path structure
    assert str(collection.directory).endswith('archive/News/example.com')
