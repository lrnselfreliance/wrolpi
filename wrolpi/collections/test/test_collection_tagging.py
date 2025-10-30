import pathlib
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
