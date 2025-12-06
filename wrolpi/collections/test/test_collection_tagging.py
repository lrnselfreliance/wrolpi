import pathlib

import pytest
import yaml
from sqlalchemy.orm import Session

from wrolpi.collections import collections_config
from wrolpi.collections.models import Collection
from wrolpi.common import get_media_directory


# from wrolpi.switches import await_switches


@pytest.mark.asyncio
async def test_tagging_directory_collection_moves_files_and_updates_config(
        test_session: Session,
        test_directory: pathlib.Path,
        video_factory,
        async_client,
        tag_factory,
):
    # Start clean
    assert test_session.query(Collection).count() == 0

    # Create source directory and a few videos
    src_dir = test_directory / 'videos' / 'collections_tagging' / 'dir_case'
    src_dir.mkdir(parents=True, exist_ok=True)
    v1 = video_factory(with_video_file=src_dir / 'a1.mp4')
    v2 = video_factory(with_video_file=src_dir / 'a2.mp4')
    test_session.commit()

    # Create a directory-restricted Collection (kind=channel) via config import semantics
    rel_dir = src_dir.relative_to(get_media_directory())
    cfg = {
        'name': 'Funny Clips',
        'description': 'Clips that make me laugh',
        'directory': str(rel_dir),
        'kind': 'channel',
    }
    coll = Collection.from_config(cfg, session=test_session)
    test_session.commit()

    # Verify it populated
    assert {i.file_group_id for i in coll.get_items(session=test_session)} == {v1.file_group_id, v2.file_group_id}

    # Dump config and verify (config stores absolute paths)
    collections_config.dump_config()
    cfg_file = collections_config.get_file()
    data = yaml.safe_load(cfg_file.read_text())
    dumped = data.get('collections', [])
    assert any(
        c.get('name') == 'Funny Clips' and c.get('directory') == str(src_dir) and c.get('kind') == 'channel' for c in
        dumped)

    # Tag the collection -> should move to videos/<Tag>/<Collection Name>
    tag = await tag_factory('Funny')
    coll.set_tag(tag.id)
    test_session.commit()

    # Compute expected destination and move
    dest_dir = coll.format_directory('Funny')
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Perform the move using the model helper
    await coll.move_collection(dest_dir, session=test_session)
    test_session.commit()

    # Validate the directory changed and files moved
    assert coll.directory == dest_dir
    assert (dest_dir / 'a1.mp4').is_file()
    assert (dest_dir / 'a2.mp4').is_file()
    assert not (src_dir / 'a1.mp4').exists()
    assert not (src_dir / 'a2.mp4').exists()

    # FileGroup paths should be in dest_dir now
    test_session.refresh(v1)
    test_session.refresh(v2)
    assert str(dest_dir) in str(v1.file_group.primary_path)
    assert str(dest_dir) in str(v2.file_group.primary_path)

    # Dump config again and verify updated directory and tag (config stores absolute paths)
    collections_config.dump_config()
    data = yaml.safe_load(cfg_file.read_text())
    dumped = data.get('collections', [])
    assert any(
        c.get('name') == 'Funny Clips' and c.get('directory') == str(dest_dir) and c.get('tag_name') == 'Funny' for
        c in dumped)


@pytest.mark.asyncio
async def test_tagging_unrestricted_collection_updates_config_only(
        test_session: Session,
        test_directory: pathlib.Path,
        make_files_structure,
        async_client,
        tag_factory,
):
    # Create a couple files in different places using make_files_structure
    files = [
        'videos/loose/x1.mp4',
        'videos/misc/x2.mp4',
    ]
    fg1, fg2 = make_files_structure(files, file_groups=True, session=test_session)
    test_session.commit()

    # Create an unrestricted collection and add both files
    coll = Collection.from_config({'name': 'Loose Stuff', 'kind': 'channel'}, session=test_session)
    # Unrestricted, so add manually
    coll.add_file_groups([fg1, fg2], session=test_session)
    test_session.commit()

    # Dump config and verify directory is absent/None
    collections_config.dump_config()
    cfg_file = collections_config.get_file()
    data = yaml.safe_load(cfg_file.read_text())
    dumped = data.get('collections', [])
    entry = next(c for c in dumped if c.get('name') == 'Loose Stuff')
    assert 'directory' not in entry

    # Tag the collection; files should not move
    before_paths = (fg1.primary_path, fg2.primary_path)
    # Create a Tag synchronously and assign by name
    # from wrolpi.tags import Tag
    # tag = Tag(name='Favorites', color='#00ff00')
    # test_session.add(tag)
    # test_session.commit()
    await tag_factory('Favorites')
    coll.set_tag('Favorites')
    test_session.commit()

    # Assert paths unchanged
    test_session.refresh(fg1)
    test_session.refresh(fg2)
    after_paths = (fg1.primary_path, fg2.primary_path)
    assert before_paths == after_paths

    # Dump config and verify tag written, directory still not set
    collections_config.dump_config()
    data = yaml.safe_load(cfg_file.read_text())
    dumped = data.get('collections', [])
    entry = next(c for c in dumped if c.get('name') == 'Loose Stuff')
    assert entry.get('tag_name') == 'Favorites'
    assert 'directory' not in entry


def test_set_tag_on_directory_less_domain_collection(test_session):
    """Test that set_tag works on domain collections without a directory."""
    from wrolpi.tags import Tag

    # Create a domain collection without a directory
    collection = Collection(name='example.com', kind='domain', directory=None)
    test_session.add(collection)

    # Create a tag directly
    tag = Tag(name='TestTag', color='#ff0000')
    test_session.add(tag)
    test_session.commit()

    # This should NOT raise ValueError - it should successfully set the tag
    # (Currently raises: ValueError: Cannot tag domain collection 'example.com' without a directory)
    collection.set_tag('TestTag')
    test_session.commit()

    # Verify tag was set
    assert collection.tag_id == tag.id
    assert collection.tag_name == 'TestTag'
    # Directory should still be None
    assert collection.directory is None


@pytest.mark.asyncio
async def test_tag_collection_removes_tag_and_updates_directory(test_session, test_directory, tag_factory,
                                                                await_switches):
    """When removing a tag via tag_collection, the directory should be updated if provided."""
    from wrolpi.collections.lib import tag_collection

    # Create a domain collection with a tag and tagged directory
    tagged_dir = test_directory / 'archive' / 'News' / 'example.com'
    tagged_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='example.com',
        kind='domain',
        directory=tagged_dir,
    )
    test_session.add(collection)

    # Create tag using factory
    tag = await tag_factory(name='News')
    collection.tag = tag
    test_session.commit()

    # Verify initial state
    assert collection.tag_name == 'News'
    assert 'News' in str(collection.directory)

    # New directory without the tag
    untagged_dir = test_directory / 'archive' / 'example.com'
    untagged_dir.mkdir(parents=True, exist_ok=True)

    # Remove the tag AND update the directory
    result = tag_collection(
        collection_id=collection.id,
        tag_name=None,  # Remove tag
        directory=str(untagged_dir),  # New directory
        session=test_session
    )
    test_session.commit()
    await await_switches()

    # Verify tag was removed
    assert collection.tag_id is None
    assert collection.tag_name is None

    # Verify directory was updated (THIS IS THE BUG - directory is not updated)
    assert collection.directory == untagged_dir, \
        f"Expected directory to be {untagged_dir}, but got {collection.directory}"

    # Verify result contains correct directory
    assert result['directory'] == str(untagged_dir.relative_to(test_directory))
