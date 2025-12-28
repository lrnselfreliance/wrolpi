"""
File Worker - Unified queue-based file processing.

Handles all file entry points with priority-based processing.
User actions have higher priority than system actions:
- Moves: queue_move() - Priority 10 (highest, user-initiated)
- Manual refresh: queue_refresh() - Priority 20 (user explicitly requested)
- Downloads: queue_download() - Priority 30 (system action after download)
- Global refresh: queue_global_refresh() - Priority 40 (lowest, background)

Two-phase indexing:
- Surface indexing: Fast filename-based indexing (indexed=True)
- Deep indexing: Content extraction by modelers (deep_indexed=True)

All state is stored in Sanic's shared context for cross-process access:
- api_app.shared_ctx.file_worker_queue: Queue for work items
- api_app.shared_ctx.file_worker_data: Dict for progress/state
- api_app.shared_ctx.file_worker_lock: Lock to ensure single worker
"""

import asyncio
import pathlib
import queue
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, Enum
from typing import Dict, List, Optional

from wrolpi.common import logger, get_media_directory
from wrolpi.dates import now
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# VACUUM is disabled during testing by default for performance.
# Use the `enable_vacuum` fixture to enable it for specific tests.
DISABLE_VACUUM = bool(PYTEST)


class Priority(IntEnum):
    """Processing priority levels. Lower = higher priority.

    User actions have higher priority than system actions.
    """
    MOVE = 10  # Highest - user-initiated, expects immediate feedback
    MANUAL_REFRESH = 20  # High - user explicitly requested refresh
    DOWNLOAD = 30  # Normal - system action after download completes
    GLOBAL_REFRESH = 40  # Low - background full refresh


class JobStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PARTIAL = 'partial'  # Completed with some errors


@dataclass
class GlobalProgress:
    """Aggregate progress across all jobs."""
    total_jobs: int = 0
    active_jobs: int = 0
    completed_jobs: int = 0
    total_files: int = 0
    processed_files: int = 0
    surface_indexed: int = 0
    deep_indexed: int = 0
    modeled: int = 0
    jobs: Dict = field(default_factory=dict)
    move_jobs: Dict = field(default_factory=dict)


def _serialize_queue_item(priority: Priority, added_at: datetime, path: pathlib.Path,
                          job_id: str, is_directory: bool, operation: str = 'refresh') -> dict:
    """Serialize a queue item to a dict for multiprocessing Queue."""
    return {
        'priority': int(priority),
        'added_at': added_at.isoformat(),
        'path': str(path.resolve()),
        'job_id': job_id,
        'is_directory': is_directory,
        'operation': operation,
    }


def _deserialize_queue_item(item: dict) -> dict:
    """Deserialize a queue item from the multiprocessing Queue."""
    return {
        'priority': Priority(item['priority']),
        'added_at': datetime.fromisoformat(item['added_at']),
        'path': pathlib.Path(item['path']),
        'job_id': item['job_id'],
        'is_directory': item['is_directory'],
        'operation': item['operation'],
    }


# ============================================================
# SharedStateManager - Cross-process state management
# ============================================================

class SharedStateManager:
    """Manages cross-process state via Sanic's shared_ctx.

    All state is stored in multiprocessing-safe data structures:
    - file_worker_queue: Queue for work items
    - file_worker_data: Dict for progress/state/jobs
    - file_worker_lock: Lock for single-worker guarantee

    This class provides a clean interface for reading/writing
    shared state without exposing the implementation details.
    """

    def _get_shared_ctx(self):
        """Get the shared context, handling test mode."""
        from wrolpi.api_utils import api_app
        return api_app.shared_ctx

    def get_queue(self):
        """Get the cross-process queue."""
        return self._get_shared_ctx().file_worker_queue

    def get_lock(self):
        """Get the cross-process lock for single worker guarantee."""
        return self._get_shared_ctx().file_worker_lock

    def _get_data(self) -> dict:
        """Get the cross-process data dict."""
        return self._get_shared_ctx().file_worker_data

    def _init_data_if_needed(self):
        """Initialize data dict structure if not already set."""
        data = self._get_data()
        if 'jobs' not in data:
            data['jobs'] = {}
        if 'move_jobs' not in data:
            data['move_jobs'] = {}
        if 'running' not in data:
            data['running'] = False
        if 'failed_items' not in data:
            data['failed_items'] = []
        if 'idempotency' not in data:
            data['idempotency'] = None

    # ---- Jobs State ----

    def get_jobs(self) -> dict:
        """Get jobs dict from shared context."""
        self._init_data_if_needed()
        return dict(self._get_data().get('jobs', {}))

    def set_jobs(self, jobs: dict):
        """Set jobs dict in shared context."""
        self._init_data_if_needed()
        self._get_data()['jobs'] = dict(jobs)

    # ---- Move Jobs State ----

    def get_move_jobs(self) -> dict:
        """Get move_jobs dict from shared context."""
        self._init_data_if_needed()
        return dict(self._get_data().get('move_jobs', {}))

    def set_move_jobs(self, move_jobs: dict):
        """Set move_jobs dict in shared context."""
        self._init_data_if_needed()
        self._get_data()['move_jobs'] = dict(move_jobs)

    # ---- Failed Items State ----

    def get_failed_items(self) -> list:
        """Get failed_items list from shared context."""
        self._init_data_if_needed()
        return list(self._get_data().get('failed_items', []))

    def add_failed_item(self, item: dict):
        """Add a failed item to the retry list."""
        self._init_data_if_needed()
        data = self._get_data()
        failed = list(data.get('failed_items', []))
        failed.append(item)
        data['failed_items'] = failed

    def clear_failed_items(self):
        """Clear failed_items in shared context."""
        self._init_data_if_needed()
        self._get_data()['failed_items'] = []

    # ---- Idempotency State ----

    def get_idempotency(self) -> Optional[datetime]:
        """Get idempotency timestamp from shared context."""
        self._init_data_if_needed()
        val = self._get_data().get('idempotency')
        if val and isinstance(val, str):
            return datetime.fromisoformat(val)
        return val

    def set_idempotency(self, value: Optional[datetime]):
        """Set idempotency timestamp in shared context."""
        self._init_data_if_needed()
        if value:
            self._get_data()['idempotency'] = value.isoformat()
        else:
            self._get_data()['idempotency'] = None

    # ---- Running State ----

    def is_running(self) -> bool:
        """Check if worker is running."""
        self._init_data_if_needed()
        return self._get_data().get('running', False)

    def set_running(self, value: bool):
        """Set worker running state."""
        self._init_data_if_needed()
        self._get_data()['running'] = value


# ============================================================
# JobTracker - Job lifecycle and progress management
# ============================================================

class JobTracker:
    """Tracks job creation, progress, and completion.

    Jobs are stored in SharedStateManager but this class
    provides the business logic for job lifecycle.
    """

    def __init__(self, state: SharedStateManager):
        self._state = state

    # ---- Job Creation ----

    def create_refresh_job(self, job_type: str) -> str:
        """Create a new refresh job and return its ID."""
        job_id = str(uuid.uuid4())
        jobs = self._state.get_jobs()
        jobs[job_id] = {
            'job_id': job_id,
            'job_type': job_type,
            'status': JobStatus.PENDING.value,
            'total_items': 0,
            'processed_items': 0,
            'surface_indexed': 0,
            'deep_indexed': 0,
            'modeled': 0,
            'errors': 0,
            'error_paths': [],
            'created_at': now().isoformat(),
            'started_at': None,
            'completed_at': None,
        }
        self._state.set_jobs(jobs)
        return job_id

    def create_move_job(self, sources: List[pathlib.Path], destination: pathlib.Path) -> str:
        """Create a new move job and return its ID."""
        job_id = str(uuid.uuid4())

        # Store job progress
        jobs = self._state.get_jobs()
        jobs[job_id] = {
            'job_id': job_id,
            'job_type': 'move',
            'status': JobStatus.PENDING.value,
            'total_items': len(sources),
            'processed_items': 0,
            'errors': 0,
            'error_paths': [],
            'created_at': now().isoformat(),
            'started_at': None,
            'completed_at': None,
        }
        self._state.set_jobs(jobs)

        # Store move metadata
        move_jobs = self._state.get_move_jobs()
        move_jobs[job_id] = {
            'sources': [str(s) for s in sources],
            'destination': str(destination),
        }
        self._state.set_move_jobs(move_jobs)

        return job_id

    # ---- Job Updates ----

    def update_job(self, job_id: str, updates: dict):
        """Update a specific job in shared context."""
        jobs = self._state.get_jobs()
        if job_id in jobs:
            job = dict(jobs[job_id])
            job.update(updates)
            jobs[job_id] = job
            self._state.set_jobs(jobs)

    def mark_running(self, job_id: str):
        """Mark a job as running with timestamp."""
        self.update_job(job_id, {
            'status': JobStatus.RUNNING.value,
            'started_at': now().isoformat(),
        })

    def mark_completed(self, job_id: str, errors: int = 0):
        """Mark a job as completed or partial (if errors)."""
        status = JobStatus.COMPLETED.value if errors == 0 else JobStatus.PARTIAL.value
        self.update_job(job_id, {
            'status': status,
            'completed_at': now().isoformat(),
        })

    def mark_failed(self, job_id: str, error_msg: str):
        """Mark a job as failed."""
        self.update_job(job_id, {
            'status': JobStatus.FAILED.value,
            'errors': 1,
            'error_paths': [error_msg],
            'completed_at': now().isoformat(),
        })

    def increment_processed(self, job_id: str, surface_indexed: bool = True):
        """Increment the processed count for a job."""
        jobs = self._state.get_jobs()
        if job_id in jobs:
            job = dict(jobs[job_id])
            # Set status to RUNNING if still PENDING
            if job.get('status') == JobStatus.PENDING.value:
                job['status'] = JobStatus.RUNNING.value
                job['started_at'] = now().isoformat()
            job['processed_items'] = job.get('processed_items', 0) + 1
            if surface_indexed:
                job['surface_indexed'] = job.get('surface_indexed', 0) + 1
            jobs[job_id] = job
            self._state.set_jobs(jobs)

    def increment_total(self, job_id: str, count: int):
        """Increment the total items count for a job."""
        jobs = self._state.get_jobs()
        if job_id in jobs:
            job = dict(jobs[job_id])
            # Set status to RUNNING if still PENDING (directory expansion means we're working)
            if job.get('status') == JobStatus.PENDING.value:
                job['status'] = JobStatus.RUNNING.value
                job['started_at'] = now().isoformat()
            job['total_items'] = job.get('total_items', 0) + count
            jobs[job_id] = job
            self._state.set_jobs(jobs)

    def add_error(self, job_id: str, path: pathlib.Path):
        """Add an error to a job."""
        jobs = self._state.get_jobs()
        if job_id in jobs:
            job = dict(jobs[job_id])
            job['errors'] = job.get('errors', 0) + 1
            error_paths = list(job.get('error_paths', []))
            error_paths.append(str(path))
            job['error_paths'] = error_paths
            jobs[job_id] = job
            self._state.set_jobs(jobs)

    # ---- Progress Reporting ----

    def get_progress(self) -> GlobalProgress:
        """Get current progress across all jobs."""
        jobs = self._state.get_jobs()

        # Separate move jobs from other jobs
        move_jobs = {k: v for k, v in jobs.items() if v.get('job_type') == 'move'}
        other_jobs = {k: v for k, v in jobs.items() if v.get('job_type') != 'move'}

        progress = GlobalProgress(
            total_jobs=len(jobs),
            active_jobs=sum(1 for j in jobs.values()
                           if j.get('status') == JobStatus.RUNNING.value),
            completed_jobs=sum(1 for j in jobs.values()
                              if j.get('status') in (JobStatus.COMPLETED.value, JobStatus.PARTIAL.value)),
            jobs=dict(other_jobs),
            move_jobs=dict(move_jobs),
        )

        for job in jobs.values():
            progress.total_files += job.get('total_items', 0)
            progress.processed_files += job.get('processed_items', 0)
            progress.surface_indexed += job.get('surface_indexed', 0)
            progress.deep_indexed += job.get('deep_indexed', 0)
            progress.modeled += job.get('modeled', 0)

        return progress

    def cleanup_completed_jobs(self):
        """Remove completed jobs older than 5 seconds.

        Jobs are kept briefly after completion so the UI can show them as complete
        before they disappear.
        """
        jobs = self._state.get_jobs()
        cutoff = (now() - timedelta(seconds=5)).isoformat()

        cleaned = {k: v for k, v in jobs.items()
                   if v.get('status') not in (JobStatus.COMPLETED.value, JobStatus.PARTIAL.value, JobStatus.FAILED.value)
                   or (v.get('completed_at') and v.get('completed_at') > cutoff)}

        if len(cleaned) != len(jobs):
            self._state.set_jobs(cleaned)

    def get_progress_dict(self) -> dict:
        """Get progress as a JSON-serializable dict for API responses.

        Also cleans up old completed jobs before returning progress.
        """
        self.cleanup_completed_jobs()

        progress = self.get_progress()
        return {
            'total_jobs': progress.total_jobs,
            'active_jobs': progress.active_jobs,
            'completed_jobs': progress.completed_jobs,
            'total_files': progress.total_files,
            'processed_files': progress.processed_files,
            'surface_indexed': progress.surface_indexed,
            'deep_indexed': progress.deep_indexed,
            'modeled': progress.modeled,
            'jobs': progress.jobs,
            'move_jobs': progress.move_jobs,
        }

    # ---- Move Job Helpers ----

    def pop_move_data(self, job_id: str) -> Optional[dict]:
        """Pop and return move data for a job, or None if not found."""
        move_jobs = self._state.get_move_jobs()
        if job_id not in move_jobs:
            return None
        move_data = move_jobs.pop(job_id)
        self._state.set_move_jobs(move_jobs)
        return move_data

    def finalize_running_jobs(self):
        """Mark all RUNNING or PENDING jobs (with progress) as complete.

        Used by run_sync() to finalize jobs after queue processing.
        """
        jobs = self._state.get_jobs()
        for job_id, job in jobs.items():
            status = job.get('status')
            # Mark RUNNING or PENDING jobs (with processed items) as complete
            if status == JobStatus.RUNNING.value or (status == JobStatus.PENDING.value and job.get('processed_items', 0) > 0):
                job = dict(job)
                job['status'] = JobStatus.COMPLETED.value if job.get('errors', 0) == 0 else JobStatus.PARTIAL.value
                job['completed_at'] = now().isoformat()
                jobs[job_id] = job
        self._state.set_jobs(jobs)


# ============================================================
# FileWorker - Main orchestrator
# ============================================================

class FileWorker:
    """
    Unified file worker with cross-process queue and progress tracking.

    Delegates state management to SharedStateManager and job tracking to JobTracker.
    This class orchestrates the processing pipeline and exposes the public API.

    Usage:
        # Production (async)
        file_worker.queue_download(path)
        # Worker runs in background via perpetual_signal

        # Testing (sync)
        file_worker.queue_refresh(paths)
        file_worker.run_sync()  # Blocks until complete
    """

    def __init__(self):
        # Helper classes for state and job management
        self._state = SharedStateManager()
        self._jobs = JobTracker(self._state)

        # Local state only - not shared across processes
        self._sync_mode: bool = False
        self._seen_paths: set = set()  # Local set for O(1) deduplication
        self._found_directories: set = set()  # Directories found during expansion
        self._refresh_paths: List[pathlib.Path] = []  # Paths being refreshed (for stale deletion)
        self._send_events: bool = False  # Whether to send events during refresh

    # ============================================================
    # Entry Points
    # ============================================================

    def queue_download(self, path: pathlib.Path) -> str:
        """Queue a downloaded file for immediate indexing."""
        return self._queue_paths([path], Priority.DOWNLOAD, 'download')

    def queue_move(self, sources: List[pathlib.Path],
                   destination: pathlib.Path) -> str:
        """Queue a move operation.

        Creates a job to track the move, stores metadata for later execution.
        The actual move is performed by execute_move() which should be called
        after queuing.

        Args:
            sources: List of paths to move
            destination: Target directory

        Returns:
            job_id for tracking progress
        """
        return self._jobs.create_move_job(sources, destination)

    async def execute_move(self, job_id: str) -> bool:
        """Execute a queued move operation.

        Uses the existing move() function from lib.py which handles:
        - File movement with rollback on failure
        - Tag preservation
        - DB path updates
        - Indexing and modeling

        Args:
            job_id: The job ID from queue_move()

        Returns:
            True if move succeeded, False otherwise
        """
        move_data = self._jobs.pop_move_data(job_id)
        if move_data is None:
            logger.error(f'Move job {job_id} not found')
            return False

        jobs = self._state.get_jobs()
        if job_id not in jobs:
            logger.error(f'Job progress not found for {job_id}')
            return False

        # Convert back to Path objects (stored as strings for serialization)
        sources = [pathlib.Path(s) for s in move_data['sources']]
        destination = pathlib.Path(move_data['destination'])

        # Update job status to running
        self._jobs.mark_running(job_id)

        try:
            from wrolpi.files.lib import move
            from wrolpi.db import get_db_session

            with get_db_session(commit=True) as session:
                await move(session, destination, *sources)

            self._jobs.update_job(job_id, {
                'status': JobStatus.COMPLETED.value,
                'processed_items': len(sources),
                'completed_at': now().isoformat(),
            })
            logger.info(f'Move job {job_id} completed successfully')
            return True

        except Exception as e:
            logger.error(f'Move job {job_id} failed: {e}', exc_info=e)
            self._jobs.mark_failed(job_id, str(e))
            return False

    def queue_refresh(self, paths: List[pathlib.Path],
                      priority: Priority = Priority.MANUAL_REFRESH) -> str:
        """Queue paths for refresh."""
        return self._queue_paths(paths, priority, 'refresh')

    def queue_global_refresh(self) -> str:
        """Queue full media directory refresh."""
        media_dir = get_media_directory()
        return self._queue_paths([media_dir], Priority.GLOBAL_REFRESH, 'global')

    def _queue_paths(self, paths: List[pathlib.Path],
                     priority: Priority, job_type: str) -> str:
        """Internal: Add paths to queue with deduplication."""
        from wrolpi import flags

        # Set phase flags for UI progress display
        flags.refreshing.set()
        flags.refresh_discovery.set()

        # Create job via JobTracker
        job_id = self._jobs.create_refresh_job(job_type)

        q = self._state.get_queue()
        added = 0

        for path in paths:
            path = pathlib.Path(path).resolve()
            path_key = str(path)

            # Deduplication check using local set - O(1) lookup
            if path_key in self._seen_paths:
                continue

            self._seen_paths.add(path_key)

            item = _serialize_queue_item(
                priority=priority,
                added_at=now(),
                path=path,
                job_id=job_id,
                is_directory=path.is_dir(),
            )
            q.put(item)
            added += 1

        # Update job total
        self._jobs.update_job(job_id, {'total_items': added})
        logger.info(f'Queued {added} paths for {job_type} (job_id={job_id})')
        return job_id

    # ============================================================
    # Queue Management
    # ============================================================

    def queue_size(self) -> int:
        """Get current queue size."""
        return self._state.get_queue().qsize()

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue_size() == 0

    def clear(self):
        """Clear the queue and all tracking state."""
        # Clear queue
        q = self._state.get_queue()
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break

        # Clear all shared state
        self._seen_paths.clear()
        self._found_directories.clear()
        self._refresh_paths.clear()
        self._state.set_jobs({})
        self._state.set_move_jobs({})
        self._state.clear_failed_items()
        self._state.set_idempotency(None)

    def get_progress(self) -> GlobalProgress:
        """Get current progress across all jobs."""
        return self._jobs.get_progress()

    def get_progress_dict(self) -> dict:
        """Get progress as a JSON-serializable dict for API responses."""
        return self._jobs.get_progress_dict()

    # ============================================================
    # Processing
    # ============================================================

    def _expand_batch_by_stem(self, items: List[dict], q: queue.PriorityQueue) -> List[dict]:
        """
        Expand the batch to include any same-stem files remaining in the queue.

        This prevents files with the same stem from ending up in separate batches,
        which would create orphaned FileGroups (e.g., video without its thumbnail).

        Args:
            items: List of file items already pulled from queue
            q: The priority queue to check for same-stem files

        Returns:
            Expanded list of items including any same-stem files from queue
        """
        from wrolpi.files.lib import split_path_stem_and_suffix

        if not items:
            return items

        # Collect stems in current batch: {(directory, stem): True}
        batch_stems = {}
        for item in items:
            path = item['path']
            stem, _ = split_path_stem_and_suffix(path)
            key = (str(path.parent), stem)
            batch_stems[key] = True

        # Check queue for same-stem files
        remaining = []
        additional = []

        # Drain queue temporarily to check for matching stems
        while True:
            try:
                raw_item = q.get_nowait()
                temp_item = _deserialize_queue_item(raw_item)
                if temp_item['is_directory']:
                    # Keep directories in remaining
                    remaining.append(raw_item)
                else:
                    path = temp_item['path']
                    stem, _ = split_path_stem_and_suffix(path)
                    key = (str(path.parent), stem)
                    if key in batch_stems:
                        # Same stem as something in batch - add to batch
                        additional.append(temp_item)
                    else:
                        # Different stem - put back
                        remaining.append(raw_item)
            except queue.Empty:
                break

        # Put non-matching items back in queue
        for raw_item in remaining:
            q.put(raw_item)

        if additional:
            logger.debug(f'Expanded batch with {len(additional)} same-stem files')

        return items + additional

    async def process_batch(self, batch_size: int = 100) -> int:
        """
        Process a batch of queue items.

        Returns number of files processed.
        """
        if self.is_empty():
            return 0

        # Set idempotency timestamp for this batch
        if self._state.get_idempotency() is None:
            self._state.set_idempotency(now())

        q = self._state.get_queue()

        # Pull items from queue
        items: List[dict] = []
        while len(items) < batch_size:
            try:
                item = q.get_nowait()
                items.append(_deserialize_queue_item(item))
            except queue.Empty:
                break

        if not items:
            return 0

        # Sort by priority (lower = higher priority)
        items.sort(key=lambda x: (x['priority'], x['added_at']))

        # Separate files from directories
        files = [i for i in items if not i['is_directory']]
        directories = [i for i in items if i['is_directory']]

        # Expand batch to include same-stem files from queue
        # This prevents files with the same stem from being split across batches,
        # which would create orphaned FileGroups.
        files = self._expand_batch_by_stem(files, q)

        # Expand directories lazily - add children back to queue
        for dir_item in directories:
            await self._expand_directory(dir_item)

        # Process files
        processed = 0
        if files:
            processed = await self._process_files(files)

        # Update job progress for each processed file
        for item in files:
            self._jobs.increment_processed(item['job_id'])

        # Allow cancellation
        await asyncio.sleep(0)

        return processed

    async def _expand_directory(self, dir_item: dict):
        """Expand a directory into its children."""
        path = dir_item['path']
        job_id = dir_item['job_id']
        priority = dir_item['priority']

        # Track this directory for later upsert
        self._found_directories.add(path)

        try:
            children = list(path.iterdir())
        except PermissionError as e:
            logger.error(f'Permission denied: {path}', exc_info=e)
            return
        except Exception as e:
            logger.error(f'Error listing {path}', exc_info=e)
            return

        # Update job total (also sets status to RUNNING if PENDING)
        self._jobs.increment_total(job_id, len(children))

        # Add children to queue
        q = self._state.get_queue()

        for child in children:
            path_key = str(child)
            if path_key in self._seen_paths:
                continue

            self._seen_paths.add(path_key)

            item = _serialize_queue_item(
                priority=priority,
                added_at=now(),
                path=child,
                job_id=job_id,
                is_directory=child.is_dir(),
            )
            q.put(item)

    async def _process_files(self, items: List[dict]) -> int:
        """
        Process files - surface indexing using batch SQL.

        Uses _upsert_files for fast batch surface indexing.
        Files become visible immediately (indexed=True).
        Deep indexing (content extraction) happens separately via modelers.
        """
        from wrolpi.files.lib import _upsert_files, remove_files_in_ignored_directories

        # Filter to only files that exist
        paths = [i['path'] for i in items if i['path'].is_file()]

        if not paths:
            return 0

        # Remove ignored files
        paths = remove_files_in_ignored_directories(paths)

        if not paths:
            return 0

        try:
            # Batch surface indexing via raw SQL
            idempotency = self._state.get_idempotency()
            _upsert_files(paths, idempotency)
            return len(paths)
        except Exception as e:
            logger.error(f'Error in batch surface indexing', exc_info=e)
            # Track failed items for retry
            for item in items:
                if item['path'] in paths:
                    self._state.add_failed_item(_serialize_queue_item(
                        priority=item['priority'],
                        added_at=item['added_at'],
                        path=item['path'],
                        job_id=item['job_id'],
                        is_directory=item['is_directory'],
                    ))
            return 0

    # ============================================================
    # Error Handling
    # ============================================================

    async def retry_failed(self) -> int:
        """Retry failed items once."""
        failed_items = self._state.get_failed_items()
        if not failed_items:
            return 0

        self._state.clear_failed_items()

        logger.info(f'Retrying {len(failed_items)} failed items')

        retried = 0
        for serialized_item in failed_items:
            item = _deserialize_queue_item(serialized_item)
            try:
                await self._process_files([item])
                retried += 1
            except Exception as e:
                logger.warning(f'Retry failed for {item["path"]}: {e}')
                # Mark job as having errors
                self._jobs.add_error(item['job_id'], item['path'])

        return retried

    # ============================================================
    # Full Refresh Pipeline
    # ============================================================

    async def _delete_stale_files(self, paths: List[pathlib.Path], idempotency: datetime):
        """Delete FileGroup records that were not updated during refresh."""
        from wrolpi.db import get_db_curs

        with get_db_curs(commit=True) as curs:
            # Build WHERE clause for paths
            conditions = []
            for p in paths:
                p_str = str(p)
                conditions.append(curs.mogrify('(directory = %s OR directory LIKE %s)', (p_str, f'{p_str}/%')).decode())
            wheres = ' OR '.join(conditions) if conditions else ''

            idempotency_str = curs.mogrify('%s', (idempotency,)).decode()
            if wheres:
                stmt = f'''
                    DELETE FROM file_group
                    WHERE (idempotency != {idempotency_str}::timestamptz OR idempotency is null)
                    AND ({wheres})
                '''
                curs.execute(stmt)

    async def _apply_indexers(self):
        """Index FileGroups that have not yet been deep indexed by modelers."""
        from wrolpi.db import get_db_session, get_db_curs
        from wrolpi.files.lib import sanitize_filename_surrogates
        from wrolpi.files.models import FileGroup

        logger.info('Applying indexers')

        while True:
            # Continually query for Files that have not been deep indexed.
            with get_db_session(commit=False) as session:
                file_groups = session.query(FileGroup).filter(
                    FileGroup.indexed == True,  # Surface indexed (visible)
                    FileGroup.deep_indexed != True,  # Not yet deep indexed
                ).limit(200)
                file_groups: List[FileGroup] = list(file_groups)

                if not file_groups:
                    break

                processed = 0
                for file_group in file_groups:
                    processed += 1
                    try:
                        file_group.do_index()
                    except Exception:
                        # Error has already been logged in .do_index.
                        if PYTEST:
                            raise
                    # Always mark the FileGroup as deep indexed. We won't try to index it again.
                    file_group.deep_indexed = True

                    # Sleep to catch cancel.
                    await asyncio.sleep(0)

                # Commit may fail due to invalid UTF-8 surrogates in paths
                try:
                    session.commit()
                except UnicodeEncodeError as e:
                    session.rollback()
                    logger.warning(f'UnicodeEncodeError during indexer commit, attempting to fix: {e}')
                    # Find and fix the problematic file(s) by re-querying after rollback
                    fg_ids = [fg.id for fg in file_groups if fg.id]
                    session.expire_all()
                    file_groups = session.query(FileGroup).filter(FileGroup.id.in_(fg_ids)).all()

                    for fg in file_groups:
                        try:
                            # Check if primary_path has surrogates
                            primary_path_str = str(fg.primary_path)
                            try:
                                primary_path_str.encode('utf-8')
                            except UnicodeEncodeError:
                                sanitized = sanitize_filename_surrogates(fg.primary_path)
                                logger.info(f'Sanitized primary_path: {fg.primary_path} -> {sanitized}')
                                fg.primary_path = sanitized

                            # Check if files JSON has surrogates
                            if fg.files:
                                new_files = []
                                for f in fg.files:
                                    path_val = f.get('path', '')
                                    path_str = str(path_val) if path_val else ''
                                    try:
                                        path_str.encode('utf-8')
                                        new_files.append(f)
                                    except UnicodeEncodeError:
                                        sanitized = sanitize_filename_surrogates(pathlib.Path(path_str))
                                        logger.info(f'Sanitized file path: {path_str} -> {sanitized}')
                                        new_files.append({**f, 'path': str(sanitized)})
                                fg.files = new_files
                        except Exception as fix_error:
                            logger.error(f'Failed to sanitize path for FileGroup {fg.id}: {fix_error}',
                                         exc_info=fix_error)
                        # Re-mark as indexed (rollback undid this)
                        fg.indexed = True

                    # Retry commit after fixing
                    try:
                        session.commit()
                    except UnicodeEncodeError as e2:
                        # Still failing - skip these files and continue
                        session.rollback()
                        logger.error(f'Failed to fix UnicodeEncodeError, skipping batch: {e2}')
                        # Mark as indexed in a separate transaction so we don't loop forever
                        with get_db_curs(commit=True) as curs:
                            curs.execute('UPDATE file_group SET indexed = TRUE WHERE id = ANY(%s)', (fg_ids,))
                        continue

    async def _vacuum_if_enabled(self):
        """Run VACUUM ANALYZE on file_group table if enabled.

        VACUUM reclaims space and ANALYZE updates statistics for query planning.
        Disabled during testing by default for performance.
        """
        if DISABLE_VACUUM:
            return

        logger.info('Running VACUUM ANALYZE on file_group table')
        from wrolpi.db import get_db_curs
        import psycopg2.extensions

        # VACUUM cannot run inside a transaction, need autocommit mode
        with get_db_curs(commit=False) as curs:
            curs.connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            curs.execute('VACUUM ANALYZE file_group')
            curs.connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)

        logger.info('VACUUM ANALYZE completed')

    # ============================================================
    # Sync/Async Modes
    # ============================================================

    def set_sync_mode(self, enabled: bool):
        """Enable synchronous mode for testing."""
        self._sync_mode = enabled

    def run_sync(self, batch_size: int = 100):
        """
        Process queue synchronously until empty.

        For testing only - blocks until complete.
        """
        import asyncio

        async def _run():
            while not self.is_empty():
                await self.process_batch(batch_size)

            # Retry failed items
            failed = self._state.get_failed_items()
            if failed:
                await self.retry_failed()

            # Mark jobs complete via JobTracker
            self._jobs.finalize_running_jobs()

        # Run the async function
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a task
            asyncio.create_task(_run())
        else:
            loop.run_until_complete(_run())

    async def run_async(self):
        """
        Main async processing loop.

        Called by perpetual_signal in production.
        Uses lock to ensure only one worker runs across all Sanic processes.

        Phase flags are set in _queue_paths() and cleared here/in _cleanup():
        - refresh_discovery: Set on queue, cleared when queue empties
        - refresh_modeling/indexing/cleanup: Set in _run_deep_indexing()
        - refreshing: Set on queue, cleared in _cleanup()
        """
        from wrolpi import flags

        if self.is_empty():
            return

        # Try to acquire lock - if another process is running, skip
        lock = self._state.get_lock()
        if not lock.acquire(blocking=False):
            return

        try:
            self._state.set_running(True)
            await self.process_batch()

            # If queue empty, transition to deep indexing phases
            if self.is_empty():
                # Clear discovery flag - moving to deep indexing
                flags.refresh_discovery.clear()

                await self.retry_failed()
                await self._run_deep_indexing()
                await self._cleanup()
        finally:
            self._state.set_running(False)
            lock.release()

    async def run_queue_to_completion(self, paths: List[pathlib.Path] = None, send_events: bool = True) -> str:
        """
        Queue paths and process to completion. Mirrors production flow.

        Uses run_async() which handles flags, deep indexing, and cleanup.
        Sets _refresh_paths so _cleanup() will do stale file deletion.
        """
        from wrolpi.errors import UnknownDirectory
        from wrolpi.events import Events

        # Default to media directory
        if paths is None:
            media_directory = get_media_directory()
            if not media_directory.exists():
                raise UnknownDirectory(f'Media directory does not exist: {media_directory}')
            if not any(media_directory.iterdir()):
                raise UnknownDirectory(f'Media directory is empty: {media_directory}')
            paths = [media_directory]
        elif isinstance(paths, (str, pathlib.Path)):
            paths = [pathlib.Path(paths)]

        # Track refresh paths - _cleanup() will use these for stale deletion and directory upserts
        self._refresh_paths = list(paths)
        self._send_events = send_events
        for p in paths:
            if p.is_dir():
                self._found_directories.add(p)

        if send_events:
            Events.send_global_refresh_started()

        job_id = self.queue_refresh(paths)

        # Process queue until empty (mirrors perpetual signal)
        # run_async() handles flags, deep indexing, cleanup
        while not self.is_empty():
            await self.run_async()

        return job_id

    async def _run_deep_indexing(self):
        """Run modeling and indexing phases after surface indexing completes."""
        from wrolpi import flags
        from wrolpi.common import apply_modelers, apply_refresh_cleanup
        from wrolpi.events import Events

        # Delete stale files first (before deep indexing tries to read them)
        # Only happens if _refresh_paths was set (via run_queue_to_completion)
        if self._refresh_paths:
            idempotency = self._state.get_idempotency()
            if idempotency:
                await self._delete_stale_files(self._refresh_paths, idempotency)

        if self._send_events:
            Events.send_global_refresh_discovery_completed()

        # Phase 2: Deep indexing via modelers (extracts metadata like PDF content)
        with flags.refresh_modeling:
            await apply_modelers()

        if self._send_events:
            Events.send_global_refresh_modeling_completed()

        # Phase 3: Index remaining files not handled by modelers
        with flags.refresh_indexing:
            await self._apply_indexers()

        if self._send_events:
            Events.send_global_refresh_indexing_completed()

        # Phase 4: Cleanup stale records
        with flags.refresh_cleanup:
            await apply_refresh_cleanup()

    async def _cleanup(self):
        """Cleanup after queue is empty."""
        from wrolpi import flags
        from wrolpi.db import get_db_session
        from wrolpi.events import Events
        from wrolpi.files.models import Directory
        from wrolpi.files.lib import upsert_directories

        jobs = self._state.get_jobs()
        had_global_refresh = any(
            job.get('job_type') == 'global'
            for job in jobs.values()
        )

        # Upsert directories found during expansion (also deletes stale directories)
        if self._refresh_paths:
            with get_db_session() as session:
                parent_directories = {i[0] for i in session.query(Directory.path).filter(Directory.path.in_(self._refresh_paths))}
                parent_directories |= set(filter(lambda i: i.is_dir(), self._refresh_paths))
            upsert_directories(parent_directories, self._found_directories)

        if self._send_events:
            Events.send_global_after_refresh_completed()

        # Clear jobs so completed jobs don't linger in UI
        self._state.set_jobs({})

        # Clear refreshing flag (was set in _queue_paths)
        flags.refreshing.clear()

        # Set refresh_complete flag if we did a global refresh
        if had_global_refresh:
            flags.refresh_complete.set()

        if self._send_events:
            Events.send_refresh_completed()

        # Clear all tracking state for next batch
        self._seen_paths.clear()
        self._found_directories.clear()
        self._refresh_paths.clear()
        self._send_events = False
        self._state.set_idempotency(None)


# ============================================================
# Global Instance
# ============================================================

file_worker = FileWorker()


# ============================================================
# Perpetual Signal Registration
# ============================================================

async def file_worker_loop():
    """Background worker loop for processing the file queue."""
    if file_worker.is_empty():
        return

    await file_worker.run_async()


# Register as perpetual signal - runs every 0.1 seconds when there's work
from wrolpi.api_utils import perpetual_signal

file_worker_loop = perpetual_signal(sleep=0.1)(file_worker_loop)


# ============================================================
# Pytest Fixture Support
# ============================================================

def get_file_worker_for_testing() -> FileWorker:
    """Get a fresh file worker for testing."""
    worker = FileWorker()
    worker.set_sync_mode(True)
    return worker
