"""Tests for the FileWorker move task."""
import contextlib
import sqlite3
import threading
import time

import pytest

from wrolpi.conftest import production_like_sessions
from wrolpi.files import worker as worker_module
from wrolpi.files.lib import _move_file_group_files
from wrolpi.files.models import FileGroup, Directory
from wrolpi.files.worker import file_worker, FileTask, FileTaskType, build_move_plan_bulk


@pytest.mark.asyncio
async def test_file_worker_queue_move(async_client, test_session, test_directory, make_files_structure):
    """FileWorker accepts and queues move tasks."""
    file1, = make_files_structure(['source/file1.txt'])
    dest = test_directory / 'destination'
    dest.mkdir()

    # Queue a move task
    file_worker.queue_move(dest, [file1.parent])

    # Verify task is in the public queue
    assert file_worker.public_queue.qsize() == 1


@pytest.mark.asyncio
async def test_file_worker_move_single_file(async_client, test_session, test_directory, make_files_structure):
    """FileWorker moves a single file to destination."""
    file1, = make_files_structure(['source/file1.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()
    original_id = fg.id

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [file1], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify file was moved
    assert (dest / 'file1.txt').exists()
    assert not file1.exists()

    # Verify FileGroup was updated
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter(FileGroup.id == original_id).one()
    assert str(dest) in str(fg.directory)
    assert 'file1.txt' in str(fg.primary_path)


@pytest.mark.asyncio
async def test_file_worker_move_directory(async_client, test_session, test_directory, make_files_structure):
    """FileWorker moves an entire directory to destination."""
    files = make_files_structure([
        'source/file1.txt',
        'source/file2.txt',
        'source/subdir/file3.txt',
    ])

    # Create FileGroups
    for f in files:
        FileGroup.from_paths(test_session, f)
    test_session.commit()

    source_dir = test_directory / 'source'
    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [source_dir], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify files were moved
    assert (dest / 'source' / 'file1.txt').exists()
    assert (dest / 'source' / 'file2.txt').exists()
    assert (dest / 'source' / 'subdir' / 'file3.txt').exists()

    # Verify original files are gone
    assert not (source_dir / 'file1.txt').exists()

    # Verify FileGroups were updated
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 3
    for fg in file_groups:
        assert str(dest) in str(fg.directory)


@pytest.mark.asyncio
async def test_file_worker_move_status_updates(async_client, test_session, test_directory, make_files_structure):
    """FileWorker updates status during move operation."""
    files = make_files_structure([f'source/file{i}.txt' for i in range(5)])

    for f in files:
        FileGroup.from_paths(test_session, f)
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [test_directory / 'source'], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # After completion, status should be reset to idle
    status = file_worker.status
    assert status['status'] == 'idle'
    assert status['destination'] is None


@pytest.mark.asyncio
async def test_file_worker_move_preserves_tags(
        async_client, test_session, test_directory, make_files_structure, tag_factory, await_switches
):
    """FileWorker preserves tags when moving files."""
    file1, = make_files_structure(['source/file1.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()

    tag = await tag_factory()
    fg.add_tag(test_session, tag.id)
    test_session.commit()
    await await_switches()

    original_id = fg.id

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [file1], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify tag is preserved
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter(FileGroup.id == original_id).one()
    assert len(fg.tag_files) == 1
    assert fg.tag_files[0].tag_id == tag.id


@pytest.mark.asyncio
async def test_file_worker_move_with_shared_stem_files(
        async_client, test_session, test_directory, make_files_structure, video_file_factory
):
    """FileWorker moves all files sharing a stem together."""
    docs_dir = test_directory / 'source'
    docs_dir.mkdir(parents=True, exist_ok=True)

    video_path = video_file_factory(docs_dir / 'video1.mp4')
    info_path = docs_dir / 'video1.info.json'
    info_path.write_text('{"title": "test"}')

    fg = FileGroup.from_paths(test_session, video_path)
    fg.files.append({'path': 'video1.info.json', 'mimetype': 'application/json'})
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [video_path], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify both files were moved
    assert (dest / 'video1.mp4').exists()
    assert (dest / 'video1.info.json').exists()
    assert not video_path.exists()
    assert not info_path.exists()


@pytest.mark.asyncio
async def test_file_worker_move_error_file_exists(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker handles error when destination file already exists."""
    source_file, dest_file = make_files_structure([
        'source/file1.txt',
        'destination/file1.txt',
    ])

    fg = FileGroup.from_paths(test_session, source_file)
    test_session.commit()

    dest = test_directory / 'destination'

    task = FileTask(FileTaskType.move, [source_file], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Status should be reset to idle (error handled gracefully)
    status = file_worker.status
    assert status['status'] == 'idle'

    # Source file should still exist (move failed)
    assert source_file.exists()


@pytest.mark.asyncio
async def test_file_worker_move_invalid_source(async_client, test_session, test_directory):
    """FileWorker handles invalid source paths gracefully."""
    nonexistent = test_directory / 'nonexistent'
    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [nonexistent], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Status should be reset to idle
    status = file_worker.status
    assert status['status'] == 'idle'


@pytest.mark.asyncio
async def test_file_worker_move_bulk_files(async_client, test_session, test_directory, make_files_structure):
    """FileWorker handles bulk moves efficiently with chunking."""
    # Create 150+ files to test chunking (MOVE_CHUNK_SIZE = 100)
    file_count = 150
    files = make_files_structure([f'source/file{i}.txt' for i in range(file_count)])

    for f in files:
        FileGroup.from_paths(test_session, f)
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [test_directory / 'source'], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify all files moved
    test_session.expire_all()
    moved_count = test_session.query(FileGroup).filter(
        FileGroup.directory.like(f'{dest}%')
    ).count()
    assert moved_count == file_count

    # Verify physical files exist
    assert (dest / 'source' / 'file0.txt').exists()
    assert (dest / 'source' / f'file{file_count - 1}.txt').exists()


@pytest.mark.asyncio
async def test_file_worker_move_creates_destination_directories(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker creates destination directories as needed."""
    file1, = make_files_structure(['source/file1.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()

    # Destination doesn't exist yet
    dest = test_directory / 'new' / 'nested' / 'destination'
    assert not dest.exists()

    task = FileTask(FileTaskType.move, [file1], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify destination was created and file moved
    assert dest.exists()
    assert (dest / 'file1.txt').exists()


@pytest.mark.asyncio
async def test_file_worker_move_multiple_sources(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker moves multiple source files to one destination."""
    file1, file2 = make_files_structure([
        'source1/file1.txt',
        'source2/file2.txt',
    ])

    fg1 = FileGroup.from_paths(test_session, file1)
    fg2 = FileGroup.from_paths(test_session, file2)
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [file1, file2], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify both files moved
    assert (dest / 'file1.txt').exists()
    assert (dest / 'file2.txt').exists()
    assert not file1.exists()
    assert not file2.exists()


@pytest.mark.asyncio
async def test_file_worker_move_already_moved_files(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker handles files that were already moved on filesystem.

    When a user manually moves files and then tells the worker to move them,
    the worker should detect the files are already at the destination and
    simply update the database records.
    """
    import shutil

    # Create file and FileGroup at original location
    file1, = make_files_structure(['source/file1.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()
    original_id = fg.id

    # User manually moves file on filesystem (outside of WROLPi)
    dest = test_directory / 'destination'
    dest.mkdir()
    shutil.move(str(file1), str(dest / 'file1.txt'))

    # Verify: source gone, dest exists
    assert not file1.exists()
    assert (dest / 'file1.txt').exists()

    # Tell worker to move (from old location to new)
    task = FileTask(FileTaskType.move, [file1], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify FileGroup was updated to new location
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter(FileGroup.id == original_id).one()
    assert str(dest) in str(fg.directory)
    assert 'file1.txt' in str(fg.primary_path)

    # Status should be idle (success)
    assert file_worker.status['status'] == 'idle'


# ============================================================================
# Tests for missing scenarios from files.lib.move
# ============================================================================


@pytest.mark.asyncio
async def test_file_worker_move_rollback_on_failure(
        async_client, test_session, test_directory, make_files_structure, monkeypatch
):
    """FileWorker rolls back moved files when an error occurs mid-move."""
    files = make_files_structure([
        'source/file1.txt',
        'source/file2.txt',
        'source/file3.txt',
    ])

    for f in files:
        FileGroup.from_paths(test_session, f)
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    # Patch _move_file_group_files to fail after first file
    call_count = 0
    original_move = _move_file_group_files

    def failing_move(fg, new_path):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise IOError("Simulated disk failure")
        return original_move(fg, new_path)

    monkeypatch.setattr('wrolpi.files.worker._move_file_group_files', failing_move)

    task = FileTask(FileTaskType.move, [test_directory / 'source'], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # All source files should still exist (rolled back)
    assert files[0].exists(), f"file1.txt should exist after rollback"
    assert files[1].exists(), f"file2.txt should exist after rollback"
    assert files[2].exists(), f"file3.txt should exist after rollback"

    # Destination should be empty or not exist
    dest_source = dest / 'source'
    assert not dest_source.exists() or not list(dest_source.iterdir()), \
        "Destination should be empty after rollback"


@pytest.mark.asyncio
async def test_file_worker_move_unindexed_files(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker creates FileGroups for files not yet in database."""
    # Create files but don't add them all to DB
    files = make_files_structure([
        'source/indexed.txt',
        'source/unindexed.txt',
    ])

    # Only index one file
    FileGroup.from_paths(test_session, files[0])
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [test_directory / 'source'], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Both files should be moved
    assert (dest / 'source' / 'indexed.txt').exists()
    assert (dest / 'source' / 'unindexed.txt').exists()

    # Both should have FileGroups now
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 2


@pytest.mark.asyncio
async def test_file_worker_move_preserves_existing_destination_on_failure(
        async_client, test_session, test_directory, make_files_structure, monkeypatch
):
    """FileWorker preserves existing destination directory on failure."""
    source_file, existing_file = make_files_structure([
        'source/file1.txt',
        'destination/existing.txt',  # Pre-existing file
    ])

    FileGroup.from_paths(test_session, source_file)
    test_session.commit()

    dest = test_directory / 'destination'

    # Patch to fail
    def failing_move(fg, new_path):
        raise IOError("Simulated failure")

    monkeypatch.setattr('wrolpi.files.worker._move_file_group_files', failing_move)

    task = FileTask(FileTaskType.move, [source_file], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Destination should still exist with original file
    assert dest.exists(), "Existing destination should be preserved"
    assert existing_file.exists(), "Existing file should be preserved"


@pytest.mark.asyncio
async def test_file_worker_move_removes_created_destination_on_failure(
        async_client, test_session, test_directory, make_files_structure, monkeypatch
):
    """FileWorker removes destination directory it created when move fails."""
    source_file, = make_files_structure(['source/file1.txt'])

    FileGroup.from_paths(test_session, source_file)
    test_session.commit()

    dest = test_directory / 'new_destination'
    assert not dest.exists()  # Doesn't exist yet

    # Patch to fail
    def failing_move(fg, new_path):
        raise IOError("Simulated failure")

    monkeypatch.setattr('wrolpi.files.worker._move_file_group_files', failing_move)

    task = FileTask(FileTaskType.move, [source_file], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Destination should NOT exist (was created by move and should be cleaned up)
    assert not dest.exists(), "Created destination should be removed on failure"


@pytest.mark.asyncio
async def test_file_worker_move_cleans_directory_records(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker removes Directory records for directories that no longer exist.

    Directories that still exist (even if empty) keep their DB records.
    """
    files = make_files_structure([
        'source/subdir/file1.txt',
    ])

    # Create directory records
    source_dir = test_directory / 'source'
    subdir = source_dir / 'subdir'
    test_session.add(Directory(path=str(source_dir), name='source'))
    test_session.add(Directory(path=str(subdir), name='subdir'))

    FileGroup.from_paths(test_session, files[0])
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    task = FileTask(FileTaskType.move, [source_dir], destination=dest)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    test_session.expire_all()

    # subdir no longer exists - its DB record should be deleted
    subdir_record = test_session.query(Directory).filter(
        Directory.path == str(subdir)
    ).one_or_none()
    assert subdir_record is None, "subdir Directory record should be deleted (directory no longer exists)"
    assert not subdir.exists(), "subdir should not exist on disk"

    # source still exists (empty) - its DB record should remain
    source_record = test_session.query(Directory).filter(
        Directory.path == str(source_dir)
    ).one_or_none()
    assert source_record is not None, "source Directory record should remain (directory still exists)"
    assert source_dir.exists(), "source should still exist on disk (empty)"


@contextlib.contextmanager
def _write_lock_held_briefly(db_file: str, seconds: float = 1.0):
    """Hold the SQLite write lock on `db_file` for `seconds`, from another connection.

    Simulates the concurrent writer (refresh, download, config save) that a real WROLPi runs
    alongside a move.  The lock is released while the test's move is still planning, so a
    correctly-written move waits (busy_timeout) and then succeeds.
    """
    holder = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    holder.isolation_level = None
    holder.execute('PRAGMA busy_timeout=30000')
    holder.execute('BEGIN IMMEDIATE')

    def release():
        time.sleep(seconds)
        holder.execute('ROLLBACK')
        holder.close()

    thread = threading.Thread(target=release, daemon=True)
    thread.start()
    try:
        yield
    finally:
        thread.join(timeout=30)


@pytest.mark.asyncio
async def test_build_move_plan_waits_for_concurrent_writer(
        async_client, test_session, test_directory, make_files_structure
):
    """`build_move_plan_bulk` must not fail instantly when another connection is writing.

    Regression test for the tag-a-channel move that died with `database is locked` while
    INSERTing a FileGroup for an unindexed file.  The plan's transaction begins *deferred*
    (a read), then upgrades to a writer at that INSERT; SQLite refuses a lock upgrade
    immediately, skipping busy_timeout, so any concurrent writer aborts the whole move.
    Beginning the transaction as a writer lets busy_timeout absorb the contention instead.
    """
    # An unindexed file, so planning must INSERT a FileGroup (the write that failed in production).
    file1, = make_files_structure(['source/file1.txt'])
    dest = test_directory / 'destination'
    dest.mkdir()

    db_file = test_session.get_bind().url.database

    with production_like_sessions(test_session):
        with _write_lock_held_briefly(db_file):
            plan, _ = await build_move_plan_bulk([file1], dest)

    assert plan == {file1: dest / 'file1.txt'}


@pytest.mark.asyncio
async def test_file_worker_move_survives_concurrent_writer(
        async_client, test_session, test_directory, make_files_structure, monkeypatch
):
    """Executing a move must survive a concurrent writer holding the write lock.

    `_execute_move_chunks` reads FileGroups/Directories and then writes them, so its transaction
    must begin as a writer too - SQLite refuses the mid-transaction lock upgrade instantly and the
    move aborts.  The lock is taken only *after* planning finishes, so this fails if the execute
    site alone regresses; planning cannot absorb the contention on the execute site's behalf.
    """
    file1, = make_files_structure(['source/file1.txt'])
    FileGroup.from_paths(test_session, file1)
    test_session.commit()

    dest = test_directory / 'destination'
    dest.mkdir()

    db_file = test_session.get_bind().url.database

    task = FileTask(FileTaskType.move, [file1], destination=dest)
    file_worker.private_queue.put_nowait(task)

    with contextlib.ExitStack() as stack:
        maker = stack.enter_context(production_like_sessions(test_session))

        real_build_move_plan_bulk = worker_module.build_move_plan_bulk

        async def build_plan_then_hold_write_lock(*args, **kwargs):
            plan = await real_build_move_plan_bulk(*args, **kwargs)
            # Planning is done; the contention now falls entirely on the execute phase.
            stack.enter_context(_write_lock_held_briefly(db_file))
            return plan

        monkeypatch.setattr(worker_module, 'build_move_plan_bulk', build_plan_then_hold_write_lock)

        await file_worker.process_queue()

        assert (dest / 'file1.txt').is_file(), 'file was not moved'
        assert not file1.exists(), 'file was left at its old path'

        session = maker()
        fg = session.query(FileGroup).one()
        assert fg.primary_path == dest / 'file1.txt', 'FileGroup was not updated to the new path'
