"""Tests for the file comparison worker."""
import asyncio

import pytest

from wrolpi.conftest import await_switches
from wrolpi.files.models import FileGroup
from wrolpi.files.worker import compare_file_groups, count_files, file_worker, FileGroupDiff, FileTask, FileTaskType


@pytest.mark.asyncio
async def test_compare_file_groups_empty(test_session, test_directory):
    """Compare with empty filesystem and database returns empty results."""
    result = await compare_file_groups(test_directory)

    assert result.unchanged == []
    assert result.new == []
    assert result.deleted == []
    assert result.modified == []


@pytest.mark.asyncio
async def test_compare_file_groups_new_files(test_session, test_directory, make_files_structure):
    """Files on disk but not in DB are reported as new."""
    make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
        'docs/file2.txt',
    ])

    result = await compare_file_groups(test_directory)

    assert len(result.new) == 2
    assert len(result.unchanged) == 0
    assert len(result.deleted) == 0
    assert len(result.modified) == 0

    # Check the new file groups
    stems = {diff.stem for diff in result.new}
    assert 'file1' in stems
    assert 'file2' in stems

    # Check file1 has both files grouped
    file1_diff = next(d for d in result.new if d.stem == 'file1')
    assert file1_diff.fs_files == {'file1.txt', 'file1.json'}
    assert file1_diff.db_files == set()
    assert file1_diff.is_new is True


@pytest.mark.asyncio
async def test_compare_file_groups_deleted_files(test_session, test_directory, make_files_structure):
    """Files in DB but not on disk are reported as deleted."""
    # Create files and FileGroups
    file1, file1_json = make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
    ])

    # Create FileGroup in DB using single file (simpler)
    fg = FileGroup.from_paths(test_session, file1)
    # Manually add the second file to the files list
    fg.files.append({'path': 'file1.json', 'mimetype': 'application/json', 'size': 0})
    test_session.commit()

    # Delete files from disk
    file1.unlink()
    file1_json.unlink()

    result = await compare_file_groups(test_directory)

    assert len(result.deleted) == 1
    assert len(result.unchanged) == 0
    assert len(result.new) == 0
    assert len(result.modified) == 0

    deleted_diff = result.deleted[0]
    assert deleted_diff.stem == 'file1'
    assert deleted_diff.db_files == {'file1.txt', 'file1.json'}
    assert deleted_diff.fs_files == set()
    assert deleted_diff.is_deleted is True


@pytest.mark.asyncio
async def test_compare_file_groups_unchanged(test_session, test_directory, make_files_structure):
    """Files matching between DB and filesystem are reported as unchanged."""
    file1, file1_json = make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
    ])

    # Create FileGroup in DB
    fg = FileGroup.from_paths(test_session, file1)
    fg.files.append({'path': 'file1.json', 'mimetype': 'application/json', 'size': 0})
    test_session.commit()

    result = await compare_file_groups(test_directory)

    assert len(result.unchanged) == 1
    assert len(result.new) == 0
    assert len(result.deleted) == 0
    assert len(result.modified) == 0

    unchanged_diff = result.unchanged[0]
    assert unchanged_diff.stem == 'file1'
    assert unchanged_diff.is_unchanged is True


@pytest.mark.asyncio
async def test_compare_file_groups_modified_file_added(test_session, test_directory, make_files_structure):
    """FileGroup with new file on disk is reported as modified."""
    file1, = make_files_structure([
        'docs/file1.txt',
    ])

    # Create FileGroup in DB with just one file
    FileGroup.from_paths(test_session, file1)
    test_session.commit()

    # Add a new file to the group on disk
    file1_json = test_directory / 'docs/file1.json'
    file1_json.touch()

    result = await compare_file_groups(test_directory)

    assert len(result.modified) == 1
    assert len(result.unchanged) == 0
    assert len(result.new) == 0
    assert len(result.deleted) == 0

    modified_diff = result.modified[0]
    assert modified_diff.stem == 'file1'
    assert modified_diff.added_files == {'file1.json'}
    assert modified_diff.removed_files == set()
    assert modified_diff.needs_update is True


@pytest.mark.asyncio
async def test_compare_file_groups_modified_file_removed(test_session, test_directory, make_files_structure):
    """FileGroup with file removed from disk is reported as modified."""
    file1, file1_json = make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
    ])

    # Create FileGroup in DB with both files
    fg = FileGroup.from_paths(test_session, file1)
    fg.files.append({'path': 'file1.json', 'mimetype': 'application/json', 'size': 0})
    test_session.commit()

    # Remove one file from disk
    file1_json.unlink()

    result = await compare_file_groups(test_directory)

    assert len(result.modified) == 1
    assert len(result.unchanged) == 0
    assert len(result.new) == 0
    assert len(result.deleted) == 0

    modified_diff = result.modified[0]
    assert modified_diff.stem == 'file1'
    assert modified_diff.added_files == set()
    assert modified_diff.removed_files == {'file1.json'}
    assert modified_diff.needs_update is True


@pytest.mark.asyncio
async def test_compare_file_groups_mixed(test_session, test_directory, make_files_structure):
    """Test with a mix of new, deleted, unchanged, and modified FileGroups."""
    # Create files on disk
    file1, file1_json, file2, file3, file3_json = make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
        'docs/file2.txt',
        'docs/file3.txt',
        'docs/file3.json',
    ])

    # file1: Will be unchanged (in DB and on disk)
    fg1 = FileGroup.from_paths(test_session, file1)
    fg1.files.append({'path': 'file1.json', 'mimetype': 'application/json', 'size': 0})

    # file2: Will be modified (in DB, but we'll add a file on disk)
    FileGroup.from_paths(test_session, file2)

    # file4: Will be deleted (in DB but not on disk)
    file4 = test_directory / 'docs/file4.txt'
    file4.parent.mkdir(parents=True, exist_ok=True)
    file4.touch()
    FileGroup.from_paths(test_session, file4)
    file4.unlink()

    test_session.commit()

    # file3: Is new (on disk but not in DB) - no action needed

    # Add file to file2 group on disk
    file2_json = test_directory / 'docs/file2.json'
    file2_json.touch()

    result = await compare_file_groups(test_directory)

    assert len(result.unchanged) == 1
    assert len(result.new) == 1
    assert len(result.deleted) == 1
    assert len(result.modified) == 1

    # Verify each category
    unchanged_stems = {i.stem for i in result.unchanged}
    new_stems = {i.stem for i in result.new}
    deleted_stems = {i.stem for i in result.deleted}
    modified_stems = {i.stem for i in result.modified}

    assert 'file1' in unchanged_stems
    assert 'file3' in new_stems
    assert 'file4' in deleted_stems
    assert 'file2' in modified_stems


def test_file_group_diff_properties():
    """Test FileGroupDiff property calculations."""
    # New FileGroup
    diff = FileGroupDiff(
        directory='/test',
        stem='video1',
        db_files=set(),
        fs_files={'video1.mp4', 'video1.info.json'},
        file_group_id=None,
    )
    assert diff.is_new is True
    assert diff.is_deleted is False
    assert diff.needs_update is False
    assert diff.is_unchanged is False
    assert diff.added_files == {'video1.mp4', 'video1.info.json'}
    assert diff.removed_files == set()

    # Deleted FileGroup
    diff = FileGroupDiff(
        directory='/test',
        stem='video2',
        db_files={'video2.mp4'},
        fs_files=set(),
        file_group_id=1,
    )
    assert diff.is_new is False
    assert diff.is_deleted is True
    assert diff.needs_update is False
    assert diff.is_unchanged is False

    # Modified FileGroup
    diff = FileGroupDiff(
        directory='/test',
        stem='video3',
        db_files={'video3.mp4'},
        fs_files={'video3.mp4', 'video3.info.json'},
        file_group_id=2,
    )
    assert diff.is_new is False
    assert diff.is_deleted is False
    assert diff.needs_update is True
    assert diff.is_unchanged is False
    assert diff.added_files == {'video3.info.json'}
    assert diff.removed_files == set()

    # Unchanged FileGroup
    diff = FileGroupDiff(
        directory='/test',
        stem='video4',
        db_files={'video4.mp4', 'video4.info.json'},
        fs_files={'video4.mp4', 'video4.info.json'},
        file_group_id=3,
    )
    assert diff.is_new is False
    assert diff.is_deleted is False
    assert diff.needs_update is False
    assert diff.is_unchanged is True


@pytest.mark.asyncio
async def test_compare_file_groups_ignores_outside_root(test_session, test_directory, make_files_structure):
    """FileGroups outside the root directory should be ignored."""
    # Create files in two separate directories
    videos_file, = make_files_structure(['videos/video1.mp4'])
    archives_file, = make_files_structure(['archives/page1.html'])

    # Create FileGroups for both
    FileGroup.from_paths(test_session, videos_file)
    FileGroup.from_paths(test_session, archives_file)
    test_session.commit()

    # Compare only the videos directory
    videos_dir = test_directory / 'videos'
    result = await compare_file_groups(videos_dir)

    # Should find unchanged video, NOT report archives as deleted
    assert len(result.unchanged) == 1
    assert result.unchanged[0].stem == 'video1'
    assert len(result.deleted) == 0  # archives FileGroup should be ignored
    assert len(result.new) == 0
    assert len(result.modified) == 0


@pytest.mark.asyncio
async def test_compare_file_groups_cancelable(test_session, test_directory, make_files_structure):
    """compare_file_groups can be canceled during long operations and reports progress via callback."""
    # Create many files to ensure scan takes time
    make_files_structure([f'docs/file{i}.txt' for i in range(100)])

    # Test cancellation
    task = asyncio.create_task(compare_file_groups(test_directory))
    await asyncio.sleep(0)  # Let task start
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Test progress callback with small batch size
    progress_counts = []
    await compare_file_groups(test_directory, batch_size=10, progress_callback=progress_counts.append)
    # Should have been called multiple times with increasing counts
    assert len(progress_counts) >= 1
    assert progress_counts == sorted(progress_counts)  # Counts should be increasing


@pytest.mark.asyncio
async def test_count_files_empty(test_directory):
    """Count files in empty directory returns 0."""
    result = await count_files([test_directory])
    assert result == 0


@pytest.mark.asyncio
async def test_count_files_single_directory(test_directory, make_files_structure):
    """Count files in a single directory."""
    make_files_structure([
        'docs/file1.txt',
        'docs/file2.txt',
        'docs/file3.txt',
    ])

    result = await count_files([test_directory])
    assert result == 3


@pytest.mark.asyncio
async def test_count_files_multiple_directories(test_directory, make_files_structure):
    """Count files across multiple directories."""
    make_files_structure([
        'docs/file1.txt',
        'docs/file2.txt',
        'videos/video1.mp4',
        'videos/video2.mp4',
        'videos/video3.mp4',
    ])

    docs_dir = test_directory / 'docs'
    videos_dir = test_directory / 'videos'

    result = await count_files([docs_dir, videos_dir])
    assert result == 5


@pytest.mark.asyncio
async def test_count_files_nested_directories(test_directory, make_files_structure):
    """Count files in nested directory structure."""
    make_files_structure([
        'docs/file1.txt',
        'docs/subdir/file2.txt',
        'docs/subdir/deep/file3.txt',
    ])

    result = await count_files([test_directory])
    assert result == 3


@pytest.mark.asyncio
async def test_count_files_ignores_hidden(test_directory, make_files_structure):
    """Hidden files and directories are not counted."""
    make_files_structure([
        'docs/file1.txt',
        'docs/.hidden_file.txt',
    ])
    # Create hidden directory with files
    hidden_dir = test_directory / '.hidden_dir'
    hidden_dir.mkdir()
    (hidden_dir / 'secret.txt').touch()

    result = await count_files([test_directory])
    assert result == 1  # Only file1.txt


@pytest.mark.asyncio
async def test_count_files_empty_list():
    """Count files with empty directory list returns 0."""
    result = await count_files([])
    assert result == 0


@pytest.mark.asyncio
async def test_count_files_ignores_configured_directories(test_directory, make_files_structure, test_wrolpi_config,
                                                          await_switches, await_background_tasks):
    """Files in ignored_directories config are not counted."""
    make_files_structure([
        'docs/file1.txt',
        'ignored_dir/file2.txt',
        'ignored_dir/subdir/file3.txt',
    ])

    from wrolpi.common import get_wrolpi_config
    # Set the ignored directory (absolute path).
    get_wrolpi_config().ignored_directories = [str(test_directory / 'ignored_dir'), str(test_directory / 'config')]
    await await_background_tasks()
    result = await count_files([test_directory])
    assert result == 1  # Only docs/file1.txt


@pytest.mark.asyncio
async def test_count_files_ignores_relative_directories(test_directory, make_files_structure, test_wrolpi_config,
                                                        await_background_tasks):
    """Relative paths in ignored_directories are resolved against media directory."""
    make_files_structure([
        'docs/file1.txt',
        'config/file2.txt',  # 'config' is in default ignored_directories
    ])

    from wrolpi.common import get_wrolpi_config
    # Use relative path (like default 'config' and 'tags')
    get_wrolpi_config().ignored_directories = ['config']
    await await_background_tasks()
    result = await count_files([test_directory])
    assert result == 1  # Only docs/file1.txt, config is ignored


@pytest.mark.asyncio
async def test_file_worker_status_during_count(async_client, test_session, test_directory, make_files_structure):
    """FileWorker updates status during counting phase."""
    make_files_structure([f'docs/file{i}.txt' for i in range(10)])

    # Create count task that chains to refresh
    task = FileTask(FileTaskType.count, [test_directory], next_task_type=FileTaskType.refresh)
    file_worker.private_queue.put_nowait(task)

    # Process the count task
    await file_worker.process_queue()

    # After count, status should show counting completed with total
    status = file_worker.status
    assert status['operation_total'] == 10
    assert status['operation_processed'] == 10
    assert status['operation_percent'] == 100
    assert status['task_type'] == 'refresh'
    assert str(test_directory) in status['paths']


@pytest.mark.asyncio
async def test_file_worker_status_during_refresh(async_client, test_session, test_directory, make_files_structure):
    """FileWorker updates status during refresh with comparison results."""
    make_files_structure(['docs/file1.txt', 'docs/file2.txt'])

    # Create refresh task with count already set
    task = FileTask(FileTaskType.refresh, [test_directory], count=2)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # After refresh completes, status should be reset to idle
    # (We can't easily capture intermediate states without mocking)
    status = file_worker.status
    assert status['status'] == 'idle'


@pytest.mark.asyncio
async def test_file_worker_status_resets_after_refresh(async_client, test_session, test_directory, make_files_structure):
    """FileWorker resets status to idle after refresh completes."""
    make_files_structure(['docs/file1.txt'])

    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    status = file_worker.status
    assert status['status'] == 'idle'
    assert status['operation_total'] == 0
    assert status['operation_processed'] == 0
    assert status['operation_percent'] == 0


@pytest.mark.asyncio
async def test_file_worker_count_only_resets_status(async_client, test_session, test_directory, make_files_structure):
    """Standalone count task (no next_task_type) resets status after completion."""
    make_files_structure(['docs/file1.txt', 'docs/file2.txt'])

    # Count only, no chaining to refresh
    task = FileTask(FileTaskType.count, [test_directory])
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    status = file_worker.status
    assert status['status'] == 'idle'
    assert status['operation_total'] == 0
    assert status['operation_processed'] == 0
    assert status['operation_percent'] == 0


@pytest.mark.asyncio
async def test_file_worker_refresh_inserts_new_files(async_client, test_session, test_directory, make_files_structure,
                                                      video_file_factory):
    """FileWorker inserts new FileGroups during refresh."""
    # Create files on disk but not in DB
    # Note: txt/json files without recognizable primary types (video, epub, etc.)
    # will each become their own FileGroup per _upsert_files behavior
    make_files_structure([
        'docs/file1.txt',
        'docs/file2.txt',
        'docs/file3.txt',
    ])

    # Verify no FileGroups exist yet
    assert test_session.query(FileGroup).count() == 0

    # Create refresh task with count
    task = FileTask(FileTaskType.refresh, [test_directory], count=3)
    file_worker.private_queue.put_nowait(task)

    await file_worker.process_queue()

    # Verify FileGroups were created (one per file for plain text)
    test_session.expire_all()  # Refresh from DB
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 3

    # Check primary paths contain our files
    primary_paths = {str(fg.primary_path) for fg in file_groups}
    assert any('file1.txt' in p for p in primary_paths)
    assert any('file2.txt' in p for p in primary_paths)
    assert any('file3.txt' in p for p in primary_paths)

    # Now add a real video file that shares a stem with file1
    # (must be a real video file so get_mimetype returns video/mp4)
    video_file_factory(test_directory / 'docs/file1.mp4')

    # Refresh again - should detect the modified FileGroup
    task = FileTask(FileTaskType.refresh, [test_directory], count=4)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Should still have 3 FileGroups (file1 group now has 2 files, with mp4 as primary)
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 3

    # Find the file1 FileGroup - now the mp4 is primary since video takes precedence
    file1_fg = next(fg for fg in file_groups if 'file1' in str(fg.primary_path))
    assert 'file1.mp4' in str(file1_fg.primary_path)
    file_names = {f['path'] for f in file1_fg.files}
    assert 'file1.txt' in file_names
    assert 'file1.mp4' in file_names


@pytest.mark.asyncio
async def test_file_worker_deletes_removed_file_groups(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker deletes FileGroups when all files are removed from disk."""
    # Create files and FileGroups
    # Include a baseline file that won't be deleted (media directory must have non-ignored files)
    file1, _baseline = make_files_structure(['docs/file1.txt', 'videos/baseline.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()
    fg_id = fg.id

    # Verify FileGroup exists
    assert test_session.query(FileGroup).filter_by(id=fg_id).one_or_none() is not None

    # Delete file from disk
    file1.unlink()

    # Run refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify FileGroup was deleted
    test_session.expire_all()
    assert test_session.query(FileGroup).filter_by(id=fg_id).one_or_none() is None


@pytest.mark.asyncio
async def test_file_worker_deletes_tagged_file_groups_auto_removes_tags(
        async_client, test_session, test_directory, make_files_structure,
        tag_factory, await_switches
):
    """FileWorker auto-removes tags when deleting FileGroups with missing files."""
    from wrolpi.tags import TagFile

    # Create file and FileGroup
    # Include a baseline file that won't be deleted (media directory must have non-ignored files)
    file1, _baseline = make_files_structure(['docs/file1.txt', 'videos/baseline.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()

    # Create a tag and tag the file
    tag = await tag_factory()
    fg.add_tag(test_session, tag.id)
    test_session.commit()
    await await_switches()

    fg_id = fg.id

    # Verify TagFile exists
    assert test_session.query(TagFile).filter_by(file_group_id=fg_id).count() == 1

    # Delete file from disk
    file1.unlink()

    # Run refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify FileGroup and TagFile were deleted (cascade)
    test_session.expire_all()
    assert test_session.query(FileGroup).filter_by(id=fg_id).one_or_none() is None
    assert test_session.query(TagFile).filter_by(file_group_id=fg_id).count() == 0


@pytest.mark.asyncio
async def test_file_worker_adds_deleted_file_url_to_skip_list(
        async_client, test_session, test_directory, make_files_structure,
        test_download_manager_config
):
    """FileWorker adds URL to skip list when deleting FileGroup with URL."""
    from wrolpi.downloader import get_download_manager_config

    # Create file and FileGroup with URL
    # Include a baseline file that won't be deleted (media directory must have non-ignored files)
    file1, _baseline = make_files_structure(['docs/file1.txt', 'videos/baseline.txt'])
    fg = FileGroup.from_paths(test_session, file1)
    test_url = 'https://example.com/file1.txt'
    fg.url = test_url
    test_session.commit()

    # Verify URL not in skip list
    assert test_url not in get_download_manager_config().skip_urls

    # Delete file from disk
    file1.unlink()

    # Run refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify URL was added to skip list
    assert test_url in get_download_manager_config().skip_urls


@pytest.mark.asyncio
async def test_file_worker_updates_modified_removes_deleted_file(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker updates FileGroup.files when non-primary file is deleted."""
    # Create files and FileGroup with multiple files
    file1_txt, file1_json = make_files_structure([
        'docs/file1.txt',
        'docs/file1.json',
    ])

    fg = FileGroup.from_paths(test_session, file1_txt)
    fg.files.append({'path': 'file1.json', 'mimetype': 'application/json'})
    test_session.commit()
    fg_id = fg.id

    # Verify both files are in the FileGroup
    assert len(fg.files) == 2

    # Delete non-primary file
    file1_json.unlink()

    # Run refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify FileGroup still exists but files list is updated
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter_by(id=fg_id).one()
    assert len(fg.files) == 1
    assert fg.files[0]['path'] == 'file1.txt'


@pytest.mark.asyncio
async def test_file_worker_handles_primary_file_deleted(
        async_client, test_session, test_directory, make_files_structure,
        video_file_factory
):
    """FileWorker handles case where primary file deleted but others remain.

    When the primary file is deleted, the group is detected as "modified" and
    a new FileGroup is created for remaining files. The old FileGroup record
    persists until its files list no longer matches anything on the filesystem.
    The Video model associated with the deleted file should be cleaned up.

    Note: This tests the modified FileGroup handling, which creates a new
    FileGroup for the remaining files.
    """
    from modules.videos.models import Video

    # Create FileGroup with video (primary) and info.json
    # Create directory first
    docs_dir = test_directory / 'docs'
    docs_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_file_factory(docs_dir / 'video1.mp4')
    assert video_path.is_file(), 'Video file must exist for modeler'
    info_path = docs_dir / 'video1.info.json'
    info_path.write_text('{"title": "test"}')

    fg = FileGroup.from_paths(test_session, video_path)
    fg.files.append({'path': 'video1.info.json', 'mimetype': 'application/json'})
    fg.indexed = True  # Mark as indexed so modeler doesn't try to process
    test_session.commit()

    # Create a Video model for this FileGroup
    video = Video(file_group=fg, file_group_id=fg.id)
    test_session.add(video)
    test_session.commit()
    video_id = video.id

    # Verify video is primary and Video model exists
    assert 'video1.mp4' in str(fg.primary_path)
    assert test_session.query(Video).filter_by(id=video_id).one_or_none() is not None

    # Delete primary video file from disk
    video_path.unlink()

    # Refresh: creates new FileGroup for remaining files
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    test_session.expire_all()
    file_groups = test_session.query(FileGroup).all()

    # A new FileGroup should exist for the remaining info.json file
    info_fg = [fg for fg in file_groups if 'video1.info.json' in str(fg.primary_path)]
    assert len(info_fg) == 1
    assert info_fg[0].files[0]['path'] == 'video1.info.json'

    # Video model should be cleaned up (no longer exists)
    assert test_session.query(Video).filter_by(id=video_id).one_or_none() is None


@pytest.mark.asyncio
async def test_file_worker_handles_singlefile_deleted(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker cleans up Archive when SingleFile HTML is deleted but other files remain."""
    from modules.archive.models import Archive

    # Create singlefile and readability files
    docs_dir = test_directory / 'archives'
    docs_dir.mkdir(parents=True, exist_ok=True)

    singlefile_path = docs_dir / '2024-01-01-12-00-00_example.html'
    singlefile_path.write_text('<!--\n Page saved with SingleFile\n--><html>content</html>')

    readability_path = docs_dir / '2024-01-01-12-00-00_example.readability.html'
    readability_path.write_text('<html>readable content</html>')

    # Create FileGroup with Archive
    fg = FileGroup.from_paths(test_session, singlefile_path)
    fg.files.append({'path': readability_path.name, 'mimetype': 'text/html'})
    fg.indexed = True
    test_session.commit()

    archive = Archive(file_group=fg, file_group_id=fg.id)
    test_session.add(archive)
    test_session.commit()
    archive_id = archive.id

    # Verify Archive exists
    assert test_session.query(Archive).filter_by(id=archive_id).one_or_none() is not None

    # Delete SingleFile from disk
    singlefile_path.unlink()

    # Refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    test_session.expire_all()

    # Archive should be cleaned up
    assert test_session.query(Archive).filter_by(id=archive_id).one_or_none() is None


@pytest.mark.asyncio
async def test_file_worker_deletes_multiple_file_groups(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker can delete multiple FileGroups in one refresh."""
    # Create multiple files and FileGroups
    # Include a baseline file that won't be deleted (media directory must have non-ignored files)
    file1, file2, file3, _baseline = make_files_structure([
        'docs/file1.txt',
        'docs/file2.txt',
        'docs/file3.txt',
        'videos/baseline.txt',
    ])

    fg1 = FileGroup.from_paths(test_session, file1)
    fg2 = FileGroup.from_paths(test_session, file2)
    fg3 = FileGroup.from_paths(test_session, file3)
    test_session.commit()

    fg1_id, fg2_id, fg3_id = fg1.id, fg2.id, fg3.id

    # Delete all test files (not the baseline)
    file1.unlink()
    file2.unlink()
    file3.unlink()

    # Run refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify all FileGroups were deleted
    test_session.expire_all()
    assert test_session.query(FileGroup).filter(
        FileGroup.id.in_([fg1_id, fg2_id, fg3_id])
    ).count() == 0


@pytest.mark.asyncio
async def test_worker_status_endpoint(async_client):
    """The worker_status endpoint returns current FileWorker status."""
    from http import HTTPStatus

    request, response = await async_client.get('/api/files/worker_status')
    assert response.status_code == HTTPStatus.OK
    status = response.json['status']
    assert 'status' in status
    assert 'task_type' in status
    assert 'paths' in status
    assert 'error' in status
    assert 'operation_total' in status
    assert 'operation_processed' in status
    assert 'operation_percent' in status
    # Default idle state
    assert status['status'] == 'idle'
    assert status['operation_total'] == 0
    assert status['operation_processed'] == 0
    assert status['operation_percent'] == 0


@pytest.mark.asyncio
async def test_handle_refresh_runs_indexing(async_client, test_session, test_directory, make_files_structure):
    """FileWorker.handle_refresh should index new FileGroups."""
    # Create a file that will be discovered
    file1, = make_files_structure(['videos/test.txt'])

    # Queue refresh with count
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify FileGroup was created AND indexed
    test_session.expire_all()
    fg = test_session.query(FileGroup).filter(FileGroup.primary_path.like('%test.txt')).one()
    assert fg.indexed == True


@pytest.mark.asyncio
async def test_handle_refresh_runs_modelers(async_client, test_session, test_directory, video_file_factory):
    """FileWorker.handle_refresh should run modelers on new FileGroups."""
    from modules.videos.models import Video

    # Create a video file that modelers will process
    (test_directory / 'videos').mkdir(parents=True, exist_ok=True)
    video_file_factory(test_directory / 'videos' / 'test_video.mp4')

    # Queue refresh with count
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Verify Video model was created by modeler
    test_session.expire_all()
    video = test_session.query(Video).one_or_none()
    assert video is not None


@pytest.mark.asyncio
async def test_handle_refresh_status_includes_indexing(async_client, test_session, test_directory, make_files_structure):
    """FileWorker.handle_refresh should update status during indexing phase."""
    # Create files
    make_files_structure(['file1.txt', 'file2.txt'])

    # Track status changes
    statuses = []
    original_update = file_worker.update_status

    def tracking_update(**kwargs):
        statuses.append(kwargs.get('status'))
        original_update(**kwargs)

    file_worker.update_status = tracking_update
    try:
        task = FileTask(FileTaskType.refresh, [test_directory], count=2)
        file_worker.private_queue.put_nowait(task)
        await file_worker.process_queue()
    finally:
        file_worker.update_status = original_update

    # Verify indexing status was set
    assert 'indexing' in statuses


@pytest.mark.asyncio
async def test_refresh_complete_flag_set_on_full_refresh(async_client, test_session, test_directory, make_files_structure, flags_lock):
    """refresh_complete flag is set when refreshing the entire media directory."""
    from wrolpi import flags

    # Clear the flag to ensure clean state
    flags.refresh_complete.clear()
    assert flags.refresh_complete.is_set() is False

    make_files_structure(['docs/file1.txt'])

    # Refresh the entire media directory (test_directory IS the media directory in tests)
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Flag should be set after full refresh
    assert flags.refresh_complete.is_set() is True


@pytest.mark.asyncio
async def test_refresh_complete_flag_not_set_on_partial_refresh(async_client, test_session, test_directory, make_files_structure, flags_lock):
    """refresh_complete flag is NOT set when refreshing only a subdirectory."""
    from wrolpi import flags

    # Clear the flag to ensure clean state
    flags.refresh_complete.clear()
    assert flags.refresh_complete.is_set() is False

    make_files_structure(['docs/file1.txt', 'other/file2.txt'])

    # Refresh only a subdirectory (not the full media directory)
    subdirectory = test_directory / 'docs'
    task = FileTask(FileTaskType.refresh, [subdirectory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Flag should NOT be set after partial refresh
    assert flags.refresh_complete.is_set() is False


@pytest.mark.asyncio
async def test_file_worker_refuses_refresh_when_only_ignored_files_exist(
        async_client, test_session, test_directory, make_files_structure, test_wrolpi_config, await_background_tasks
):
    """FileWorker refuses to perform a global refresh when media directory only contains ignored files.

    This prevents accidentally wiping the database when the media directory is effectively empty
    (e.g., only has config files but no actual content).
    """
    from wrolpi.common import get_wrolpi_config
    from wrolpi.errors import UnknownDirectory

    # Set up ignored directories - these are the only directories that will have files
    get_wrolpi_config().ignored_directories = ['config', 'tags']
    await await_background_tasks()

    # Create files ONLY in ignored directories
    make_files_structure([
        'config/wrolpi.yaml',
        'config/channels.yaml',
        'tags/tags.yaml',
    ])

    # Queue a global refresh (refreshing the entire media directory)
    task = FileTask(FileTaskType.refresh, [test_directory], count=0)
    file_worker.private_queue.put_nowait(task)

    # The refresh should raise UnknownDirectory because there are no non-ignored files
    with pytest.raises(UnknownDirectory) as exc_info:
        await file_worker.process_queue()

    assert 'empty' in str(exc_info.value).lower() or 'ignored' in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_file_worker_allows_refresh_when_non_ignored_files_exist(
        async_client, test_session, test_directory, make_files_structure, test_wrolpi_config, await_background_tasks
):
    """FileWorker allows refresh when there are non-ignored files in the media directory."""
    from wrolpi.common import get_wrolpi_config

    # Set up ignored directories
    get_wrolpi_config().ignored_directories = ['config', 'tags']
    await await_background_tasks()

    # Create files in both ignored and non-ignored directories
    make_files_structure([
        'config/wrolpi.yaml',
        'videos/video1.txt',  # This is a non-ignored file
    ])

    # Queue a global refresh
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)

    # Should not raise - refresh should proceed normally
    await file_worker.process_queue()

    # Verify FileGroup was created for the non-ignored file
    test_session.expire_all()
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 1
    assert 'video1.txt' in str(file_groups[0].primary_path)


@pytest.mark.asyncio
async def test_global_refresh_sends_global_events(
        async_client, test_session, test_directory, make_files_structure, events_fixture
):
    """Global refresh (entire media directory) should send global_* events."""
    make_files_structure(['docs/file1.txt'])

    # Global refresh = refreshing the media directory (test_directory)
    task = FileTask(FileTaskType.refresh, [test_directory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Global refresh should send global_* events
    events_fixture.assert_has_event('global_refresh_started')
    events_fixture.assert_has_event('global_refresh_discovery_completed')
    events_fixture.assert_has_event('global_refresh_modeling_completed')
    events_fixture.assert_has_event('global_refresh_indexing_completed')
    events_fixture.assert_has_event('global_after_refresh_completed')
    events_fixture.assert_has_event('refresh_completed')

    # Should NOT send directory_refresh or files_refreshed
    events_fixture.assert_no_event('directory_refresh')
    events_fixture.assert_no_event('files_refreshed')


@pytest.mark.asyncio
async def test_single_directory_refresh_sends_directory_events(
        async_client, test_session, test_directory, make_files_structure, events_fixture
):
    """Refreshing a single subdirectory should send directory_refresh events, not global_* events."""
    make_files_structure(['docs/file1.txt', 'videos/file2.txt'])

    # Single directory refresh = refreshing just a subdirectory
    subdirectory = test_directory / 'docs'
    task = FileTask(FileTaskType.refresh, [subdirectory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Should send directory_refresh events (for start and completion)
    events_fixture.assert_has_event('directory_refresh')
    events_fixture.assert_has_event('directory_refresh', 'Refreshing: docs')
    events_fixture.assert_has_event('directory_refresh', 'Refreshed: docs')

    # Should NOT send global_* events
    events_fixture.assert_no_event('global_refresh_started')
    events_fixture.assert_no_event('global_refresh_discovery_completed')
    events_fixture.assert_no_event('global_refresh_modeling_completed')
    events_fixture.assert_no_event('global_refresh_indexing_completed')
    events_fixture.assert_no_event('global_after_refresh_completed')
    events_fixture.assert_no_event('refresh_completed')


@pytest.mark.asyncio
async def test_multiple_paths_refresh_sends_files_refreshed_events(
        async_client, test_session, test_directory, make_files_structure, events_fixture
):
    """Refreshing multiple paths should send files_refreshed events, not global_* events."""
    make_files_structure(['docs/file1.txt', 'videos/file2.txt', 'archives/file3.txt'])

    # Multiple paths refresh
    paths = [test_directory / 'docs', test_directory / 'videos']
    task = FileTask(FileTaskType.refresh, paths, count=2)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Should send files_refreshed events
    events_fixture.assert_has_event('files_refreshed')
    events_fixture.assert_has_event('files_refreshed', 'Refreshing 2 paths')
    events_fixture.assert_has_event('files_refreshed', 'Refreshed 2 paths')

    # Should NOT send global_* events
    events_fixture.assert_no_event('global_refresh_started')
    events_fixture.assert_no_event('global_refresh_discovery_completed')
    events_fixture.assert_no_event('global_refresh_modeling_completed')
    events_fixture.assert_no_event('global_refresh_indexing_completed')
    events_fixture.assert_no_event('global_after_refresh_completed')
    events_fixture.assert_no_event('refresh_completed')

    # Should NOT send directory_refresh (that's for single directory only)
    events_fixture.assert_no_event('directory_refresh')


@pytest.mark.asyncio
async def test_file_worker_refresh_files_directly(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker can refresh specific files without scanning entire directories."""
    # Create some files
    file1, file2 = make_files_structure([
        'docs/file1.txt',
        'docs/file2.txt',
    ])

    # Refresh specific files (not directories)
    task = FileTask(FileTaskType.refresh, [file1, file2])
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Both files should be indexed as FileGroups
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 2

    primary_paths = {str(fg.primary_path) for fg in file_groups}
    assert str(file1) in primary_paths
    assert str(file2) in primary_paths


@pytest.mark.asyncio
async def test_file_worker_refresh_non_primary_file_expands_to_filegroup(
        async_client, test_session, test_directory, video_file_factory
):
    """Refreshing a non-primary file should expand to refresh the entire FileGroup."""
    # Create a FileGroup with multiple files (video + info.json)
    docs_dir = test_directory / 'docs'
    docs_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_file_factory(docs_dir / 'myvideo.mp4')
    info_path = docs_dir / 'myvideo.info.json'
    info_path.write_text('{"title": "test video"}')

    # Refresh only the info.json file (not the primary video file)
    task = FileTask(FileTaskType.refresh, [info_path])
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Should create a single FileGroup with both files
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 1

    fg = file_groups[0]
    file_names = {f['path'] for f in fg.files}
    assert 'myvideo.mp4' in file_names
    assert 'myvideo.info.json' in file_names


@pytest.mark.asyncio
async def test_file_worker_refresh_mixed_files_and_directories(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker can handle mixed files and directories in a single refresh task."""
    # Create files in two directories
    file1, file2, file3 = make_files_structure([
        'docs/doc1.txt',
        'videos/video1.mp4',
        'archives/archive1.html',
    ])

    # Refresh: one specific file + one directory
    subdirectory = test_directory / 'videos'
    task = FileTask(FileTaskType.refresh, [file1, subdirectory], count=1)
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # Should have created FileGroups for the file and the directory contents
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 2

    primary_paths = {str(fg.primary_path) for fg in file_groups}
    assert str(file1) in primary_paths  # The specific file
    assert str(file2) in primary_paths  # From the directory scan

    # The archive file in a different directory should NOT be included
    assert str(file3) not in primary_paths


@pytest.mark.asyncio
async def test_file_worker_refresh_deleted_file(
        async_client, test_session, test_directory, make_files_structure
):
    """FileWorker can handle refreshing a path where the file was deleted.

    When a file is deleted and we refresh its path directly, the FileGroup should
    be removed from the database (since no files exist on disk anymore).
    """
    # Create and index a file
    file1, _baseline = make_files_structure([
        'docs/file1.txt',
        'docs/baseline.txt',  # Keep at least one file so directory exists
    ])

    # First, create the FileGroup
    fg = FileGroup.from_paths(test_session, file1)
    test_session.commit()
    fg_id = fg.id

    # Delete the file from disk
    file1.unlink()

    # Refresh the deleted file path directly (not the directory)
    # This tests that we can find and delete FileGroups by their primary_path
    task = FileTask(FileTaskType.refresh, [file1])
    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    test_session.expire_all()

    # The FileGroup for file1 should be deleted
    assert test_session.query(FileGroup).filter_by(id=fg_id).one_or_none() is None


@pytest.mark.asyncio
async def test_file_worker_refresh_file_skips_count_phase(
        async_client, test_session, test_directory, make_files_structure
):
    """Refreshing files directly should skip the count phase (no count required)."""
    file1, = make_files_structure(['docs/file1.txt'])

    # Create a refresh task WITHOUT count - should work for files
    task = FileTask(FileTaskType.refresh, [file1])
    assert task.count is None  # No count provided

    file_worker.private_queue.put_nowait(task)
    await file_worker.process_queue()

    # File should be indexed without going through count first
    file_groups = test_session.query(FileGroup).all()
    assert len(file_groups) == 1
    assert str(file_groups[0].primary_path) == str(file1)


@pytest.mark.asyncio
async def test_queue_refresh_returns_job_id(async_client, test_session, test_directory, make_files_structure,
                                             await_background_tasks):
    """queue_refresh returns a job_id that can be tracked to completion."""
    make_files_structure(['docs/file1.txt'])

    job_id = file_worker.queue_refresh([test_directory])

    # Job ID should be returned and job should be pending
    assert job_id is not None
    assert job_id.startswith('refresh-')
    assert file_worker.get_job_status(job_id) == 'pending'

    await await_background_tasks()

    # Job should be complete after processing
    assert file_worker.get_job_status(job_id) == 'complete'


@pytest.mark.asyncio
async def test_wait_for_job(async_client, test_session, test_directory, make_files_structure,
                             await_background_tasks):
    """wait_for_job waits for a job to complete."""
    make_files_structure(['docs/file1.txt'])

    job_id = file_worker.queue_refresh([test_directory])

    # Start background task processing (will run concurrently)
    import asyncio
    process_task = asyncio.create_task(await_background_tasks())

    # Wait for the job
    await file_worker.wait_for_job(job_id, timeout=10)

    # Job should be complete
    assert file_worker.get_job_status(job_id) == 'complete'

    await process_task
