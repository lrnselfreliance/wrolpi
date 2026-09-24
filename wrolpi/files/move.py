"""FileWorker move jobs: plan, execute, revert.

Extracted from worker.py so the queue/status class is not mixed with move logic.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shutil
import stat as stat_module
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Dict, List, Set, Tuple

from sqlalchemy import text, or_

from wrolpi import flags
from wrolpi.common import get_media_directory, logger, walk, unique_by_predicate, chunks
from wrolpi.db import get_db_session, get_db_curs
from wrolpi.errors import NoPrimaryFile
from wrolpi.events import Events
from wrolpi.files.lib import (
    split_path_stem_and_suffix, get_unique_files_by_stem, glob_shared_stem,
    group_files_by_stem, get_primary_file, delete_directory,
    _move_file_group_files, _bulk_update_file_groups_db, MOVE_CHUNK_SIZE,
    get_normalized_ignored_directories, remove_files_in_ignored_directories,
)

logger = logger.getChild(__name__)


async def build_move_plan_bulk(
        sources: list[pathlib.Path],
        destination: pathlib.Path,
        progress_callback: Callable[[int, int], None] = None,
) -> Tuple[Dict[pathlib.Path, pathlib.Path], list[pathlib.Path]]:
    """
    Build move plan using bulk SQL operations instead of per-source queries.

    Uses a temp table pattern similar to compare_file_groups for O(1) query complexity.

    Args:
        sources: List of file/directory paths to move
        destination: Target directory
        progress_callback: Optional callback(processed, total) called during file collection

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
    total_sources = len(sources)

    for i, source in enumerate(sources, 1):
        try:
            st = source.stat()
            if stat_module.S_ISREG(st.st_mode):
                file_sources.append(source)
            elif stat_module.S_ISDIR(st.st_mode):
                dir_sources.append(source)
            # Other types (symlinks, etc.) are silently skipped
        except FileNotFoundError:
            deleted_sources.append(source)

        # Report progress during source partitioning (first 50% of planning)
        if progress_callback and i % 100 == 0:
            progress_callback(i, total_sources * 2)  # *2 because file collection is second half

    # Collect all paths to insert: file paths + expanded directory contents.  This walks the whole
    # source tree, which is slow on Pi storage, so it must finish before the DB session opens - the
    # session holds the SQLite write lock for its lifetime and would starve every other writer.
    all_file_paths: list[pathlib.Path] = []
    files_collected = 0
    # Use total_sources as the denominator for the second half of progress
    total_items = len(file_sources) + len(dir_sources)

    # For files, collect the file and its shared-stem siblings
    file_source_set: Set[str] = set()
    for i, source in enumerate(file_sources, 1):
        files = glob_shared_stem(source)
        all_file_paths.extend(files)
        file_source_set.update(str(f) for f in files)
        files_collected += 1
        # Report progress (second half: 50-100%)
        if progress_callback and files_collected % 50 == 0:
            progress = total_sources + (files_collected * total_sources // max(total_items, 1))
            progress_callback(progress, total_sources * 2)

    # For directories, walk and collect all files
    dir_file_mapping: Dict[pathlib.Path, pathlib.Path] = {}  # file -> source_dir
    for i, source_dir in enumerate(dir_sources, 1):
        for f in walk(source_dir):
            if f.is_file():
                all_file_paths.append(f)
                dir_file_mapping[f] = source_dir
        files_collected += 1
        # Report progress during directory walking (every 10 directories)
        if progress_callback and files_collected % 10 == 0:
            progress = total_sources + (files_collected * total_sources // max(total_items, 1))
            progress_callback(progress, total_sources * 2)

    # Final progress update before deduplication
    if progress_callback:
        progress_callback(total_sources * 2, total_sources * 2)

    # Deduplicate
    all_file_paths = list(set(all_file_paths))

    # Planning reads FileGroups and then INSERTs the ones missing from the DB, so the transaction
    # must begin as a writer.  A deferred transaction upgrading to a writer mid-way gets "database
    # is locked" *immediately* (busy_timeout is skipped for lock upgrades), so any concurrent
    # writer - a refresh, a download, a config save - would abort the whole move.
    with get_db_session(commit=True) as session:
        try:
            # Create temp table for source paths.  SQLite has no ON COMMIT DROP; the table is
            # explicitly dropped below on success/failure (and IF NOT EXISTS + DELETE guard
            # against any leftover from a previous failed run on the same connection).
            session.execute(text("""
                                 CREATE TEMP TABLE IF NOT EXISTS move_sources
                                 (
                                     source_path      TEXT PRIMARY KEY,
                                     source_type      TEXT NOT NULL,
                                     source_directory TEXT
                                 )
                                 """))
            session.execute(text("DELETE FROM move_sources"))

            # Bulk insert file paths into temp table
            if all_file_paths:
                session.execute(
                    text("""
                         INSERT INTO move_sources (source_path, source_type, source_directory)
                         VALUES (:path, :type, :dir)
                         ON CONFLICT DO NOTHING
                         """),
                    [{"path": str(p), "type": 'file', "dir": str(p.parent)} for p in all_file_paths],
                )

            # Also insert deleted sources (for pre-moved files lookup)
            if deleted_sources:
                session.execute(
                    text("""
                         INSERT INTO move_sources (source_path, source_type, source_directory)
                         VALUES (:path, :type, :dir)
                         ON CONFLICT DO NOTHING
                         """),
                    [{"path": str(p), "type": 'deleted', "dir": str(p.parent)} for p in deleted_sources],
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

            # Process files from direct file sources (`file_source_set` was collected above)
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

        except BaseException:
            # SQLite has no ON COMMIT DROP; attempt to drop the temp table, but do NOT
            # commit — partial plan work must not be persisted on failure.  (Outside of
            # tests, get_db_session rolls back, which also undoes the CREATE TEMP TABLE;
            # the IF NOT EXISTS + DELETE guard above handles any leftover.)
            try:
                session.execute(text("DROP TABLE IF EXISTS move_sources"))
            except Exception:
                logger.exception('Failed to drop move_sources temp table')
            raise
        else:
            # Drop the temp table, then commit the plan work (SQLite has no ON COMMIT DROP).
            session.execute(text("DROP TABLE IF EXISTS move_sources"))
            session.commit()

    # Sort plan by depth (deepest first) for safe move ordering
    plan = OrderedDict(
        sorted(plan.items(), key=lambda i: (len(i[0].parents), i[0].name), reverse=True)
    )

    logger.info(f'build_move_plan_bulk: plan has {len(plan)} items')
    return plan, old_directories


class FileMoveMixin:
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

            # Delete old directories.  `delete_directory` is not used here because it opens its own
            # session; a second connection deadlocks against the write lock this transaction holds.
            for old_dir in old_dirs:
                if old_dir.is_dir():
                    try:
                        old_dir.rmdir()
                    except OSError:
                        continue  # Directory not empty yet
                    session.query(Directory).filter_by(path=str(old_dir)).delete(synchronize_session=False)

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
                curs.execute('DELETE FROM directory WHERE path IN (SELECT value FROM json_each(:paths))',
                             {'paths': json.dumps(deleted_dirs_for_db)})

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
            self._fail_job(task.job_id, 'Invalid move task: missing destination or sources')
            self.reset_status()
            return

        media_directory = get_media_directory()

        if not self._validate_move_paths(sources, destination, media_directory):
            self._fail_job(task.job_id, 'Move paths are not within the media directory')
            return

        # Estimate total for planning phase based on number of sources
        planning_total = len(sources) * 2  # Approximation for progress tracking

        self.update_status(
            status='planning',
            task_type='move',
            paths=[str(p) for p in sources],
            destination=str(destination),
            operation_total=planning_total,
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

        # Progress callback for planning phase
        def on_planning_progress(processed: int, total: int):
            percent = int((processed / total) * 100) if total > 0 else 0
            self.update_status(operation_processed=processed, operation_total=total, operation_percent=percent)

        try:
            destination.mkdir(parents=True, exist_ok=True)

            # Build the move plan using bulk SQL operations
            plan, old_directories = await build_move_plan_bulk(sources, destination, on_planning_progress)

            # Update status with total
            self.update_status(
                status='moving',
                operation_total=len(plan),
            )

            # Execute the plan in chunks.  This reads FileGroups/Directories then updates them, so
            # it must begin as a writer; a deferred transaction's lock upgrade fails instantly when
            # anything else is writing (see `build_move_plan_bulk`).
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
            try:
                if revert_plan:
                    self._revert_move(revert_plan, created_directories, destination, destination_existed)
            except Exception as revert_error:
                logger.error(f'Failed to revert cancelled move: {revert_error}')
            self._fail_job(task.job_id, 'Move task was cancelled')
            raise
        except Exception as e:
            logger.error(f'Move failed: {e}, reverting {len(revert_plan)} items', exc_info=e)
            self.update_status(status='reverting', error=str(e))
            self._revert_move(revert_plan, created_directories, destination, destination_existed)
            self._fail_job(task.job_id, e)
            Events.send_file_move_failed(f'Move to {destination} failed: {e}')
        finally:
            self.reset_status()
