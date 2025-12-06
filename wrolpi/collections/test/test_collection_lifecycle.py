import pathlib

import pytest
import yaml
from sqlalchemy.orm import Session

from wrolpi.collections import collections_config
from wrolpi.collections.models import Collection
from wrolpi.common import get_media_directory


@pytest.mark.asyncio
async def test_collection_lifecycle_end_to_end(async_client, test_session: Session, test_directory: pathlib.Path,
                                               video_factory):
    """
    Lifecycle:
    - Start with no collections
    - Create a directory-restricted collection with a unique directory containing some videos
    - Dump to config (collections.yaml)
    - Add a new video to that directory; ensure collection fetches show it
    - Remove one video from the collection only (files remain)
    - Delete another video entirely (files removed and item gone from collection)
    - Delete the collection; dump config; files remain (except the deleted video)
    """
    # 1) Start clean
    assert test_directory.is_dir()
    assert test_session.query(Collection).count() == 0

    # 2) Prepare unique directory with some videos
    coll_dir = test_directory / 'videos' / 'collections_lifecycle' / 'case_001'
    coll_dir.mkdir(parents=True, exist_ok=True)

    # Create three videos in the directory
    v1 = video_factory(with_video_file=coll_dir / 'v1.mp4')
    v2 = video_factory(with_video_file=coll_dir / 'v2.mp4')
    v3 = video_factory(with_video_file=coll_dir / 'v3.mp4')
    test_session.commit()

    # Sanity: files exist
    assert v1.file_group.primary_path.exists()
    assert v2.file_group.primary_path.exists()
    assert v3.file_group.primary_path.exists()

    # 3) Create a directory-restricted collection via config import semantics
    rel_dir = coll_dir.relative_to(get_media_directory())
    cfg = {
        'name': 'Lifecycle Test Collection',
        'description': 'E2E lifecycle test',
        'directory': str(rel_dir),
        'kind': 'channel',
    }
    coll = Collection.from_config(cfg, session=test_session)
    test_session.commit()

    # After creation, items should be auto-populated from directory
    items = coll.get_items(session=test_session)
    fg_ids = {i.file_group_id for i in items}
    assert {v1.file_group_id, v2.file_group_id, v3.file_group_id}.issubset(fg_ids)

    # 4) Dump collections config; verify entry present
    collections_config.dump_config()
    config_file = collections_config.get_file()
    assert config_file.is_file(), f"Expected config file at {config_file}"

    data = yaml.safe_load(config_file.read_text())
    assert isinstance(data, dict)
    dumped = data.get('collections', [])
    # Config stores absolute paths
    assert any(c.get('name') == 'Lifecycle Test Collection' and c.get('directory') == str(coll_dir) and c.get(
        'kind') == 'channel' for c in dumped)

    # 5) Add a new video to the same directory; ensure fetch methods include it after population
    v4 = video_factory(with_video_file=coll_dir / 'v4.mp4')
    test_session.commit()

    # Populate from directory to pick up new file group
    coll.populate_from_directory(session=test_session)
    test_session.commit()

    items = coll.get_items(session=test_session)
    fg_ids = {i.file_group_id for i in items}
    assert v4.file_group_id in fg_ids

    # 6) Remove one video from the collection only (do not delete the video)
    coll.remove_file_group(v2.file_group_id, session=test_session)
    test_session.commit()

    items = coll.get_items(session=test_session)
    fg_ids = {i.file_group_id for i in items}
    assert v2.file_group_id not in fg_ids, 'Removed video should not be visible in collection fetch methods'
    # Files should remain on disk
    assert v2.file_group.primary_path.exists()

    # 7) Delete another video entirely (remove files too)
    # Use the model's delete to remove files and DB rows
    v3.delete()
    test_session.commit()

    # File should be removed from disk
    assert not v3.file_group.primary_path.exists()

    # The collection should no longer reference it (FK cascade or absence after populate)
    items = coll.get_items(session=test_session)
    fg_ids = {i.file_group_id for i in items}
    assert v3.file_group_id not in fg_ids

    # 8) Finally, delete the collection
    test_session.delete(coll)
    test_session.commit()

    # Dump config again; collection should be removed from config
    collections_config.dump_config()
    data = yaml.safe_load(config_file.read_text())
    dumped = data.get('collections', [])
    assert not any(c.get('name') == 'Lifecycle Test Collection' and c.get('directory') == str(rel_dir) for c in dumped)

    # All remaining files should still exist except the one for the deleted video
    assert v1.file_group.primary_path.exists()
    assert v2.file_group.primary_path.exists()
    assert v4.file_group.primary_path.exists()
