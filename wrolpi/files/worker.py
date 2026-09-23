"""File worker queue: refresh, move, and reorganize jobs.

Filesystem compare/discover lives in `wrolpi.files.refresh`.  Move and reorganize
handlers live in `wrolpi.files.move` and `wrolpi.files.reorganize_job`.  This module
owns the job queue, status, and applying compare results (upsert, delete, model).
"""
import asyncio
import json
import os
import pathlib
import queue
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Callable, Set, Dict, List, Tuple

from sqlalchemy import text, or_

from wrolpi import flags
from wrolpi.common import apply_modelers, apply_refresh_cleanup
from wrolpi.common import get_media_directory, logger
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.events import Events
from wrolpi.vars import PYTEST
from wrolpi.files.lib import (
    split_path_stem_and_suffix, _upsert_files, glob_shared_stem,
    group_files_by_stem, choose_primary_file, apply_indexers,
    get_normalized_ignored_directories, remove_files_in_ignored_directories,
)
from wrolpi.files.refresh import (
    FileGroupDiff, FileComparisonResult, classify_file_group_diffs, compare_file_groups,
    count_files, count_files_with_progress, find_directories, GNU_FIND_PRINTF,
    _await_db, _diff_to_paths, _filenames_from_files_json, _stream_filesystem_entries,
)
from wrolpi.files.move import FileMoveMixin, build_move_plan_bulk
from wrolpi.files.reorganize_job import FileReorganizeMixin

logger = logger.getChild(__name__)

# Re-export refresh compare API so existing `from wrolpi.files.worker import compare_file_groups`
# call sites keep working.  Internals used by FileWorker are imported above.

# Update status every N items to avoid excessive overhead
PROGRESS_UPDATE_INTERVAL = 100

# Log if jobs sit queued while the worker reports idle for this long.
QUEUE_STALL_SECONDS = 30

__all__ = [
    'FileGroupDiff',
    'FileComparisonResult',
    'FileWorkerJobFailed',
    'classify_file_group_diffs',
    'compare_file_groups',
    'count_files',
    'file_worker',
    'GNU_FIND_PRINTF',
    'build_move_plan_bulk',
]


class FileWorkerJobFailed(RuntimeError):
    """A tracked file-worker job finished unsuccessfully."""


class FileTaskType(str, Enum):
    count = auto()  # Simply count the files.
    refresh = auto()  # Update the DB to match the files that exist on disk.
    move = auto()  # Move files and directories to a new location, file names are not changed.
    rename = auto()  # Rename files, requires deeper updating of FileGroup.files and FileGroup.data.
    tag = auto()  # Add TagFile records for files.
    reorganize = auto()  # Reorganize files with arbitrary source->dest mappings for collection reorganization.
    batch_reorganize = auto()  # Batch reorganize multiple collections sequentially.


@dataclass
class FileTask:
    task_type: FileTaskType
    paths: list[pathlib.Path]
    destination: pathlib.Path = None  # For move tasks
    count: int = None
    found_directories: set[pathlib.Path] = None  # Directories found during count phase
    unchanged_files: bool = None
    new_files: list[pathlib.Path] = None
    deleted_files: bool = None
    modified_files: bool = None
    prev_task_type: FileTaskType = None
    next_task_type: FileTaskType = None
    job_id: str = None  # Unique ID for tracking completion
    expand_stems: bool = True  # Whether to expand files to their FileGroup stem-mates
    send_events: bool = True  # Whether to notify the user with Events (automatic refreshes set False)
    # For reorganize tasks: list of (source_path, dest_path) tuples
    move_mappings: list[tuple[pathlib.Path, pathlib.Path]] = None
    collection_id: int = None  # Collection being reorganized
    collection_kind: str = None  # 'channel' or 'domain' for reorganize tasks
    # For batch_reorganize tasks
    collection_ids: list[int] = None  # List of collection IDs to process
    batch_kind: str = None  # 'channel' or 'domain'
    # For deferred file_format update (only updated after successful completion)
    pending_file_format: str = None


class FileWorker(FileMoveMixin, FileReorganizeMixin):

    def __init__(self):
        # Use last-in, first out so a task that inserts another task is handled next.
        self.private_queue = asyncio.LifoQueue()
        self._queue_stall_since: float | None = None

    @property
    def public_queue(self) -> Queue:
        from wrolpi.api_utils import api_app
        return api_app.shared_ctx.file_worker_public_queue

    @property
    def status(self) -> dict:
        from wrolpi.api_utils import api_app
        return api_app.shared_ctx.file_worker_status

    def update_status(self, **kwargs):
        """Update file worker status in shared context."""
        from wrolpi.api_utils import api_app
        for key, value in kwargs.items():
            api_app.shared_ctx.file_worker_status[key] = value

    def reset_status(self):
        """Reset status to idle."""
        self.update_status(
            status='idle',
            task_type=None,
            paths=[],
            destination=None,
            error=None,
            operation_total=0,
            operation_processed=0,
            operation_percent=0,
        )

    @property
    def _jobs(self) -> dict:
        """Access the shared job tracking dict."""
        from wrolpi.api_utils import api_app
        return api_app.shared_ctx.file_worker_jobs

    def _set_job_status(self, job_id: str, status: str, error: str | None = None):
        """Set the status of a tracked job.

        Failed jobs store ``{'status': 'failed', 'error': ...}`` so waiters can
        surface the recorded error after ``reset_status()`` clears worker status.
        """
        if not job_id:
            return
        if error is not None:
            self._jobs[job_id] = {'status': status, 'error': error}
        else:
            self._jobs[job_id] = status

    def _complete_job(self, job_id: str):
        """Mark a job as complete."""
        self._set_job_status(job_id, 'complete')

    def _fail_job(self, job_id: str, error: str | BaseException):
        """Mark a job as failed and record the error for waiters."""
        self._set_job_status(job_id, 'failed', error=str(error))

    def get_job_status(self, job_id: str) -> str | None:
        """Get the status of a tracked job."""
        job_status = self._jobs.get(job_id)
        if not job_status:
            raise RuntimeError(f'Job {job_id} does not exist')
        if isinstance(job_status, dict):
            return job_status.get('status')
        return job_status

    def get_job_error(self, job_id: str) -> str | None:
        """Return the recorded error for a failed job, if any."""
        job_status = self._jobs.get(job_id)
        if isinstance(job_status, dict):
            return job_status.get('error')
        return None

    async def wait_for_job(self, job_id: str, timeout: float = 300):
        """Wait for a job to complete or fail.

        In tests (no perpetual file-worker loop) this drains the shared queue
        so the job actually runs.  Production request processes only poll:
        stealing from the public queue reorders work (the private queue is
        LIFO) and can starve the perpetual loop.

        Args:
            job_id: The job ID to wait for
            timeout: Maximum time to wait in seconds (default 5 minutes)

        Raises:
            TimeoutError: If job doesn't complete within timeout
            FileWorkerJobFailed: If the job is marked failed
        """
        start = time.time()
        iteration = 0
        while time.time() - start < timeout:
            iteration += 1
            status = self.get_job_status(job_id)
            if status == 'complete':
                return
            if status == 'failed':
                error = self.get_job_error(job_id) or 'unknown error'
                logger.error(f'wait_for_job: job_id={job_id} failed: {error}')
                raise FileWorkerJobFailed(f'Job {job_id} failed: {error}')
            if PYTEST:
                self.transfer_queue()
                await self.process_queue()
            # Tests poll tightly; production is an IPC round-trip per check.
            await asyncio.sleep(0.01 if PYTEST else 0.1)
        logger.error(f'wait_for_job: TIMEOUT job_id={job_id} after {iteration} iterations')
        raise TimeoutError(f'Job {job_id} did not complete in time')

    def _get_relative_path(self, path: pathlib.Path) -> str:
        """Get relative path from media directory for display in event messages."""
        media_directory = get_media_directory()
        try:
            return str(path.relative_to(media_directory))
        except ValueError:
            return str(path)

    def queue_refresh(self, paths: list[pathlib.Path | str], expand_stems: bool = True,
                      send_events: bool = True) -> str:
        """Queue a refresh task for background processing.

        Args:
            paths: List of file or directory paths to refresh
            expand_stems: Whether to expand files to their FileGroup stem-mates.
                         Set to False when API users explicitly select specific files.
            send_events: Whether to notify the user with Events.  Automatic refreshes
                         (like a Channel refresh before downloading) set this to False.

        Returns:
            A unique job_id that can be used with wait_for_job() to track completion.
        """
        import uuid
        job_id = f'refresh-{uuid.uuid4().hex[:8]}'
        task = FileTask(
            FileTaskType.count,
            paths,
            next_task_type=FileTaskType.refresh,
            job_id=job_id,
            expand_stems=expand_stems,
            send_events=send_events,
        )
        self._set_job_status(job_id, 'pending')
        self.public_queue.put_nowait(task)
        return job_id

    def queue_move(self, destination: pathlib.Path, sources: list[pathlib.Path]) -> str:
        """Queue a move task for background processing.

        Args:
            destination: Target directory (absolute path)
            sources: List of files/directories to move (absolute paths)

        Returns:
            Job ID for tracking completion
        """
        import uuid
        job_id = f'move-{uuid.uuid4().hex[:8]}'
        task = FileTask(FileTaskType.move, sources, destination=destination, job_id=job_id)
        self._set_job_status(job_id, 'pending')
        self.public_queue.put_nowait(task)
        return job_id

    def queue_reorganize(
            self,
            move_mappings: list[tuple[pathlib.Path, pathlib.Path]],
            collection_id: int = None,
            collection_kind: str = None,
            pending_file_format: str = None,
    ) -> str:
        """Queue a reorganize task for collection file reorganization.

        Unlike queue_move which moves all files to a single destination,
        queue_reorganize handles arbitrary source->destination mappings
        where each file can move to a different location.

        Args:
            move_mappings: List of (source_path, dest_path) tuples
            collection_id: Optional collection ID being reorganized (for status tracking)
            collection_kind: 'channel' or 'domain' (for status tracking / navbar navigation)
            pending_file_format: File format to set on collection after successful completion
                                 (deferred update enables retry on failure)

        Returns:
            Job ID for tracking completion
        """
        import uuid
        job_id = f'reorganize-{uuid.uuid4().hex[:8]}'
        # Paths list is empty for reorganize tasks - we use move_mappings instead
        task = FileTask(
            FileTaskType.reorganize,
            paths=[],
            move_mappings=move_mappings,
            collection_id=collection_id,
            collection_kind=collection_kind,
            job_id=job_id,
            pending_file_format=pending_file_format,
        )
        self._set_job_status(job_id, 'pending')
        self.public_queue.put_nowait(task)
        return job_id

    def queue_batch_reorganize(
            self,
            collection_ids: list[int],
            kind: str,
    ) -> str:
        """Queue a batch reorganize task for multiple collections.

        Processes collections sequentially, stopping on first failure.
        Tracks overall progress and per-collection progress.

        Args:
            collection_ids: List of collection IDs to reorganize
            kind: 'channel' or 'domain'

        Returns:
            Batch job ID for tracking completion
        """
        import uuid
        job_id = f'batch-reorganize-{uuid.uuid4().hex[:8]}'
        task = FileTask(
            FileTaskType.batch_reorganize,
            paths=[],
            collection_ids=collection_ids,
            batch_kind=kind,
            job_id=job_id,
        )
        self._set_job_status(job_id, 'pending')
        self.public_queue.put_nowait(task)
        return job_id

    async def refresh_sync(self, paths: list[pathlib.Path], post_processing: bool = True):
        """Synchronously refresh specific files. Use sparingly - prefer queue_refresh."""
        if not paths:
            return
        # `_upsert_file_groups`/`_delete_file_groups`/`_apply_post_processing` all advance the
        # shared status (upserting/deleting/modeling/indexing/cleanup).  Unlike the queued
        # handlers this path has no `process_queue` wrapper to reset it, so reset here or the UI
        # is stranded at the last phase (e.g. 'cleanup' after deleting files).  Mirror
        # `process_queue`: reset to idle only on success, leave a terminal 'error' status on
        # failure (and re-raise so the synchronous caller still sees it).
        try:
            result = await self._refresh_files_directly(paths)
            self._cleanup_modified_models(result.modified)
            await self._delete_file_groups(result.deleted)
            await self._upsert_file_groups(result.new + result.modified)
            if post_processing and (result.new or result.modified or result.deleted):
                # Skip global modelers/indexers when the caller opts out (e.g. `lib.delete` from the
                # upload path defers that to the post-upload `upsert_file`) or when nothing changed.
                # Without this guard a synchronous caller would block on the entire backlog of
                # unindexed files and could exceed Sanic's RESPONSE_TIMEOUT.
                await self._apply_post_processing(is_global_refresh=False)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f'refresh_sync failed for {len(paths)} paths', exc_info=e)
            self.update_status(status='error', error=str(e))
            raise
        else:
            self.reset_status()

    def transfer_queue(self):
        """Transfer items from the public queue to the private queue.

        Uses ``get_nowait()`` in a loop rather than checking ``qsize()`` first:
        the public queue is a multiprocessing.Queue drained by every process, so
        ``qsize() > 0`` followed by ``get_nowait()`` races and raises
        ``queue.Empty``.
        """
        while True:
            try:
                item = self.public_queue.get_nowait()
            except queue.Empty:
                break
            self.private_queue.put_nowait(item)

    def check_queue_stall(self, processed: bool = False) -> None:
        """Log if jobs sit queued while the worker looks idle.

        ``process_queue`` handles one task per tick, so a shrinking backlog is
        not a stall.  Only warn when a tick processed nothing and the queues
        stayed non-empty while status is idle.  This runs inside the pump, so
        it cannot report the pump's own death.
        """
        if processed:
            self._queue_stall_since = None
            return
        try:
            queued = self.public_queue.qsize() + self.private_queue.qsize()
        except Exception:
            return
        if queued and self.status.get('status') == 'idle':
            now = time.time()
            if self._queue_stall_since is None:
                self._queue_stall_since = now
            elif now - self._queue_stall_since >= QUEUE_STALL_SECONDS:
                logger.error(
                    'File worker appears stalled: %s queued job(s) while status is idle for %ss',
                    queued,
                    int(now - self._queue_stall_since),
                )
                self._queue_stall_since = now
        else:
            self._queue_stall_since = None

    async def process_queue(self) -> bool:
        """Process one queued task.  Returns True if a task was handled."""
        try:
            task: FileTask = self.private_queue.get_nowait()
        except asyncio.QueueEmpty:
            # No tasks - clear flag if set and both queues are empty
            if flags.file_worker_busy.is_set() and self.public_queue.qsize() == 0:
                flags.file_worker_busy.clear()
            await asyncio.sleep(0)
            return False

        # Set flag before processing any task (if not already set)
        if not flags.file_worker_busy.is_set():
            flags.file_worker_busy.set()

        try:
            match task.task_type:
                case FileTaskType.count:
                    await self.handle_count(task)
                case FileTaskType.refresh:
                    await self.handle_refresh(task)
                case FileTaskType.move:
                    await self.handle_move(task)
                case FileTaskType.reorganize:
                    await self.handle_reorganize(task)
                case FileTaskType.batch_reorganize:
                    await self.handle_batch_reorganize(task)
        except asyncio.CancelledError:
            self._fail_job(task.job_id, 'File worker task was cancelled')
            raise
        except Exception as e:
            # `handle_count`/`handle_refresh` reset their own status on success (or intentionally
            # leave it set when chaining to a follow-up task), but they have no try/except, so an
            # error mid-phase would otherwise strand the status (e.g. 'counting'/'cleanup') and the
            # UI would show that phase forever.  Record a terminal 'error' status so the worker is
            # not stranded, then re-raise so callers and the perpetual worker loop still see the
            # failure.  (handle_move/handle_reorganize handle their own errors and do not reach here.)
            logger.error(f'FileWorker task {task.task_type} failed', exc_info=e)
            self.update_status(status='error', error=str(e))
            self._fail_job(task.job_id, e)
            raise
        finally:
            # Clear flag if both queues are now empty
            if self.private_queue.qsize() == 0 and self.public_queue.qsize() == 0:
                flags.file_worker_busy.clear()
        return True

    async def handle_count(self, task: FileTask):
        """Count files in the task's paths and chain to next task if specified."""
        self.update_status(
            status='counting',
            task_type=task.next_task_type.name if task.next_task_type else 'count',
            paths=[str(p) for p in task.paths],
            operation_total=0,  # Unknown until complete
            operation_processed=0,
            operation_percent=0,
        )

        with flags.file_worker_counting:
            directories = [pathlib.Path(p) for p in task.paths if pathlib.Path(p).is_dir()]
            files = [pathlib.Path(p) for p in task.paths if pathlib.Path(p).is_file()]

            def update_count(count: int):
                self.update_status(operation_processed=count)

            # Count files in directories with progress updates + individual files
            dir_count = await count_files_with_progress(directories, callback=update_count) if directories else 0
            file_count = len(files)
            total_count = dir_count + file_count

            # Find all directories for tracking in the database
            found_directories = await find_directories(directories) if directories else set()

            self.update_status(operation_total=total_count, operation_processed=total_count, operation_percent=100)
            logger.info(
                f'Counted {total_count} files in {len(task.paths)} paths, found {len(found_directories)} directories')

        if task.next_task_type == FileTaskType.refresh:
            next_task = FileTask(
                FileTaskType.refresh,
                task.paths,
                count=total_count,
                found_directories=found_directories,
                prev_task_type=FileTaskType.count,
                job_id=task.job_id,
                expand_stems=task.expand_stems,
                send_events=task.send_events,
            )
            self.private_queue.put_nowait(next_task)
        else:
            self.reset_status()

    async def handle_refresh(self, task: FileTask):
        from wrolpi.errors import UnknownDirectory

        media_directory = get_media_directory()

        # Check that media directory exists
        if not media_directory.is_dir():
            raise UnknownDirectory('Refusing to refresh because media directory does not exist.')

        # Separate files from directories
        all_paths = [pathlib.Path(p) for p in task.paths]
        file_paths = [p for p in all_paths if p.is_file()]
        dir_paths = [p for p in all_paths if p.is_dir()]
        # Deleted paths might be files or directories - handle as files for FileGroup cleanup
        deleted_paths = [p for p in all_paths if not p.exists()]
        file_paths.extend(deleted_paths)

        # For global refreshes, check that there are non-ignored files
        is_global_refresh = len(dir_paths) == 1 and dir_paths[0] == media_directory and not file_paths
        if is_global_refresh:
            ignored_directories = set(get_normalized_ignored_directories())
            has_non_ignored_files = False
            for item in media_directory.iterdir():
                if item.name.startswith('.'):
                    continue
                if str(item) in ignored_directories:
                    continue
                has_non_ignored_files = True
                break
            if not has_non_ignored_files:
                raise UnknownDirectory(
                    'Refusing to refresh because media directory contains only ignored files or is empty.'
                )

        # Directories require a count first; files do not
        if dir_paths and task.count is None:
            # Missing count for directories, send it back through count first.
            count_task = FileTask(
                FileTaskType.count,
                task.paths,
                next_task_type=FileTaskType.refresh,
                send_events=task.send_events,
            )
            self.private_queue.put_nowait(count_task)
            return

        # Send appropriate start event based on refresh scope
        global_refresh_start_time = None
        if is_global_refresh:
            global_refresh_start_time = time.time()
            logger.info(f'Starting global refresh with {task.count} files')
            flags.global_refresh_active.set()
            Events.send_global_refresh_started()
        elif task.send_events:
            if dir_paths and len(dir_paths) == 1 and not file_paths:
                relative_path = self._get_relative_path(dir_paths[0])
                Events.send_directory_refresh(f'Refreshing: {relative_path}')
            elif file_paths:
                Events.send_files_refreshed(f'Refreshing {len(file_paths)} files')
            else:
                Events.send_files_refreshed(f'Refreshing {len(task.paths)} paths')

        # Process files and directories within discovery flag context
        # This covers comparing, upserting, and deleting phases

        with flags.file_worker_discovery:
            # Process files directly (fast path)
            # expand_stems controls whether to expand files to their FileGroup stem-mates.
            # API callers set expand_stems=False when users explicitly select specific files.
            # Deleted paths (handled above) will still be processed individually.
            if file_paths:
                self.update_status(
                    status='comparing',
                    operation_total=len(file_paths),
                    operation_processed=0,
                    operation_percent=0,
                )
                logger.info(f'Refreshing {len(file_paths)} files directly')
                file_result = await self._refresh_files_directly(file_paths, expand_stems=task.expand_stems)

                # Delete first so a new primary_path cannot collide on (directory, stem)
                # with a duplicate FileGroup that compare already marked deleted.
                self._cleanup_modified_models(file_result.modified)
                await self._delete_file_groups(file_result.deleted)
                await self._upsert_file_groups(file_result.new + file_result.modified)

            # Process directories with full scan (existing path)
            if dir_paths:
                self.update_status(
                    status='comparing',
                    operation_total=task.count,
                    operation_processed=0,
                    operation_percent=0,
                )
                logger.info(f'Comparing {task.count} files in {len(dir_paths)} directories')

                def on_compare_progress(count: int):
                    percent = int((count / task.count) * 100) if task.count > 0 else 0
                    self.update_status(operation_processed=count, operation_percent=percent)

                dir_result = await compare_file_groups(roots=dir_paths, progress_callback=on_compare_progress)
                if is_global_refresh:
                    Events.send_global_refresh_discovery_completed()

                logger.info(
                    f'Refresh comparison: {len(dir_result.new)} new, {len(dir_result.modified)} modified, '
                    f'{len(dir_result.deleted)} deleted, {len(dir_result.unchanged)} unchanged'
                )

                # Delete first so a new primary_path cannot collide on (directory, stem)
                # with a duplicate FileGroup that compare already marked deleted.
                self._cleanup_modified_models(dir_result.modified)
                await self._delete_file_groups(dir_result.deleted)
                await self._upsert_file_groups(dir_result.new + dir_result.modified)

        # Run indexers, modelers, and cleanup once for all changes
        await self._apply_post_processing(is_global_refresh=is_global_refresh)

        # Track directories in the database (use directories found during count phase)
        if dir_paths:
            from wrolpi.files.lib import upsert_directories
            parent_directories = set(dir_paths)
            found_directories = task.found_directories or set()
            found_directories = found_directories - parent_directories
            upsert_directories(parent_directories, found_directories)

        # Clean up directory entries for deleted paths
        if deleted_paths:
            from wrolpi.db import get_db_curs
            with get_db_curs(commit=True) as curs:
                for path in deleted_paths:
                    curs.execute('DELETE FROM directory WHERE path = ?', (str(path.absolute()),))

        # Send appropriate completion event based on refresh scope
        if is_global_refresh:
            elapsed = time.time() - global_refresh_start_time
            message = f'Global refresh completed in {elapsed:.1f} seconds'
            logger.info(message)
            Events.send_global_after_refresh_completed(message)
        elif task.send_events:
            if dir_paths and len(dir_paths) == 1 and not file_paths:
                relative_path = self._get_relative_path(dir_paths[0])
                Events.send_directory_refresh(f'Refreshed: {relative_path}')
            elif file_paths:
                Events.send_files_refreshed(f'Refreshed {len(file_paths)} files')
            else:
                Events.send_files_refreshed(f'Refreshed {len(task.paths)} paths')

        # Set refresh_complete flag only when refreshing the entire media directory
        if is_global_refresh:
            # Refresh statistics for the query planner; without sqlite_stat1 (or after the table
            # contents change wholesale) SQLite picks full scans over the covering indexes.
            from wrolpi.db import get_db_curs
            with get_db_curs(commit=True) as curs:
                curs.execute('PRAGMA optimize')

            flags.refresh_complete.set()
            flags.global_refresh_active.clear()
            # After a DB rebuild, playlists.yaml was imported before any files were indexed, so its
            # file/zim items were skipped.  They are indexed now; re-import to restore them.
            from wrolpi.collections.config import import_playlists_config
            import_playlists_config.activate_switch()

        # Mark job as complete if tracking
        self._complete_job(task.job_id)

        self.reset_status()

    async def _upsert_file_groups(self, diffs: list[FileGroupDiff]):
        """Insert new FileGroups or update modified ones."""
        if not diffs:
            return

        total = len(diffs)
        self.update_status(
            status='upserting',
            operation_total=total,
            operation_processed=0,
            operation_percent=0,
        )

        # For modified diffs where file_group_id exists, we need to handle primary_path changes.
        # If the primary file changed (e.g., video deleted, leaving only poster), the ON CONFLICT
        # won't match, so we need to update the existing FileGroup's primary_path first.
        modified_ids_to_update = []
        for diff in diffs:
            if diff.file_group_id and diff.fs_files:
                # This is a modified FileGroup - may need to update primary_path
                new_paths = [diff.directory / f for f in diff.fs_files]
                new_primary = choose_primary_file(new_paths)
                if new_primary:
                    modified_ids_to_update.append((diff.file_group_id, str(new_primary)))

        # Pre-update primary_paths for modified FileGroups so ON CONFLICT will match
        # Only update if the primary_path is actually changing to avoid unique constraint violations
        # Optimized: batch all checks and updates to reduce N queries to 2
        if modified_ids_to_update:
            with get_db_curs(commit=True) as curs:
                # Build lookup of id -> new_primary_path
                id_to_path = {fg_id: new_path for fg_id, new_path in modified_ids_to_update}
                all_new_paths = list(id_to_path.values())
                all_ids = list(id_to_path.keys())

                # Batch check: find all primary_paths that already exist on OTHER FileGroups
                curs.execute(
                    '''SELECT primary_path, id
                       FROM file_group
                       WHERE primary_path IN (SELECT value FROM json_each(:paths))''',
                    {'paths': json.dumps(all_new_paths)}
                )
                existing_path_to_id = {row[0]: row[1] for row in curs.fetchall()}

                # Filter out updates where the path is already used by a different FileGroup
                valid_updates = []
                for fg_id, new_path in modified_ids_to_update:
                    existing_id = existing_path_to_id.get(new_path)
                    if existing_id is None or existing_id == fg_id:
                        # Path is free OR already belongs to this FileGroup (no change needed)
                        valid_updates.append((fg_id, new_path))
                    else:
                        logger.warning(
                            f'Skipping primary_path update for fg_id={fg_id}: {new_path} already exists')

                # Bulk UPDATE using UPDATE...FROM over a JSON array of [id, new_path] pairs
                if valid_updates:
                    curs.execute(
                        '''UPDATE file_group
                           SET primary_path = v.new_path
                           FROM (SELECT json_extract(value, '$[0]') AS id,
                                        json_extract(value, '$[1]') AS new_path
                                 FROM json_each(:updates)) AS v
                           WHERE file_group.id = v.id
                             AND file_group.primary_path != v.new_path''',
                        {'updates': json.dumps([[fg_id, new_path] for fg_id, new_path in valid_updates])}
                    )

        # Collect all file paths from the diffs (fast operation, no progress tracking needed)
        all_paths = []
        for diff in diffs:
            all_paths.extend(_diff_to_paths(diff))

        # Update total to reflect actual files being processed
        total_files = len(all_paths)
        self.update_status(
            operation_total=total_files,
            operation_processed=0,
            operation_percent=0,
        )

        # Create progress callback for the actual DB upsert operations
        def on_upsert_progress(processed: int, total: int):
            percent = int((processed / total) * 100) if total > 0 else 0
            self.update_status(operation_processed=processed, operation_percent=percent)

        # Use existing _upsert_files function which handles grouping and primary file detection
        await _await_db(_upsert_files, all_paths, on_upsert_progress)
        logger.info(f'Upserted {len(diffs)} FileGroups ({len(all_paths)} files)')

    async def _delete_file_groups(self, diffs: list[FileGroupDiff]):
        """Delete FileGroups where all files have been removed from disk.

        Handles auto-removing tags, Download cleanup, and FileGroup deletion.
        Physical files are already gone - this only cleans up DB records.
        Processes in batches for progress reporting.
        """
        if not diffs:
            return

        file_group_ids = [diff.file_group_id for diff in diffs if diff.file_group_id]
        if not file_group_ids:
            return

        total = len(file_group_ids)
        self.update_status(
            status='deleting',
            operation_total=total,
            operation_processed=0,
            operation_percent=0,
        )

        from wrolpi.downloader import Download, download_manager
        from wrolpi.files.models import FileGroup
        from wrolpi.tags import TagFile, save_tags_config, sync_tags_directory

        # Process in batches for progress reporting
        batch_size = PROGRESS_UPDATE_INTERVAL
        deleted_count = 0
        had_tags = False
        all_urls = []

        for batch_start in range(0, total, batch_size):
            batch_ids = file_group_ids[batch_start:batch_start + batch_size]

            with get_db_session(commit=True) as session:
                # Check if any have tags
                if session.query(TagFile).filter(
                        TagFile.file_group_id.in_(batch_ids)
                ).count() > 0:
                    had_tags = True

                # Get URLs for skip list
                file_groups = session.query(FileGroup).filter(
                    FileGroup.id.in_(batch_ids)
                ).all()

                for fg in file_groups:
                    if fg.url:
                        all_urls.append(fg.url)
                        if Download.get_by_url(session, fg.url):
                            session.query(Download).filter(
                                Download.url == fg.url
                            ).delete(synchronize_session=False)

                # Delete FileGroups (TagFiles cascade-deleted automatically)
                batch_deleted = session.query(FileGroup).filter(
                    FileGroup.id.in_(batch_ids)
                ).delete(synchronize_session=False)
                deleted_count += batch_deleted

            # Update progress
            processed = min(batch_start + batch_size, total)
            percent = int((processed / total) * 100)
            self.update_status(operation_processed=processed, operation_percent=percent)

        # Add URLs to skip list
        for url in all_urls:
            download_manager.add_to_skip_list(url)

        # Trigger tag config saves if needed
        if had_tags:
            save_tags_config.activate_switch()
            sync_tags_directory.activate_switch()

        logger.info(f'Deleted {deleted_count} FileGroups ({len(all_urls)} URLs added to skip list)')

    def _cleanup_modified_models(self, diffs: list[FileGroupDiff]):
        """Delete Videos/Archives/Docs for modified FileGroups where primary file was removed.

        Optimized: uses a single UNION ALL query to fetch all model types at once,
        reducing 3 SELECT queries to 1.
        """
        if not diffs:
            return

        # Get file_group_ids from modified diffs that have removed files
        file_group_ids = [d.file_group_id for d in diffs if d.file_group_id and d.removed_files]
        if not file_group_ids:
            return

        # Build mapping of file_group_id -> removed files
        removed_by_id = {d.file_group_id: d.removed_files for d in diffs if d.file_group_id}

        with get_db_curs(commit=True) as curs:
            # Single UNION ALL query to fetch all models at once (reduces 3 queries to 1)
            curs.execute('''
                         SELECT 'video' AS model_type, v.id AS model_id, fg.id AS fg_id, fg.primary_path
                         FROM video v
                                  JOIN file_group fg ON v.file_group_id = fg.id
                         WHERE fg.id IN (SELECT value FROM json_each(:fg_ids))
                         UNION ALL
                         SELECT 'archive', a.id, fg.id, fg.primary_path
                         FROM archive a
                                  JOIN file_group fg ON a.file_group_id = fg.id
                         WHERE fg.id IN (SELECT value FROM json_each(:fg_ids))
                         UNION ALL
                         SELECT 'doc', d.id, fg.id, fg.primary_path
                         FROM doc d
                                  JOIN file_group fg ON d.file_group_id = fg.id
                         WHERE fg.id IN (SELECT value FROM json_each(:fg_ids))
                         ''', {'fg_ids': json.dumps(file_group_ids)})

            # Group results by model type
            video_ids_to_delete = []
            archive_ids_to_delete = []
            doc_ids_to_delete = []

            for model_type, model_id, fg_id, primary_path in curs.fetchall():
                basename = pathlib.Path(primary_path).name
                if basename in removed_by_id.get(fg_id, set()):
                    if model_type == 'video':
                        video_ids_to_delete.append(model_id)
                    elif model_type == 'archive':
                        archive_ids_to_delete.append(model_id)
                    elif model_type == 'doc':
                        doc_ids_to_delete.append(model_id)

            # Batch delete each model type
            if video_ids_to_delete:
                logger.info(f'Deleting {len(video_ids_to_delete)} Videos whose primary file was removed')
                params = {'ids': json.dumps(video_ids_to_delete)}
                curs.execute('''
                             UPDATE file_group
                             SET model = NULL
                             WHERE id IN (SELECT file_group_id
                                          FROM video
                                          WHERE id IN (SELECT value FROM json_each(:ids)))
                             ''', params)
                curs.execute('DELETE FROM video WHERE id IN (SELECT value FROM json_each(:ids))', params)

            if archive_ids_to_delete:
                logger.info(f'Deleting {len(archive_ids_to_delete)} Archives whose primary file was removed')
                params = {'ids': json.dumps(archive_ids_to_delete)}
                curs.execute('''
                             UPDATE file_group
                             SET model = NULL
                             WHERE id IN (SELECT file_group_id
                                          FROM archive
                                          WHERE id IN (SELECT value FROM json_each(:ids)))
                             ''', params)
                curs.execute('DELETE FROM archive WHERE id IN (SELECT value FROM json_each(:ids))', params)

            if doc_ids_to_delete:
                logger.info(f'Deleting {len(doc_ids_to_delete)} Docs whose primary file was removed')
                params = {'ids': json.dumps(doc_ids_to_delete)}
                curs.execute('''
                             UPDATE file_group
                             SET model = NULL
                             WHERE id IN (SELECT file_group_id
                                          FROM doc
                                          WHERE id IN (SELECT value FROM json_each(:ids)))
                             ''', params)
                curs.execute('DELETE FROM doc WHERE id IN (SELECT value FROM json_each(:ids))', params)

    async def _refresh_files_directly(
            self,
            file_paths: list[pathlib.Path],
            expand_stems: bool = True,
    ) -> FileComparisonResult:
        """Efficiently refresh specific files without scanning entire directories.

        Args:
            file_paths: List of file paths to refresh
            expand_stems: If True, expands each file to its full FileGroup (via glob_shared_stem)
                         so that refreshing a non-primary file refreshes the whole group.
                         If False, only refreshes the exact files specified.

        Returns a FileComparisonResult with diffs for the affected FileGroups.
        """
        from wrolpi.files.models import FileGroup

        # Track deleted file paths separately for special handling
        deleted_paths: set[pathlib.Path] = set()

        # Collect files to process
        all_fs_files: set[pathlib.Path] = set()
        for file_path in file_paths:
            if file_path.is_file():
                if expand_stems:
                    # Expand to all files sharing the same stem (full FileGroup)
                    related = glob_shared_stem(file_path)
                    all_fs_files.update(related)
                else:
                    # Only include the specific file
                    all_fs_files.add(file_path)
            elif not file_path.exists():
                # File was deleted - still try to find related files or process deletion
                deleted_paths.add(file_path)
                if expand_stems:
                    related = glob_shared_stem(file_path)
                    if related:
                        all_fs_files.update(related)
                    else:
                        # No related files exist, add the original path for deletion processing
                        all_fs_files.add(file_path)
                else:
                    all_fs_files.add(file_path)

        # Never index files in ignored directories (playlists/tags hold hard links of already-indexed files, which
        # would otherwise become duplicate FileGroups).  Deleted paths are kept so stale records are still removed.
        existing_files = [i for i in all_fs_files if i.exists()]
        allowed_files = set(remove_files_in_ignored_directories(existing_files))
        all_fs_files = {i for i in all_fs_files if not i.exists() or i in allowed_files}

        if not all_fs_files:
            return FileComparisonResult(unchanged=[], new=[], deleted=[], modified=[])

        # Group files by (directory, stem)
        fs_groups: Dict[Tuple[str, str], Set[str]] = {}
        for file_path in all_fs_files:
            directory = str(file_path.parent)
            stem, _ = split_path_stem_and_suffix(file_path)
            key = (directory, stem)
            if key not in fs_groups:
                fs_groups[key] = set()
            if file_path.exists():
                fs_groups[key].add(file_path.name)

        # Query existing FileGroups that might match our files
        directories = list(set(str(f.parent) for f in all_fs_files))

        # Collect ALL FileGroups per (directory, stem) key — duplicates are deduped after.
        db_groups: Dict[Tuple[str, str], List[Tuple[int, Set[str], float]]] = defaultdict(list)

        with get_db_session() as session:
            # Query FileGroups in our directories
            query = session.query(FileGroup).filter(FileGroup.directory.in_(directories))
            file_groups = query.all()

            for fg in file_groups:
                stem = fg.stem or split_path_stem_and_suffix(fg.primary_path)[0]
                key = (str(fg.directory), stem)
                if key not in fs_groups:
                    continue
                mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                db_groups[key].append((fg.id, _filenames_from_files_json(fg.files), mtime))

            # Track FG IDs already loaded by the directory query to avoid double-appending
            seen_fg_ids: set[int] = set()
            for entries in db_groups.values():
                for fg_id, _, _ in entries:
                    seen_fg_ids.add(fg_id)

            # Also query for FileGroups by primary_path for deleted files
            # This handles cases where the file was deleted and no related files exist
            if deleted_paths:
                deleted_path_strs = [str(p) for p in deleted_paths]
                deleted_fgs = session.query(FileGroup).filter(
                    FileGroup.primary_path.in_(deleted_path_strs),
                    ~FileGroup.id.in_(seen_fg_ids) if seen_fg_ids else True,
                ).all()
                for fg in deleted_fgs:
                    seen_fg_ids.add(fg.id)
                    stem = fg.stem or split_path_stem_and_suffix(fg.primary_path)[0]
                    key = (str(fg.directory), stem)
                    mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                    db_groups[key].append((fg.id, _filenames_from_files_json(fg.files), mtime))
                    if key not in fs_groups:
                        fs_groups[key] = set()

                # Also query for FileGroups contained in deleted directories
                for deleted_path in deleted_paths:
                    deleted_path_str = str(deleted_path)
                    dir_deleted_fgs = session.query(FileGroup).filter(
                        or_(
                            FileGroup.directory == deleted_path_str,
                            FileGroup.directory.like(f'{deleted_path_str}/%')
                        ),
                        ~FileGroup.id.in_(seen_fg_ids) if seen_fg_ids else True,
                    ).all()
                    for fg in dir_deleted_fgs:
                        seen_fg_ids.add(fg.id)
                        stem = fg.stem or split_path_stem_and_suffix(fg.primary_path)[0]
                        key = (str(fg.directory), stem)
                        mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                        db_groups[key].append((fg.id, _filenames_from_files_json(fg.files), mtime))
                        if key not in fs_groups:
                            fs_groups[key] = set()

        result = classify_file_group_diffs(fs_groups, db_groups)
        logger.info(
            f'Direct file refresh: {len(result.unchanged)} unchanged, {len(result.new)} new, '
            f'{len(result.deleted)} deleted, {len(result.modified)} modified'
        )
        return result

    async def _apply_post_processing(self, is_global_refresh: bool = False) -> None:
        """Run modelers, indexers, and cleanup after file operations.

        Args:
            is_global_refresh: If True, send global_* events. Otherwise, skip them.
        """
        from wrolpi.tags import save_tags_config

        def on_modeling_progress(processed: int, total: int):
            percent = int((processed / total) * 100) if total > 0 else 0
            self.update_status(operation_total=total, operation_processed=processed, operation_percent=percent)

        self.update_status(status='modeling', operation_total=0, operation_processed=0, operation_percent=0)
        with flags.file_worker_modeling:
            await apply_modelers(progress_callback=on_modeling_progress)
        if is_global_refresh:
            Events.send_global_refresh_modeling_completed()

        def on_indexing_progress(processed: int, total: int):
            percent = int((processed / total) * 100) if total > 0 else 0
            self.update_status(operation_total=total, operation_processed=processed, operation_percent=percent)

        self.update_status(status='indexing', operation_total=0, operation_processed=0, operation_percent=0)
        with flags.file_worker_indexing:
            await apply_indexers(progress_callback=on_indexing_progress)
        if is_global_refresh:
            Events.send_global_refresh_indexing_completed()

        self.update_status(status='cleanup', operation_total=0, operation_processed=0, operation_percent=0)
        with flags.file_worker_cleanup:
            await apply_refresh_cleanup()
            save_tags_config.activate_switch()


# Each Sanic worker constructs a FileWorker.  The perpetual signal is started
# once, but request handlers (and wait_for_job in tests) can also drain the
# shared public queue in this process.
file_worker = FileWorker()
