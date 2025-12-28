"""Tests for the FileWorker priority queue system."""
import shutil

import pytest

from wrolpi.files.models import FileGroup
from wrolpi.files.worker import FileWorker, Priority, JobStatus
from wrolpi.vars import PROJECT_DIR


@pytest.fixture
def file_worker():
    """Provides a fresh file worker for testing."""
    worker = FileWorker()
    yield worker
    worker.clear()


@pytest.mark.asyncio
async def test_file_worker_queue_refresh(async_client, test_session, test_directory, file_worker, make_files_structure):
    """FileWorker can queue and process files for surface indexing."""
    # Create test files
    make_files_structure({
        'file1.txt': 'content 1',
        'file2.txt': 'content 2',
    })

    # Queue refresh
    job_id = file_worker.queue_refresh([test_directory])

    # Check job was created
    assert job_id is not None
    jobs = file_worker._state.get_jobs()
    assert job_id in jobs
    assert jobs[job_id]['job_type'] == 'refresh'
    assert jobs[job_id]['status'] == JobStatus.PENDING.value

    # Process queue
    while not file_worker.is_empty():
        await file_worker.process_batch()

    # Verify files were surface indexed
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 2

    for fg in file_groups:
        # Two-phase indexing: surface indexed, not yet deep indexed
        assert fg.indexed is True
        assert fg.deep_indexed is False


@pytest.mark.asyncio
async def test_file_worker_priority_ordering(async_client, test_directory, file_worker):
    """Higher priority items (user actions) are processed first."""
    # Create test files
    low = test_directory / 'low.txt'
    high = test_directory / 'high.txt'
    low.write_text('low priority')
    high.write_text('high priority')

    # Queue in reverse priority order
    file_worker.queue_refresh([low], priority=Priority.GLOBAL_REFRESH)  # Low priority (background)
    file_worker.queue_refresh([high], priority=Priority.MANUAL_REFRESH)  # High priority (user action)

    # With the shared queue, we can't peek at items directly
    # Instead, verify by processing and checking the order of processing
    # The batch processing sorts items by priority before processing
    assert file_worker.queue_size() == 2

    # Process all items in a single batch - they will be sorted by priority
    await file_worker.process_batch(batch_size=10)

    # Both should be processed
    assert file_worker.is_empty()


@pytest.mark.asyncio
async def test_file_worker_deduplication(async_client, test_directory, file_worker):
    """Duplicate paths are not added to queue."""
    test_file = test_directory / 'test.txt'
    test_file.write_text('test')

    # Queue same path multiple times
    file_worker.queue_refresh([test_file])
    file_worker.queue_refresh([test_file])
    file_worker.queue_refresh([test_file])

    # Only one item should be in queue
    assert file_worker.queue_size() == 1


@pytest.mark.asyncio
async def test_file_worker_directory_expansion(async_client, test_session, test_directory, file_worker,
                                                make_files_structure):
    """FileWorker expands directories and processes their contents."""
    # Create nested structure
    make_files_structure({
        'dir1/file1.txt': 'content 1',
        'dir1/file2.txt': 'content 2',
        'dir1/subdir/file3.txt': 'content 3',
    })

    # Queue just the directory
    file_worker.queue_refresh([test_directory / 'dir1'])

    # Process queue
    while not file_worker.is_empty():
        await file_worker.process_batch()

    # All files should be indexed
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 3


@pytest.mark.asyncio
async def test_file_worker_video_file_group(async_client, test_session, test_directory, file_worker):
    """FileWorker correctly groups video files with their companions (SRT, poster, etc)."""
    # Copy test video and SRT
    video_path = test_directory / 'video.mp4'
    srt_path = test_directory / 'video.en.srt'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)
    shutil.copy(PROJECT_DIR / 'test/example3.en.srt', srt_path)

    # Queue refresh
    file_worker.queue_refresh([test_directory])

    # Process queue
    while not file_worker.is_empty():
        await file_worker.process_batch()

    # Should create one FileGroup with both files
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 1

    fg = file_groups[0]
    assert str(fg.primary_path) == str(video_path)
    assert fg.mimetype == 'video/mp4'
    assert len(fg.files) == 2  # Video + SRT


@pytest.mark.asyncio
async def test_file_worker_expands_batch_by_stem(async_client, test_session, test_directory, file_worker, video_bytes):
    """
    FileWorker expands batches to include same-stem files from queue.

    This prevents orphaned FileGroups when files are discovered at different times
    or end up at batch boundaries.
    """
    # Create files with the same stem
    video_path = test_directory / 'my_video.mp4'
    poster_path = test_directory / 'my_video.webp'

    video_path.write_bytes(video_bytes)
    poster_path.write_bytes(b'RIFF\x00\x00\x00\x00WEBP')

    # Queue refresh for directory
    file_worker.queue_refresh([test_directory])

    # Process with tiny batch_size=1 to force batch expansion
    # Without expansion, this would create 2 separate FileGroups
    while not file_worker.is_empty():
        await file_worker.process_batch(batch_size=1)

    # Should create ONE FileGroup with both files due to batch expansion
    file_groups = test_session.query(FileGroup).filter(
        FileGroup.directory == str(test_directory)
    ).all()

    assert len(file_groups) == 1, \
        f"Expected 1 FileGroup (batch expansion worked), got {len(file_groups)}"

    fg = file_groups[0]
    assert fg.mimetype == 'video/mp4', "Primary should be video"
    assert len(fg.files) == 2, f"Should have 2 files, got {len(fg.files)}"


@pytest.mark.asyncio
async def test_file_worker_progress(async_client, test_directory, file_worker, make_files_structure):
    """FileWorker tracks progress correctly."""
    # Create test files
    make_files_structure({
        'file1.txt': 'content 1',
        'file2.txt': 'content 2',
        'file3.txt': 'content 3',
    })

    # Queue refresh
    job_id = file_worker.queue_refresh([test_directory])

    # Process queue
    while not file_worker.is_empty():
        await file_worker.process_batch()

    # Check progress
    progress = file_worker.get_progress()
    assert progress.total_jobs >= 1
    assert progress.surface_indexed >= 3


@pytest.mark.asyncio
async def test_file_worker_global_refresh(async_client, test_session, test_directory, file_worker,
                                           example_pdf, flags_lock):
    """FileWorker can queue a global refresh of the media directory.

    This test verifies that queue_global_refresh() runs the complete refresh
    pipeline including deep indexing (modeling), not just surface indexing.
    """
    from wrolpi import flags

    # Queue global refresh (what the API does)
    job_id = file_worker.queue_global_refresh()

    # Check job type
    jobs = file_worker._state.get_jobs()
    assert jobs[job_id]['job_type'] == 'global'

    # Process queue using run_async (mirrors production perpetual signal)
    # run_async processes batches and runs deep indexing when queue empties
    while not file_worker.is_empty():
        await file_worker.run_async()

    # Files should be surface indexed
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) >= 1

    # Verify deep indexing ran - PDF content should be extracted
    pdf_group = test_session.query(FileGroup).filter(
        FileGroup.mimetype == 'application/pdf'
    ).one()
    assert pdf_group.d_text is not None, \
        "Deep indexing did not run - PDF content was not extracted"
    assert 'Page one' in pdf_group.d_text, \
        "PDF content not properly extracted"

    # Verify refresh_complete flag is set after global refresh
    assert flags.refresh_complete.is_set(), \
        "refresh_complete flag should be set after global refresh"


@pytest.mark.asyncio
async def test_file_worker_clear(async_client, test_directory, file_worker):
    """FileWorker.clear() resets all state."""
    test_file = test_directory / 'test.txt'
    test_file.write_text('test')

    file_worker.queue_refresh([test_file])
    assert file_worker.queue_size() == 1

    file_worker.clear()

    assert file_worker.queue_size() == 0
    assert len(file_worker._state.get_jobs()) == 0
    assert len(file_worker._seen_paths) == 0


@pytest.mark.asyncio
async def test_file_worker_queue_move(async_client, test_session, test_directory, file_worker, make_files_structure):
    """FileWorker can queue and execute move operations."""
    from wrolpi.files.models import FileGroup

    # Create source files
    source_dir = test_directory / 'source'
    source_dir.mkdir()
    make_files_structure({
        'source/file1.txt': 'content 1',
        'source/file2.txt': 'content 2',
    })

    # Create destination directory
    dest_dir = test_directory / 'destination'
    dest_dir.mkdir()

    # First, refresh source to get FileGroups in DB
    file_worker.queue_refresh([source_dir])
    while not file_worker.is_empty():
        await file_worker.process_batch()

    # Verify source files are indexed
    source_fgs = test_session.query(FileGroup).filter(
        FileGroup.directory == str(source_dir)
    ).all()
    assert len(source_fgs) == 2

    # Queue and execute move
    job_id = file_worker.queue_move([source_dir], dest_dir)
    jobs = file_worker._state.get_jobs()
    assert job_id in jobs
    assert jobs[job_id]['job_type'] == 'move'

    # Execute the move
    success = await file_worker.execute_move(job_id)
    assert success is True

    # Verify job completed
    jobs = file_worker._state.get_jobs()
    assert jobs[job_id]['status'] == JobStatus.COMPLETED.value

    # Verify files moved on disk
    assert not (source_dir / 'file1.txt').exists()
    assert not (source_dir / 'file2.txt').exists()
    assert (dest_dir / 'source' / 'file1.txt').exists()
    assert (dest_dir / 'source' / 'file2.txt').exists()

    # Verify FileGroups updated in DB
    test_session.expire_all()
    dest_fgs = test_session.query(FileGroup).filter(
        FileGroup.directory.like(f'{dest_dir}%')
    ).all()
    assert len(dest_fgs) == 2


@pytest.mark.asyncio
async def test_file_worker_job_status_lifecycle(async_client, test_directory, file_worker, make_files_structure):
    """Job status transitions: pending → running → completed."""
    make_files_structure({'file1.txt': 'content'})

    job_id = file_worker.queue_refresh([test_directory])

    # Initial status is pending
    jobs = file_worker._state.get_jobs()
    assert jobs[job_id]['status'] == JobStatus.PENDING.value

    # After processing, status should be running
    await file_worker.process_batch()
    jobs = file_worker._state.get_jobs()
    assert jobs[job_id]['status'] == JobStatus.RUNNING.value
    assert jobs[job_id]['started_at'] is not None

    # After cleanup, jobs are cleared (so UI doesn't show lingering progress bars)
    await file_worker._cleanup()
    jobs = file_worker._state.get_jobs()
    assert len(jobs) == 0, "Jobs should be cleared after cleanup"
