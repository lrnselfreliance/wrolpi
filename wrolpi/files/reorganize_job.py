"""FileWorker reorganize jobs: per-collection and batch.

Extracted from worker.py.  Collection-level name-format logic lives in
wrolpi.collections.reorganize; this module applies the resulting move mappings.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
from pathlib import Path

from wrolpi import flags
from wrolpi.common import logger
from wrolpi.db import get_db_session
from wrolpi.events import Events
from wrolpi.files.lib import (
    split_path_stem_and_suffix, _bulk_update_file_groups_reorganize, delete_directory,
    MOVE_CHUNK_SIZE,
)

logger = logger.getChild(__name__)

PROGRESS_UPDATE_INTERVAL = 100


class FileReorganizeMixin:
    async def handle_reorganize(self, task: FileTask):
        """Handle reorganize task for collection file reorganization.

        Unlike handle_move which moves all files to a single destination,
        handle_reorganize handles arbitrary source->destination mappings
        where each file (or FileGroup) can move to a different location.

        This is used when a user changes their file_name_format configuration
        and wants to reorganize existing files to match the new format.

        Optimized for bulk operations:
        - Single query to pre-fetch all FileGroups
        - Uses FileGroup.files instead of filesystem globs
        - Dict lookup for O(n) path matching
        - Batched database updates
        """
        from wrolpi.events import Events
        from wrolpi.files.models import FileGroup

        move_mappings = task.move_mappings

        if not move_mappings:
            logger.info('Reorganize task has no move mappings, nothing to do')
            self._complete_job(task.job_id)
            self.reset_status()
            return

        total_moves = len(move_mappings)
        logger.info(f'Starting reorganize task with {total_moves} file moves')

        # Transition job from 'pending' to 'running' so progress can be tracked
        self._set_job_status(task.job_id, 'running')

        self.update_status(
            status='reorganizing',
            task_type='reorganize',
            paths=[],
            destination=None,
            operation_total=total_moves,
            operation_processed=0,
            operation_percent=0,
            error=None,
            collection_id=task.collection_id,
            collection_kind=task.collection_kind,
        )

        # Track successful moves for rollback
        completed_moves: list[tuple[pathlib.Path, pathlib.Path]] = []
        # Track created directories for cleanup
        created_directories: set[pathlib.Path] = set()
        # Track source directories to clean up after moves
        source_directories: set[pathlib.Path] = set()

        try:
            with flags.file_worker_discovery:
                # Phase 1: Bulk pre-fetch all FileGroups
                source_paths = [str(s) for s, d in move_mappings]
                with get_db_session() as session:
                    file_groups = session.query(FileGroup).filter(
                        FileGroup.primary_path.in_(source_paths)
                    ).all()
                    # Build lookup dict and detach from session
                    # Note: fg.primary_path is a pathlib.Path (from MediaPathType), but
                    # source_paths are strings, so we use str() for the dictionary keys
                    fg_by_path = {}
                    for fg in file_groups:
                        fg_by_path[str(fg.primary_path)] = {
                            'id': fg.id,
                            'directory': pathlib.Path(fg.directory),
                            'files': list(fg.files),  # Copy the list
                            'data': dict(fg.data) if fg.data else None,
                        }

                processed = 0
                pending_updates = []

                for source_path, dest_path in move_mappings:
                    source_path = pathlib.Path(source_path)
                    dest_path = pathlib.Path(dest_path)

                    source_exists = source_path.exists()
                    dest_exists = dest_path.exists()

                    # Look up the pre-fetched FileGroup
                    fg_info = fg_by_path.get(str(source_path))
                    if not fg_info:
                        logger.debug(f'FileGroup not found by primary_path: {source_path}')
                        processed += 1
                        continue

                    if source_exists and dest_exists:
                        # Conflict: both exist - skip with warning
                        logger.warning(f'Reorganize: both source and destination exist: {source_path} -> {dest_path}')
                        processed += 1
                        continue

                    if not source_exists and not dest_exists:
                        # Neither exists - skip with warning
                        logger.warning(f'Reorganize: neither source nor destination exist: {source_path}')
                        processed += 1
                        continue

                    if not source_exists and dest_exists:
                        # Recovery case: file already moved, just update DB to match destination
                        logger.info(f'Reorganize recovery: updating DB for already-moved file: {dest_path}')

                        dest_stem, _ = split_path_stem_and_suffix(dest_path)

                        # Find existing files at destination that match the FileGroup's file extensions
                        moved_files = []
                        for file_info in fg_info['files']:
                            _, suffix = split_path_stem_and_suffix(pathlib.Path(file_info['path']))
                            dest_file = dest_path.parent / f'{dest_stem}{suffix}'
                            if dest_file.exists():
                                # Map original source path to destination for DB update
                                src_file = fg_info['directory'] / file_info['path']
                                moved_files.append((src_file, dest_file))

                        if moved_files:
                            # Build DB update using existing destination files
                            moved_lookup = {src: dst for src, dst in moved_files}
                            new_files = []
                            for file_info in fg_info['files']:
                                old_file_path = pathlib.Path(file_info['path'])
                                if not old_file_path.is_absolute():
                                    old_file_path = fg_info['directory'] / old_file_path
                                if old_file_path in moved_lookup:
                                    file_info = dict(file_info)
                                    file_info['path'] = moved_lookup[old_file_path].name
                                new_files.append(file_info)

                            new_data = fg_info['data']
                            if new_data:
                                new_data = dict(new_data)
                                filename_lookup = {src.name: dst.name for src, dst in moved_files}
                                for key, value in new_data.items():
                                    if isinstance(value, str) and value in filename_lookup:
                                        new_data[key] = filename_lookup[value]
                                    elif isinstance(value, list):
                                        new_data[key] = [filename_lookup.get(v, v) for v in value]

                            pending_updates.append({
                                'id': fg_info['id'],
                                'directory': str(dest_path.parent),
                                'primary_path': str(dest_path),
                                'files': new_files,
                                'data': new_data,
                            })
                            completed_moves.append((source_path, dest_path))

                        processed += 1
                        if processed % PROGRESS_UPDATE_INTERVAL == 0:
                            percent = int((processed / total_moves) * 100)
                            self.update_status(operation_processed=processed, operation_percent=percent)
                        continue

                    # Normal case: source exists, dest doesn't - move files
                    # Track source directory for cleanup
                    source_directories.add(source_path.parent)

                    # Create destination directory if needed
                    if not dest_path.parent.exists():
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        created_directories.add(dest_path.parent)

                    # Phase 2: Use FileGroup.files instead of glob_shared_stem()
                    source_stem_files = []
                    for file_info in fg_info['files']:
                        file_path = pathlib.Path(file_info['path'])
                        if not file_path.is_absolute():
                            file_path = fg_info['directory'] / file_path
                        source_stem_files.append(file_path)

                    # Move all files in the FileGroup
                    dest_stem, _ = split_path_stem_and_suffix(dest_path)
                    moved_files = []
                    for src_file in source_stem_files:
                        if not src_file.exists():
                            continue
                        # Compute destination for this file based on its suffix
                        _, src_suffix = split_path_stem_and_suffix(src_file)
                        dest_file = dest_path.parent / f'{dest_stem}{src_suffix}'

                        try:
                            shutil.move(str(src_file), str(dest_file))
                            moved_files.append((src_file, dest_file))
                            logger.debug(f'Reorganize: moved {src_file} -> {dest_file}')
                        except Exception as e:
                            logger.error(f'Failed to move {src_file} -> {dest_file}: {e}')
                            raise

                    # Prepare FileGroup update
                    if moved_files:
                        # Phase 3: Use dict lookup instead of nested loop
                        moved_lookup = {src: dst for src, dst in moved_files}

                        # Update files list with new paths
                        new_files = []
                        for file_info in fg_info['files']:
                            old_file_path = pathlib.Path(file_info['path'])
                            if not old_file_path.is_absolute():
                                old_file_path = fg_info['directory'] / old_file_path

                            # Find the corresponding new path using dict lookup
                            if old_file_path in moved_lookup:
                                file_info = dict(file_info)
                                file_info['path'] = moved_lookup[old_file_path].name
                            new_files.append(file_info)

                        # Update data dict if it has path references
                        # Data fields store filenames only (no '/'), so use filename-to-filename lookup
                        new_data = fg_info['data']
                        if new_data:
                            new_data = dict(new_data)
                            # Build filename-to-filename lookup (not full paths)
                            filename_lookup = {src.name: dst.name for src, dst in moved_files}
                            for key, value in new_data.items():
                                if isinstance(value, str) and value in filename_lookup:
                                    new_data[key] = filename_lookup[value]
                                elif isinstance(value, list):
                                    # Handle list fields like caption_paths
                                    new_data[key] = [filename_lookup.get(v, v) for v in value]

                        # Phase 4: Collect update for batch processing
                        pending_updates.append({
                            'id': fg_info['id'],
                            'directory': str(dest_path.parent),
                            'primary_path': str(dest_path),
                            'files': new_files,
                            'data': new_data,
                        })
                        completed_moves.append((source_path, dest_path))

                        # Flush every MOVE_CHUNK_SIZE items
                        if len(pending_updates) >= MOVE_CHUNK_SIZE:
                            _bulk_update_file_groups_reorganize(pending_updates)
                            pending_updates = []

                    processed += 1

                    # Update progress
                    if processed % PROGRESS_UPDATE_INTERVAL == 0 or processed == total_moves:
                        percent = int((processed / total_moves) * 100)
                        logger.info(f'Reorganize progress: {processed}/{total_moves} files ({percent}%)')
                        self.update_status(
                            operation_processed=processed,
                            operation_percent=percent,
                        )

                # Final flush of pending updates
                if pending_updates:
                    _bulk_update_file_groups_reorganize(pending_updates)

                # Clean up empty source directories
                for directory in sorted(source_directories, key=lambda p: len(p.parents), reverse=True):
                    try:
                        if directory.is_dir() and not any(directory.iterdir()):
                            delete_directory(directory)
                            logger.debug(f'Cleaned up empty directory: {directory}')
                    except (OSError, StopIteration):
                        pass

            # Skip post-processing - reorganization only moves files, nothing to re-index

            # Update file_format after successful completion (deferred update for resumability)
            if task.collection_id and task.pending_file_format:
                from wrolpi.collections.models import Collection
                with get_db_session(commit=True) as session:
                    collection = session.query(Collection).filter_by(id=task.collection_id).one_or_none()
                    if collection:
                        collection.file_format = task.pending_file_format
                        logger.info(f'Updated file_format for collection {collection.name}')
                        # Trigger config save
                        if collection.kind == 'domain':
                            from modules.archive.lib import save_domains_config
                            save_domains_config.activate_switch()
                        elif collection.kind == 'channel':
                            from modules.videos.lib import save_channels_config
                            save_channels_config.activate_switch()

            logger.info(f'Reorganize completed: {len(completed_moves)} files moved')
            Events.send_file_move_completed(f'Reorganized {len(completed_moves)} files')
            self._complete_job(task.job_id)

        except asyncio.CancelledError:
            logger.warning('Reorganize task was cancelled')
            self._fail_job(task.job_id, 'Reorganize task was cancelled')
            raise
        except Exception as e:
            logger.error(f'Reorganize failed: {e}', exc_info=e)
            self.update_status(status='error', error=str(e))
            # Note: We don't attempt automatic rollback for reorganize tasks
            # as the partial state may be complex. User should refresh files.
            self._fail_job(task.job_id, e)
            Events.send_file_move_failed(f'Reorganize failed: {e}')
        finally:
            self.reset_status()

    async def handle_batch_reorganize(self, task: FileTask):
        """Handle batch reorganization of multiple collections.

        Processes collections sequentially:
        1. For each collection, execute reorganization
        2. Track overall progress and per-collection progress
        3. Stop on first failure, report which collection failed

        Progress tracking:
        - overall_percent = (completed_collections + current_collection_%) / total_collections
        - batch_status dict tracks completed list, current collection, and failure info
        """
        from wrolpi.collections.reorganize import execute_reorganization
        from wrolpi.collections.models import Collection
        from wrolpi.events import Events

        collection_ids = task.collection_ids or []
        kind = task.batch_kind

        if not collection_ids:
            logger.info('Batch reorganize task has no collections, nothing to do')
            self._complete_job(task.job_id)
            self.reset_status()
            return

        total_collections = len(collection_ids)
        logger.info(f'Starting batch reorganization of {total_collections} {kind} collections')

        # Transition job from 'pending' to 'running'
        self._set_job_status(task.job_id, 'running')

        # Initialize batch status tracking
        batch_status = {
            'batch_job_id': task.job_id,  # Include job ID so frontend can resume polling
            'total_collections': total_collections,
            'completed': [],
            'current_collection': None,
            'failed_collection': None,
            'error': None,
            'overall_percent': 0,
        }

        self.update_status(
            status='batch_reorganizing',
            task_type='batch_reorganize',
            paths=[],
            destination=None,
            operation_total=total_collections,
            operation_processed=0,
            operation_percent=0,
            error=None,
            batch_status=batch_status,
            collection_kind=kind,
        )

        try:
            for idx, collection_id in enumerate(collection_ids):
                # Fetch collection info
                with get_db_session() as session:
                    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
                    if not collection:
                        logger.warning(f'Batch reorganize: collection {collection_id} not found, skipping')
                        continue

                    collection_name = collection.name

                    # Update current collection in status
                    batch_status['current_collection'] = {
                        'id': collection_id,
                        'name': collection_name,
                        'status': 'running',
                        'total': 0,
                        'completed': 0,
                        'percent': 0,
                    }
                    self.update_status(batch_status=batch_status)

                    logger.info(f'Batch reorganize: processing {collection_name} ({idx + 1}/{total_collections})')

                    try:
                        # Execute reorganization for this collection
                        # This queues a sub-job that we need to wait for
                        job_id = execute_reorganization(collection_id, session)

                        if job_id:
                            # Wait for the reorganization job to complete
                            # Poll for completion while updating batch status
                            await self._wait_for_sub_job_with_progress(
                                job_id, batch_status, collection_id, collection_name, idx, total_collections
                            )

                        # Mark this collection as completed
                        batch_status['completed'].append({
                            'id': collection_id,
                            'name': collection_name,
                            'status': 'complete',
                        })

                        # Update overall progress
                        completed_count = len(batch_status['completed'])
                        batch_status['overall_percent'] = int((completed_count / total_collections) * 100)
                        batch_status['current_collection'] = None
                        self.update_status(
                            operation_processed=completed_count,
                            operation_percent=batch_status['overall_percent'],
                            batch_status=batch_status,
                        )

                        logger.info(f'Batch reorganize: completed {collection_name}')

                    except Exception as e:
                        # Collection failed - stop batch processing
                        logger.error(f'Batch reorganize: {collection_name} failed: {e}')

                        # Get the actual channel ID for the UI link (collection_id != channel_id)
                        channel_id = None
                        if kind == 'channel':
                            from modules.videos.models import Channel
                            channel = session.query(Channel).filter_by(collection_id=collection_id).one_or_none()
                            channel_id = channel.id if channel else None

                        batch_status['failed_collection'] = {
                            'id': collection_id,
                            'name': collection_name,
                            'channel_id': channel_id,
                        }
                        batch_status['error'] = str(e)
                        batch_status['current_collection'] = None
                        self.update_status(
                            status='error',
                            error=str(e),
                            batch_status=batch_status,
                        )
                        self._fail_job(task.job_id, e)
                        Events.send_file_move_failed(
                            f'Batch reorganization failed on {collection_name}: {e}'
                        )
                        return

            # All collections completed successfully
            logger.info(f'Batch reorganization completed: {len(batch_status["completed"])} collections processed')
            Events.send_file_move_completed(
                f'Batch reorganization completed: {len(batch_status["completed"])} {kind}s reorganized'
            )
            self._complete_job(task.job_id)

        except asyncio.CancelledError:
            logger.warning('Batch reorganize task was cancelled')
            self._fail_job(task.job_id, 'Batch reorganize task was cancelled')
            raise
        except Exception as e:
            logger.error(f'Batch reorganize failed: {e}', exc_info=e)
            batch_status['error'] = str(e)
            self.update_status(status='error', error=str(e), batch_status=batch_status)
            self._fail_job(task.job_id, e)
            Events.send_file_move_failed(f'Batch reorganization failed: {e}')
        finally:
            self.reset_status()

    async def _wait_for_sub_job_with_progress(
            self,
            job_id: str,
            batch_status: dict,
            collection_id: int,
            collection_name: str,
            collection_idx: int,
            total_collections: int,
    ):
        """Wait for a sub-job to complete while updating batch progress.

        This is used by handle_batch_reorganize to wait for each collection's
        reorganization job while keeping the batch status updated.
        """
        import time
        start = time.time()
        timeout = 3600  # 1 hour max per collection

        while time.time() - start < timeout:
            status = self.get_job_status(job_id)
            if status == 'complete':
                return
            if status == 'failed':
                error = self.get_job_error(job_id) or 'unknown error'
                from wrolpi.files.worker import FileWorkerJobFailed
                raise FileWorkerJobFailed(
                    f'Collection {collection_name} reorganization failed: {error}'
                )

            # Nested under process_queue (batch reorganize); must drain the
            # sub-job ourselves or this wait deadlocks.
            self.transfer_queue()
            await self.process_queue()

            # Update current collection progress based on worker status (now fresh)
            worker_status = self.status
            current = batch_status.get('current_collection', {})
            if current:
                current['total'] = worker_status.get('operation_total', 0)
                current['completed'] = worker_status.get('operation_processed', 0)
                current['percent'] = worker_status.get('operation_percent', 0)
                batch_status['current_collection'] = current

                # Calculate overall percent including current progress
                completed_count = len(batch_status.get('completed', []))
                current_progress = current['percent'] / 100
                batch_status['overall_percent'] = int(
                    ((completed_count + current_progress) / total_collections) * 100
                )
                self.update_status(batch_status=batch_status)

            await asyncio.sleep(0.05)

