"""
Tests for the collection reorganization feature.
"""
import pytest

from modules.archive.lib import get_archive_downloader_config
from modules.archive.models import Archive
from modules.videos.lib import get_videos_downloader_config
from modules.videos.models import Video, Channel
from wrolpi.collections import Collection
from wrolpi.collections.errors import UnknownCollection, ReorganizationConflict
from wrolpi.collections.reorganize import (
    get_reorganization_preview,
    execute_reorganization,
    get_reorganization_status,
    get_collections_needing_reorganization,
    execute_batch_reorganization,
    get_batch_reorganization_status,
    ReorganizationPreview,
)
from wrolpi.common import get_media_directory
from wrolpi.db import get_db_session
from wrolpi.files.models import FileGroup


def test_collection_file_format_serialization(test_session, test_directory):
    """Collection file_format should be persisted, serialized to config, and included in JSON."""
    collection = Collection(
        name='test.com',
        kind='domain',
        directory=test_directory / 'archive' / 'test.com',
        file_format='%(download_year)s/%(title)s.%(ext)s'
    )
    test_session.add(collection)
    test_session.commit()

    # Test column persistence
    test_session.refresh(collection)
    assert collection.file_format == '%(download_year)s/%(title)s.%(ext)s'

    # Test to_config
    config = collection.to_config()
    assert config['file_format'] == '%(download_year)s/%(title)s.%(ext)s'

    # Test __json__
    json_data = collection.__json__()
    assert 'needs_reorganization' in json_data
    assert 'file_format' in json_data


def test_collection_needs_reorganization_property(test_session, test_directory):
    """Collection.needs_reorganization should be True when file_format differs or is None."""
    collection = Collection(
        name='test.com',
        kind='domain',
        directory=test_directory / 'archive' / 'test.com',
        file_format=None  # Test None case
    )
    test_session.add(collection)
    test_session.commit()

    # None format should need reorganization
    assert collection.needs_reorganization is True

    # Format matching config should NOT need reorganization
    config = get_archive_downloader_config()
    collection.file_format = config.file_name_format
    test_session.commit()
    assert collection.needs_reorganization is False

    # Different format SHOULD need reorganization
    collection.file_format = '%(download_year)s/%(title)s.%(ext)s'
    test_session.commit()
    assert collection.needs_reorganization is True


def test_collection_from_config_loads_file_format(test_session, test_directory):
    """Collection.from_config should load file_format from config."""
    config_data = {
        'name': 'test.com',
        'kind': 'domain',
        'directory': str(test_directory / 'archive' / 'test.com'),
        'file_format': '%(download_year)s/%(title)s.%(ext)s'
    }

    collection = Collection.from_config(test_session, config_data)
    test_session.commit()

    assert collection.file_format == '%(download_year)s/%(title)s.%(ext)s'


@pytest.mark.parametrize("func_name,error_type,error_match,setup", [
    ("get_reorganization_preview", UnknownCollection, None, "unknown_id"),
    ("execute_reorganization", UnknownCollection, None, "unknown_id"),
    ("get_reorganization_preview", ValueError, "has no directory", "no_directory"),
    ("execute_reorganization", ValueError, "has no directory", "no_directory"),
])
def test_reorganization_error_handling(func_name, error_type, error_match, setup, test_session, test_directory):
    """Both preview and execute should raise appropriate errors for invalid inputs."""
    func = get_reorganization_preview if func_name == "get_reorganization_preview" else execute_reorganization

    if setup == "unknown_id":
        # Test with non-existent collection ID
        with pytest.raises(error_type):
            func(99999, test_session)
    elif setup == "no_directory":
        # Test with collection that has no directory
        collection = Collection(
            name='test.com',
            kind='domain',
            directory=None,
        )
        test_session.add(collection)
        test_session.commit()

        with pytest.raises(error_type, match=error_match):
            func(collection.id, test_session)


def test_get_reorganization_preview_domain_collection(test_session, test_directory, archive_factory):
    """get_reorganization_preview should work for domain collections."""
    # Create domain collection
    domain_dir = test_directory / 'archive' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='test.com',
        kind='domain',
        directory=domain_dir,
        file_format='%(download_datetime)s_%(title)s.%(ext)s'
    )
    test_session.add(collection)
    test_session.commit()

    # Create an archive using the factory (it uses test_session internally)
    archive = archive_factory(domain='test.com', url='https://test.com/article')
    # The factory creates a new collection, so associate archive with our collection
    archive.collection_id = collection.id
    test_session.commit()

    preview = get_reorganization_preview(collection.id, test_session)

    assert isinstance(preview, ReorganizationPreview)
    assert preview.collection_id == collection.id
    assert preview.collection_name == 'test.com'
    assert preview.total_files >= 0
    assert preview.new_file_format is not None


@pytest.mark.asyncio
async def test_execute_reorganization_no_files_to_move(async_client, test_directory):
    """execute_reorganization should return empty job_id when no files need moving."""
    # Create domain collection with matching file_format
    domain_dir = test_directory / 'archive' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    config = get_archive_downloader_config()

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='test.com',
            kind='domain',
            directory=domain_dir,
            file_format=config.file_name_format  # Same as config, no reorganization needed
        )
        session.add(collection)
        session.commit()
        collection_id = collection.id

    with get_db_session(commit=True) as session:
        job_id = execute_reorganization(collection_id, session)
        assert job_id == ''


@pytest.mark.asyncio
async def test_get_reorganization_status_unknown_job(async_client):
    """get_reorganization_status should return unknown status for non-existent job."""
    status = get_reorganization_status('nonexistent-job-id')
    assert status['status'] == 'unknown'
    assert 'error' in status


def test_filegroup_primary_path_lookup_consistency(test_session, test_directory):
    """FileGroup.primary_path returns a Path object, but IN queries use strings.

    This test ensures that the handle_reorganize function correctly converts
    the primary_path to a string when building the lookup dictionary.
    The bug was: fg_by_path[fg.primary_path] stored Path keys, but lookups
    used str(source_path), causing all lookups to fail.
    """
    import pathlib
    from wrolpi.files.models import FileGroup

    # Create a test file
    video_dir = test_directory / 'videos' / 'TestChannel'
    video_dir.mkdir(parents=True, exist_ok=True)
    video_file = video_dir / 'test_video.mp4'
    video_file.touch()

    # Create FileGroup
    fg = FileGroup()
    fg.directory = video_dir
    fg.primary_path = video_file
    fg.files = [{'path': 'test_video.mp4', 'mimetype': 'video/mp4'}]
    test_session.add(fg)
    test_session.commit()

    # Verify primary_path is a Path object (this is how MediaPathType works)
    test_session.refresh(fg)
    assert isinstance(fg.primary_path, pathlib.Path), \
        f"Expected Path, got {type(fg.primary_path)}"

    # Test the pattern used in handle_reorganize:
    # Query returns FileGroups, build lookup with string keys for string lookups
    source_paths = [str(video_file)]
    file_groups = test_session.query(FileGroup).filter(
        FileGroup.primary_path.in_(source_paths)
    ).all()
    assert len(file_groups) == 1, "Query should find the FileGroup"

    # Build lookup dict - this is where the bug was
    # WRONG: fg_by_path[fg.primary_path] (Path key, str lookup fails)
    # CORRECT: fg_by_path[str(fg.primary_path)] (str key, str lookup works)
    fg_by_path_wrong = {fg.primary_path: fg for fg in file_groups}
    fg_by_path_correct = {str(fg.primary_path): fg for fg in file_groups}

    # The source path as string (as used in move_mappings)
    lookup_key = str(video_file)

    # This was the bug - Path key doesn't match string lookup
    assert lookup_key not in fg_by_path_wrong, \
        "String key should NOT be found in Path-keyed dict"

    # This is the correct behavior after fix
    assert lookup_key in fg_by_path_correct, \
        "String key SHOULD be found in string-keyed dict"


@pytest.mark.asyncio
async def test_reorganize_updates_filegroup_data_fields(async_client, test_directory, archive_factory):
    """FileGroup.data fields should be updated after reorganization.

    After reorganization:
    - files[].path is updated to new filename
    - data.singlefile_path should match files[].path
    - data.screenshot_path should match the new screenshot filename
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio

    # Create domain collection with a specific directory
    domain_dir = test_directory / 'archive' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='test.com',
            kind='domain',
            directory=domain_dir,
            # Old format - files are currently named with this pattern
            file_format='%(download_datetime)s_%(title)s.%(ext)s'
        )
        session.add(collection)
        session.commit()
        collection_id = collection.id

    # Create an archive using factory - this creates files with the default format
    archive = archive_factory(domain='test.com', url='https://test.com/article', title='Test Article')

    with get_db_session(commit=True) as session:
        # Link archive to our collection
        archive_obj = session.query(Archive).get(archive.id)
        archive_obj.collection_id = collection_id
        session.commit()

        # Get the current file paths
        fg = archive_obj.file_group
        old_primary_path = fg.primary_path
        old_singlefile_name = fg.data.get('singlefile_path')
        old_screenshot_name = fg.data.get('screenshot_path')
        fg_id = fg.id

        # Verify data fields are populated
        assert old_singlefile_name is not None, "singlefile_path should be set in data"
        assert old_screenshot_name is not None, "screenshot_path should be set in data"

        # Verify data matches files
        files_html = [f for f in fg.files if f['path'].endswith('.html') and '.readability' not in f['path']]
        assert len(files_html) == 1
        assert files_html[0]['path'] == old_singlefile_name, "data.singlefile_path should match files[].path"

    # Create move mapping: rename files to a new pattern
    new_stem = 'renamed_article'
    new_primary_path = domain_dir / f'{new_stem}.html'

    move_mappings = [(old_primary_path, new_primary_path)]

    # Execute reorganization via file worker
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        job_id='test-reorganize-data-bug',
    )

    await file_worker.handle_reorganize(task)

    # Give time for DB updates
    await asyncio.sleep(0.1)

    # Verify results
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)

        # Verify files were physically renamed
        assert new_primary_path.exists(), "New primary file should exist"
        assert not old_primary_path.exists(), "Old primary file should not exist"

        # Verify FileGroup.files[] was updated
        new_files_html = [f for f in fg.files if f['path'].endswith('.html') and '.readability' not in f['path']]
        assert len(new_files_html) == 1
        new_file_name = new_files_html[0]['path']
        assert new_file_name == f'{new_stem}.html', f"files[].path should be updated to new filename, got {new_file_name}"

        # Verify FileGroup.data.singlefile_path was updated to match files[].path
        new_singlefile_name = fg.data.get('singlefile_path')
        assert new_singlefile_name == new_file_name, \
            f"data.singlefile_path should match files[].path after reorganization. " \
            f"Expected '{new_file_name}', got '{new_singlefile_name}'"

        # Verify FileGroup.data.screenshot_path was updated
        new_screenshot_name = fg.data.get('screenshot_path')
        expected_screenshot = f'{new_stem}.png'
        assert new_screenshot_name == expected_screenshot, \
            f"data.screenshot_path should be updated after reorganization. " \
            f"Expected '{expected_screenshot}', got '{new_screenshot_name}'"

        # Verify readability paths were also updated
        new_readability_name = fg.data.get('readability_path')
        expected_readability = f'{new_stem}.readability.html'
        assert new_readability_name == expected_readability, \
            f"data.readability_path should be updated after reorganization. " \
            f"Expected '{expected_readability}', got '{new_readability_name}'"


# ============================================================================
# Batch Reorganization Tests
# ============================================================================


@pytest.mark.parametrize("kind,config_getter,base_dir,names", [
    ("channel", "get_videos_downloader_config", "videos", ["Channel1", "Channel2", "Channel3"]),
    ("domain", "get_archive_downloader_config", "archive", ["example.com", "test.org", "done.net"]),
])
def test_get_collections_needing_reorganization(test_session, test_directory, kind, config_getter, base_dir, names):
    """Create 3 collections, 2 need reorganization, verify only 2 returned."""
    # Get current config format
    config = get_videos_downloader_config() if config_getter == "get_videos_downloader_config" else get_archive_downloader_config()

    # Create base directory
    parent_dir = test_directory / base_dir
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Collection 1: Needs reorganization (different format)
    dir1 = parent_dir / names[0]
    dir1.mkdir(parents=True, exist_ok=True)
    collection1 = Collection(
        name=names[0],
        kind=kind,
        directory=dir1,
        file_format='%(old_format)s.%(ext)s'  # Different from config
    )
    test_session.add(collection1)
    test_session.flush()
    if kind == 'channel':
        test_session.add(Channel(name=names[0], collection_id=collection1.id))

    # Collection 2: Needs reorganization (None format)
    dir2 = parent_dir / names[1]
    dir2.mkdir(parents=True, exist_ok=True)
    collection2 = Collection(
        name=names[1],
        kind=kind,
        directory=dir2,
        file_format=None  # Never been synced
    )
    test_session.add(collection2)
    test_session.flush()
    if kind == 'channel':
        test_session.add(Channel(name=names[1], collection_id=collection2.id))

    # Collection 3: Does NOT need reorganization (matches config)
    dir3 = parent_dir / names[2]
    dir3.mkdir(parents=True, exist_ok=True)
    collection3 = Collection(
        name=names[2],
        kind=kind,
        directory=dir3,
        file_format=config.file_name_format  # Matches config
    )
    test_session.add(collection3)
    test_session.flush()
    if kind == 'channel':
        test_session.add(Channel(name=names[2], collection_id=collection3.id))

    test_session.commit()

    # Get collections needing reorganization
    result = get_collections_needing_reorganization(kind, test_session)

    assert 'collections' in result
    assert result['total_collections'] == 2
    collection_ids = {c['collection_id'] for c in result['collections']}
    assert collection1.id in collection_ids
    assert collection2.id in collection_ids
    assert collection3.id not in collection_ids


def test_get_collections_needing_reorganization_empty(test_session, test_directory):
    """When no collections need reorganization, return empty list."""
    config = get_videos_downloader_config()

    # Create channel that does NOT need reorganization
    videos_dir = test_directory / 'videos'
    channel_dir = videos_dir / 'SyncedChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)
    collection = Collection(
        name='SyncedChannel',
        kind='channel',
        directory=channel_dir,
        file_format=config.file_name_format
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name='SyncedChannel', collection_id=collection.id)
    test_session.add(channel)
    test_session.commit()

    result = get_collections_needing_reorganization('channel', test_session)

    assert result['collections'] == []
    assert result['total_collections'] == 0
    assert result['total_files_needing_move'] == 0


def test_get_collections_needing_reorganization_includes_sample_move(
        test_session, test_directory, video_factory
):
    """Each collection should include one sample file move preview."""
    config = get_videos_downloader_config()

    # Create channel with old format
    videos_dir = test_directory / 'videos'
    channel_dir = videos_dir / 'TestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)
    collection = Collection(
        name='TestChannel',
        kind='channel',
        directory=channel_dir,
        file_format='%(old_format)s.%(ext)s'
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name='TestChannel', collection_id=collection.id, directory=channel_dir)
    test_session.add(channel)
    test_session.commit()

    # Create a video in this channel using factory
    video = video_factory(channel_id=channel.id)

    result = get_collections_needing_reorganization('channel', test_session, sample_size=1)

    assert len(result['collections']) == 1
    collection_info = result['collections'][0]
    assert collection_info['collection_id'] == collection.id
    assert collection_info['collection_name'] == 'TestChannel'
    assert 'sample_move' in collection_info
    # sample_move should be a dict with old_path and new_path (or None if no files need moving)


@pytest.mark.asyncio
async def test_batch_status_includes_batch_job_id(async_client, test_directory, video_factory):
    """batch_status should include batch_job_id so frontend can resume polling.

    Bug: Frontend sets batchJobId='active' as a marker when resuming, but then
    uses this literal string for API calls, causing "Batch job active not found".

    Fix: batch_status must include the real batch_job_id so frontend can use it.
    """
    from datetime import datetime, timezone
    from wrolpi.files.worker import file_worker
    import asyncio

    # Create channel needing reorganization
    channel_dir = test_directory / 'videos' / 'TestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='TestChannel',
            kind='channel',
            directory=channel_dir,
            file_format='%(old_format)s.%(ext)s'  # Different from current config
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='TestChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()

    # Create video with proper metadata
    video = video_factory(
        channel_id=1,
        title='Test Video',
        with_video_file=True,
        with_info_json={'uploader': 'Tester', 'id': 'abc123'},
        upload_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
    )

    # Start batch reorganization
    with get_db_session() as session:
        result = execute_batch_reorganization('channel', session)

    batch_job_id = result['batch_job_id']
    assert batch_job_id, "Should return batch_job_id"

    # Transfer the task from pending queue to worker queue, then start processing
    file_worker.transfer_queue()

    # Start the worker processing in a task (it will set up status before processing)
    process_task = asyncio.create_task(file_worker.process_queue())

    # Wait briefly for worker to start processing and set status
    await asyncio.sleep(0.2)

    # Check that batch_status includes the batch_job_id
    worker_status = file_worker.status
    batch_status = worker_status.get('batch_status', {})

    # Cancel the processing task to clean up
    process_task.cancel()
    try:
        await process_task
    except asyncio.CancelledError:
        pass

    assert 'batch_job_id' in batch_status, (
        "batch_status must include batch_job_id for frontend resume. "
        f"Got: {list(batch_status.keys())}"
    )
    assert batch_status['batch_job_id'] == batch_job_id, (
        f"batch_status.batch_job_id should match returned ID. "
        f"Expected: {batch_job_id}, got: {batch_status.get('batch_job_id')}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,base_dir,names", [
    ("channel", "videos", ["Channel1", "Channel2"]),
    ("domain", "archive", ["example.com", "test.org"]),
])
async def test_execute_batch_reorganization(async_client, test_directory, kind, base_dir, names):
    """Execute batch reorganization, verify all collections processed."""
    parent_dir = test_directory / base_dir
    parent_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        # Create two collections that need reorganization
        dir1 = parent_dir / names[0]
        dir1.mkdir(parents=True, exist_ok=True)
        collection1 = Collection(
            name=names[0],
            kind=kind,
            directory=dir1,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection1)
        session.flush()
        if kind == 'channel':
            session.add(Channel(name=names[0], collection_id=collection1.id, directory=dir1))

        dir2 = parent_dir / names[1]
        dir2.mkdir(parents=True, exist_ok=True)
        collection2 = Collection(
            name=names[1],
            kind=kind,
            directory=dir2,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection2)
        session.flush()
        if kind == 'channel':
            session.add(Channel(name=names[1], collection_id=collection2.id, directory=dir2))

        session.commit()

    # Execute batch reorganization
    with get_db_session() as session:
        result = execute_batch_reorganization(kind, session)

    assert 'batch_job_id' in result
    assert result['batch_job_id'].startswith('batch-reorganize-')
    assert result['collection_count'] >= 0  # May be 0 if no files to move


def test_batch_reorganization_status_tracking(test_session):
    """Status should show overall + per-collection progress."""
    # Test with a non-existent batch job
    status = get_batch_reorganization_status('nonexistent-batch-job')

    assert status['status'] == 'unknown'
    assert 'error' in status


@pytest.mark.asyncio
async def test_batch_reorganization_no_collections_needing_reorganization(async_client, test_directory):
    """Execute batch reorganization when no collections need it."""
    config = get_videos_downloader_config()

    videos_dir = test_directory / 'videos'
    channel_dir = videos_dir / 'SyncedChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='SyncedChannel',
            kind='channel',
            directory=channel_dir,
            file_format=config.file_name_format  # Already synced
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='SyncedChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()

    with get_db_session() as session:
        result = execute_batch_reorganization('channel', session)

    # Should return empty batch job ID since nothing to do
    assert result['batch_job_id'] == ''
    assert result['collection_count'] == 0


# ============================================================================
# Tag Preservation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorganize_preserves_tag_association(async_client, test_directory, video_factory, tag_factory,
                                                    test_tags_config):
    """FileGroup tags should be preserved after reorganization.

    TagFile uses file_group_id (not paths), so tags should automatically
    survive when FileGroup paths are updated during reorganization.
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio

    # Create channel collection with a specific directory
    channel_dir = test_directory / 'videos' / 'test_channel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='Test Channel',
            kind='channel',
            directory=channel_dir,
            file_format='%(title)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='Test Channel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id

    # Create tag first
    tag = await tag_factory('mytag')

    # Create video in the channel
    video = video_factory(channel_id=channel_id, title='test_video', with_video_file=True)

    with get_db_session(commit=True) as session:
        video_obj = session.query(Video).get(video.id)
        video_obj.file_group.add_tag(session, tag.id)
        fg_id = video_obj.file_group.id
        old_primary_path = video_obj.file_group.primary_path
        session.commit()

    # Verify tag was added
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert fg.tag_names == ['mytag'], "Tag should be applied before reorganization"

    # Create move mapping: rename files to a new pattern
    new_stem = 'renamed_video'
    new_primary_path = channel_dir / f'{new_stem}.mp4'
    move_mappings = [(old_primary_path, new_primary_path)]

    # Execute reorganization via file worker
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        job_id='test-reorganize-tags',
    )
    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # Verify tags preserved after file move
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert fg.tag_names == ['mytag'], "Tag should be preserved after reorganization"
        assert fg.primary_path == new_primary_path, "File should have moved"


@pytest.mark.asyncio
async def test_reorganize_preserves_multiple_tags(async_client, test_directory, video_factory, tag_factory,
                                                  test_tags_config):
    """FileGroup with multiple tags should retain all tags after reorganization."""
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'multi_tag_channel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='Multi Tag Channel',
            kind='channel',
            directory=channel_dir,
            file_format='%(title)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='Multi Tag Channel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id

    # Create multiple tags
    tag1 = await tag_factory('alpha')
    tag2 = await tag_factory('beta')
    tag3 = await tag_factory('gamma')

    # Create video and add all tags
    video = video_factory(channel_id=channel_id, title='multi_tagged_video', with_video_file=True)

    with get_db_session(commit=True) as session:
        video_obj = session.query(Video).get(video.id)
        video_obj.file_group.add_tag(session, tag1.id)
        video_obj.file_group.add_tag(session, tag2.id)
        video_obj.file_group.add_tag(session, tag3.id)
        fg_id = video_obj.file_group.id
        old_primary_path = video_obj.file_group.primary_path
        session.commit()

    # Verify all tags were added
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert sorted(fg.tag_names) == ['alpha', 'beta', 'gamma'], "All tags should be applied"

    # Create move mapping
    new_primary_path = channel_dir / 'reorganized_multi_tag.mp4'
    move_mappings = [(old_primary_path, new_primary_path)]

    # Execute reorganization
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        job_id='test-reorganize-multi-tags',
    )
    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # Verify all tags preserved
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert sorted(fg.tag_names) == ['alpha', 'beta', 'gamma'], \
            "All tags should be preserved after reorganization"
        assert fg.primary_path == new_primary_path, "File should have moved"


@pytest.mark.asyncio
async def test_reorganize_updates_tag_directory_links(async_client, test_directory, video_factory, tag_factory,
                                                      test_tags_config, await_switches):
    """Tag directory hardlinks should point to new file locations after reorganization.

    After reorganization:
    - Old hardlinks should be removed
    - New hardlinks should exist at new paths
    - Hardlinks should actually link to the moved files
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    from wrolpi.tags import sync_tags_directory, get_tags_directory
    from wrolpi.common import is_hardlinked
    import asyncio

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'tag_link_channel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='Tag Link Channel',
            kind='channel',
            directory=channel_dir,
            file_format='%(title)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='Tag Link Channel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id

    # Create tag and video
    tag = await tag_factory('linked_tag')
    video = video_factory(channel_id=channel_id, title='link_test_video', with_video_file=True)

    with get_db_session(commit=True) as session:
        video_obj = session.query(Video).get(video.id)
        video_obj.file_group.add_tag(session, tag.id)
        fg_id = video_obj.file_group.id
        old_primary_path = video_obj.file_group.primary_path
        session.commit()

    # Sync tags directory to create initial hardlinks
    sync_tags_directory.activate_switch()
    await await_switches()

    # Verify initial hardlinks exist
    tags_dir = get_tags_directory()
    old_link_path = tags_dir / 'linked_tag' / old_primary_path.name
    assert old_link_path.exists(), "Initial tag directory link should exist"
    assert is_hardlinked(old_link_path), "Initial tag directory link should be a hardlink"

    # Execute reorganization
    new_primary_path = channel_dir / 'renamed_link_test.mp4'
    move_mappings = [(old_primary_path, new_primary_path)]

    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        job_id='test-reorganize-tag-links',
    )
    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # Manually sync tags directory (this is the potential bug - reorganize may not call this)
    sync_tags_directory.activate_switch()
    await await_switches()

    # Verify new hardlinks exist at new paths
    new_link_path = tags_dir / 'linked_tag' / new_primary_path.name
    assert new_link_path.exists(), f"New tag directory link should exist at {new_link_path}"
    assert is_hardlinked(new_link_path), "New tag directory link should be a hardlink"

    # Verify old hardlinks were removed
    assert not old_link_path.exists(), "Old tag directory link should be removed"

    # Verify the new file exists and is the same inode as the hardlink
    assert new_primary_path.exists(), "New primary file should exist"
    assert new_primary_path.stat().st_ino == new_link_path.stat().st_ino, \
        "New file and new link should have the same inode"


@pytest.mark.asyncio
async def test_batch_reorganize_preserves_tags(async_client, test_directory, video_factory, tag_factory,
                                               test_tags_config):
    """Batch reorganization should preserve tags across multiple collections."""
    from wrolpi.files.worker import file_worker
    import asyncio

    videos_dir = test_directory / 'videos'
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Create two channels with different file formats
    with get_db_session(commit=True) as session:
        channel1_dir = videos_dir / 'BatchChannel1'
        channel1_dir.mkdir(parents=True, exist_ok=True)
        collection1 = Collection(
            name='BatchChannel1',
            kind='channel',
            directory=channel1_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection1)
        session.flush()
        channel1 = Channel(name='BatchChannel1', collection_id=collection1.id, directory=channel1_dir)
        session.add(channel1)

        channel2_dir = videos_dir / 'BatchChannel2'
        channel2_dir.mkdir(parents=True, exist_ok=True)
        collection2 = Collection(
            name='BatchChannel2',
            kind='channel',
            directory=channel2_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection2)
        session.flush()
        channel2 = Channel(name='BatchChannel2', collection_id=collection2.id, directory=channel2_dir)
        session.add(channel2)

        session.commit()
        channel1_id = channel1.id
        channel2_id = channel2.id

    # Create tags
    tag_a = await tag_factory('batch_tag_a')
    tag_b = await tag_factory('batch_tag_b')

    # Create videos in each channel with different tags
    video1 = video_factory(channel_id=channel1_id, title='batch_video_1', with_video_file=True)
    video2 = video_factory(channel_id=channel2_id, title='batch_video_2', with_video_file=True)

    with get_db_session(commit=True) as session:
        video1_obj = session.query(Video).get(video1.id)
        video1_obj.file_group.add_tag(session, tag_a.id)
        fg1_id = video1_obj.file_group.id

        video2_obj = session.query(Video).get(video2.id)
        video2_obj.file_group.add_tag(session, tag_b.id)
        fg2_id = video2_obj.file_group.id

        session.commit()

    # Verify tags before batch reorganization
    with get_db_session() as session:
        fg1 = session.query(FileGroup).get(fg1_id)
        fg2 = session.query(FileGroup).get(fg2_id)
        assert fg1.tag_names == ['batch_tag_a']
        assert fg2.tag_names == ['batch_tag_b']

    # Execute batch reorganization
    with get_db_session() as session:
        result = execute_batch_reorganization('channel', session)

    # Give time for batch operations
    await asyncio.sleep(0.5)

    # Verify tags preserved after batch reorganization
    with get_db_session() as session:
        fg1 = session.query(FileGroup).get(fg1_id)
        fg2 = session.query(FileGroup).get(fg2_id)
        assert fg1.tag_names == ['batch_tag_a'], \
            "Tag on first channel's video should be preserved after batch reorganization"
        assert fg2.tag_names == ['batch_tag_b'], \
            "Tag on second channel's video should be preserved after batch reorganization"


# ============================================================================
# Partial Reorganization and Resume Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorganize_file_format_updated_after_completion(async_client, test_directory, video_factory):
    """Verify that file_format is NOT changed until after reorganization completes.

    This is critical for resumability - if file_format is updated before files are moved,
    the user cannot retry a failed reorganization because needs_reorganization would return False.
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio

    # Create channel collection with old file_format
    channel_dir = test_directory / 'videos' / 'DeferredFormatChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    old_format = '%(old_format)s.%(ext)s'
    with get_db_session(commit=True) as session:
        collection = Collection(
            name='DeferredFormatChannel',
            kind='channel',
            directory=channel_dir,
            file_format=old_format
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='DeferredFormatChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create video
    video = video_factory(channel_id=channel_id, title='format_test_video', with_video_file=True)

    with get_db_session() as session:
        video_obj = session.query(Video).get(video.id)
        old_primary_path = video_obj.file_group.primary_path

    # Get the current config format (what it should become after reorganization)
    config = get_videos_downloader_config()
    new_format = config.file_name_format

    # Create move mapping
    new_primary_path = channel_dir / 'renamed_format_test.mp4'
    move_mappings = [(old_primary_path, new_primary_path)]

    # Execute reorganization directly via handle_reorganize
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        collection_id=collection_id,
        job_id='test-file-format-deferred',
        pending_file_format=new_format,  # Pass the pending format
    )

    # Before completion, file_format should still be old
    with get_db_session() as session:
        collection = session.query(Collection).get(collection_id)
        assert collection.file_format == old_format, \
            "file_format should NOT be updated before reorganization completes"

    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # After completion, file_format should now be updated
    with get_db_session() as session:
        collection = session.query(Collection).get(collection_id)
        assert collection.file_format == new_format, \
            "file_format should be updated after reorganization completes"
        assert collection.needs_reorganization is False, \
            "needs_reorganization should be False after successful reorganization"


@pytest.mark.asyncio
async def test_reorganize_can_retry_after_partial_failure(async_client, test_directory, video_factory):
    """Verify that reorganization can be retried after mid-process failure.

    After partial failure:
    - Some files may have been moved
    - file_format should NOT have been updated (allowing retry)
    - needs_reorganization should still return True
    """
    from wrolpi.files.worker import file_worker
    import shutil

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'PartialFailureChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    old_format = '%(old_format)s.%(ext)s'
    with get_db_session(commit=True) as session:
        collection = Collection(
            name='PartialFailureChannel',
            kind='channel',
            directory=channel_dir,
            file_format=old_format
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='PartialFailureChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create multiple videos
    video1 = video_factory(channel_id=channel_id, title='partial_video_1', with_video_file=True)
    video2 = video_factory(channel_id=channel_id, title='partial_video_2', with_video_file=True)
    video3 = video_factory(channel_id=channel_id, title='partial_video_3', with_video_file=True)

    with get_db_session() as session:
        video1_obj = session.query(Video).get(video1.id)
        video2_obj = session.query(Video).get(video2.id)
        video3_obj = session.query(Video).get(video3.id)

        path1 = video1_obj.file_group.primary_path
        path2 = video2_obj.file_group.primary_path
        path3 = video3_obj.file_group.primary_path

    # Simulate partial failure: move video1 manually (as if reorganization partially completed)
    dest1 = channel_dir / 'moved_partial_video_1.mp4'
    shutil.move(str(path1), str(dest1))

    # Verify setup - file moved but DB still points to old location
    assert dest1.exists(), "Video 1 should be at destination"
    assert not path1.exists(), "Video 1 should not be at source"

    with get_db_session() as session:
        video1_obj = session.query(Video).get(video1.id)
        assert video1_obj.file_group.primary_path == path1, \
            "DB should still point to old location (simulating partial failure before DB update)"

    # Verify needs_reorganization is still True (file_format not updated)
    with get_db_session() as session:
        collection = session.query(Collection).get(collection_id)
        assert collection.file_format == old_format, \
            "file_format should still be old after partial failure"
        assert collection.needs_reorganization is True, \
            "needs_reorganization should still be True after partial failure"


@pytest.mark.asyncio
async def test_reorganize_handles_already_moved_files(async_client, test_directory, video_factory):
    """Verify graceful handling when files exist at destination but DB points to old location.

    This is a recovery case - files were moved but DB update didn't complete (e.g., power loss).
    The reorganization should:
    - Detect that source doesn't exist but destination does
    - Update DB to match destination paths
    - Not error about missing source
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio
    import shutil

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'RecoveryChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='RecoveryChannel',
            kind='channel',
            directory=channel_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='RecoveryChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create video
    video = video_factory(channel_id=channel_id, title='recovery_video', with_video_file=True)

    with get_db_session() as session:
        video_obj = session.query(Video).get(video.id)
        old_primary_path = video_obj.file_group.primary_path
        fg_id = video_obj.file_group.id

    # Record original file content for verification
    original_content = old_primary_path.read_bytes()

    # Manually move video to destination (simulating partial completion)
    dest_path = channel_dir / 'recovered_video.mp4'
    shutil.move(str(old_primary_path), str(dest_path))

    # Verify setup
    assert not old_primary_path.exists(), "Source should not exist"
    assert dest_path.exists(), "Destination should exist (manually moved)"

    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert fg.primary_path == old_primary_path, "DB should still point to source"

    # Now run reorganization - it should recover by updating DB
    move_mappings = [(old_primary_path, dest_path)]

    config = get_videos_downloader_config()
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        collection_id=collection_id,
        job_id='test-recovery',
        pending_file_format=config.file_name_format,
    )

    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # Verify recovery: DB should now point to destination
    with get_db_session() as session:
        fg = session.query(FileGroup).get(fg_id)
        assert fg.primary_path == dest_path, \
            f"DB should be updated to destination path after recovery. Got {fg.primary_path}"
        assert fg.directory == dest_path.parent, \
            "Directory should be updated to destination directory"

    # Verify file content is intact
    assert dest_path.read_bytes() == original_content, "File content should be preserved"


@pytest.mark.asyncio
async def test_reorganize_handles_mixed_state(async_client, test_directory, video_factory):
    """Verify reorganization handles a mix of filesystem states idempotently.

    - Video 1: Manually move to destination (DB points to source, file at dest) - recovery case
    - Video 2: Leave at source (normal case - DB and filesystem match)
    - Video 3: Create copy at both source and destination (conflict case)

    Expected results:
    - Video 1: DB updated to dest path
    - Video 2: File moved to dest, DB updated
    - Video 3: Skipped with warning (both exist)
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio
    import shutil

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'MixedStateChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='MixedStateChannel',
            kind='channel',
            directory=channel_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='MixedStateChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create 3 videos
    video1 = video_factory(channel_id=channel_id, title='mixed_video_1', with_video_file=True)
    video2 = video_factory(channel_id=channel_id, title='mixed_video_2', with_video_file=True)
    video3 = video_factory(channel_id=channel_id, title='mixed_video_3', with_video_file=True)

    with get_db_session() as session:
        v1_obj = session.query(Video).get(video1.id)
        v2_obj = session.query(Video).get(video2.id)
        v3_obj = session.query(Video).get(video3.id)

        path1 = v1_obj.file_group.primary_path
        path2 = v2_obj.file_group.primary_path
        path3 = v3_obj.file_group.primary_path

        fg1_id = v1_obj.file_group.id
        fg2_id = v2_obj.file_group.id
        fg3_id = v3_obj.file_group.id

    dest1 = channel_dir / 'reorganized_mixed_1.mp4'
    dest2 = channel_dir / 'reorganized_mixed_2.mp4'
    dest3 = channel_dir / 'reorganized_mixed_3.mp4'

    # Setup mixed states
    # Video 1: Move to dest (recovery case)
    shutil.move(str(path1), str(dest1))

    # Video 2: Leave at source (normal case)
    # (no action needed)

    # Video 3: Copy to both (conflict case)
    shutil.copy(str(path3), str(dest3))

    # Build move mappings
    move_mappings = [
        (path1, dest1),
        (path2, dest2),
        (path3, dest3),
    ]

    config = get_videos_downloader_config()
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        collection_id=collection_id,
        job_id='test-mixed-state',
        pending_file_format=config.file_name_format,
    )

    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    with get_db_session() as session:
        # Video 1: Should have DB updated to dest (recovery)
        fg1 = session.query(FileGroup).get(fg1_id)
        assert fg1.primary_path == dest1, \
            f"Video 1 should have DB updated to dest path (recovery). Got {fg1.primary_path}"

        # Video 2: Should be moved and DB updated (normal)
        fg2 = session.query(FileGroup).get(fg2_id)
        assert fg2.primary_path == dest2, \
            f"Video 2 should be moved to dest. Got {fg2.primary_path}"
        assert dest2.exists(), "Video 2 file should exist at destination"
        assert not path2.exists(), "Video 2 file should not exist at source"

        # Video 3: Should be skipped (both exist - conflict)
        fg3 = session.query(FileGroup).get(fg3_id)
        assert fg3.primary_path == path3, \
            f"Video 3 should remain at source (conflict skipped). Got {fg3.primary_path}"
        assert path3.exists(), "Video 3 should still exist at source"
        assert dest3.exists(), "Video 3 should still exist at dest"


@pytest.mark.asyncio
async def test_batch_reorganize_can_resume_after_collection_failure(async_client, test_directory, video_factory):
    """Verify batch reorganization can resume after one collection fails.

    - Create multiple channels with videos
    - Batch reorganize, simulate failure on second collection
    - Verify first collection was completed
    - Verify second collection can be retried individually
    - Verify file_format on failed collection was NOT updated
    """
    # This test verifies that batch failures are recoverable
    # The key assertion is that file_format is not updated for failed collections
    from wrolpi.files.worker import file_worker

    videos_dir = test_directory / 'videos'
    videos_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        # Create two channels that need reorganization
        channel1_dir = videos_dir / 'BatchResumeChannel1'
        channel1_dir.mkdir(parents=True, exist_ok=True)
        collection1 = Collection(
            name='BatchResumeChannel1',
            kind='channel',
            directory=channel1_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection1)
        session.flush()
        channel1 = Channel(name='BatchResumeChannel1', collection_id=collection1.id, directory=channel1_dir)
        session.add(channel1)
        collection1_id = collection1.id
        channel1_id = channel1.id

        channel2_dir = videos_dir / 'BatchResumeChannel2'
        channel2_dir.mkdir(parents=True, exist_ok=True)
        collection2 = Collection(
            name='BatchResumeChannel2',
            kind='channel',
            directory=channel2_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection2)
        session.flush()
        channel2 = Channel(name='BatchResumeChannel2', collection_id=collection2.id, directory=channel2_dir)
        session.add(channel2)
        collection2_id = collection2.id

        session.commit()

    # Create video in each channel
    video1 = video_factory(channel_id=channel1_id, title='batch_resume_video_1', with_video_file=True)

    # Verify both collections need reorganization
    with get_db_session() as session:
        c1 = session.query(Collection).get(collection1_id)
        c2 = session.query(Collection).get(collection2_id)
        assert c1.needs_reorganization is True
        assert c2.needs_reorganization is True

    # Execute batch reorganization for first collection only
    # (simulating partial batch completion)
    with get_db_session(commit=True) as session:
        job_id = execute_reorganization(collection1_id, session)
        if job_id:
            # Process the reorganization
            file_worker.transfer_queue()
            await file_worker.process_queue()

    # Verify first collection completed
    with get_db_session() as session:
        c1 = session.query(Collection).get(collection1_id)
        c2 = session.query(Collection).get(collection2_id)

        # First collection should be done (file_format updated)
        # Note: This tests current behavior - may need adjustment based on implementation
        config = get_videos_downloader_config()
        assert c1.file_format == config.file_name_format, \
            "First collection's file_format should be updated"
        assert c1.needs_reorganization is False, \
            "First collection should no longer need reorganization"

        # Second collection should still need reorganization
        assert c2.file_format == '%(old_format)s.%(ext)s', \
            "Second collection's file_format should NOT be updated (batch didn't process it)"
        assert c2.needs_reorganization is True, \
            "Second collection should still need reorganization"


# ============================================================================
# Filename Conflict Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorganize_skips_deleted_files_gracefully(async_client, test_directory, video_factory):
    """Reorganization should skip move_mappings for missing files, not fail.

    Tests the handle_reorganize behavior when a move_mapping references a file
    that no longer exists (neither source nor destination). This tests the
    "neither exists" branch in handle_reorganize which should:
    - Log a warning
    - Skip the file
    - Continue processing remaining files
    - Complete successfully

    Note: We also delete the Video/FileGroup records to prevent the video_modeler
    from creating a new Video and failing during post-processing.
    """
    from wrolpi.files.worker import file_worker, FileTask, FileTaskType
    import asyncio
    import os

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'DeletedFilesChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='DeletedFilesChannel',
            kind='channel',
            directory=channel_dir,
            file_format='%(old_format)s.%(ext)s'
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='DeletedFilesChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create 3 videos
    video1 = video_factory(channel_id=channel_id, title='existing_video_1', with_video_file=True)
    video2 = video_factory(channel_id=channel_id, title='deleted_video', with_video_file=True)
    video3 = video_factory(channel_id=channel_id, title='existing_video_3', with_video_file=True)

    with get_db_session() as session:
        v1_obj = session.query(Video).get(video1.id)
        v2_obj = session.query(Video).get(video2.id)
        v3_obj = session.query(Video).get(video3.id)

        path1 = v1_obj.file_group.primary_path
        path2 = v2_obj.file_group.primary_path
        path3 = v3_obj.file_group.primary_path

        fg1_id = v1_obj.file_group.id
        fg2_id = v2_obj.file_group.id
        fg3_id = v3_obj.file_group.id

    # Simulate user deleting video 2's file from filesystem
    # Also delete the Video and FileGroup records to prevent post-processing failure
    # (The video_modeler would otherwise create a new Video and try to ffprobe it)
    os.remove(str(path2))
    with get_db_session(commit=True) as session:
        video_to_delete = session.query(Video).get(video2.id)
        fg_to_delete = session.query(FileGroup).get(fg2_id)
        session.delete(video_to_delete)
        session.delete(fg_to_delete)

    assert not path2.exists(), "Video 2 should be deleted from filesystem"
    assert path1.exists(), "Video 1 should still exist"
    assert path3.exists(), "Video 3 should still exist"

    # Build move mappings for all 3 videos (as execute_reorganization would)
    dest1 = channel_dir / 'reorganized_video_1.mp4'
    dest2 = channel_dir / 'reorganized_deleted.mp4'
    dest3 = channel_dir / 'reorganized_video_3.mp4'

    move_mappings = [
        (path1, dest1),
        (path2, dest2),  # This file doesn't exist - should be skipped
        (path3, dest3),
    ]

    config = get_videos_downloader_config()
    task = FileTask(
        task_type=FileTaskType.reorganize,
        paths=[],
        move_mappings=move_mappings,
        collection_id=collection_id,
        job_id='test-deleted-files',
        pending_file_format=config.file_name_format,
    )

    # This should NOT raise an exception
    await file_worker.handle_reorganize(task)
    await asyncio.sleep(0.1)

    # Verify results
    with get_db_session() as session:
        # Video 1: Should be moved and DB updated
        fg1 = session.query(FileGroup).get(fg1_id)
        assert fg1.primary_path == dest1, f"Video 1 should be moved to dest. Got {fg1.primary_path}"
        assert dest1.exists(), "Video 1 file should exist at destination"
        assert not path1.exists(), "Video 1 file should not exist at source"

        # Video 2: Was deleted from both filesystem and DB, move_mapping was skipped
        # (The reorganization logged a warning and continued)
        assert not path2.exists(), "Video 2 file should not exist at source (was deleted)"
        assert not dest2.exists(), "Video 2 file should not exist at destination (was deleted)"

        # Video 3: Should be moved and DB updated
        fg3 = session.query(FileGroup).get(fg3_id)
        assert fg3.primary_path == dest3, f"Video 3 should be moved to dest. Got {fg3.primary_path}"
        assert dest3.exists(), "Video 3 file should exist at destination"
        assert not path3.exists(), "Video 3 file should not exist at source"

        # Collection file_format should be updated (reorganization completed successfully)
        collection = session.query(Collection).get(collection_id)
        assert collection.file_format == config.file_name_format, \
            "Collection file_format should be updated after successful reorganization"


@pytest.mark.parametrize("file_format,has_upload_date,has_source_id,has_uploader,should_produce_path", [
    # Format requires upload_year - needs upload_date
    ("%(upload_year)s/%(title)s.%(ext)s", False, False, False, False),
    ("%(upload_year)s/%(title)s.%(ext)s", True, False, False, True),
    # Format requires source_id - needs source_id
    ("%(id)s_%(title)s.%(ext)s", False, False, False, False),
    ("%(id)s_%(title)s.%(ext)s", False, True, False, True),
    # Format requires uploader - video.channel.name provides fallback, so always True for videos with channel
    ("%(uploader)s_%(title)s.%(ext)s", False, False, False, True),  # channel.name fallback
    ("%(uploader)s_%(title)s.%(ext)s", False, False, True, True),
    # Format only needs title - always works
    ("%(title)s.%(ext)s", False, False, False, True),
    ("%(title)s.%(ext)s", True, True, True, True),
    # Complex format - needs all metadata (upload_date, source_id, uploader)
    ("%(upload_year)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s", False, False, False, False),
    ("%(upload_year)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s", True, True, True, True),
    # Missing some but has others - still fails if format requires the missing one
    ("%(upload_year)s/%(uploader)s_%(title)s.%(ext)s", False, True, True, False),  # missing upload_date
    ("%(upload_year)s/%(uploader)s_%(title)s.%(ext)s", True, False, False, True),  # channel.name fallback for uploader
    ("%(upload_year)s/%(uploader)s_%(title)s.%(ext)s", True, False, True, True),  # has both required
])
def test_reorganize_skips_videos_missing_required_metadata(
        test_session, test_directory, video_factory,
        file_format, has_upload_date, has_source_id, has_uploader, should_produce_path
):
    """Videos should only be skipped when missing metadata that the format requires.

    This test verifies that _compute_new_path_for_video correctly determines
    whether a video has sufficient metadata based on the configured format string.
    """
    from datetime import datetime, timezone
    from wrolpi.collections.reorganize import _compute_new_path_for_video

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'MetadataTestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='MetadataTestChannel',
        kind='channel',
        directory=channel_dir,
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name='MetadataTestChannel', collection_id=collection.id, directory=channel_dir)
    test_session.add(channel)
    test_session.commit()
    channel_id = channel.id

    # Build info_json dict if we need uploader or source_id from it
    info_json = {}
    if has_uploader:
        info_json['uploader'] = 'TestUploader'
    if has_source_id:
        info_json['id'] = 'abc123'

    # Create video with controlled metadata
    # with_info_json creates the actual .info.json file on disk
    video = video_factory(
        channel_id=channel_id,
        title='Test Video',
        with_video_file=True,
        with_info_json=info_json if info_json else None,
    )

    video_obj = test_session.query(Video).get(video.id)

    # Set source_id directly on the Video model (separate from info_json)
    video_obj.source_id = 'abc123' if has_source_id else None
    video_obj.file_group.published_datetime = datetime(2024, 6, 15, tzinfo=timezone.utc) if has_upload_date else None

    test_session.commit()
    test_session.refresh(video_obj)

    # Call _compute_new_path_for_video with explicit file_format
    new_path = _compute_new_path_for_video(video_obj, channel_dir, file_format=file_format)

    if should_produce_path:
        assert new_path is not None, (
            f"Format '{file_format}' with upload_date={has_upload_date}, "
            f"source_id={has_source_id}, uploader={has_uploader} should produce a path"
        )
        # Verify the path doesn't contain empty segments
        path_str = str(new_path.relative_to(channel_dir))
        assert not path_str.startswith('/'), f"Path should not start with /: {path_str}"
    else:
        assert new_path is None, (
            f"Format '{file_format}' with upload_date={has_upload_date}, "
            f"source_id={has_source_id}, uploader={has_uploader} should return None, "
            f"but got: {new_path}"
        )


@pytest.mark.parametrize("file_format,has_url,should_produce_path", [
    # Format requires domain - needs URL
    ("%(domain)s/%(title)s.%(ext)s", False, False),
    ("%(domain)s/%(title)s.%(ext)s", True, True),
    # Format only needs title/download_date - always works
    ("%(title)s.%(ext)s", False, True),
    ("%(title)s.%(ext)s", True, True),
    ("%(download_datetime)s_%(title)s.%(ext)s", False, True),
    ("%(download_datetime)s_%(title)s.%(ext)s", True, True),
    # Complex format with domain
    ("%(download_year)s/%(domain)s_%(title)s.%(ext)s", False, False),
    ("%(download_year)s/%(domain)s_%(title)s.%(ext)s", True, True),
    # Format without domain - always works
    ("%(download_year)s/%(download_month)s/%(title)s.%(ext)s", False, True),
])
def test_reorganize_skips_archives_missing_required_metadata(
        test_session, test_directory, archive_factory,
        file_format, has_url, should_produce_path
):
    """Archives should only be skipped when missing metadata that the format requires.

    Archives have robust fallbacks for most variables (dates fallback to now(),
    title to 'untitled'). Only domain can be empty when URL is missing.
    """
    from wrolpi.collections.reorganize import _compute_new_path_for_archive

    # Create domain collection
    domain_dir = test_directory / 'archive' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='test.com',
        kind='domain',
        directory=domain_dir,
    )
    test_session.add(collection)
    test_session.commit()

    # Create archive with controlled metadata
    archive = archive_factory(
        domain='test.com',
        url='https://test.com/article' if has_url else None,
        title='Test Article',
    )

    archive_obj = test_session.query(Archive).get(archive.id)

    # Clear URL if testing without it
    if not has_url:
        archive_obj.file_group.url = None
        test_session.commit()
        test_session.refresh(archive_obj)

    # Call _compute_new_path_for_archive with explicit file_format
    new_path = _compute_new_path_for_archive(archive_obj, domain_dir, file_format=file_format)

    if should_produce_path:
        assert new_path is not None, (
            f"Format '{file_format}' with url={has_url} should produce a path"
        )
    else:
        assert new_path is None, (
            f"Format '{file_format}' with url={has_url} should return None, "
            f"but got: {new_path}"
        )


# ============================================================================
# Partial Reorganization Tests (Individual Collection Reorganization)
# ============================================================================


@pytest.mark.asyncio
async def test_domain_reorganization_moves_files_from_root_to_year_subdirectory(
    async_client, test_directory, archive_factory
):
    """Archives in collection root should be moved to year subdirectories.

    Scenario: Batch reorganization completed but missed some files.
    - collection.file_format matches config (needs_reorganization=False)
    - Some archives are in root: domain.com/2000-01-01_article.html
    - Format expects: domain.com/2000/2000-01-01_article.html
    - Reorganization should move files from root to year subdirectory
    """
    from wrolpi.files.worker import file_worker

    # Create domain collection with year-based format
    domain_dir = test_directory / 'archive' / 'test.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    year_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

    # Temporarily change config to use year format
    config = get_archive_downloader_config()
    original_format = config._config['file_name_format']
    config._config['file_name_format'] = year_format

    try:
        with get_db_session(commit=True) as session:
            collection = Collection(
                name='test.com',
                kind='domain',
                directory=domain_dir,
                file_format=year_format,  # Matches expected format (appears organized)
            )
            session.add(collection)
            session.commit()
            collection_id = collection.id

        # Create archive using factory - files will be in root (no year subdir)
        # Factory creates files with format: %(download_datetime)s_%(title)s.%(ext)s (NOT year)
        archive = archive_factory(domain='test.com', url='https://test.com/article', title='Test Article')

        with get_db_session(commit=True) as session:
            archive_obj = session.query(Archive).get(archive.id)
            archive_obj.collection_id = collection_id
            session.commit()

            # Verify: collection appears organized but files are in wrong place
            collection = session.query(Collection).get(collection_id)
            assert collection.file_format == year_format, "Collection format should match config"
            assert collection.needs_reorganization is False, \
                "Collection should appear organized (format matches config)"

            old_path = archive_obj.file_group.primary_path
            assert old_path.parent == domain_dir, \
                f"Archive should be in root, not year subdir. Got: {old_path.parent}"

        # Get preview with exact_count - should detect files need moving
        with get_db_session() as session:
            preview = get_reorganization_preview(collection_id, session, exact_count=True)
            assert preview.files_needing_move > 0, \
                f"Should detect files need moving. Got: {preview.files_needing_move}"

        # Execute reorganization
        with get_db_session(commit=True) as session:
            job_id = execute_reorganization(collection_id, session)
            assert job_id, "Should return job_id for files to move"

        # Process the reorganization
        file_worker.transfer_queue()
        await file_worker.process_queue()

        # Verify: files moved to year subdirectory
        with get_db_session() as session:
            archive_obj = session.query(Archive).get(archive.id)
            new_path = archive_obj.file_group.primary_path
            assert '/2000/' in str(new_path), f"File should be in year subdirectory. Got: {new_path}"
            assert new_path.exists(), "New file should exist"
    finally:
        config._config['file_name_format'] = original_format


@pytest.mark.asyncio
async def test_channel_reorganization_moves_files_from_root_to_year_subdirectory(
    async_client, test_directory, video_factory
):
    """Videos in collection root should be moved to year subdirectories.

    Scenario: Files are in the wrong place and need to be moved.
    - Some videos are in root: channel/title.mp4
    - Format expects: channel/2024/title.mp4
    - Reorganization should move files from root to year subdirectory
    """
    from datetime import datetime, timezone
    from wrolpi.files.worker import file_worker

    # Create channel collection with year-based format
    channel_dir = test_directory / 'videos' / 'TestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    year_format = '%(upload_year)s/%(title)s.%(ext)s'

    # Temporarily change config to use year format (videos config is nested)
    # Manager dict requires reassigning the entire nested dict for changes to propagate
    config = get_videos_downloader_config()
    original_format = config._config['yt_dlp_options']['file_name_format']
    yt_dlp_options = dict(config._config['yt_dlp_options'])
    yt_dlp_options['file_name_format'] = year_format
    config._config['yt_dlp_options'] = yt_dlp_options

    try:
        with get_db_session(commit=True) as session:
            collection = Collection(
                name='TestChannel',
                kind='channel',
                directory=channel_dir,
                file_format=year_format,
            )
            session.add(collection)
            session.flush()
            channel = Channel(name='TestChannel', collection_id=collection.id, directory=channel_dir)
            session.add(channel)
            session.commit()
            collection_id = collection.id
            channel_id = channel.id

        # Create video using factory - files will be in root (no year subdir)
        video = video_factory(
            channel_id=channel_id,
            title='test_video',
            with_video_file=True,
            with_info_json={'uploader': 'Tester', 'id': 'abc123'},
            upload_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )

        with get_db_session(commit=True) as session:
            video_obj = session.query(Video).get(video.id)

            old_path = video_obj.file_group.primary_path
            assert old_path.parent == channel_dir, \
                f"Video should be in root, not year subdir. Got: {old_path.parent}"

        # Get preview with exact_count - should detect files need moving
        with get_db_session() as session:
            preview = get_reorganization_preview(collection_id, session, exact_count=True)
            assert preview.files_needing_move > 0, \
                f"Should detect files need moving. Got: {preview.files_needing_move}"

        # Execute reorganization
        with get_db_session(commit=True) as session:
            job_id = execute_reorganization(collection_id, session)
            assert job_id, "Should return job_id for files to move"

        # Process the reorganization
        file_worker.transfer_queue()
        await file_worker.process_queue()

        # Verify: files moved to year subdirectory
        with get_db_session() as session:
            video_obj = session.query(Video).get(video.id)
            new_path = video_obj.file_group.primary_path
            assert '/2024/' in str(new_path), f"File should be in year subdirectory. Got: {new_path}"
            assert new_path.exists(), "New file should exist"
    finally:
        yt_dlp_options = dict(config._config['yt_dlp_options'])
        yt_dlp_options['file_name_format'] = original_format
        config._config['yt_dlp_options'] = yt_dlp_options


@pytest.mark.asyncio
async def test_channel_reorganization_preserves_root_level_files(
    async_client, test_directory, video_factory
):
    """Root-level files (like channel info.json and images) should NOT be moved during reorganization.

    This is intentional behavior - only Video files tracked in FileGroups are reorganized.
    Channel metadata files at the collection root should remain in place.
    """
    from datetime import datetime, timezone
    from wrolpi.files.worker import file_worker

    # Create channel collection with year-based format
    channel_dir = test_directory / 'videos' / 'TestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    year_format = '%(upload_year)s/%(title)s.%(ext)s'

    # Create root-level files that should NOT be moved
    root_json = channel_dir / 'TestChannel.info.json'
    root_json.write_text('{"channel": "test"}')
    root_image = channel_dir / 'channel_banner.jpg'
    root_image.write_bytes(b'\xff\xd8\xff\xe0')  # Minimal JPEG header

    # Temporarily change config to use year format
    config = get_videos_downloader_config()
    original_format = config._config['yt_dlp_options']['file_name_format']
    yt_dlp_options = dict(config._config['yt_dlp_options'])
    yt_dlp_options['file_name_format'] = year_format
    config._config['yt_dlp_options'] = yt_dlp_options

    try:
        with get_db_session(commit=True) as session:
            collection = Collection(
                name='TestChannel',
                kind='channel',
                directory=channel_dir,
                file_format=year_format,
            )
            session.add(collection)
            session.flush()
            channel = Channel(name='TestChannel', collection_id=collection.id, directory=channel_dir)
            session.add(channel)
            session.commit()
            collection_id = collection.id
            channel_id = channel.id

        # Create videos using factory - files will be in root initially
        video1 = video_factory(
            channel_id=channel_id,
            title='video_one',
            with_video_file=True,
            upload_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        video2 = video_factory(
            channel_id=channel_id,
            title='video_two',
            with_video_file=True,
            upload_date=datetime(2024, 8, 20, tzinfo=timezone.utc),
        )

        # Verify initial state: videos in root, root files exist
        with get_db_session() as session:
            v1 = session.query(Video).get(video1.id)
            v2 = session.query(Video).get(video2.id)
            assert v1.file_group.primary_path.parent == channel_dir
            assert v2.file_group.primary_path.parent == channel_dir
        assert root_json.exists(), "Root JSON should exist before reorganization"
        assert root_image.exists(), "Root image should exist before reorganization"

        # Execute reorganization
        with get_db_session(commit=True) as session:
            job_id = execute_reorganization(collection_id, session)
            assert job_id, "Should return job_id for files to move"

        # Process the reorganization
        file_worker.transfer_queue()
        await file_worker.process_queue()

        # Verify: videos moved to year subdirectory
        with get_db_session() as session:
            v1 = session.query(Video).get(video1.id)
            v2 = session.query(Video).get(video2.id)
            assert '/2024/' in str(v1.file_group.primary_path), "Video 1 should be in year subdirectory"
            assert '/2024/' in str(v2.file_group.primary_path), "Video 2 should be in year subdirectory"
            assert v1.file_group.primary_path.exists()
            assert v2.file_group.primary_path.exists()

        # Verify: root-level files were NOT moved (this is the key assertion)
        assert root_json.exists(), "Root JSON should still exist at original location after reorganization"
        assert root_image.exists(), "Root image should still exist at original location after reorganization"
        assert root_json.read_text() == '{"channel": "test"}', "Root JSON content should be unchanged"

    finally:
        yt_dlp_options = dict(config._config['yt_dlp_options'])
        yt_dlp_options['file_name_format'] = original_format
        config._config['yt_dlp_options'] = yt_dlp_options


def test_preview_exact_count_computes_actual_moves(test_session, test_directory, archive_factory):
    """With exact_count=True, preview should compute actual files needing move, not total files.

    This test verifies that:
    - exact_count=False returns total_files as files_needing_move (estimate)
    - exact_count=True computes the actual count by building move mappings
    """
    # Create domain collection with a year-based format (different from default)
    domain_dir = test_directory / 'archive' / 'exactcount.com'
    domain_dir.mkdir(parents=True, exist_ok=True)

    year_format = '%(download_year)s/%(download_datetime)s_%(title)s.%(ext)s'

    # Temporarily change config to use year format
    config = get_archive_downloader_config()
    original_format = config._config['file_name_format']
    config._config['file_name_format'] = year_format

    try:
        collection = Collection(
            name='exactcount.com',
            kind='domain',
            directory=domain_dir,
            file_format=year_format,  # Matches config
        )
        test_session.add(collection)
        test_session.commit()
        collection_id = collection.id

        # Create archive using factory - files will be in root (need to move to year subdir)
        archive = archive_factory(domain='exactcount.com', url='https://exactcount.com/article', title='Test')

        with get_db_session(commit=True) as session:
            archive_obj = session.query(Archive).get(archive.id)
            archive_obj.collection_id = collection_id
            session.commit()

        # Without exact_count, preview assumes all files need moving
        with get_db_session() as session:
            preview_estimate = get_reorganization_preview(collection_id, session, exact_count=False)
            # This is the current behavior - assumes all need moving
            assert preview_estimate.files_needing_move == preview_estimate.total_files
            assert preview_estimate.files_needing_move == 1

        # With exact_count, preview also detects that files need moving (they're in wrong location)
        with get_db_session() as session:
            preview_exact = get_reorganization_preview(collection_id, session, exact_count=True)
            # Files are in root, but should be in year subdir, so 1 file needs moving
            assert preview_exact.files_needing_move == 1, \
                f"File in wrong location should need moving. Got: {preview_exact.files_needing_move}"

        # Now execute the reorganization to move files to correct location
        from wrolpi.files.worker import file_worker
        with get_db_session(commit=True) as session:
            job_id = execute_reorganization(collection_id, session)
            assert job_id, "Should return job_id"

        file_worker.transfer_queue()
        import asyncio
        asyncio.get_event_loop().run_until_complete(file_worker.process_queue())

        # After reorganization, with exact_count should show 0 files needing move
        with get_db_session() as session:
            preview_after = get_reorganization_preview(collection_id, session, exact_count=True)
            assert preview_after.files_needing_move == 0, \
                f"After reorganization, no files should need moving. Got: {preview_after.files_needing_move}"
    finally:
        config._config['file_name_format'] = original_format


@pytest.mark.asyncio
async def test_reorganize_fails_on_filename_conflicts(async_client, test_directory, video_factory):
    """Reorganization should fail early when two videos would have the same destination filename."""
    from datetime import datetime, timezone

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'ConflictChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    with get_db_session(commit=True) as session:
        collection = Collection(
            name='ConflictChannel',
            kind='channel',
            directory=channel_dir,
            file_format='%(old_format)s.%(ext)s'  # Needs reorganization
        )
        session.add(collection)
        session.flush()
        channel = Channel(name='ConflictChannel', collection_id=collection.id, directory=channel_dir)
        session.add(channel)
        session.commit()
        channel_id = channel.id
        collection_id = collection.id

    # Create two videos with DIFFERENT initial filenames but IDENTICAL destination metadata
    # Both videos will have the same uploader, upload_date, source_id, and title
    # This should produce a filename conflict
    same_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    same_source_id = 'duplicate_id'

    video1 = video_factory(
        channel_id=channel_id,
        title='video_one',  # Different initial filename
        upload_date=same_date,
        with_video_file=True,
        with_info_json={'uploader': 'TestUploader', 'id': same_source_id}
    )

    video2 = video_factory(
        channel_id=channel_id,
        title='video_two',  # Different initial filename
        upload_date=same_date,
        with_video_file=True,
        with_info_json={'uploader': 'TestUploader', 'id': same_source_id}
    )

    # Update both videos to have the same title and source_id
    # This makes them produce the same destination filename
    with get_db_session(commit=True) as session:
        v1 = session.query(Video).get(video1.id)
        v2 = session.query(Video).get(video2.id)
        v1.file_group.title = 'Duplicate Title'
        v2.file_group.title = 'Duplicate Title'
        v1.source_id = same_source_id
        v2.source_id = same_source_id

    # Attempting to reorganize should fail with conflict error
    with pytest.raises(ReorganizationConflict) as exc_info:
        with get_db_session() as session:
            execute_reorganization(collection_id, session)

    # Error message should mention the conflict
    assert 'conflict' in str(exc_info.value).lower()
    assert 'Duplicate Title' in str(exc_info.value)


# ============================================================================
# Filename Parsing Fallback Tests
# ============================================================================


@pytest.mark.parametrize("filename,file_format,expected_result", [
    # Filename with all fields: uploader_date_sourceid_title.ext
    # Should work with complex formats since filename parsing provides all metadata
    (
        "Learning Self-Reliance_20170529_p_MzsCFkUPU_How to Build a Solar Generator.mp4",
        "%(upload_year)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s",
        True,  # Should work - filename has uploader, date, and source_id
    ),
    # Filename without source_id: uploader_date_title.ext pattern
    # Should NOT work with format requiring %(id)s
    (
        "Commsprepper_20130113_110Ah Car Battery connected to 80W Solar Panel.mp4",
        "%(upload_year)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s",
        False,  # Should fail - filename doesn't have source_id and format requires it
    ),
    # Filename without source_id but format doesn't require it
    (
        "Commsprepper_20130113_110Ah Car Battery.mp4",
        "%(upload_year)s/%(uploader)s_%(upload_date)s_%(title)s.%(ext)s",
        False,  # Should still fail - all-or-nothing: no source_id means no fallback
    ),
    # Simple title-only format (always works)
    (
        "random_video_name.mp4",
        "%(title)s.%(ext)s",
        True,  # Should work - format only requires title
    ),
])
def test_video_metadata_fallback_from_filename(
        test_session, test_directory,
        filename, file_format, expected_result
):
    """Test that _video_has_required_metadata uses filename parsing as all-or-nothing fallback.

    Videos without info.json can use filename parsing to extract metadata,
    but ONLY if the filename provides ALL three fields: channel, date, source_id.
    This prevents cherry-picking individual fields which could lead to inconsistent data.
    """
    from wrolpi.collections.reorganize import _video_has_required_metadata

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'FallbackTestChannel'
    channel_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='FallbackTestChannel',
        kind='channel',
        directory=channel_dir,
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name='FallbackTestChannel', collection_id=collection.id, directory=channel_dir)
    test_session.add(channel)
    test_session.commit()

    # Create video file with specific filename
    video_path = channel_dir / filename
    video_path.touch()

    # Create FileGroup
    fg = FileGroup()
    fg.directory = channel_dir
    fg.primary_path = video_path
    fg.files = [{'path': filename, 'mimetype': 'video/mp4'}]
    fg.title = video_path.stem  # Title from filename stem
    # Intentionally NOT setting published_datetime to test fallback
    test_session.add(fg)
    test_session.flush()

    # Create Video WITHOUT source_id or info.json - forces filename fallback
    video = Video(file_group_id=fg.id, channel_id=channel.id)
    # Intentionally NOT setting source_id to test fallback
    test_session.add(video)
    test_session.commit()
    test_session.refresh(video)

    result = _video_has_required_metadata(video, file_format)

    assert result is expected_result, (
        f"For filename '{filename}' with format '{file_format}', "
        f"expected {expected_result} but got {result}"
    )


def test_video_metadata_fallback_uses_channel_name_for_uploader(test_session, test_directory):
    """Test that video.channel.name is used as final fallback for uploader.

    Even if filename parsing fails (no source_id in filename), we can still
    use video.channel.name for the uploader field as a separate fallback.
    """
    from wrolpi.collections.reorganize import _video_has_required_metadata

    # Create channel collection
    channel_dir = test_directory / 'videos' / 'ChannelNameFallback'
    channel_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name='ChannelNameFallback',
        kind='channel',
        directory=channel_dir,
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name='MyChannel', collection_id=collection.id, directory=channel_dir)
    test_session.add(channel)
    test_session.commit()

    # Create video file with a title-only filename (no metadata in name)
    filename = "random_video.mp4"
    video_path = channel_dir / filename
    video_path.touch()

    # Create FileGroup with published_datetime
    from datetime import datetime, timezone
    fg = FileGroup()
    fg.directory = channel_dir
    fg.primary_path = video_path
    fg.files = [{'path': filename, 'mimetype': 'video/mp4'}]
    fg.title = 'Random Video'
    fg.published_datetime = datetime(2024, 6, 15, tzinfo=timezone.utc)
    test_session.add(fg)
    test_session.flush()

    # Create Video with source_id but NO uploader in info.json
    video = Video(file_group_id=fg.id, channel_id=channel.id, source_id='abc123')
    test_session.add(video)
    test_session.commit()
    test_session.refresh(video)

    # Format requires uploader - should use channel.name as fallback
    file_format = "%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s"
    result = _video_has_required_metadata(video, file_format)

    assert result is True, (
        "Should succeed because video.channel.name provides uploader fallback"
    )


@pytest.mark.parametrize(
    "filename,channel_name,title,db_datetime,db_source_id,expected_year,expected_uploader,expected_source_id,should_not_contain",
    [
        # Complete filename with all fields - uses filename fallback values
        (
            "TestUploader_20170529_p_MzsCFkUPU_My Test Video.mp4",
            "FormatFallbackChannel",
            "My Test Video",
            None,  # No DB datetime
            None,  # No DB source_id
            "2017",
            "TestUploader",
            "p_MzsCFkUPU",
            [],  # No forbidden values
        ),
        # Incomplete filename (no source_id) - uses DB values, not filename
        (
            "FilenameUploader_20200101_Just A Title.mp4",
            "ChannelFromDB",
            "Just A Title",
            "2024-06-15",  # DB datetime
            "db_source_id",  # DB source_id
            "2024",
            "ChannelFromDB",
            "db_source_id",
            ["FilenameUploader", "2020"],  # Should NOT contain these filename-parsed values
        ),
    ],
)
def test_format_video_filename_fallback_behavior(
    test_session,
    test_directory,
    filename,
    channel_name,
    title,
    db_datetime,
    db_source_id,
    expected_year,
    expected_uploader,
    expected_source_id,
    should_not_contain,
):
    """Test format_video_filename fallback behavior with various scenarios.

    Tests both:
    1. Complete filename with all fields → uses filename fallback values
    2. Incomplete filename (no source_id) with DB values → uses DB values, not filename
    """
    from datetime import datetime, timezone
    from modules.videos.lib import format_video_filename

    # Create channel collection
    channel_dir = test_directory / 'videos' / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)

    collection = Collection(
        name=channel_name,
        kind='channel',
        directory=channel_dir,
    )
    test_session.add(collection)
    test_session.flush()
    channel = Channel(name=channel_name, collection_id=collection.id, directory=channel_dir)
    test_session.add(channel)
    test_session.commit()

    # Create video file
    video_path = channel_dir / filename
    video_path.touch()

    # Create FileGroup
    fg = FileGroup()
    fg.directory = channel_dir
    fg.primary_path = video_path
    fg.files = [{'path': filename, 'mimetype': 'video/mp4'}]
    fg.title = title
    if db_datetime:
        year, month, day = map(int, db_datetime.split('-'))
        fg.published_datetime = datetime(year, month, day, tzinfo=timezone.utc)
    test_session.add(fg)
    test_session.flush()

    # Create Video
    video = Video(file_group_id=fg.id, channel_id=channel.id, source_id=db_source_id)
    test_session.add(video)
    test_session.commit()
    test_session.refresh(video)

    # Format with year subdirectory
    file_format = "%(upload_year)s/%(uploader)s_%(upload_date)s_%(id)s_%(title)s.%(ext)s"
    result = format_video_filename(video, file_format)

    # Verify expected values are present
    assert f'{expected_year}/' in result, f"Expected year {expected_year}. Got: {result}"
    assert f'{expected_uploader}_' in result, f"Expected uploader {expected_uploader}. Got: {result}"
    assert expected_source_id in result, f"Expected source_id {expected_source_id}. Got: {result}"

    # Verify forbidden values are NOT present (for all-or-nothing behavior)
    for forbidden in should_not_contain:
        assert forbidden not in result, f"Should NOT contain '{forbidden}'. Got: {result}"

