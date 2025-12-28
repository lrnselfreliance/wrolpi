"""
Tests for move operation recovery scenarios.

These tests verify that WROLPi can recover from various failure states
that can occur during move operations, such as:
- Server crashes mid-move
- Files manually moved by user
- Partial database updates
- Filesystem/database mismatches
"""
import shutil
from unittest import mock

import pytest

from wrolpi.files import lib
from wrolpi.files.worker import file_worker
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_recovery_files_moved_db_stale(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #44: Files physically at new location, DB FileGroup points to old location.

    Simulates crash after files moved but before DB updated.
    Files are at new location, FileGroup.primary_path points to old location.

    Expected: Refresh should reconcile by:
    1. Creating new FileGroup at actual location
    2. Deleting orphaned FileGroup at old location
    """
    # Create source directory with files
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    video, srt = make_files_structure({
        'source/video.mp4': b'fake video content',
        'source/video.srt': b'fake subtitle content',
    })

    # Create FileGroup via refresh
    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Verify initial state
    fg = test_session.query(FileGroup).filter(FileGroup.primary_path == video).one()
    original_fg_id = fg.id
    assert fg.primary_path == video
    assert fg.directory == source_dir
    # Note: Files may or may not be grouped depending on mimetype detection

    # Simulate crash: physically move files WITHOUT updating DB
    shutil.move(str(video), str(dest_dir / 'video.mp4'))
    shutil.move(str(srt), str(dest_dir / 'video.srt'))

    # Verify mismatch state: DB points to old, files at new
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter(FileGroup.id == original_fg_id).one()
    assert fg.primary_path == video  # Still points to old location
    assert not video.exists()  # But file doesn't exist there
    assert (dest_dir / 'video.mp4').exists()  # File is at new location

    # Recovery: Refresh both directories
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Assert recovery: FileGroups should now point to new location
    fgs = test_session.query(FileGroup).all()

    # All FileGroups should be at dest (orphans at source deleted)
    for fg in fgs:
        assert fg.directory == dest_dir, f"FileGroup {fg.primary_path} should be at dest, not {fg.directory}"

    # The video file should have a FileGroup at the new location
    video_fg = test_session.query(FileGroup).filter(
        FileGroup.primary_path == dest_dir / 'video.mp4'
    ).first()
    assert video_fg is not None, "video.mp4 FileGroup should exist at new location"

    # The original FileGroup at source should be gone (orphaned and deleted)
    old_fg = test_session.query(FileGroup).filter(
        FileGroup.primary_path == video
    ).first()
    assert old_fg is None, "Original FileGroup should be deleted (orphaned)"


@pytest.mark.asyncio
async def test_recovery_files_split_between_locations(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #24, #52: Files exist at both old and new locations (partial move).

    Simulates interrupted move or manual partial move.
    Some files at old location, some at new location.
    FileGroups point to old location.

    Expected: Refresh should create FileGroups for files at both locations.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create 4 video files at source
    files = make_files_structure({
        'source/video1.mp4': b'video 1 content',
        'source/video2.mp4': b'video 2 content',
        'source/video3.mp4': b'video 3 content',
        'source/video4.mp4': b'video 4 content',
    })

    # Create FileGroups via refresh
    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Verify initial state: 4 FileGroups at source
    fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    assert len(fgs) == 4

    # Simulate partial move: physically move 2 files to dest
    shutil.move(str(source_dir / 'video1.mp4'), str(dest_dir / 'video1.mp4'))
    shutil.move(str(source_dir / 'video2.mp4'), str(dest_dir / 'video2.mp4'))

    # Verify mismatch: 2 files at source, 2 at dest, but all 4 FGs point to source
    assert (source_dir / 'video3.mp4').exists()
    assert (source_dir / 'video4.mp4').exists()
    assert (dest_dir / 'video1.mp4').exists()
    assert (dest_dir / 'video2.mp4').exists()
    assert not (source_dir / 'video1.mp4').exists()
    assert not (source_dir / 'video2.mp4').exists()

    # Recovery: Refresh both directories
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Assert: Should have 4 FileGroups total - 2 at each location
    all_fgs = test_session.query(FileGroup).all()
    assert len(all_fgs) == 4, f"Expected 4 FileGroups, got {len(all_fgs)}"

    source_fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    dest_fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()

    assert len(source_fgs) == 2, f"Expected 2 at source, got {len(source_fgs)}"
    assert len(dest_fgs) == 2, f"Expected 2 at dest, got {len(dest_fgs)}"

    # Verify correct files at each location
    source_paths = {fg.primary_path.name for fg in source_fgs}
    dest_paths = {fg.primary_path.name for fg in dest_fgs}

    assert source_paths == {'video3.mp4', 'video4.mp4'}
    assert dest_paths == {'video1.mp4', 'video2.mp4'}


@pytest.mark.asyncio
async def test_recovery_partial_filegroup_updates(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #46, #22: Some FileGroups updated in DB, others still point to old location.

    Simulates crash during bulk DB update - some FileGroups updated, others not.
    All files physically at new location, but half the FileGroups point to old.

    Expected: Refresh should reconcile all FileGroups to actual file locations.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create 4 video files at source
    make_files_structure({
        'source/video1.mp4': b'video 1 content',
        'source/video2.mp4': b'video 2 content',
        'source/video3.mp4': b'video 3 content',
        'source/video4.mp4': b'video 4 content',
    })

    # Create FileGroups via refresh
    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    assert len(fgs) == 4

    # Physically move ALL files to dest
    for f in source_dir.iterdir():
        shutil.move(str(f), str(dest_dir / f.name))

    # Simulate partial DB update: Update only 2 FileGroups
    # (This simulates a crash during _bulk_update_file_groups_db)
    updated_count = 0
    for fg in fgs:
        if updated_count < 2:
            fg.primary_path = dest_dir / fg.primary_path.name
            fg.directory = dest_dir
            updated_count += 1
    test_session.commit()

    # Verify mismatch state
    test_session.expire_all()
    source_fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    dest_fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()
    assert len(source_fgs) == 2, "2 FileGroups should still point to source"
    assert len(dest_fgs) == 2, "2 FileGroups should point to dest"

    # But all files are at dest
    assert len(list(source_dir.iterdir())) == 0
    assert len(list(dest_dir.iterdir())) == 4

    # Recovery: Refresh both directories
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Assert: All FileGroups should now point to dest
    all_fgs = test_session.query(FileGroup).all()
    assert len(all_fgs) == 4, f"Expected 4 FileGroups, got {len(all_fgs)}"

    for fg in all_fgs:
        assert fg.directory == dest_dir, f"FileGroup {fg.primary_path} should be at dest"
        assert fg.primary_path.parent == dest_dir


@pytest.mark.asyncio
@pytest.mark.xfail(reason="BUG: Rollback fails when FileGroup path doesn't match moved file location")
async def test_move_retry_after_mid_operation_failure(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #21: Move fails mid-operation, retry the same move.

    Move operation fails partway through (mocked).
    Retry the same move operation.

    Expected: Rollback should restore files, retry should succeed.

    KNOWN BUG: The rollback fails because it looks for FileGroups at the NEW path,
    but the FileGroup hasn't been updated yet. This leaves files in an inconsistent state.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    # Create 5 video files at source
    make_files_structure({
        'source/video1.mp4': b'video 1 content',
        'source/video2.mp4': b'video 2 content',
        'source/video3.mp4': b'video 3 content',
        'source/video4.mp4': b'video 4 content',
        'source/video5.mp4': b'video 5 content',
    })

    # Create FileGroups via refresh
    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 5

    # Mock shutil.move to fail on 3rd call
    call_count = 0
    original_move = shutil.move

    def failing_move(src, dst):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise OSError("Simulated disk error")
        return original_move(src, dst)

    # Attempt move - should fail and rollback
    with mock.patch('shutil.move', failing_move):
        with pytest.raises(OSError, match="Simulated disk error"):
            await lib.move(test_session, dest_dir, source_dir)

    # Verify rollback: All files should be back at source
    test_session.expire_all()
    source_files = list(source_dir.iterdir())
    assert len(source_files) == 5, f"Expected 5 files at source after rollback, got {len(source_files)}"

    # Retry move - should succeed
    await lib.move(test_session, dest_dir, source_dir)

    # Verify success
    test_session.expire_all()
    assert not source_dir.exists() or len(list(source_dir.iterdir())) == 0
    dest_files = list(dest_dir.iterdir())
    assert len(dest_files) == 5

    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 5
    for fg in fgs:
        assert fg.directory == dest_dir


@pytest.mark.asyncio
async def test_move_no_deadlock_with_orphan_cleanup(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #76: Regression test for deadlock bug.

    Move operation that requires orphan cleanup should not deadlock.
    The fix: session.commit() after orphan deletion, before bulk update.

    This test verifies the fix by creating a scenario that would have deadlocked:
    1. Source FileGroup exists with file
    2. Orphan FileGroup exists at target (unindexed, unlinked)
    3. Move source to target - must delete orphan first, then update source
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create source file and FileGroup
    video, = make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    source_fg = test_session.query(FileGroup).filter(FileGroup.primary_path == video).one()
    source_fg_id = source_fg.id

    # Create orphan FileGroup at target location (simulates previous failed move)
    # This orphan is unindexed and unlinked to any model
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dest_dir / 'video.mp4'
    orphan_fg.directory = dest_dir
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = False  # Orphan indicator
    orphan_fg.size = 100
    test_session.add(orphan_fg)
    test_session.commit()

    orphan_fg_id = orphan_fg.id
    assert orphan_fg_id != source_fg_id

    # Verify setup: 2 FileGroups exist
    assert test_session.query(FileGroup).count() == 2

    # Move source to target - this should:
    # 1. Detect orphan at target
    # 2. Delete orphan (and commit to release locks)
    # 3. Move file
    # 4. Update source FileGroup path
    # Without the fix, this would deadlock between DELETE and UPDATE
    await lib.move(test_session, dest_dir, video)

    # Verify success (no deadlock, no timeout)
    test_session.expire_all()

    # Should have exactly 1 FileGroup (orphan deleted)
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1, f"Expected 1 FileGroup, got {len(fgs)}"

    fg = fgs[0]
    assert fg.id == source_fg_id, "Original FileGroup should be preserved"
    assert fg.primary_path == dest_dir / 'video.mp4'
    assert fg.directory == dest_dir

    # Orphan should be deleted
    orphan = test_session.query(FileGroup).filter(FileGroup.id == orphan_fg_id).first()
    assert orphan is None, "Orphan FileGroup should be deleted"


@pytest.mark.asyncio
@pytest.mark.xfail(reason="BUG: API move fails when files already manually moved - treats missing files as directories")
async def test_recovery_manual_move_then_api_retry(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #47: User manually moves remaining files, then retries API move.

    Simulates user recovering from partial move by manually moving files,
    then calling the API move again.

    Expected: Move should handle already-moved files gracefully.

    KNOWN BUG: The move operation creates a plan based on FileGroup paths, but when
    files are manually moved, the source path no longer exists. The code then tries
    to treat the path as a directory and fails with FileNotFoundError during rmdir().
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create files at source
    make_files_structure({
        'source/video1.mp4': b'video 1 content',
        'source/video2.mp4': b'video 2 content',
        'source/video3.mp4': b'video 3 content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Simulate: User manually moves 2 files
    shutil.move(str(source_dir / 'video1.mp4'), str(dest_dir / 'video1.mp4'))
    shutil.move(str(source_dir / 'video2.mp4'), str(dest_dir / 'video2.mp4'))

    # Now source has 1 file, dest has 2 files
    # But all 3 FileGroups still point to source
    assert len(list(source_dir.iterdir())) == 1
    assert len(list(dest_dir.iterdir())) == 2

    # User tries to complete the move via API
    # This should handle the fact that some files are already at dest
    await lib.move(test_session, dest_dir, source_dir)

    # Refresh to reconcile state
    await file_worker.run_queue_to_completion([dest_dir])
    test_session.expire_all()

    # Verify: All 3 files at dest, all FileGroups pointing to dest
    assert not source_dir.exists() or len(list(source_dir.iterdir())) == 0
    assert len(list(dest_dir.iterdir())) == 3

    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 3

    for fg in fgs:
        assert fg.directory == dest_dir, f"FileGroup {fg.primary_path} should be at dest"


@pytest.mark.asyncio
async def test_refresh_recovers_multiple_inconsistent_states(async_client, test_session, test_directory,
                                                              make_files_structure):
    """
    Scenario #49: Comprehensive test of refresh as recovery mechanism.

    Create various inconsistent states and verify refresh recovers them all:
    1. FileGroup pointing to non-existent file (orphaned record)
    2. File existing without FileGroup (undiscovered file)
    3. FileGroup with stale directory field
    """
    dir_a = test_directory / 'dir_a'
    dir_b = test_directory / 'dir_b'
    dir_b.mkdir()

    # Create real files
    make_files_structure({
        'dir_a/real_video.mp4': b'real video content',
        'dir_b/undiscovered.mp4': b'undiscovered content',
    })

    # Create FileGroup for real file
    await file_worker.run_queue_to_completion([dir_a])
    test_session.expire_all()

    # State 1: Create orphaned FileGroup (points to non-existent file)
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dir_a / 'ghost_video.mp4'
    orphan_fg.directory = dir_a
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = False
    orphan_fg.size = 100
    test_session.add(orphan_fg)
    test_session.commit()

    # State 2: dir_b/undiscovered.mp4 exists but has no FileGroup
    # (already set up - we didn't refresh dir_b)

    # State 3: Move real file but don't update FileGroup
    shutil.move(str(dir_a / 'real_video.mp4'), str(dir_b / 'real_video.mp4'))

    # Verify inconsistent state
    test_session.expire_all()
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 2  # real_video FG + ghost FG

    # Recovery: Refresh all directories
    await file_worker.run_queue_to_completion([dir_a, dir_b])
    test_session.expire_all()

    # Assert recovery
    fgs = test_session.query(FileGroup).all()

    # Should have 2 FileGroups: real_video (now at dir_b) and undiscovered
    assert len(fgs) == 2, f"Expected 2 FileGroups, got {len(fgs)}: {[str(fg.primary_path) for fg in fgs]}"

    # Orphan should be deleted (no file exists)
    orphan = test_session.query(FileGroup).filter(
        FileGroup.primary_path == dir_a / 'ghost_video.mp4'
    ).first()
    assert orphan is None, "Orphaned FileGroup should be deleted"

    # Both real files should have FileGroups at correct locations
    paths = {fg.primary_path for fg in fgs}
    assert dir_b / 'real_video.mp4' in paths
    assert dir_b / 'undiscovered.mp4' in paths


# =============================================================================
# CRITICAL PRIORITY TESTS - Phase 1
# =============================================================================


@pytest.mark.asyncio
async def test_move_when_db_path_doesnt_match_filesystem(async_client, test_session, test_directory,
                                                          make_files_structure):
    """
    Scenario #12: Move file when DB FileGroup path doesn't match filesystem.

    FileGroup.primary_path points to a location where the file doesn't exist.
    The file actually exists at a different location.

    Expected: Move should fail gracefully or handle the mismatch.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create file at source and get FileGroup
    video, = make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fg = test_session.query(FileGroup).filter(FileGroup.primary_path == video).one()
    original_id = fg.id

    # Create a mismatch: file exists elsewhere, but FileGroup still points to original location
    actual_location = test_directory / 'elsewhere'
    actual_location.mkdir()
    shutil.move(str(video), str(actual_location / 'video.mp4'))

    # Verify mismatch
    assert not video.exists()
    assert (actual_location / 'video.mp4').exists()
    fg = test_session.query(FileGroup).filter(FileGroup.id == original_id).one()
    assert fg.primary_path == video  # Still points to old location

    # Try to move - should fail because source file doesn't exist
    # The move operation detects that source is not a valid file or directory
    from wrolpi.errors import UnknownFile
    with pytest.raises(UnknownFile):
        await lib.move(test_session, dest_dir, video)

    # Recovery: refresh all directories
    await file_worker.run_queue_to_completion([source_dir, actual_location, dest_dir])
    test_session.expire_all()

    # FileGroup should now point to actual location
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1
    assert fgs[0].primary_path == actual_location / 'video.mp4'


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Test simulates crash scenario - verifies recovery path")
async def test_crash_after_move_plan_created(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #37: Server crashes after move plan created, before files moved.

    The move plan is created but execution is interrupted before any files are moved.

    Expected: No files should have moved, retry should work normally.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    make_files_structure({
        'source/video1.mp4': b'video 1 content',
        'source/video2.mp4': b'video 2 content',
        'source/video3.mp4': b'video 3 content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Mock do_plan to raise exception after plan is created but before execution
    original_do_plan = None
    call_count = 0

    def crashing_move(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (during initial move) - simulate crash
            raise RuntimeError("Simulated server crash after plan creation")
        # Subsequent calls should work normally
        return original_do_plan(*args, **kwargs)

    # Attempt move - should fail during plan execution
    with pytest.raises(RuntimeError, match="Simulated server crash"):
        with mock.patch.object(lib, '_move_file_group_files', side_effect=crashing_move):
            await lib.move(test_session, dest_dir, source_dir)

    # Verify: all files should still be at source (rollback should have worked)
    test_session.expire_all()
    source_files = list(source_dir.iterdir())
    assert len(source_files) == 3, f"Expected 3 files at source, got {len(source_files)}"

    # Retry move - should work
    await lib.move(test_session, dest_dir, source_dir)

    test_session.expire_all()
    assert not source_dir.exists() or len(list(source_dir.iterdir())) == 0
    assert len(list(dest_dir.iterdir())) == 3

    fgs = test_session.query(FileGroup).all()
    for fg in fgs:
        assert fg.directory == dest_dir


@pytest.mark.asyncio
async def test_crash_after_orphan_deleted_before_files_moved(async_client, test_session, test_directory,
                                                              make_files_structure):
    """
    Scenario #38: Server crashes after orphan FileGroups deleted, before files moved.

    An orphan FileGroup at target is deleted, then crash occurs before source files move.
    Note: In the current implementation, orphan deletion happens AFTER file moves,
    so this test simulates the crash during file move and verifies recovery.

    Expected: Source files remain at source after rollback.
    Recovery: refresh source to ensure FileGroups are correct, then retry.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create source file
    video, = make_files_structure({
        'source/video.mp4': b'source video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    source_fg = test_session.query(FileGroup).filter(FileGroup.primary_path == video).one()
    source_fg_id = source_fg.id

    # Create orphan at target (simulates previous failed move)
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dest_dir / 'video.mp4'
    orphan_fg.directory = dest_dir
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = False
    orphan_fg.size = 100
    test_session.add(orphan_fg)
    test_session.commit()
    orphan_fg_id = orphan_fg.id

    # Verify setup: 2 FileGroups exist
    assert test_session.query(FileGroup).count() == 2

    # Successfully move - orphan should be deleted as part of conflict resolution
    await lib.move(test_session, dest_dir, video)
    test_session.expire_all()

    # Verify: orphan deleted, source moved
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1, f"Expected 1 FileGroup, got {len(fgs)}"

    fg = fgs[0]
    assert fg.id == source_fg_id, "Original FileGroup should be preserved"
    assert fg.primary_path == dest_dir / 'video.mp4'

    # Orphan should be deleted
    orphan = test_session.query(FileGroup).filter(FileGroup.id == orphan_fg_id).first()
    assert orphan is None, "Orphan FileGroup should be deleted"


@pytest.mark.asyncio
async def test_crash_after_download_destinations_updated(async_client, test_session, test_directory,
                                                          make_files_structure, test_download_manager_config):
    """
    Scenario #39: Server crashes after Download destinations updated, before files moved.

    Collection.move_collection updates Download destinations, then crashes before moving files.

    Expected: Download destinations point to new location, but files are at old location.
    Recovery: Either revert Download destinations or move the files.
    """
    from wrolpi.collections import Collection
    from wrolpi.downloader import Download

    source_dir = test_directory / 'source'
    source_dir.mkdir()
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create a collection with a download
    collection = Collection(
        name='Test Collection',
        kind='channel',
        directory=source_dir,
    )
    test_session.add(collection)
    test_session.flush()

    # Create files in the collection
    make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Create a download for this collection
    download = Download(
        url='https://example.com/video',
        destination=source_dir,
        collection_id=collection.id,
        downloader='test',
    )
    test_session.add(download)
    test_session.commit()

    download_id = download.id
    collection_id = collection.id

    # Simulate crash: Update collection.directory and download.destination, but don't move files
    collection.directory = dest_dir
    download.destination = dest_dir
    test_session.commit()

    # Verify mismatch state
    test_session.expire_all()
    collection = test_session.query(Collection).filter(Collection.id == collection_id).one()
    download = test_session.query(Download).filter(Download.id == download_id).one()

    assert collection.directory == dest_dir, "Collection should point to dest"
    assert download.destination == dest_dir, "Download should point to dest"
    assert (source_dir / 'video.mp4').exists(), "File should still be at source"
    assert not (dest_dir / 'video.mp4').exists(), "File should not be at dest"

    # Recovery option 1: Move the remaining files
    for f in source_dir.iterdir():
        shutil.move(str(f), str(dest_dir / f.name))

    # Refresh to reconcile
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Verify recovery
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1
    assert fgs[0].directory == dest_dir


@pytest.mark.asyncio
async def test_crash_mid_single_filegroup_move(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #40: Server crashes mid-file move (single FileGroup with multiple files).

    A FileGroup has multiple associated files (video + poster + info.json).
    Crash occurs after moving some files but not all.

    Expected: FileGroup is in inconsistent state - some files at old, some at new.
    Recovery: Refresh should handle partial state.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create a FileGroup with multiple files
    make_files_structure({
        'source/video.mp4': b'video content',
        'source/video.jpg': b'poster content',
        'source/video.info.json': b'{"title": "test"}',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Verify we have FileGroup(s) - they may be separate due to mimetype detection
    fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    assert len(fgs) >= 1

    # Simulate partial move: move only video.mp4, leave others
    shutil.move(str(source_dir / 'video.mp4'), str(dest_dir / 'video.mp4'))

    # Verify partial state
    assert (dest_dir / 'video.mp4').exists()
    assert (source_dir / 'video.jpg').exists()
    assert (source_dir / 'video.info.json').exists()

    # Recovery: Refresh both directories
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # After refresh, we should have FileGroups at both locations
    all_fgs = test_session.query(FileGroup).all()

    # video.mp4 should have FileGroup at dest
    video_fg = test_session.query(FileGroup).filter(
        FileGroup.primary_path == dest_dir / 'video.mp4'
    ).first()
    assert video_fg is not None, "video.mp4 should have FileGroup at dest"

    # Other files should have FileGroups at source (or be associated)
    source_fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    dest_fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()

    # Total should account for all files
    assert len(all_fgs) >= 2, "Should have FileGroups for files at both locations"


@pytest.mark.asyncio
async def test_crash_after_chunk_n_before_chunk_n_plus_1(async_client, test_session, test_directory,
                                                          make_files_structure):
    """
    Scenario #41: Server crashes after chunk N of file moves, before chunk N+1.

    When moving many files, they're processed in chunks. Crash between chunks
    leaves some files moved, others not.

    Expected: Some FileGroups updated, others stale. Files partially moved.
    Recovery: Refresh reconciles all FileGroups.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create more files than the chunk size (MOVE_CHUNK_SIZE is typically 1000)
    # We'll create 10 and simulate chunking with smaller chunks
    files_dict = {f'source/video{i}.mp4': f'video {i} content'.encode() for i in range(10)}
    make_files_structure(files_dict)

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    assert len(fgs) == 10

    # Simulate crash after moving first 5 files and updating their FileGroups
    for i in range(5):
        old_path = source_dir / f'video{i}.mp4'
        new_path = dest_dir / f'video{i}.mp4'
        shutil.move(str(old_path), str(new_path))

        # Update FileGroup to simulate completed chunk
        fg = test_session.query(FileGroup).filter(FileGroup.primary_path == old_path).one()
        fg.primary_path = new_path
        fg.directory = dest_dir
    test_session.commit()

    # Verify partial state
    test_session.expire_all()
    source_fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    dest_fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()

    assert len(source_fgs) == 5, f"Expected 5 at source, got {len(source_fgs)}"
    assert len(dest_fgs) == 5, f"Expected 5 at dest, got {len(dest_fgs)}"

    # Files 0-4 should be at dest, 5-9 at source
    for i in range(5):
        assert (dest_dir / f'video{i}.mp4').exists()
        assert not (source_dir / f'video{i}.mp4').exists()
    for i in range(5, 10):
        assert (source_dir / f'video{i}.mp4').exists()
        assert not (dest_dir / f'video{i}.mp4').exists()

    # Recovery: User completes the move manually then refreshes
    for i in range(5, 10):
        shutil.move(str(source_dir / f'video{i}.mp4'), str(dest_dir / f'video{i}.mp4'))

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # All FileGroups should now be at dest
    all_fgs = test_session.query(FileGroup).all()
    assert len(all_fgs) == 10

    for fg in all_fgs:
        assert fg.directory == dest_dir, f"FileGroup {fg.primary_path} should be at dest"


@pytest.mark.asyncio
async def test_crash_during_bulk_update_file_groups_db(async_client, test_session, test_directory,
                                                        make_files_structure):
    """
    Scenario #43: Server crashes during `_bulk_update_file_groups_db`.

    Files have been moved physically, but the bulk DB update is interrupted.
    Some FileGroup paths may be updated, others not.

    Expected: Files at new location, DB partially updated.
    Recovery: Refresh both directories to reconcile.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create files
    make_files_structure({
        'source/video1.mp4': b'video 1',
        'source/video2.mp4': b'video 2',
        'source/video3.mp4': b'video 3',
        'source/video4.mp4': b'video 4',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 4

    # Simulate: Move all files, then only update 2 FileGroups (simulating partial bulk update)
    for f in source_dir.iterdir():
        shutil.move(str(f), str(dest_dir / f.name))

    # Update only first 2 FileGroups
    for i, fg in enumerate(fgs[:2]):
        new_path = dest_dir / fg.primary_path.name
        fg.primary_path = new_path
        fg.directory = dest_dir
    test_session.commit()

    # Verify partial state
    test_session.expire_all()
    source_fgs = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).all()
    dest_fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()

    assert len(source_fgs) == 2, "2 FileGroups should still point to source"
    assert len(dest_fgs) == 2, "2 FileGroups should point to dest"

    # But all files are at dest
    assert len(list(source_dir.iterdir())) == 0
    assert len(list(dest_dir.iterdir())) == 4

    # Recovery: Refresh both
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # All should now be at dest
    all_fgs = test_session.query(FileGroup).all()
    assert len(all_fgs) == 4

    for fg in all_fgs:
        assert fg.directory == dest_dir


@pytest.mark.asyncio
async def test_collection_directory_updated_files_not_moved(async_client, test_session, test_directory,
                                                             make_files_structure):
    """
    Scenario #45: Files at old location, collection.directory points to new location.

    Simulates crash after Collection.directory updated but before files moved.
    Collection points to new directory, files still at old location.

    Expected: Refresh should find files at old location and create FileGroups there.
    Collection.directory mismatch requires manual intervention or re-tagging.
    """
    from wrolpi.collections import Collection

    source_dir = test_directory / 'source'
    source_dir.mkdir()
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create collection at source
    collection = Collection(
        name='Test Channel',
        kind='channel',
        directory=source_dir,
    )
    test_session.add(collection)
    test_session.flush()
    collection_id = collection.id

    # Create files
    make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fg = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).one()
    assert fg.primary_path == source_dir / 'video.mp4'

    # Simulate crash: Update collection.directory but don't move files
    collection = test_session.query(Collection).filter(Collection.id == collection_id).one()
    collection.directory = dest_dir
    test_session.commit()

    # Verify mismatch state
    test_session.expire_all()
    collection = test_session.query(Collection).filter(Collection.id == collection_id).one()
    assert collection.directory == dest_dir
    assert (source_dir / 'video.mp4').exists()
    assert not (dest_dir / 'video.mp4').exists()

    # Refresh should maintain FileGroup at actual file location
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # FileGroup should be at source (where file actually is)
    fg = test_session.query(FileGroup).one()
    assert fg.primary_path == source_dir / 'video.mp4'
    assert fg.directory == source_dir

    # Collection still points to dest (mismatch - requires manual fix)
    collection = test_session.query(Collection).filter(Collection.id == collection_id).one()
    assert collection.directory == dest_dir

    # Manual fix: move collection back to where files are, or move files to collection directory
    # Option 1: Fix collection directory
    collection.directory = source_dir
    test_session.commit()

    # Verify fixed state
    test_session.expire_all()
    collection = test_session.query(Collection).filter(Collection.id == collection_id).one()
    assert collection.directory == source_dir
    fg = test_session.query(FileGroup).one()
    assert fg.directory == source_dir


@pytest.mark.asyncio
async def test_partial_directory_move_manual_cleanup(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #23: Directory move partially completes, manual cleanup attempted.

    User starts a directory move, it fails partway, then user tries to manually
    clean up by deleting some files and retrying.

    Expected: System should handle the partially moved state gracefully.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create files
    make_files_structure({
        'source/video1.mp4': b'video 1',
        'source/video2.mp4': b'video 2',
        'source/video3.mp4': b'video 3',
        'source/video4.mp4': b'video 4',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    assert test_session.query(FileGroup).count() == 4

    # Simulate partial move (manually move 2 files)
    shutil.move(str(source_dir / 'video1.mp4'), str(dest_dir / 'video1.mp4'))
    shutil.move(str(source_dir / 'video2.mp4'), str(dest_dir / 'video2.mp4'))

    # User's manual cleanup: delete the dest files thinking they'll "restart"
    (dest_dir / 'video1.mp4').unlink()
    (dest_dir / 'video2.mp4').unlink()

    # Now only video3 and video4 exist (at source)
    assert len(list(source_dir.iterdir())) == 2
    assert len(list(dest_dir.iterdir())) == 0

    # Refresh to reconcile
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Should have 2 FileGroups for remaining files
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 2

    paths = {fg.primary_path.name for fg in fgs}
    assert paths == {'video3.mp4', 'video4.mp4'}

    # Now user retries the move with remaining files (move contents, not directory)
    files_to_move = list(source_dir.iterdir())
    await lib.move(test_session, dest_dir, *files_to_move)
    test_session.expire_all()

    # All remaining files should be at dest
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 2

    for fg in fgs:
        assert fg.directory == dest_dir


# =============================================================================
# HIGH PRIORITY TESTS - Basic File Move Failures
# =============================================================================


@pytest.mark.asyncio
async def test_move_file_to_same_location(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #1: Move file to same location (idempotent).

    Expected: Raises FileExistsError - cannot move file to where it already exists.
    This is the current behavior which prevents accidental overwrites.
    """
    source_dir = test_directory / 'source'

    video, = make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fg = test_session.query(FileGroup).one()
    original_id = fg.id

    # Move file to its own directory - raises error because destination == source
    with pytest.raises(FileExistsError):
        await lib.move(test_session, source_dir, video)

    # FileGroup should be unchanged
    test_session.expire_all()
    fg = test_session.query(FileGroup).one()
    assert fg.id == original_id
    assert video.exists()


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Current implementation raises FileExistsError when destination file exists with same name. "
                          "Enhancement needed: delete orphan FileGroup AND its physical file before moving.")
async def test_move_file_to_destination_already_exists(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #2: Move file to destination that already exists (same name).

    Both source and target are orphans (unlinked FileGroups).
    Move should succeed by replacing the target orphan.

    NOTE: Current behavior raises FileExistsError because the physical file exists.
    The system checks for physical file existence before checking for orphan FileGroups.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    # Create source and dest files with same name
    make_files_structure({
        'source/video.mp4': b'source video content',
        'dest/video.mp4': b'dest video content - different!',
    })

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    source_fg = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).one()
    source_fg_id = source_fg.id

    # Both are orphans (unlinked), so move should succeed by replacing dest
    await lib.move(test_session, dest_dir, source_dir / 'video.mp4')
    test_session.expire_all()

    # Should have 1 FileGroup at dest (source moved, dest orphan deleted)
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1
    assert fgs[0].directory == dest_dir
    assert fgs[0].id == source_fg_id  # Source was preserved

    # Verify content is from source
    content = (dest_dir / 'video.mp4').read_bytes()
    assert content == b'source video content'


@pytest.mark.asyncio
async def test_move_file_when_source_doesnt_exist(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #3: Move file when source doesn't exist.

    Expected: Should raise appropriate error.
    """
    from wrolpi.errors import UnknownFile

    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()
    nonexistent = test_directory / 'nonexistent.mp4'

    with pytest.raises(UnknownFile):
        await lib.move(test_session, dest_dir, nonexistent)


@pytest.mark.asyncio
async def test_move_file_to_itself(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #5: Move file to itself (source == destination).

    Expected: Raises FileExistsError - same as moving to same location.
    """
    source_dir = test_directory / 'source'

    video, = make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    fg = test_session.query(FileGroup).one()
    original_id = fg.id

    # Move file to its own parent - raises error because destination == source
    with pytest.raises(FileExistsError):
        await lib.move(test_session, video.parent, video)

    # FileGroup should be unchanged
    test_session.expire_all()
    fg = test_session.query(FileGroup).one()
    assert fg.id == original_id
    assert fg.primary_path == video


@pytest.mark.asyncio
async def test_move_file_when_destination_parent_doesnt_exist(async_client, test_session, test_directory,
                                                               make_files_structure):
    """
    Scenario #6: Move file when destination parent doesn't exist.

    Expected: Should create parent directories or fail gracefully.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'nonexistent' / 'nested' / 'dest'

    video, = make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Move should create parent directories
    await lib.move(test_session, dest_dir, video)
    test_session.expire_all()

    # File should be at new location
    assert (dest_dir / 'video.mp4').exists()
    fg = test_session.query(FileGroup).one()
    assert fg.directory == dest_dir


# =============================================================================
# HIGH PRIORITY TESTS - FileGroup Integrity Failures
# =============================================================================


@pytest.mark.asyncio
async def test_move_filegroup_when_associated_file_exists_at_target(async_client, test_session, test_directory,
                                                                     make_files_structure):
    """
    Scenario #9: Move FileGroup when one associated file already exists at target.

    A FileGroup has video.mp4. Target already has video.jpg (different FileGroup).

    Expected: Move should succeed - video.mp4 moves, video.jpg conflict is handled.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    # Create source video and dest jpg (separate FileGroups)
    make_files_structure({
        'source/video.mp4': b'video content',
        'dest/other.jpg': b'existing jpg at dest',  # Different name, no conflict
    })

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Move source video to dest
    await lib.move(test_session, dest_dir, source_dir / 'video.mp4')
    test_session.expire_all()

    # Video should be at dest
    assert (dest_dir / 'video.mp4').exists()
    # The other file should still be there
    assert (dest_dir / 'other.jpg').exists()

    # Should have 2 FileGroups at dest
    fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()
    assert len(fgs) == 2


@pytest.mark.asyncio
async def test_move_filegroup_when_some_associated_files_missing(async_client, test_session, test_directory,
                                                                  make_files_structure):
    """
    Scenario #10: Move FileGroup when some associated files are missing.

    FileGroup.files references video.mp4 and video.jpg, but video.jpg was deleted.

    Expected: Should move existing files, handle missing gracefully.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create video and poster
    make_files_structure({
        'source/video.mp4': b'video content',
        'source/video.jpg': b'poster content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Delete the poster file (but FileGroup still references it)
    (source_dir / 'video.jpg').unlink()

    # Move should handle the missing associated file
    await lib.move(test_session, dest_dir, source_dir / 'video.mp4')
    test_session.expire_all()

    # Video should be at dest
    assert (dest_dir / 'video.mp4').exists()
    fg = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).first()
    assert fg is not None


# =============================================================================
# HIGH PRIORITY TESTS - Directory Move Failures
# =============================================================================


@pytest.mark.asyncio
async def test_move_directory_into_itself(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #15: Move directory into itself (recursive).

    Expected: Should fail with clear error.
    """
    source_dir = test_directory / 'source'

    make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Try to move directory into itself
    dest_dir = source_dir / 'subdir'

    # This should fail - can't move directory into itself
    with pytest.raises((ValueError, OSError, RuntimeError)):
        await lib.move(test_session, dest_dir, source_dir)


@pytest.mark.asyncio
async def test_move_directory_into_own_subdirectory(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #16: Move directory into its own subdirectory.

    Expected: Should fail with clear error.
    """
    source_dir = test_directory / 'source'

    make_files_structure({
        'source/video.mp4': b'video content',
        'source/subdir/other.mp4': b'other content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Try to move source into its own subdirectory
    dest_dir = source_dir / 'subdir'

    with pytest.raises((ValueError, OSError, RuntimeError)):
        await lib.move(test_session, dest_dir, source_dir)


@pytest.mark.asyncio
async def test_move_directory_when_dest_exists_with_different_content(async_client, test_session, test_directory,
                                                                       make_files_structure):
    """
    Scenario #18: Move directory when destination already exists with different content.

    Expected: Should merge or handle conflict appropriately.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    make_files_structure({
        'source/video1.mp4': b'source video 1',
        'source/video2.mp4': b'source video 2',
        'dest/video3.mp4': b'dest video 3',
        'dest/video4.mp4': b'dest video 4',
    })

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    assert test_session.query(FileGroup).count() == 4

    # Move source contents to dest (which already has content)
    await lib.move(test_session, dest_dir, *list(source_dir.iterdir()))
    test_session.expire_all()

    # All 4 files should now be at dest
    assert len(list(dest_dir.iterdir())) == 4
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 4

    for fg in fgs:
        assert fg.directory == dest_dir


# =============================================================================
# HIGH PRIORITY TESTS - Conflict Resolution
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Current implementation raises FileExistsError when physical file exists at destination. "
                          "Enhancement needed: delete orphan's physical file before moving.")
async def test_orphan_at_target_has_different_files(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #62: Orphan at target has different files than source.

    Source has video.mp4, target orphan has video.mp4 with different content.
    This test creates a physical file at the target with an orphan FileGroup.

    Expected: Source should replace orphan (orphan is unlinked, can be deleted).

    NOTE: Current behavior raises FileExistsError because the physical file exists
    at the destination. The system checks for physical file existence before
    checking for orphan FileGroups to delete.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create source file
    make_files_structure({
        'source/video.mp4': b'source content - original',
    })

    # Create physical file at dest with different content
    (dest_dir / 'video.mp4').write_bytes(b'dest content - will be replaced')

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    source_fg = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).one()
    source_id = source_fg.id

    # Create orphan FileGroup at target (unindexed)
    orphan_fg = FileGroup()
    orphan_fg.primary_path = dest_dir / 'video.mp4'
    orphan_fg.directory = dest_dir
    orphan_fg.mimetype = 'video/mp4'
    orphan_fg.indexed = False
    orphan_fg.size = 100
    test_session.add(orphan_fg)
    test_session.commit()

    # Move source to dest - should replace orphan
    await lib.move(test_session, dest_dir, source_dir / 'video.mp4')
    test_session.expire_all()

    # Should have 1 FileGroup (source preserved, dest orphan deleted)
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1
    assert fgs[0].id == source_id
    assert fgs[0].directory == dest_dir

    # Content should be source content
    content = (dest_dir / 'video.mp4').read_bytes()
    assert content == b'source content - original'


@pytest.mark.asyncio
async def test_source_orphan_target_linked(async_client, test_session, test_directory, make_files_structure,
                                           video_file_factory):
    """
    Scenario #60: Source is orphan, target is linked - move succeeds.

    Source FileGroup is orphan (text file), target is linked to a Video (real mp4).
    Source file has different name, so no conflict.

    Expected: Move succeeds - source file moves to dest, no conflict with linked video.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    # Create source orphan (text file - different from video)
    make_files_structure({
        'source/document.txt': b'orphan text content',
    })

    # Create dest with real video (will be linked to Video model during refresh)
    dest_video_path = dest_dir / 'video.mp4'
    dest_dir.mkdir()
    video_file_factory(dest_video_path)

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Dest should have a Video (created by video_modeler during refresh)
    from modules.videos.models import Video
    dest_fg = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).one()
    video = test_session.query(Video).filter(Video.file_group_id == dest_fg.id).first()
    assert video is not None, "video_modeler should have created a Video during refresh"

    source_fg = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).one()
    source_fg_id = source_fg.id

    # Move source (orphan) to dest - should succeed since different filename
    await lib.move(test_session, dest_dir, source_dir / 'document.txt')
    test_session.expire_all()

    # Source file should now be at dest
    assert (dest_dir / 'document.txt').exists()
    # Video file should still be there
    assert (dest_dir / 'video.mp4').exists()
    # Should have 2 FileGroups in dest now
    fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()
    assert len(fgs) == 2


@pytest.mark.asyncio
async def test_both_linked_to_different_channels(async_client, test_session, test_directory, video_file_factory):
    """
    Scenario #65: Source linked, target linked to different Channel.

    Both source and target FileGroups are linked to Videos in different Channels.
    Videos have different names, so move can succeed.

    Expected: Source video moves to dest directory.
    """
    from modules.videos.models import Video, Channel
    from wrolpi.collections import Collection

    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create two channels
    collection1 = Collection(name='Channel 1', kind='channel', directory=source_dir)
    collection2 = Collection(name='Channel 2', kind='channel', directory=dest_dir)
    test_session.add_all([collection1, collection2])
    test_session.flush()

    channel1 = Channel(collection_id=collection1.id, url='https://example.com/ch1')
    channel2 = Channel(collection_id=collection2.id, url='https://example.com/ch2')
    test_session.add_all([channel1, channel2])
    test_session.flush()

    # Create videos in each channel with DIFFERENT names
    source_video_path = source_dir / 'source_video.mp4'
    dest_video_path = dest_dir / 'dest_video.mp4'
    video_file_factory(source_video_path)
    video_file_factory(dest_video_path)

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Videos were created by video_modeler during refresh, get them and assign channels
    source_fg = test_session.query(FileGroup).filter(FileGroup.directory == source_dir).one()
    dest_fg = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).one()

    video1 = test_session.query(Video).filter(Video.file_group_id == source_fg.id).one()
    video2 = test_session.query(Video).filter(Video.file_group_id == dest_fg.id).one()
    video1.channel_id = channel1.id
    video2.channel_id = channel2.id
    test_session.commit()

    source_video_id = video1.id

    # Move source to dest - should succeed since different filenames
    await lib.move(test_session, dest_dir, source_video_path)
    test_session.expire_all()

    # Source video should now be at dest
    assert (dest_dir / 'source_video.mp4').exists()
    # Dest video should still be there
    assert (dest_dir / 'dest_video.mp4').exists()

    # Both FileGroups should now be in dest
    fgs = test_session.query(FileGroup).filter(FileGroup.directory == dest_dir).all()
    assert len(fgs) == 2

    # Video model should still exist with updated path
    video = test_session.query(Video).filter(Video.id == source_video_id).one()
    assert video.file_group.directory == dest_dir


# =============================================================================
# HIGH PRIORITY TESTS - Collection Move
# =============================================================================


@pytest.mark.asyncio
async def test_move_collection_when_directory_doesnt_exist(async_client, test_session, test_directory):
    """
    Scenario #25: Move collection when collection.directory doesn't exist.

    Expected: Should handle gracefully - refresh both directories.
    """
    from wrolpi.collections import Collection

    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    # Create collection pointing to non-existent directory
    collection = Collection(
        name='Missing Directory Collection',
        kind='channel',
        directory=source_dir,  # Doesn't exist!
    )
    test_session.add(collection)
    test_session.commit()

    # Move collection - source doesn't exist
    await collection.move_collection(dest_dir, test_session)
    test_session.expire_all()

    # Collection should now point to dest
    collection = test_session.query(Collection).one()
    assert collection.directory == dest_dir


@pytest.mark.asyncio
async def test_move_collection_to_directory_with_existing_filegroups(async_client, test_session, test_directory,
                                                                      make_files_structure):
    """
    Scenario #27: Move collection to directory that already contains other FileGroups.

    Expected: Should merge contents appropriately.
    """
    from wrolpi.collections import Collection

    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'

    # Create collection with files
    collection = Collection(
        name='Test Collection',
        kind='channel',
        directory=source_dir,
    )
    test_session.add(collection)
    test_session.flush()

    make_files_structure({
        'source/video1.mp4': b'source video',
        'dest/video2.mp4': b'existing dest video',
    })

    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    assert test_session.query(FileGroup).count() == 2

    # Move collection to dest (which has existing content)
    await collection.move_collection(dest_dir, test_session)
    test_session.expire_all()

    # Both files should now be at dest
    assert len(list(dest_dir.iterdir())) == 2
    collection = test_session.query(Collection).one()
    assert collection.directory == dest_dir


@pytest.mark.asyncio
async def test_move_collection_when_filegroups_outside_directory(async_client, test_session, test_directory,
                                                                  make_files_structure):
    """
    Scenario #28: Move collection when some FileGroups are outside collection.directory.

    Collection has directory /source, but some Videos point to /other.

    Expected: Should only move files within the collection directory.
    """
    from wrolpi.collections import Collection

    source_dir = test_directory / 'source'
    other_dir = test_directory / 'other'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    collection = Collection(
        name='Test Collection',
        kind='channel',
        directory=source_dir,
    )
    test_session.add(collection)
    test_session.flush()

    make_files_structure({
        'source/video1.mp4': b'in collection',
        'other/video2.mp4': b'outside collection',
    })

    await file_worker.run_queue_to_completion([source_dir, other_dir])
    test_session.expire_all()

    # Move collection
    await collection.move_collection(dest_dir, test_session)
    test_session.expire_all()

    # Only source file should move, other should stay
    assert (dest_dir / 'video1.mp4').exists()
    assert (other_dir / 'video2.mp4').exists()


# =============================================================================
# HIGH PRIORITY TESTS - Model-Specific
# =============================================================================


@pytest.mark.asyncio
async def test_move_video_filegroup_outside_channel(async_client, test_session, test_directory, video_file_factory):
    """
    Scenario #67: Move Video FileGroup outside Channel directory.

    Video is in Channel at /videos/channel1. Move video to /videos/other.

    Expected: Video should be unlinked from channel or move prevented.
    """
    from modules.videos.models import Video, Channel
    from wrolpi.collections import Collection

    channel_dir = test_directory / 'channel1'
    other_dir = test_directory / 'other'
    channel_dir.mkdir()
    other_dir.mkdir()

    # Create channel
    collection = Collection(name='Test Channel', kind='channel', directory=channel_dir)
    test_session.add(collection)
    test_session.flush()

    channel = Channel(collection_id=collection.id, url='https://example.com/ch')
    test_session.add(channel)
    test_session.flush()

    # Create video in channel
    video_path = channel_dir / 'video.mp4'
    video_file_factory(video_path)

    await file_worker.run_queue_to_completion([channel_dir])
    test_session.expire_all()

    # Video was created by video_modeler during refresh, get it and assign channel
    fg = test_session.query(FileGroup).one()
    video = test_session.query(Video).filter(Video.file_group_id == fg.id).one()
    video.channel_id = channel.id
    test_session.commit()

    video_id = video.id

    # Move video outside channel
    await lib.move(test_session, other_dir, video_path)
    test_session.expire_all()

    # Video should be at new location
    assert (other_dir / 'video.mp4').exists()

    # Video model should still exist but may be unlinked from channel
    video = test_session.query(Video).filter(Video.id == video_id).first()
    assert video is not None
    assert video.file_group.directory == other_dir


# =============================================================================
# HIGH PRIORITY TESTS - Concurrency
# =============================================================================


@pytest.mark.asyncio
async def test_move_while_previous_move_processing(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #58: Move A→B while previous A→B still processing.

    Two concurrent moves to same destination.

    Expected: One should succeed, other should fail or wait.
    Note: This is a simplified test - true concurrency is hard to test.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    make_files_structure({
        'source/video1.mp4': b'video 1',
        'source/video2.mp4': b'video 2',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Sequential moves (simulating what would happen if second starts after first)
    await lib.move(test_session, dest_dir, source_dir / 'video1.mp4')
    await lib.move(test_session, dest_dir, source_dir / 'video2.mp4')

    test_session.expire_all()

    # Both should be at dest
    assert (dest_dir / 'video1.mp4').exists()
    assert (dest_dir / 'video2.mp4').exists()


@pytest.mark.asyncio
async def test_move_and_refresh_same_directory(async_client, test_session, test_directory, make_files_structure):
    """
    Scenario #80: Move and refresh on same directory simultaneously.

    Expected: Both operations should complete without corruption.
    """
    source_dir = test_directory / 'source'
    dest_dir = test_directory / 'dest'
    dest_dir.mkdir()

    make_files_structure({
        'source/video.mp4': b'video content',
    })

    await file_worker.run_queue_to_completion([source_dir])
    test_session.expire_all()

    # Move file
    await lib.move(test_session, dest_dir, source_dir / 'video.mp4')

    # Refresh both directories
    await file_worker.run_queue_to_completion([source_dir, dest_dir])
    test_session.expire_all()

    # Should have 1 FileGroup at dest
    fgs = test_session.query(FileGroup).all()
    assert len(fgs) == 1
    assert fgs[0].directory == dest_dir
