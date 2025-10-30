"""Tests for domain collection tagging functionality."""

import pytest

from wrolpi.collections import Collection


@pytest.mark.asyncio
async def test_create_domain_collection_with_directory(test_session, test_directory):
    """Domain collection can be created with a directory."""
    domain_dir = test_directory / 'archives' / 'example.com'
    domain_dir.mkdir(parents=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=domain_dir
    )
    test_session.add(collection)
    test_session.commit()

    assert collection.directory == domain_dir
    assert collection.can_be_tagged is True


@pytest.mark.asyncio
async def test_create_unrestricted_domain_collection(test_session):
    """Unrestricted domain collection (no directory) cannot be tagged."""
    collection = Collection(
        name='example.com',
        kind='domain',
        directory=None  # Unrestricted
    )
    test_session.add(collection)
    test_session.commit()

    assert collection.directory is None
    assert collection.can_be_tagged is False


@pytest.mark.asyncio
async def test_tag_domain_collection_with_directory(async_client, test_session, test_directory, tag_factory):
    """Domain collection with directory can be tagged."""
    domain_dir = test_directory / 'archives' / 'example.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=domain_dir
    )
    test_session.add(collection)
    tag = await tag_factory(name='News')
    test_session.commit()

    # Tag the collection
    collection.set_tag('News')
    test_session.commit()

    assert collection.tag is not None
    assert collection.tag.name == 'News'
    assert collection.tag_id == tag.id


@pytest.mark.asyncio
async def test_cannot_tag_unrestricted_domain_collection(async_client, test_session, tag_factory):
    """Domain collection without directory cannot be tagged."""
    collection = Collection(
        name='example.com',
        kind='domain',
        directory=None  # Unrestricted
    )
    test_session.add(collection)
    tag = await tag_factory(name='News')
    test_session.commit()

    assert collection.can_be_tagged is False

    with pytest.raises(ValueError, match='Cannot tag domain collection.*without a directory'):
        collection.set_tag('News')


@pytest.mark.asyncio
async def test_tag_domain_collection_moves_files(
        test_session, archive_factory, tag_factory, test_directory, make_files_structure, archive_directory,
        await_switches,
):
    """Tagging domain collection with directory moves archive files."""
    # Create domain collection with directory
    # Use archive_directory fixture to match where archive_factory creates files
    domain_dir = archive_directory / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='test.com',
        kind='domain',
        directory=domain_dir
    )
    test_session.add(collection)
    test_session.flush()

    # Create archives in domain directory
    archive1 = archive_factory(domain='test.com')
    archive2 = archive_factory(domain='test.com')
    archive1.collection = collection
    archive2.collection = collection
    test_session.commit()

    # Get file paths before move
    old_paths = []
    for archive in [archive1, archive2]:
        for path in archive.my_paths():
            old_paths.append(path)

    assert all(p.is_file() for p in old_paths), "Files should exist before move"

    # Create tag and assign to collection
    tag = await tag_factory(name='Tech')
    collection.set_tag('Tech')
    test_session.commit()

    # Compute new directory and move collection
    new_directory = collection.format_directory('Tech')
    # Create the destination directory before moving
    new_directory.mkdir(parents=True, exist_ok=True)
    await collection.move_collection(new_directory, test_session)

    # Verify files moved
    assert new_directory.is_dir(), "New directory should exist"
    assert 'Tech' in str(new_directory), "New directory should contain tag name"
    assert 'test.com' in str(new_directory), "New directory should contain domain name"

    # Old paths should no longer exist
    for old_path in old_paths:
        assert not old_path.is_file(), f"Old file should be moved: {old_path}"


@pytest.mark.asyncio
async def test_domain_config_with_directory_and_tag(test_session, test_directory, tag_factory, async_client):
    """Domain config can include directory and tag_name."""
    from modules.archive.lib import DomainsConfig

    # Create config file
    config_file = test_directory / 'domains.yaml'
    config_file.write_text("""
collections:
  - name: "example.com"
    kind: "domain"
    description: "News from example.com"
    directory: "archives/example.com"
    tag_name: "News"
""")

    # Create tag first
    tag = await tag_factory(name='News')
    test_session.commit()

    # Import config
    domains_config = DomainsConfig()
    domains_config.import_config(config_file)

    # Verify collection created with directory and tag
    collection = test_session.query(Collection).filter_by(
        name='example.com',
        kind='domain'
    ).one()

    assert collection.directory is not None
    assert 'example.com' in str(collection.directory)
    assert collection.tag is not None
    assert collection.tag.name == 'News'
    assert collection.can_be_tagged is True


@pytest.mark.asyncio
async def test_domain_config_warns_tag_without_directory(test_session, test_directory, tag_factory, caplog,
                                                         async_client):
    """Config warns when tag_name provided without directory."""
    from modules.archive.lib import DomainsConfig

    # Create config file with tag but no directory
    config_file = test_directory / 'domains.yaml'
    config_file.write_text("""
collections:
  - name: "example.com"
    kind: "domain"
    tag_name: "News"
""")

    # Create tag first
    tag = await tag_factory(name='News')
    test_session.commit()

    # Import config
    domains_config = DomainsConfig()
    domains_config.import_config(config_file)

    # Verify collection created without tag
    collection = test_session.query(Collection).filter_by(
        name='example.com',
        kind='domain'
    ).one()

    assert collection.directory is None
    assert collection.tag is None  # Tag ignored
    assert collection.can_be_tagged is False

    # Check warning was logged
    assert "tags require a directory" in caplog.text


@pytest.mark.asyncio
async def test_domain_config_export_includes_directory_and_tag(test_session, test_directory, tag_factory, async_client):
    """Exporting domain config includes directory and tag_name."""
    from modules.archive.lib import DomainsConfig
    from wrolpi.common import get_media_directory
    import yaml

    # Create domain collection with directory and tag
    domain_dir = get_media_directory() / 'archives' / 'news.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='news.com',
        kind='domain',
        directory=domain_dir,
        description='News website'
    )
    test_session.add(collection)
    tag = await tag_factory(name='News')
    collection.set_tag('News')
    test_session.commit()

    # Export config
    config_file = test_directory / 'domains.yaml'
    domains_config = DomainsConfig()
    domains_config.dump_config(config_file, overwrite=True)

    # Read and verify exported config
    with open(config_file) as f:
        exported = yaml.safe_load(f)

    assert len(exported['collections']) == 1
    domain_config = exported['collections'][0]
    assert domain_config['name'] == 'news.com'
    assert domain_config['kind'] == 'domain'
    assert 'archives/news.com' in domain_config['directory']
    assert domain_config['tag_name'] == 'News'
    assert domain_config['description'] == 'News website'


@pytest.mark.asyncio
async def test_get_or_create_domain_collection_with_directory(test_session, test_directory):
    """get_or_create_domain_collection can create collection with directory."""
    from modules.archive.lib import get_or_create_domain_collection
    from wrolpi.common import get_media_directory

    domain_dir = get_media_directory() / 'archives' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    # Create with directory
    collection = get_or_create_domain_collection(
        test_session,
        'https://test.com/article',
        directory=domain_dir
    )

    assert collection.name == 'test.com'
    assert collection.kind == 'domain'
    assert collection.directory == domain_dir
    assert collection.can_be_tagged is True


@pytest.mark.asyncio
async def test_get_archive_destination_with_directory(test_session, test_directory):
    """get_archive_destination returns collection directory when set."""
    from modules.archive.lib import get_archive_destination
    from wrolpi.common import get_media_directory

    domain_dir = get_media_directory() / 'archives' / 'tagged' / 'example.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=domain_dir
    )
    test_session.add(collection)
    test_session.commit()

    destination = get_archive_destination(collection)

    assert destination == domain_dir
    assert destination.is_dir()


@pytest.mark.asyncio
async def test_get_archive_destination_unrestricted(test_session):
    """get_archive_destination returns default path for unrestricted collection."""
    from modules.archive.lib import get_archive_destination, get_archive_directory

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=None  # Unrestricted
    )
    test_session.add(collection)
    test_session.commit()

    destination = get_archive_destination(collection)
    expected = get_archive_directory() / 'example.com'

    assert destination == expected
