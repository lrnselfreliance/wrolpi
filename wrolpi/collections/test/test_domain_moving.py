"""
Tests for domain collection moving when tagging.

These tests verify that when a domain collection is tagged with a new directory,
the files (Archives) are actually moved to the new location.
"""
import pathlib
from http import HTTPStatus

import pytest
from sqlalchemy.orm import Session

from wrolpi.collections.models import Collection


@pytest.mark.asyncio
async def test_tag_domain_collection_moves_archives(
        test_session: Session,
        test_directory: pathlib.Path,
        archive_factory,
        async_client,
        tag_factory,
):
    """
    When a domain collection with a directory is tagged via the API with a new directory,
    the Archive files should be moved to the new directory.
    """
    # Create a domain collection with a directory
    src_dir = test_directory / 'archive' / 'example.com'
    src_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=src_dir,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create archives in the domain directory
    archive1 = archive_factory(domain='example.com', title='Article 1', url='https://example.com/1')
    archive2 = archive_factory(domain='example.com', title='Article 2', url='https://example.com/2')
    # Link archives to collection
    archive1.collection = collection
    archive2.collection = collection
    test_session.commit()

    # Verify initial state
    assert collection.directory == src_dir
    assert str(src_dir) in str(archive1.file_group.primary_path)
    assert str(src_dir) in str(archive2.file_group.primary_path)

    # Create tag and new directory
    tag = await tag_factory('News')
    dest_dir = test_directory / 'archive' / 'News' / 'example.com'
    dest_dir.mkdir(parents=True, exist_ok=True)
    test_session.commit()

    # Tag the collection via API with a new directory
    body = {'tag_name': 'News', 'directory': 'archive/News/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Verify collection directory was updated
    assert collection.directory == dest_dir

    # Verify archives were moved
    assert str(dest_dir) in str(archive1.file_group.primary_path), \
        f'Archive 1 should be in {dest_dir}, but is at {archive1.file_group.primary_path}'
    assert str(dest_dir) in str(archive2.file_group.primary_path), \
        f'Archive 2 should be in {dest_dir}, but is at {archive2.file_group.primary_path}'

    # Verify files actually exist at new location
    assert archive1.file_group.primary_path.exists(), \
        f'Archive 1 file should exist at {archive1.file_group.primary_path}'
    assert archive2.file_group.primary_path.exists(), \
        f'Archive 2 file should exist at {archive2.file_group.primary_path}'

    # Verify old directory is empty or removed
    if src_dir.exists():
        assert not list(src_dir.iterdir()), f'Old directory {src_dir} should be empty'

    # Verify FileGroup paths were updated correctly
    for archive in [archive1, archive2]:
        data = archive.file_group.data
        assert data is not None, f"Archive {archive.id} should have FileGroup.data"
        # FileGroup.directory should point to new location
        assert str(dest_dir) in str(archive.file_group.directory), \
            f"FileGroup.directory should be in {dest_dir}, got {archive.file_group.directory}"
        # Paths in data are now relative filenames, they don't need to change on move.
        # The key is that directory + filename resolves to the correct absolute path.
        for key, value in data.items():
            if key.endswith('_path') and value:
                resolved = archive.file_group.resolve_path(value)
                assert str(dest_dir) in str(resolved), \
                    f"FileGroup.data['{key}'] resolved to {resolved}, should be in {dest_dir}"


@pytest.mark.asyncio
async def test_tag_domain_collection_moves_extra_files(
        test_session: Session,
        test_directory: pathlib.Path,
        archive_factory,
        async_client,
        tag_factory,
):
    """
    Extra files (not associated with Archives) in the domain directory should also be moved.
    """
    # Create a domain collection with a directory
    src_dir = test_directory / 'archive' / 'example.com'
    src_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=src_dir,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create an archive in the domain directory
    archive = archive_factory(domain='example.com', title='Article', url='https://example.com/1')
    archive.collection = collection

    # Create an extra file in the directory (not part of any archive)
    extra_file = src_dir / 'notes.txt'
    extra_file.write_text('Some notes about this domain')
    test_session.commit()

    # Create tag and new directory
    tag = await tag_factory('News')
    dest_dir = test_directory / 'archive' / 'News' / 'example.com'
    dest_dir.mkdir(parents=True, exist_ok=True)
    test_session.commit()

    # Tag the collection via API with a new directory
    body = {'tag_name': 'News', 'directory': 'archive/News/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Verify extra file was moved
    assert (dest_dir / 'notes.txt').exists(), 'Extra file should be moved to new directory'
    assert (dest_dir / 'notes.txt').read_text() == 'Some notes about this domain'
    assert not extra_file.exists(), 'Extra file should not exist at old location'


@pytest.mark.asyncio
async def test_tag_domain_collection_old_directory_removed(
        test_session: Session,
        test_directory: pathlib.Path,
        archive_factory,
        async_client,
        tag_factory,
):
    """
    After moving, the old directory should be removed if empty.
    """
    # Create a domain collection with a directory
    src_dir = test_directory / 'archive' / 'example.com'
    src_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=src_dir,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create an archive in the domain directory
    archive = archive_factory(domain='example.com', title='Article', url='https://example.com/1')
    archive.collection = collection
    test_session.commit()

    # Create tag and new directory
    tag = await tag_factory('News')
    dest_dir = test_directory / 'archive' / 'News' / 'example.com'
    dest_dir.mkdir(parents=True, exist_ok=True)
    test_session.commit()

    # Tag the collection via API with a new directory
    body = {'tag_name': 'News', 'directory': 'archive/News/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Verify old directory was removed
    assert not src_dir.exists(), f'Old directory {src_dir} should be removed after move'


@pytest.mark.asyncio
async def test_untag_domain_collection_moves_back(
        test_session: Session,
        test_directory: pathlib.Path,
        make_files_structure,
        async_client,
        tag_factory,
):
    """
    When removing a tag from a domain collection with a new directory,
    files should be moved to the new directory.
    """
    from wrolpi.files.models import FileGroup

    # Create a domain collection with a tag and tagged directory
    tagged_dir = test_directory / 'archive' / 'News' / 'example.com'
    tagged_dir.mkdir(parents=True, exist_ok=True)

    tag = await tag_factory('News')

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=tagged_dir,
        tag=tag,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create a file directly in the tagged directory (using FileGroup, not Archive)
    file_path = tagged_dir / 'article.html'
    file_path.write_text('<html></html>')
    file_group = FileGroup.from_paths(test_session, file_path)
    test_session.commit()

    # Verify initial state
    assert collection.tag_name == 'News'
    assert str(tagged_dir) in str(file_group.primary_path)

    # Untagged directory
    untagged_dir = test_directory / 'archive' / 'example.com'
    untagged_dir.mkdir(parents=True, exist_ok=True)

    # Store collection ID for lookup after API call (collection may be deleted)
    collection_id = collection.id

    # Remove the tag and move to untagged directory
    body = {'tag_name': None, 'directory': 'archive/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection_id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Query fresh from database - collection may be deleted during cleanup
    collection = test_session.query(Collection).filter_by(id=collection_id).one_or_none()

    # Note: The collection may be deleted if it becomes empty during refresh cleanup
    # This is expected behavior for domain collections without items
    if collection is not None:
        # Verify tag was removed
        assert collection.tag_id is None
        assert collection.directory == untagged_dir

    # Verify file was moved - the key test here is that files moved, not the collection state
    assert str(untagged_dir) in str(file_group.primary_path), \
        f'File should be in {untagged_dir}, but is at {file_group.primary_path}'


@pytest.mark.asyncio
async def test_tag_domain_collection_without_directory_no_move(
        test_session: Session,
        test_directory: pathlib.Path,
        archive_factory,
        async_client,
        tag_factory,
):
    """
    When tagging a domain collection without providing a directory,
    no files should be moved - only the tag is updated.
    """
    # Create a domain collection with a directory
    src_dir = test_directory / 'archive' / 'example.com'
    src_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=src_dir,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create an archive in the domain directory
    archive = archive_factory(domain='example.com', title='Article', url='https://example.com/1')
    archive.collection = collection
    test_session.commit()

    original_path = archive.file_group.primary_path

    # Create tag
    tag = await tag_factory('News')
    test_session.commit()

    # Tag the collection via API WITHOUT a directory
    body = {'tag_name': 'News'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Verify tag was set
    assert collection.tag_name == 'News'

    # Verify directory was NOT changed
    assert collection.directory == src_dir

    # Verify archive was NOT moved
    assert archive.file_group.primary_path == original_path, \
        f'Archive should NOT be moved when directory is not provided'


@pytest.mark.asyncio
async def test_tag_domain_comprehensive(
        async_client,
        test_session: Session,
        test_directory: pathlib.Path,
        archive_factory,
        tag_factory,
        test_download_manager,
        test_downloader,
        await_switches,
):
    """
    Comprehensive test for domain collection tagging - equivalent to test_tag_channel.

    Tests:
    1. Domain collection directory moves
    2. Archive files move with the collection
    3. Extra files in the directory move
    4. Download destinations are updated
    5. Config is saved with new directory
    6. Untagging moves files back
    7. Downloads are moved back when untagging
    8. Tagging without directory doesn't move files
    """
    from modules.archive.lib import save_domains_config, get_domains_config
    from wrolpi.downloader import Download
    from wrolpi.common import walk

    # Create domain collection directory in the usual archive directory
    archive_directory = test_directory / 'archive'
    archive_directory.mkdir(parents=True, exist_ok=True)
    domain_directory = archive_directory / 'example.com'
    domain_directory.mkdir(parents=True, exist_ok=True)

    # Create domain collection with directory
    collection = Collection(
        name='example.com',
        kind='domain',
        directory=domain_directory,
    )
    test_session.add(collection)
    test_session.flush([collection])

    # Create tag
    tag = await tag_factory('News')

    # Create archives in the domain directory
    archive1 = archive_factory(domain='example.com', title='Article 1', url='https://example.com/article1')
    archive2 = archive_factory(domain='example.com', title='Article 2', url='https://example.com/article2')
    archive1.collection = collection
    archive2.collection = collection

    # Create recurring download which uses the domain's directory
    download = test_download_manager.recurring_download(
        test_session,
        'https://example.com/feed',
        60,
        test_downloader.name,
        destination=str(domain_directory),
        collection_id=collection.id
    )
    test_session.commit()

    # Save domain config
    save_domains_config()
    await await_switches()

    # Verify initial state - config has correct directory
    config = get_domains_config()
    domain_entry = next((c for c in config.collections if c['name'] == 'example.com'), None)
    assert domain_entry is not None, "Domain not in config"
    # Config stores absolute paths
    assert domain_entry['directory'] == str(domain_directory), \
        f"Config directory should be: {domain_entry['directory']}"

    # Domain download downloads into the domain's directory
    assert collection.downloads[0].destination == domain_directory, \
        f"Download destination should be {domain_directory}, got {collection.downloads[0].destination}"

    # Make extra file in the domain's directory, it should be moved
    (domain_directory / 'extra file.txt').write_text('extra file contents')

    # Domain directory is in the archive directory
    assert collection.directory == domain_directory

    # Archives are in the domain's directory
    assert str(domain_directory) in str(archive1.file_group.primary_path)
    assert str(domain_directory) in str(archive2.file_group.primary_path)

    archive_files = [i for i in walk(archive_directory) if i.is_file()]
    initial_file_count = len(archive_files)

    # Tag the domain with a new directory
    new_domain_directory = test_directory / 'archive' / 'News' / 'example.com'
    new_domain_directory.mkdir(parents=True, exist_ok=True)

    body = {'tag_name': tag.name, 'directory': 'archive/News/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    assert collection.tag_name == tag.name
    # Domain was moved to Tag's directory, old directory was removed
    assert collection.directory == new_domain_directory, 'Domain directory should have been changed.'
    assert new_domain_directory.is_dir(), 'Domain should have been moved.'
    assert next(new_domain_directory.iterdir(), None), 'Domain archives should have been moved.'
    assert not domain_directory.exists(), 'Old domain directory should have been deleted.'

    # Domain download goes into the domain's directory
    assert download.destination == new_domain_directory, f'{download} was not moved'

    # Archives were moved
    assert str(new_domain_directory) in str(archive1.file_group.primary_path), \
        f'Archive 1 should be in new directory'
    assert str(new_domain_directory) in str(archive2.file_group.primary_path), \
        f'Archive 2 should be in new directory'

    # Extra file was also moved
    assert (new_domain_directory / 'extra file.txt').read_text() == 'extra file contents'

    # No new files were created
    assert len([i for i in walk(archive_directory) if i.is_file()]) == initial_file_count

    # Config was updated
    config = get_domains_config()
    domain_entry = next((c for c in config.collections if c['name'] == 'example.com'), None)
    assert domain_entry is not None, "Domain should still be in config"
    assert domain_entry['directory'] == str(new_domain_directory), \
        f"Config directory should be updated: {domain_entry['directory']}"

    # Remove tag, domain/archives should be moved back
    original_directory = test_directory / 'archive' / 'example.com'
    original_directory.mkdir(parents=True, exist_ok=True)

    body = {'tag_name': None, 'directory': 'archive/example.com'}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    # Query collection from DB
    collection = test_session.query(Collection).filter_by(name='example.com').one_or_none()

    # Collection may be deleted during cleanup if empty, but we can still verify downloads
    if collection:
        assert collection.tag_name is None
        assert collection.directory == original_directory

    # Archives were moved back
    assert str(original_directory) in str(archive1.file_group.primary_path), \
        f'Archive 1 should be moved back'
    assert str(original_directory) in str(archive2.file_group.primary_path), \
        f'Archive 2 should be moved back'

    # Download was moved back
    assert download.destination == original_directory, f'{download} was not moved back'

    assert not (test_directory / 'archive/News/example.com').exists(), \
        'Old tagged directory should have been deleted'

    # Domain can be Tagged without moving directories
    # First recreate collection if it was deleted
    if not collection:
        collection = Collection(
            name='example.com',
            kind='domain',
            directory=original_directory,
        )
        test_session.add(collection)
        test_session.commit()

    body = {'tag_name': tag.name}
    request, response = await async_client.post(f'/api/collections/{collection.id}/tag', json=body)
    assert response.status_code == HTTPStatus.OK, response.content.decode()

    assert collection.tag_name == 'News'
    assert collection.directory == original_directory, 'Directory should not change without explicit directory'

    # Archives were not moved
    assert str(original_directory) in str(archive1.file_group.primary_path)
    assert str(original_directory) in str(archive2.file_group.primary_path)

    # Download was not changed
    assert download.destination == original_directory, f'{download} should not have moved'
