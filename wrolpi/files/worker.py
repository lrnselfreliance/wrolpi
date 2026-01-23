"""
File comparison worker for comparing database FileGroups to filesystem state.

This module provides memory-efficient comparison of potentially millions of files
on resource-constrained devices like Raspberry Pi.
"""
import asyncio
import os
import pathlib
import shlex
import shutil
import stat as stat_module
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from multiprocessing.queues import Queue
from pathlib import Path
from typing import AsyncGenerator, Callable, Set, Dict, List, Tuple

from sqlalchemy import text, or_

from wrolpi import flags
from wrolpi.common import get_media_directory, get_wrolpi_config, logger, walk, chunks, unique_by_predicate
from wrolpi.dates import now
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import NoPrimaryFile
from wrolpi.events import Events
from wrolpi.common import apply_modelers, apply_refresh_cleanup
from wrolpi.files.lib import (
    split_path_stem_and_suffix, _upsert_files, get_unique_files_by_stem, glob_shared_stem,
    group_files_by_stem, get_primary_file, delete_directory, apply_indexers,
    _move_file_group_files, _bulk_update_file_groups_db, MOVE_CHUNK_SIZE,
)

logger = logger.getChild(__name__)

# Update status every N items to avoid excessive overhead
PROGRESS_UPDATE_INTERVAL = 100

__all__ = [
    'FileGroupDiff',
    'FileComparisonResult',
    'compare_file_groups',
    'count_files',
    'file_worker',
]


@dataclass
class FileGroupDiff:
    """Represents changes needed for a FileGroup."""
    directory: Path | str
    stem: str
    db_files: Set[str] = field(default_factory=set)  # Filenames in DB
    fs_files: Set[str] = field(default_factory=set)  # Filenames on filesystem
    file_group_id: int | None = None

    @property
    def added_files(self) -> Set[str]:
        """Files on disk but not in DB."""
        return self.fs_files - self.db_files

    @property
    def removed_files(self) -> Set[str]:
        """Files in DB but not on disk."""
        return self.db_files - self.fs_files

    @property
    def is_new(self) -> bool:
        """FileGroup doesn't exist in DB."""
        return self.file_group_id is None and bool(self.fs_files)

    @property
    def is_deleted(self) -> bool:
        """All files deleted from disk."""
        return not self.fs_files and bool(self.db_files)

    @property
    def needs_update(self) -> bool:
        """FileGroup exists but files changed (not completely deleted)."""
        return (self.file_group_id is not None
                and bool(self.added_files or self.removed_files)
                and bool(self.fs_files))  # Not deleted - still has files on disk

    @property
    def is_unchanged(self) -> bool:
        """FileGroup matches filesystem exactly."""
        return self.db_files == self.fs_files and bool(self.db_files)


@dataclass
class FileComparisonResult:
    """Result of comparing DB to filesystem at FileGroup level."""
    unchanged: list  # FileGroupDiff where is_unchanged
    new: list  # FileGroupDiff where is_new
    deleted: list  # FileGroupDiff where is_deleted
    modified: list  # FileGroupDiff where needs_update


def _diff_to_paths(diff: FileGroupDiff) -> list[pathlib.Path]:
    """Convert a FileGroupDiff to full file paths."""
    directory = pathlib.Path(diff.directory)
    return [directory / filename for filename in diff.fs_files]


def _get_normalized_ignored_directories() -> list[str]:
    """Get ignored directories as absolute paths.

    Matches the normalization logic in remove_files_in_ignored_directories().
    """
    ignored = list(map(str, get_wrolpi_config().ignored_directories))
    media_dir = get_media_directory()
    result = []
    for d in ignored:
        p = pathlib.Path(d)
        if not p.is_absolute():
            result.append(str(media_dir / d))
        else:
            result.append(d)
    return result


async def count_files(directories: list[Path]) -> int:
    """Lightning-fast file count using find | wc -l.

    Uses the same find arguments as _stream_filesystem_paths for consistency.
    Excludes directories listed in get_wrolpi_config().ignored_directories.
    Pipes to wc -l to avoid loading all paths into Python memory.
    """
    if not directories:
        return 0

    # Build find arguments with ignored directory exclusions
    find_args = [shlex.quote(str(d)) for d in directories]
    find_args.extend(['-type', 'f', '-not', '-path', "'*/.*'"])

    # Add exclusions for each ignored directory
    for ignored in _get_normalized_ignored_directories():
        find_args.extend(['-not', '-path', shlex.quote(f'{ignored}/*')])

    cmd = f"find {' '.join(find_args)} | wc -l"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await proc.communicate()
        return int(stdout.strip())
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def count_files_with_progress(
        directories: list[Path],
        callback: Callable[[int], None] = None,
        batch_size: int = 1000,
) -> int:
    """Count files with progress updates.

    Streams find output and calls callback with running count every batch_size files.
    Excludes hidden files and directories listed in ignored_directories config.
    """
    if not directories:
        return 0

    find_args = [str(d) for d in directories]
    find_args.extend(['-type', 'f', '-not', '-path', '*/.*'])
    for ignored in _get_normalized_ignored_directories():
        find_args.extend(['-not', '-path', f'{ignored}/*'])

    proc = await asyncio.create_subprocess_exec(
        'find', *find_args,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        count = 0
        async for line in proc.stdout:
            count += 1
            if callback and count % batch_size == 0:
                callback(count)
                await asyncio.sleep(0)  # Yield for cancellation
        if callback:
            callback(count)  # Final count
        await proc.wait()
        return count
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def find_directories(directories: list[Path]) -> set[Path]:
    """Find all subdirectories using find command.

    Excludes hidden directories and ignored directories from config.
    """
    if not directories:
        return set()

    find_args = [str(d) for d in directories]
    find_args.extend(['-type', 'd', '-not', '-path', '*/.*'])
    for ignored in _get_normalized_ignored_directories():
        find_args.extend(['-not', '-path', f'{ignored}/*'])

    proc = await asyncio.create_subprocess_exec(
        'find', *find_args,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        found = set()
        count = 0
        async for line in proc.stdout:
            found.add(Path(line.decode().strip()))
            count += 1
            if count % 100 == 0:
                await asyncio.sleep(0)  # Yield for cancellation
        await proc.wait()
        return found
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def _stream_filesystem_paths(root: Path) -> AsyncGenerator[str, None]:
    """Stream file paths using find command. Memory efficient and cancellable.

    Excludes hidden files and ignored directories from config.
    """
    # Build find arguments with ignored directory exclusions
    find_args = [str(root), '-type', 'f', '-not', '-path', '*/.*']
    for ignored in _get_normalized_ignored_directories():
        find_args.extend(['-not', '-path', f'{ignored}/*'])

    proc = await asyncio.create_subprocess_exec(
        'find', *find_args,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        async for line in proc.stdout:
            path = line.decode().rstrip('\n')
            if path:
                yield path
        await proc.wait()
    finally:
        # Kill subprocess if still running (handles both normal exit and cancellation)
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


def _insert_fs_batch(session, batch: list):
    """Bulk insert filesystem files using unnest for speed."""
    if not batch:
        return
    session.execute(
        text("""
             INSERT INTO fs_files (directory, filename, stem)
             SELECT *
             FROM unnest(
                     CAST(:dirs AS text[]),
                     CAST(:files AS text[]),
                     CAST(:stems AS text[])
                  )
             ON CONFLICT DO NOTHING
             """),
        {
            "dirs": [b[0] for b in batch],
            "files": [b[1] for b in batch],
            "stems": [b[2] for b in batch],
        }
    )


async def compare_file_groups(root: Path = None, batch_size: int = 10000) -> FileComparisonResult:
    """
    Compare FileGroups in DB to filesystem. Memory efficient for Raspberry Pi.

    Uses a temporary PostgreSQL table to handle millions of files without
    loading everything into Python memory.

    Returns which FileGroups are new, deleted, modified, or unchanged.

    This function is async and cancellable - when cancelled, it will terminate
    the subprocess scanning the filesystem.
    """
    root = root or get_media_directory()

    with get_db_session() as session:
        # Create temp table for filesystem files with computed stems
        session.execute(text("""
                             CREATE TEMP TABLE IF NOT EXISTS fs_files
                             (
                                 directory TEXT NOT NULL,
                                 filename  TEXT NOT NULL,
                                 stem      TEXT NOT NULL,
                                 PRIMARY KEY (directory, filename)
                             ) ON COMMIT DROP
                             """))
        session.execute(text("TRUNCATE fs_files"))

        # Stream filesystem files into temp table with stems
        batch = []
        file_count = 0
        path_gen = _stream_filesystem_paths(root)
        try:
            async for path in path_gen:
                p = Path(path)
                directory = str(p.parent)
                filename = p.name
                stem, _ = split_path_stem_and_suffix(p)
                batch.append((directory, filename, stem))

                if len(batch) >= batch_size:
                    _insert_fs_batch(session, batch)
                    file_count += len(batch)
                    batch = []
                    await asyncio.sleep(0)  # Cancellation yield point
        finally:
            await path_gen.aclose()  # Ensure subprocess is killed on cancellation

        if batch:
            _insert_fs_batch(session, batch)
            file_count += len(batch)

        logger.info(f'Scanned {file_count} files from filesystem')

        # Index for fast grouping
        session.execute(text("CREATE INDEX IF NOT EXISTS fs_files_stem_idx ON fs_files(directory, stem)"))
        session.execute(text("ANALYZE fs_files"))

        # Get filesystem files grouped by (directory, stem)
        fs_groups: Dict[Tuple[str, str], Set[str]] = {}
        result = session.execute(text("""
                                      SELECT directory, stem, array_agg(filename) as files
                                      FROM fs_files
                                      GROUP BY directory, stem
                                      """))
        for row in result:
            fs_groups[(row.directory, row.stem)] = set(row.files)

        logger.info(f'Found {len(fs_groups)} file groups on filesystem')

        # Get all DB FileGroups within root directory (both with files and empty)
        # Include modification_datetime for mtime comparison
        db_groups: Dict[Tuple[str, str], Tuple[int, Set[str], float]] = {}  # key -> (id, files, mtime_timestamp)
        root_str = str(root)

        # Initialize result lists before the loop so empty FileGroups can be processed inline
        unchanged = []
        new = []
        deleted = []
        modified = []
        empty_count = 0

        result = session.execute(text("""
                                      SELECT fg.id,
                                             fg.directory,
                                             fg.primary_path,
                                             fg.files IS NULL OR fg.files = '[]'::jsonb   as is_empty,
                                             EXTRACT(EPOCH FROM fg.modification_datetime) as mtime_epoch,
                                             CASE
                                                 WHEN fg.files IS NOT NULL AND jsonb_typeof(fg.files) = 'array' AND
                                                      fg.files != '[]'::jsonb
                                                     THEN (SELECT array_agg(f ->> 'path')
                                                           FROM jsonb_array_elements(fg.files) as f)
                                                 ELSE NULL
                                                 END                                      as files
                                      FROM file_group fg
                                      WHERE fg.directory IS NOT NULL
                                        AND (fg.directory = :root OR fg.directory LIKE :root_pattern)
                                      """), {"root": root_str, "root_pattern": f"{root_str}/%"})

        for row in result:
            if row.is_empty:
                # Process empty FileGroup immediately (no intermediate list)
                empty_count += 1
                stem, _ = split_path_stem_and_suffix(Path(row.primary_path))
                key = (row.directory, stem)
                fs_files = fs_groups.pop(key, set())  # Remove from fs_groups to avoid double-processing
                diff = FileGroupDiff(
                    directory=Path(row.directory),
                    stem=stem,
                    db_files=set(),
                    fs_files=fs_files,
                    file_group_id=row.id,
                )
                if fs_files:
                    # Files exist on disk but not in DB - update the FileGroup
                    modified.append(diff)
                else:
                    # No files on disk and no files in DB - delete the FileGroup
                    deleted.append(diff)
            elif row.files:
                # Compute stem from first file (all files in group share stem)
                first_file = row.files[0]
                stem, _ = split_path_stem_and_suffix(Path(row.directory) / first_file)
                db_groups[(row.directory, stem)] = (row.id, set(row.files), row.mtime_epoch or 0)

        logger.info(f'Found {len(db_groups)} file groups in database')
        if empty_count:
            logger.debug(f'Found {empty_count} FileGroups with empty files arrays')

        # Recompute all_keys after removing empty FileGroup keys from fs_groups
        all_keys = set(fs_groups.keys()) | set(db_groups.keys())

        for key in all_keys:
            directory, stem = key
            fs_files = fs_groups.get(key, set())
            db_id, db_files, db_mtime = db_groups.get(key, (None, set(), 0))

            diff = FileGroupDiff(
                directory=Path(directory),
                stem=stem,
                db_files=db_files,
                fs_files=fs_files,
                file_group_id=db_id,
            )

            if diff.is_new:
                new.append(diff)
            elif diff.is_deleted:
                deleted.append(diff)
            elif diff.needs_update:
                modified.append(diff)
            elif diff.is_unchanged:
                # Files match by name - check if content changed via mtime
                # Get max mtime from filesystem files
                try:
                    dir_path = Path(directory)
                    fs_mtime = max(
                        (dir_path / filename).stat().st_mtime
                        for filename in fs_files
                    )
                    # If filesystem mtime is newer than DB mtime, content changed
                    if fs_mtime > float(db_mtime) + 0.001:  # small tolerance for float comparison
                        modified.append(diff)
                    else:
                        unchanged.append(diff)
                except (OSError, ValueError):
                    # If we can't stat files, treat as unchanged
                    unchanged.append(diff)

        logger.info(
            f'Comparison complete: {len(unchanged)} unchanged, {len(new)} new, '
            f'{len(deleted)} deleted, {len(modified)} modified'
        )

        return FileComparisonResult(
            unchanged=unchanged,
            new=new,
            deleted=deleted,
            modified=modified,
        )


async def build_move_plan_bulk(
        sources: list[pathlib.Path],
        destination: pathlib.Path,
) -> Tuple[Dict[pathlib.Path, pathlib.Path], list[pathlib.Path]]:
    """
    Build move plan using bulk SQL operations instead of per-source queries.

    Uses a temp table pattern similar to compare_file_groups for O(1) query complexity.

    Args:
        sources: List of file/directory paths to move
        destination: Target directory

    Returns:
        Tuple of (plan dict mapping old_primary_path -> new_primary_path,
                  list of old_directories for cleanup)
    """
    from wrolpi.files.models import FileGroup

    plan: Dict[pathlib.Path, pathlib.Path] = dict()
    old_directories: list[pathlib.Path] = list(unique_by_predicate(
        i if i.is_dir() else i.parent for i in sources
    ))

    # Deduplicate sources by stem
    sources = list(get_unique_files_by_stem(sources))
    logger.info(f'build_move_plan_bulk: processing {len(sources)} sources')

    # Partition sources into files, directories, and deleted (pre-moved)
    # Optimized: single stat() call per path instead of up to 3 (is_file, is_dir, exists)
    file_sources: list[pathlib.Path] = []
    dir_sources: list[pathlib.Path] = []
    deleted_sources: list[pathlib.Path] = []

    for source in sources:
        try:
            st = source.stat()
            if stat_module.S_ISREG(st.st_mode):
                file_sources.append(source)
            elif stat_module.S_ISDIR(st.st_mode):
                dir_sources.append(source)
            # Other types (symlinks, etc.) are silently skipped
        except FileNotFoundError:
            deleted_sources.append(source)

    with get_db_session() as session:
        # Create temp table for source paths
        session.execute(text("""
                             CREATE TEMP TABLE IF NOT EXISTS move_sources
                             (
                                 source_path      TEXT PRIMARY KEY,
                                 source_type      TEXT NOT NULL,
                                 source_directory TEXT
                             ) ON COMMIT DROP
                             """))
        session.execute(text("TRUNCATE move_sources"))

        # Collect all paths to insert: file paths + expanded directory contents
        all_file_paths: list[pathlib.Path] = []

        # For files, collect the file and its shared-stem siblings
        for source in file_sources:
            files = glob_shared_stem(source)
            all_file_paths.extend(files)

        # For directories, walk and collect all files
        dir_file_mapping: Dict[pathlib.Path, pathlib.Path] = {}  # file -> source_dir
        for source_dir in dir_sources:
            for f in walk(source_dir):
                if f.is_file():
                    all_file_paths.append(f)
                    dir_file_mapping[f] = source_dir

        # Deduplicate
        all_file_paths = list(set(all_file_paths))

        # Bulk insert file paths into temp table
        if all_file_paths:
            paths_data = [(str(p), 'file', str(p.parent)) for p in all_file_paths]
            session.execute(
                text("""
                     INSERT INTO move_sources (source_path, source_type, source_directory)
                     SELECT *
                     FROM unnest(
                             CAST(:paths AS text[]),
                             CAST(:types AS text[]),
                             CAST(:dirs AS text[])
                          )
                     ON CONFLICT DO NOTHING
                     """),
                {
                    "paths": [p[0] for p in paths_data],
                    "types": [p[1] for p in paths_data],
                    "dirs": [p[2] for p in paths_data],
                }
            )

        # Also insert deleted sources (for pre-moved files lookup)
        if deleted_sources:
            deleted_data = [(str(p), 'deleted', str(p.parent)) for p in deleted_sources]
            session.execute(
                text("""
                     INSERT INTO move_sources (source_path, source_type, source_directory)
                     SELECT *
                     FROM unnest(
                             CAST(:paths AS text[]),
                             CAST(:types AS text[]),
                             CAST(:dirs AS text[])
                          )
                     ON CONFLICT DO NOTHING
                     """),
                {
                    "paths": [p[0] for p in deleted_data],
                    "types": [p[1] for p in deleted_data],
                    "dirs": [p[2] for p in deleted_data],
                }
            )

        # Single bulk query to get all FileGroups matching our sources
        result = session.execute(text("""
                                      SELECT fg.id, fg.primary_path, fg.directory, ms.source_path, ms.source_type
                                      FROM file_group fg
                                               JOIN move_sources ms ON fg.primary_path = ms.source_path
                                      """))

        # Build lookup of found FileGroups
        fg_by_path: Dict[str, Tuple[int, str, str]] = {}  # path -> (id, primary_path, directory)
        for row in result:
            fg_by_path[row.source_path] = (row.id, row.primary_path, row.directory)

        logger.info(f'build_move_plan_bulk: found {len(fg_by_path)} FileGroups for {len(all_file_paths)} files')

        # Build plan for file sources (direct files, not from directories)
        file_source_set = set()
        for source in file_sources:
            files = glob_shared_stem(source)
            file_source_set.update(str(f) for f in files)

        # Process files from direct file sources
        for path_str, (fg_id, primary_path, directory) in fg_by_path.items():
            path = pathlib.Path(path_str)
            primary_path = pathlib.Path(primary_path)

            # Is this from a file source or a directory source?
            if path_str in file_source_set:
                # Direct file source -> destination / filename
                new_path = destination / primary_path.name
            elif path in dir_file_mapping:
                # From directory source -> destination / source_dir.name / relative_path
                source_dir = dir_file_mapping[path]
                new_path = destination / source_dir.name / primary_path.relative_to(source_dir)
            else:
                # Deleted source (pre-moved) -> destination / filename
                new_path = destination / primary_path.name

            # Check for conflicts (destination exists)
            if new_path.exists():
                if not primary_path.exists():
                    # Pre-moved - OK to proceed
                    plan[primary_path] = new_path
                else:
                    raise FileExistsError(f'Cannot move: {new_path} already exists')
            else:
                plan[primary_path] = new_path

        # Handle files not in DB - create FileGroups
        found_paths = set(fg_by_path.keys())
        missing_db_files = [p for p in all_file_paths if str(p) not in found_paths and p.exists()]

        if missing_db_files:
            logger.info(f'build_move_plan_bulk: creating FileGroups for {len(missing_db_files)} files not in DB')
            for paths in group_files_by_stem(missing_db_files):
                try:
                    get_primary_file(paths)
                    fg = FileGroup.from_paths(session, *paths)
                    session.flush()

                    # Determine destination path
                    if any(str(p) in file_source_set for p in paths):
                        new_path = destination / fg.primary_path.name
                    else:
                        # Find which directory source this came from
                        source_dir = None
                        for p in paths:
                            if p in dir_file_mapping:
                                source_dir = dir_file_mapping[p]
                                break
                        if source_dir:
                            new_path = destination / source_dir.name / fg.primary_path.relative_to(source_dir)
                        else:
                            new_path = destination / fg.primary_path.name

                    if new_path.exists() and fg.primary_path.exists():
                        raise FileExistsError(f'Cannot move: {new_path} already exists')
                    plan[fg.primary_path] = new_path

                except NoPrimaryFile:
                    for file in paths:
                        fg = FileGroup.from_paths(session, file)
                        session.flush()
                        if any(str(p) in file_source_set for p in paths):
                            new_path = destination / fg.primary_path.name
                        elif file in dir_file_mapping:
                            source_dir = dir_file_mapping[file]
                            new_path = destination / source_dir.name / fg.primary_path.relative_to(source_dir)
                        else:
                            new_path = destination / fg.primary_path.name
                        if new_path.exists() and fg.primary_path.exists():
                            raise FileExistsError(f'Cannot move: {new_path} already exists')
                        plan[fg.primary_path] = new_path

        # Add directories to plan for cleanup
        for source_dir in dir_sources:
            for directory in (i for i in walk(source_dir) if i.is_dir()):
                new_directory = destination / source_dir.name / directory.relative_to(source_dir)
                plan[directory] = new_directory

        # Commit to drop the temporary table
        session.commit()

    # Sort plan by depth (deepest first) for safe move ordering
    plan = OrderedDict(
        sorted(plan.items(), key=lambda i: (len(i[0].parents), i[0].name), reverse=True)
    )

    logger.info(f'build_move_plan_bulk: plan has {len(plan)} items')
    return plan, old_directories


class FileTaskType(str, Enum):
    count = auto()  # Simply count the files.
    refresh = auto()  # Update the DB to match the files that exist on disk.
    move = auto()  # Move files and directories to a new location, file names are not changed.
    rename = auto()  # Rename files, requires deeper updating of FileGroup.files and FileGroup.data.
    tag = auto()  # Add TagFile records for files.


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


class FileWorker:

    def __init__(self):
        # Use last-in, first out so a task that inserts another task is handled next.
        self.private_queue = asyncio.LifoQueue()

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

    def _set_job_status(self, job_id: str, status: str):
        """Set the status of a tracked job."""
        self._jobs[job_id] = status

    def _complete_job(self, job_id: str):
        """Mark a job as complete."""
        if job_id:
            self._set_job_status(job_id, 'complete')

    def get_job_status(self, job_id: str) -> str | None:
        """Get the status of a tracked job."""
        job_status = self._jobs.get(job_id)
        if not job_status:
            raise RuntimeError(f'Job {job_id} does not exist')
        return job_status

    async def wait_for_job(self, job_id: str, timeout: float = 300):
        """Wait for a job to complete.

        Transfers and processes the queue while waiting to ensure jobs are actually executed.
        This is especially important in tests and synchronous contexts.

        Args:
            job_id: The job ID to wait for
            timeout: Maximum time to wait in seconds (default 5 minutes)

        Raises:
            TimeoutError: If job doesn't complete within timeout
        """
        import time
        start = time.time()
        iteration = 0
        while time.time() - start < timeout:
            iteration += 1
            status = self.get_job_status(job_id)
            if status == 'complete':
                return
            # Transfer from public to private queue, then process
            self.transfer_queue()
            await self.process_queue()
            await asyncio.sleep(0.01)
        logger.error(f'wait_for_job: TIMEOUT job_id={job_id} after {iteration} iterations')
        raise TimeoutError(f'Job {job_id} did not complete in time')

    def _get_relative_path(self, path: pathlib.Path) -> str:
        """Get relative path from media directory for display in event messages."""
        media_directory = get_media_directory()
        try:
            return str(path.relative_to(media_directory))
        except ValueError:
            return str(path)

    def queue_refresh(self, paths: list[pathlib.Path | str], expand_stems: bool = True) -> str:
        """Queue a refresh task for background processing.

        Args:
            paths: List of file or directory paths to refresh
            expand_stems: Whether to expand files to their FileGroup stem-mates.
                         Set to False when API users explicitly select specific files.

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

    async def refresh_sync(self, paths: list[pathlib.Path]):
        """Synchronously refresh specific files. Use sparingly - prefer queue_refresh."""
        if not paths:
            return
        result = await self._refresh_files_directly(paths)
        self._cleanup_modified_models(result.modified)
        await self._upsert_file_groups(result.new + result.modified)
        await self._delete_file_groups(result.deleted)
        await self._apply_post_processing(is_global_refresh=False)

    def transfer_queue(self):
        """Transfer items from the public queue to the private queue."""
        while self.public_queue.qsize() > 0:
            item = self.public_queue.get_nowait()
            self.private_queue.put_nowait(item)

    async def process_queue(self):
        try:
            task: FileTask = self.private_queue.get_nowait()
        except asyncio.QueueEmpty:
            # No file tasks to perform. Sleep to catch cancel.
            await asyncio.sleep(0)
            return

        match task.task_type:
            case FileTaskType.count:
                await self.handle_count(task)
            case FileTaskType.refresh:
                await self.handle_refresh(task)
            case FileTaskType.move:
                await self.handle_move(task)

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
            ignored_directories = set(_get_normalized_ignored_directories())
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
            )
            self.private_queue.put_nowait(count_task)
            return

        # Send appropriate start event based on refresh scope
        if is_global_refresh:
            Events.send_global_refresh_started()
        elif dir_paths and len(dir_paths) == 1 and not file_paths:
            relative_path = self._get_relative_path(dir_paths[0])
            Events.send_directory_refresh(f'Refreshing: {relative_path}')
        elif file_paths:
            Events.send_files_refreshed(f'Refreshing {len(file_paths)} files')
        else:
            Events.send_files_refreshed(f'Refreshing {len(task.paths)} paths')

        # Process files directly (fast path)
        # expand_stems controls whether to expand files to their FileGroup stem-mates.
        # API callers set expand_stems=False when users explicitly select specific files.
        # Deleted paths (handled above) will still be processed individually.
        file_result = None
        if file_paths:
            self.update_status(
                status='comparing',
                operation_total=len(file_paths),
                operation_processed=0,
                operation_percent=0,
            )
            logger.info(f'Refreshing {len(file_paths)} files directly')
            file_result = await self._refresh_files_directly(file_paths, expand_stems=task.expand_stems)

            # Process file results
            self._cleanup_modified_models(file_result.modified)
            await self._upsert_file_groups(file_result.new + file_result.modified)
            await self._delete_file_groups(file_result.deleted)

        # Process directories with full scan (existing path)
        dir_result = None
        if dir_paths:
            self.update_status(
                status='comparing',
                operation_total=task.count,
                operation_processed=0,
                operation_percent=0,
            )
            logger.info(f'Comparing {task.count} files in {len(dir_paths)} directories')

            root = dir_paths[0] if len(dir_paths) == 1 else None
            dir_result = await compare_file_groups(root=root)
            if is_global_refresh:
                Events.send_global_refresh_discovery_completed()

            logger.info(
                f'Refresh comparison: {len(dir_result.new)} new, {len(dir_result.modified)} modified, '
                f'{len(dir_result.deleted)} deleted, {len(dir_result.unchanged)} unchanged'
            )

            # Process directory results
            self._cleanup_modified_models(dir_result.modified)
            await self._upsert_file_groups(dir_result.new + dir_result.modified)
            await self._delete_file_groups(dir_result.deleted)

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
                    curs.execute('DELETE FROM directory WHERE path = %s', (str(path.absolute()),))

        # Send appropriate completion event based on refresh scope
        if is_global_refresh:
            Events.send_global_after_refresh_completed()
            Events.send_refresh_completed()
        elif dir_paths and len(dir_paths) == 1 and not file_paths:
            relative_path = self._get_relative_path(dir_paths[0])
            Events.send_directory_refresh(f'Refreshed: {relative_path}')
        elif file_paths:
            Events.send_files_refreshed(f'Refreshed {len(file_paths)} files')
        else:
            Events.send_files_refreshed(f'Refreshed {len(task.paths)} paths')

        # Set refresh_complete flag only when refreshing the entire media directory
        if is_global_refresh:
            flags.refresh_complete.set()

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
        from wrolpi.files.lib import NoPrimaryFile
        modified_ids_to_update = []
        for diff in diffs:
            if diff.file_group_id and diff.fs_files:
                # This is a modified FileGroup - may need to update primary_path
                new_paths = [diff.directory / f for f in diff.fs_files]
                try:
                    new_primary = get_primary_file(new_paths)
                except NoPrimaryFile:
                    # No clear primary file, just use the first one
                    new_primary = new_paths[0] if new_paths else None
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
                    '''SELECT primary_path, id FROM file_group
                       WHERE primary_path = ANY(%s)''',
                    (all_new_paths,)
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

                # Bulk UPDATE using VALUES clause for all valid updates
                if valid_updates:
                    curs.execute(
                        '''UPDATE file_group AS fg
                           SET primary_path = v.new_path
                           FROM (SELECT unnest(%s::integer[]) AS id, unnest(%s::text[]) AS new_path) AS v
                           WHERE fg.id = v.id AND fg.primary_path != v.new_path''',
                        ([u[0] for u in valid_updates], [u[1] for u in valid_updates])
                    )

        # Collect all file paths from the diffs and report progress
        all_paths = []
        for i, diff in enumerate(diffs, 1):
            all_paths.extend(_diff_to_paths(diff))

            if i % PROGRESS_UPDATE_INTERVAL == 0 or i == total:
                percent = int((i / total) * 100)
                self.update_status(operation_processed=i, operation_percent=percent)

        # Use existing _upsert_files function which handles grouping and primary file detection
        idempotency = now()
        await asyncio.to_thread(_upsert_files, all_paths, idempotency)
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
        """Delete Videos/Archives/EBooks for modified FileGroups where primary file was removed.

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
                FROM video v JOIN file_group fg ON v.file_group_id = fg.id
                WHERE fg.id = ANY(%s)
                UNION ALL
                SELECT 'archive', a.id, fg.id, fg.primary_path
                FROM archive a JOIN file_group fg ON a.file_group_id = fg.id
                WHERE fg.id = ANY(%s)
                UNION ALL
                SELECT 'ebook', e.id, fg.id, fg.primary_path
                FROM ebook e JOIN file_group fg ON e.file_group_id = fg.id
                WHERE fg.id = ANY(%s)
            ''', (file_group_ids, file_group_ids, file_group_ids))

            # Group results by model type
            video_ids_to_delete = []
            archive_ids_to_delete = []
            ebook_ids_to_delete = []

            for model_type, model_id, fg_id, primary_path in curs.fetchall():
                basename = pathlib.Path(primary_path).name
                if basename in removed_by_id.get(fg_id, set()):
                    if model_type == 'video':
                        video_ids_to_delete.append(model_id)
                    elif model_type == 'archive':
                        archive_ids_to_delete.append(model_id)
                    elif model_type == 'ebook':
                        ebook_ids_to_delete.append(model_id)

            # Batch delete each model type
            if video_ids_to_delete:
                logger.info(f'Deleting {len(video_ids_to_delete)} Videos whose primary file was removed')
                curs.execute('''
                    UPDATE file_group SET model = NULL
                    WHERE id IN (SELECT file_group_id FROM video WHERE id = ANY(%s))
                ''', (video_ids_to_delete,))
                curs.execute('DELETE FROM video WHERE id = ANY(%s)', (video_ids_to_delete,))

            if archive_ids_to_delete:
                logger.info(f'Deleting {len(archive_ids_to_delete)} Archives whose primary file was removed')
                curs.execute('''
                    UPDATE file_group SET model = NULL
                    WHERE id IN (SELECT file_group_id FROM archive WHERE id = ANY(%s))
                ''', (archive_ids_to_delete,))
                curs.execute('DELETE FROM archive WHERE id = ANY(%s)', (archive_ids_to_delete,))

            if ebook_ids_to_delete:
                logger.info(f'Deleting {len(ebook_ids_to_delete)} EBooks whose primary file was removed')
                curs.execute('''
                    UPDATE file_group SET model = NULL
                    WHERE id IN (SELECT file_group_id FROM ebook WHERE id = ANY(%s))
                ''', (ebook_ids_to_delete,))
                curs.execute('DELETE FROM ebook WHERE id = ANY(%s)', (ebook_ids_to_delete,))

    def _validate_move_paths(
            self,
            sources: List[pathlib.Path],
            destination: pathlib.Path,
            media_directory: pathlib.Path,
    ) -> bool:
        """Validate that all source and destination paths are within the media directory.

        Returns True if valid, False otherwise.
        """
        for source in sources:
            if not str(source).startswith(str(media_directory)):
                logger.error(f'{source} is not within the media directory')
                self.reset_status()
                return False
        if not str(destination).startswith(str(media_directory)):
            logger.error(f'{destination} is not within the media directory')
            self.reset_status()
            return False
        return True

    async def _execute_move_chunks(
            self,
            plan: Dict[pathlib.Path, pathlib.Path],
            session,
            created_directories: Set[pathlib.Path],
            revert_plan: Dict[pathlib.Path, pathlib.Path],
    ) -> Set[pathlib.Path]:
        """Execute the move plan in chunks, updating progress.

        Returns the set of new directories created.
        """
        from wrolpi.files.models import FileGroup, Directory

        total_items = len(plan)
        processed = 0
        new_directories: Set[pathlib.Path] = set()

        # Query existing directories once
        existing_directories = {
            pathlib.Path(d[0]) for d in session.query(Directory.path).all()
        }
        inserted_directories: Set[pathlib.Path] = set()

        for chunk in chunks(list(plan.items()), MOVE_CHUNK_SIZE):
            chunk_plan = {}
            # Include files that exist OR don't exist (pre-moved)
            # but exclude directories
            old_files = [old for old, new in chunk if old.is_file() or not old.is_dir()]
            old_dirs = [old for old, new in chunk if old.is_dir()]

            # Get FileGroups for files in this chunk
            file_groups = session.query(FileGroup).filter(
                FileGroup.primary_path.in_([str(f) for f in old_files])
            ).all()

            # Build lookup
            fg_by_path = {fg.primary_path: fg for fg in file_groups}

            # Move each FileGroup's files
            for old_file in old_files:
                fg = fg_by_path.get(old_file)
                if fg:
                    new_path = plan[old_file]
                    parent = new_path.parent
                    parent.mkdir(parents=True, exist_ok=True)
                    if parent not in new_directories:
                        new_directories.add(parent)
                        created_directories.add(parent)
                    # Only move physical files if source exists
                    # (files may have been pre-moved by user)
                    if old_file.exists():
                        _move_file_group_files(fg, new_path)
                        # Track for rollback (new -> old)
                        revert_plan[new_path] = old_file
                    chunk_plan[old_file] = new_path

            # Delete old directories
            for old_dir in old_dirs:
                if old_dir.is_dir():
                    try:
                        delete_directory(old_dir)
                    except OSError:
                        pass  # Directory not empty yet

            # Insert new Directory records
            missing_dirs = new_directories - existing_directories - inserted_directories
            if missing_dirs:
                session.add_all([
                    Directory(path=str(d), name=d.name) for d in missing_dirs
                ])
                inserted_directories.update(missing_dirs)

            # Bulk update FileGroups
            _bulk_update_file_groups_db(session, chunk_plan)
            session.flush()

            # Update progress
            processed += len(chunk)
            percent = int((processed / total_items) * 100) if total_items > 0 else 100
            self.update_status(
                operation_processed=processed,
                operation_percent=percent,
            )
            await asyncio.sleep(0)  # Yield for cancellation

        return new_directories

    def _cleanup_old_directories(
            self,
            sources: List[pathlib.Path],
            old_directories: List[pathlib.Path],
    ) -> None:
        """Clean up old directories after a move operation.

        Deletes empty subdirectories within the source tree, but preserves
        the root source directories themselves (even if empty).

        Optimized: uses single stat() calls and caches directory status to reduce
        redundant filesystem operations on slow RPi storage.
        """
        from wrolpi.files.lib import delete_directory

        # Identify directory sources that were moved (not file parents)
        # Only these directories should have their subdirectories cleaned up
        # Optimized: single stat() call per source instead of up to 2 (is_dir + potential exists)
        moved_directories = set()
        for source in sources:
            try:
                st = source.stat()
                if stat_module.S_ISDIR(st.st_mode):
                    moved_directories.add(source)
            except FileNotFoundError:
                pass  # Source doesn't exist anymore

        # Collect subdirectories within moved directories for cleanup
        # These are nested subdirs that may be empty after files were moved out
        dirs_to_check = set()
        for root in moved_directories:
            try:
                # os.walk efficiently yields directories without redundant stat calls
                for dirpath, dirnames, _ in os.walk(root):
                    for dirname in dirnames:
                        dirs_to_check.add(pathlib.Path(dirpath) / dirname)
            except OSError:
                pass  # Root was deleted during move

        # Sort deepest first to delete children before parents
        dirs_to_check = sorted(dirs_to_check, key=lambda p: len(p.parts), reverse=True)

        # Batch collect directories that no longer exist for DB cleanup
        deleted_dirs_for_db = []

        for directory in dirs_to_check:
            if directory in moved_directories:
                continue  # Never delete the moved directory roots themselves
            try:
                # Try to delete if empty - rmdir fails on non-empty dirs
                # delete_directory handles the DB cleanup too
                delete_directory(directory)
            except FileNotFoundError:
                # Directory was already deleted, collect for batch DB cleanup
                deleted_dirs_for_db.append(str(directory))
            except OSError:
                pass  # Directory not empty, leave it

        # Batch cleanup DB records for directories that were already deleted
        if deleted_dirs_for_db:
            with get_db_curs(commit=True) as curs:
                curs.execute('DELETE FROM directory WHERE path = ANY(%s)', (deleted_dirs_for_db,))

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

        db_groups: Dict[Tuple[str, str], Tuple[int, Set[str], float]] = {}

        with get_db_session() as session:
            # Query FileGroups in our directories
            query = session.query(FileGroup).filter(FileGroup.directory.in_(directories))
            file_groups = query.all()

            for fg in file_groups:
                if not fg.files:
                    # Empty FileGroup - compute stem from primary_path
                    stem, _ = split_path_stem_and_suffix(fg.primary_path)
                    key = (fg.directory, stem)
                    if key in fs_groups:
                        mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                        db_groups[key] = (fg.id, set(), mtime)
                else:
                    # Compute stem from first file
                    first_file = fg.files[0]['path']
                    stem, _ = split_path_stem_and_suffix(pathlib.Path(fg.directory) / first_file)
                    key = (fg.directory, stem)

                    # Include this FileGroup if its stem matches our targets
                    if key in fs_groups:
                        fg_filenames = {pathlib.Path(f['path']).name for f in fg.files}
                        mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                        db_groups[key] = (fg.id, fg_filenames, mtime)

            # Also query for FileGroups by primary_path for deleted files
            # This handles cases where the file was deleted and no related files exist
            if deleted_paths:
                deleted_path_strs = [str(p) for p in deleted_paths]
                deleted_fgs = session.query(FileGroup).filter(
                    FileGroup.primary_path.in_(deleted_path_strs)
                ).all()
                for fg in deleted_fgs:
                    stem, _ = split_path_stem_and_suffix(fg.primary_path)
                    key = (fg.directory, stem)
                    if key not in db_groups:
                        fg_filenames = {pathlib.Path(f['path']).name for f in fg.files} if fg.files else set()
                        mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                        db_groups[key] = (fg.id, fg_filenames, mtime)
                        # Ensure the key is in fs_groups (with empty set for deleted)
                        if key not in fs_groups:
                            fs_groups[key] = set()

                # Also query for FileGroups contained in deleted directories
                # This handles cases where a directory was deleted with files inside
                for deleted_path in deleted_paths:
                    deleted_path_str = str(deleted_path)
                    dir_deleted_fgs = session.query(FileGroup).filter(
                        or_(
                            FileGroup.directory == deleted_path_str,
                            FileGroup.directory.like(f'{deleted_path_str}/%')
                        )
                    ).all()
                    for fg in dir_deleted_fgs:
                        stem, _ = split_path_stem_and_suffix(fg.primary_path)
                        key = (fg.directory, stem)
                        if key not in db_groups:
                            fg_filenames = {pathlib.Path(f['path']).name for f in fg.files} if fg.files else set()
                            mtime = fg.modification_datetime.timestamp() if fg.modification_datetime else 0
                            db_groups[key] = (fg.id, fg_filenames, mtime)
                            # Ensure the key is in fs_groups (with empty set for deleted)
                            if key not in fs_groups:
                                fs_groups[key] = set()

        # Build diffs by comparing fs_groups with db_groups
        unchanged = []
        new = []
        deleted = []
        modified = []

        all_keys = set(fs_groups.keys()) | set(db_groups.keys())

        for key in all_keys:
            directory, stem = key
            fs_files = fs_groups.get(key, set())
            db_id, db_files, db_mtime = db_groups.get(key, (None, set(), 0))

            diff = FileGroupDiff(
                directory=Path(directory),
                stem=stem,
                db_files=db_files,
                fs_files=fs_files,
                file_group_id=db_id,
            )

            if diff.is_new:
                new.append(diff)
            elif diff.is_deleted:
                deleted.append(diff)
            elif diff.needs_update:
                modified.append(diff)
            elif diff.is_unchanged:
                # Check mtime for content changes
                try:
                    dir_path = Path(directory)
                    fs_mtime = max(
                        (dir_path / filename).stat().st_mtime
                        for filename in fs_files
                    )
                    if fs_mtime > db_mtime + 1:
                        modified.append(diff)
                    else:
                        unchanged.append(diff)
                except (OSError, ValueError):
                    unchanged.append(diff)

        logger.info(
            f'Direct file refresh: {len(unchanged)} unchanged, {len(new)} new, '
            f'{len(deleted)} deleted, {len(modified)} modified'
        )

        return FileComparisonResult(
            unchanged=unchanged,
            new=new,
            deleted=deleted,
            modified=modified,
        )

    async def _apply_post_processing(self, is_global_refresh: bool = False) -> None:
        """Run modelers, indexers, and cleanup after file operations.

        Args:
            is_global_refresh: If True, send global_* events. Otherwise, skip them.
        """
        from wrolpi.tags import save_tags_config

        self.update_status(status='modeling')
        with flags.file_worker_modeling:
            await apply_modelers()
        if is_global_refresh:
            Events.send_global_refresh_modeling_completed()

        self.update_status(status='indexing')
        with flags.file_worker_indexing:
            await apply_indexers()
        if is_global_refresh:
            Events.send_global_refresh_indexing_completed()

        with flags.file_worker_cleanup:
            await apply_refresh_cleanup()
            save_tags_config.activate_switch()

    def _revert_move(
            self,
            revert_plan: Dict[pathlib.Path, pathlib.Path],
            created_directories: Set[pathlib.Path],
            destination: pathlib.Path,
            destination_existed: bool,
    ) -> None:
        """Revert a failed move operation by moving files back to original locations."""
        # Rollback: move files back to original locations
        # Use shutil.move directly (not _move_file_group_files) to avoid any
        # issues with the function that may have caused the original failure
        if revert_plan:
            for new_path, old_path in revert_plan.items():
                if new_path.exists():
                    try:
                        old_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(new_path), str(old_path))
                        logger.debug(f'Reverted: {new_path} -> {old_path}')
                    except Exception as revert_error:
                        logger.error(f'Failed to revert {new_path}: {revert_error}')

        # Clean up created directories (deepest first)
        dirs_to_clean = sorted(created_directories, key=lambda p: len(p.parents), reverse=True)
        for directory in dirs_to_clean:
            if directory.is_dir():
                try:
                    # Only delete if empty
                    if not any(directory.iterdir()):
                        delete_directory(directory)
                except (OSError, StopIteration):
                    pass

        # Clean up destination if we created it
        if not destination_existed and destination.is_dir():
            try:
                # Walk destination and delete empty dirs (deepest first)
                for path in sorted(walk(destination), key=lambda p: len(p.parents), reverse=True):
                    if path.is_dir() and not any(path.iterdir()):
                        delete_directory(path)
                # Finally delete destination if empty
                if not any(destination.iterdir()):
                    delete_directory(destination)
            except (OSError, StopIteration):
                pass

    async def handle_move(self, task: FileTask):
        """Handle move task with progress tracking.

        Moves files/directories to the destination using bulk operations.
        Updates status throughout for frontend progress display.
        """
        from wrolpi.events import Events

        destination = task.destination
        sources = task.paths

        if not destination or not sources:
            logger.error('Invalid move task: missing destination or sources')
            self.reset_status()
            return

        media_directory = get_media_directory()

        if not self._validate_move_paths(sources, destination, media_directory):
            return

        self.update_status(
            status='planning',
            task_type='move',
            paths=[str(p) for p in sources],
            destination=str(destination),
            operation_total=0,
            operation_processed=0,
            operation_percent=0,
            error=None,
        )

        # Track if destination existed before we create it (for cleanup on failure)
        destination_existed = destination.is_dir()
        # Track moved files for rollback (new_path -> old_path)
        revert_plan: Dict[pathlib.Path, pathlib.Path] = {}
        # Track directories created during move (for cleanup on failure)
        created_directories: Set[pathlib.Path] = set()
        plan = {}

        try:
            with flags.file_worker_busy:
                destination.mkdir(parents=True, exist_ok=True)

                # Build the move plan using bulk SQL operations
                plan, old_directories = await build_move_plan_bulk(sources, destination)

                # Update status with total
                self.update_status(
                    status='moving',
                    operation_total=len(plan),
                )

                # Execute the plan in chunks
                with flags.file_worker_discovery:
                    with get_db_session(commit=True) as session:
                        await self._execute_move_chunks(
                            plan, session, created_directories, revert_plan
                        )

                self._cleanup_old_directories(sources, old_directories)
                await self._apply_post_processing()

            logger.info(f'Move completed: {len(plan)} items moved to {destination}')
            Events.send_file_move_completed(f'Moved {len(sources)} items to {destination}')
            self._complete_job(task.job_id)

        except asyncio.CancelledError:
            logger.warning('Move task was cancelled')
            raise
        except Exception as e:
            logger.error(f'Move failed: {e}, reverting {len(revert_plan)} items', exc_info=e)
            self.update_status(status='reverting', error=str(e))
            self._revert_move(revert_plan, created_directories, destination, destination_existed)
            Events.send_file_move_failed(f'Move to {destination} failed: {e}')
        finally:
            self.reset_status()


# All processes create a FileWorker, but only one receives the signals and actually does work.
file_worker = FileWorker()
