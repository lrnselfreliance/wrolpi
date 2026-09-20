"""Discover filesystem FileGroups and compare them to the DB.

Extracted from the file worker so refresh (find, SQL diff, classify) is not mixed
with move/reorganize/queue.  FileWorker still orchestrates upsert/delete/model.

Identity of a group is (directory, stem).  Compare streams `find` into a TEMP
table and diffs in SQL so unchanged files are never stat()'d a second time.
"""
import asyncio
import json
import pathlib
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Set, Tuple

from sqlalchemy import text

from wrolpi.common import get_media_directory, logger
from wrolpi.db import get_db_session
from wrolpi.vars import PYTEST, IS_MACOS
from wrolpi.files.lib import (
    split_path_stem_and_suffix,
    get_normalized_ignored_directories,
    ensure_file_group_stems,
)

logger = logger.getChild(__name__)

async def _await_db(func, *args):
    """Run a function that uses get_db_curs.

    Tests share one SQLite connection via get_db_curs.  sqlite3 is not safe for concurrent
    use of that connection, so asyncio.to_thread segfaults in CI (xdist + session commit
    on the event loop while the worker thread is still in get_stem_algorithm_version /
    _upsert_files).  Production opens a dedicated raw connection and can use a thread.
    """
    if PYTEST:
        return func(*args)
    return await asyncio.to_thread(func, *args)


# Maximum mtime difference (seconds) before a file is considered "modified".
# 0.5s accommodates SD card / FAT32 / exFAT timestamp granularity on Pi 4.
MTIME_TOLERANCE_SECONDS = 0.5

# GNU find -printf format.  `\0` here is the two-character find escape, NOT a Python
# NUL: subprocess arguments cannot contain embedded null bytes.
GNU_FIND_PRINTF = r'%h\0%f\0%T@\0'

__all__ = [
    'FileGroupDiff',
    'FileComparisonResult',
    'classify_file_group_diffs',
    'compare_file_groups',
    'count_files',
    'count_files_with_progress',
    'find_directories',
    'GNU_FIND_PRINTF',
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


def _deduplicate_db_groups(
        db_groups: Dict[Tuple[str, str], List[Tuple[int, Set[str], float]]],
) -> Tuple[Dict[Tuple[str, str], Tuple[int, Set[str], float]], List[FileGroupDiff]]:
    """Pick one FileGroup per (directory, stem) key, mark the rest for deletion.

    Prefers the FG that has files (non-empty), then highest ID as a stable tiebreaker.
    """
    deduplicated: Dict[Tuple[str, str], Tuple[int, Set[str], float]] = {}
    duplicate_diffs: List[FileGroupDiff] = []
    for key, entries in db_groups.items():
        # Sort: prefer non-empty files first, then highest ID
        entries.sort(key=lambda e: (bool(e[1]), e[0]), reverse=True)
        deduplicated[key] = entries[0]
        for fg_id, fg_files, _ in entries[1:]:
            directory, stem = key
            duplicate_diffs.append(FileGroupDiff(
                directory=Path(directory),
                stem=stem,
                db_files=fg_files or {'__empty__'},
                fs_files=set(),
                file_group_id=fg_id,
            ))
    return deduplicated, duplicate_diffs


def _filenames_from_files_json(raw) -> Set[str]:
    """Filenames from a FileGroup.files JSON value (relative or absolute paths)."""
    if not raw:
        return set()
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return set()
    names = set()
    for entry in raw:
        path = entry.get('path') if isinstance(entry, dict) else entry
        if path:
            names.add(Path(path).name)
    return names


def classify_file_group_diffs(
        fs_groups: Dict[Tuple[str, str], Set[str]],
        db_groups: Dict[Tuple[str, str], List[Tuple[int, Set[str], float]]],
        fs_mtimes: Dict[Tuple[str, str], float] | None = None,
) -> FileComparisonResult:
    """Classify filesystem vs DB groups into new/deleted/modified/unchanged.

    `db_groups` may contain duplicates per (directory, stem); extras are marked deleted.
    If `fs_mtimes` is provided (max mtime per key), unchanged-by-name groups with a newer
    filesystem mtime are classified modified without a second stat().  If omitted, those
    groups are stat()'d (used by the small direct-file path).
    """
    deduplicated, duplicate_diffs = _deduplicate_db_groups(db_groups)

    unchanged = []
    new = []
    deleted = list(duplicate_diffs)
    modified = []

    all_keys = set(fs_groups.keys()) | set(deduplicated.keys())

    for key in all_keys:
        directory, stem = key
        fs_files = fs_groups.get(key, set())
        db_id, db_files, db_mtime = deduplicated.get(key, (None, set(), 0))

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
            if fs_mtimes is not None:
                fs_mtime = fs_mtimes.get(key, 0)
                if fs_mtime > float(db_mtime) + MTIME_TOLERANCE_SECONDS:
                    modified.append(diff)
                else:
                    unchanged.append(diff)
            else:
                try:
                    dir_path = Path(directory)
                    fs_mtime = max(
                        (dir_path / filename).stat().st_mtime
                        for filename in fs_files
                    )
                    if fs_mtime > float(db_mtime) + MTIME_TOLERANCE_SECONDS:
                        modified.append(diff)
                    else:
                        unchanged.append(diff)
                except (OSError, ValueError):
                    unchanged.append(diff)
        elif db_id is not None and not fs_files and not db_files:
            deleted.append(diff)

    return FileComparisonResult(
        unchanged=unchanged,
        new=new,
        deleted=deleted,
        modified=modified,
    )


def _normalize_roots(roots: Path | list[Path] | None) -> list[Path]:
    """Always at least the media directory.  An empty list is treated like None."""
    if roots is None:
        return [get_media_directory()]
    if isinstance(roots, (str, Path)):
        return [Path(roots)]
    root_list = [Path(r) for r in roots]
    return root_list or [get_media_directory()]


def _directory_in_roots_sql(roots: list[Path], column: str = 'fg.directory') -> Tuple[str, dict]:
    """SQL fragment: `column` is any of the roots or a subdirectory of one."""
    clauses = []
    params = {}
    for i, root in enumerate(roots):
        root_str = str(root)
        clauses.append(f'({column} = :root_{i} OR {column} LIKE :root_pat_{i})')
        params[f'root_{i}'] = root_str
        params[f'root_pat_{i}'] = f'{root_str}/%'
    return '(' + ' OR '.join(clauses) + ')', params


def _diff_to_paths(diff: FileGroupDiff) -> list[pathlib.Path]:
    """Convert a FileGroupDiff to full file paths."""
    directory = pathlib.Path(diff.directory)
    return [directory / filename for filename in diff.fs_files]


def _get_normalized_ignored_directories() -> list[str]:
    """Get ignored directories as absolute paths.

    Delegates to files.lib so special directories (zims, videos, …) are never excluded.
    """
    return get_normalized_ignored_directories()


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
        # Exclude the ignored directory itself as well as its contents.
        find_args.extend(['-not', '-path', ignored, '-not', '-path', f'{ignored}/*'])

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


def _find_args_for_roots(roots: list[Path]) -> list[str]:
    """Common `find` arguments: files under roots, no hidden paths, no ignored dirs, no DB file."""
    find_args = [str(r) for r in roots]
    find_args.extend(['-type', 'f', '-not', '-path', '*/.*'])
    for ignored in _get_normalized_ignored_directories():
        find_args.extend(['-not', '-path', f'{ignored}/*'])
    from wrolpi.db import get_db_file
    find_args.extend(['-not', '-path', f'{get_db_file()}*'])
    return find_args


async def _stream_filesystem_paths(root: Path | list[Path]) -> AsyncGenerator[str, None]:
    """Stream file paths using find. Kept for tests that patch this generator."""
    async for directory, filename, stem, mtime in _stream_filesystem_entries(root):
        yield str(Path(directory) / filename)


def _split_nul_field_triples(buf: bytes) -> Tuple[list, bytes]:
    """Pull complete NUL-separated (directory, filename, mtime) triples out of `buf`.

    Returns (triples, leftover_bytes).  A filename may contain tabs or newlines; only NUL
    is the delimiter (GNU find `-printf '%h\\0%f\\0%T@\\0'`).
    """
    triples = []
    while True:
        parts = buf.split(b'\0', 3)
        if len(parts) < 4:
            return triples, buf
        directory_b, filename_b, mtime_b, buf = parts
        triples.append((directory_b, filename_b, mtime_b))


def _entry_from_printf_fields(directory_b: bytes, filename_b: bytes, mtime_b: bytes):
    """Decode one find -printf record.  Returns None and logs if the record is unusable."""
    try:
        directory = directory_b.decode()
        filename = filename_b.decode()
        mtime = float(mtime_b.decode())
    except (UnicodeDecodeError, ValueError) as e:
        logger.warning(f'Skipping unreadable find record {directory_b!r}/{filename_b!r}: {e}')
        return None
    if not directory or not filename:
        return None
    stem, _ = split_path_stem_and_suffix(Path(directory) / filename)
    return directory, filename, stem, mtime


async def _stream_gnu_find_entries(find_args: list[str]) -> AsyncGenerator[Tuple[str, str, str, float], None]:
    """Stream (directory, filename, stem, mtime) using GNU find -printf with NUL delimiters."""
    proc = await asyncio.create_subprocess_exec(
        'find', *find_args, '-printf', GNU_FIND_PRINTF,
        stdout=asyncio.subprocess.PIPE,
    )
    buf = b''
    try:
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            triples, buf = _split_nul_field_triples(buf)
            for fields in triples:
                entry = _entry_from_printf_fields(*fields)
                if entry:
                    yield entry
        if buf.strip(b'\0'):
            logger.warning(f'Incomplete find -printf record discarded: {buf[:200]!r}')
        await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def _stream_filesystem_entries(
        roots: Path | list[Path],
) -> AsyncGenerator[Tuple[str, str, str, float], None]:
    """Yield (directory, filename, stem, mtime) for files under roots.

    GNU find `-printf` records mtime in the same walk (Debian/RPi).  macOS find has no
    `-printf`, so each path is stat()'d once while streaming.  Either way the mtime is
    stored in the TEMP table and unchanged groups are never stat()'d again.
    """
    root_list = _normalize_roots(roots)
    find_args = _find_args_for_roots(root_list)

    if not IS_MACOS:
        async for entry in _stream_gnu_find_entries(find_args):
            yield entry
        return

    proc = await asyncio.create_subprocess_exec(
        'find', *find_args,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        async for line in proc.stdout:
            path = line.decode().rstrip('\n')
            if not path:
                continue
            p = Path(path)
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            stem, _ = split_path_stem_and_suffix(p)
            yield str(p.parent), p.name, stem, mtime
        await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


def _datetime_text_to_epoch(value) -> float:
    """Convert a raw DB datetime (TEXT `YYYY-MM-DD HH:MM:SS.ffffff`, UTC) to a Unix epoch.

    Preserves microsecond precision (SQL `unixepoch()` truncates to whole seconds, which
    would break sub-second mtime comparisons)."""
    if not value:
        return 0
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if dt.tzinfo is None:
        # TZDateTime stores all datetimes as naive UTC text.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _insert_fs_batch(conn, table_name: str, batch: list):
    """Bulk insert filesystem files using executemany for speed."""
    if not batch:
        return
    conn.execute(
        text(f"""
             INSERT INTO {table_name} (directory, filename, stem, mtime)
             VALUES (:directory, :filename, :stem, :mtime)
             ON CONFLICT DO NOTHING
             """),
        [{"directory": b[0], "filename": b[1], "stem": b[2], "mtime": b[3]} for b in batch],
    )


def _diff_from_sql_row(row, fs_files: Set[str], db_files: Set[str]) -> FileGroupDiff:
    return FileGroupDiff(
        directory=Path(row.directory),
        stem=row.stem,
        db_files=db_files,
        fs_files=fs_files,
        file_group_id=row.id if getattr(row, 'id', None) else None,
    )


async def compare_file_groups(
        roots: Path | list[Path] | None = None,
        batch_size: int = 10000,
        progress_callback: Callable[[int], None] = None,
        root: Path | None = None,
) -> FileComparisonResult:
    """
    Compare FileGroups in DB to filesystem. Memory efficient for Raspberry Pi.

    `roots` may be a single path or a list.  Only FileGroups under those directories
    are considered; a two-directory refresh must not delete a stale row in a third.

    Uses a uniquely-named SQLite TEMP table on a dedicated connection so the set-diff
    runs in SQL (the join must use this connection; TEMP tables are per-connection).
    Unchanged groups are never stat()'d a second time: mtime is recorded during the
    find walk.

    This function is async and cancellable - when cancelled, it will terminate
    the subprocess scanning the filesystem.
    """
    if root is not None and roots is None:
        roots = root
    root_list = _normalize_roots(roots)
    await _await_db(ensure_file_group_stems)

    # Per-call table name so concurrent scans don't collide.  The work table is a TEMP table on
    # its own dedicated connection: it never shares a transaction (or locks) with the session,
    # it is invisible to other connections, and it is dropped automatically when the connection
    # closes — orphaned work tables are impossible.
    table_name = f'fs_files_{uuid.uuid4().hex[:12]}'
    groups_table = f'{table_name}_groups'
    roots_sql, root_params = _directory_in_roots_sql(root_list)

    with get_db_session() as session:
        work_conn = session.get_bind().connect()
        try:
            work_conn.execute(text(f"""
                                 CREATE TEMP TABLE {table_name}
                                 (
                                     directory TEXT NOT NULL,
                                     filename  TEXT NOT NULL,
                                     stem      TEXT NOT NULL,
                                     mtime     REAL NOT NULL DEFAULT 0,
                                     PRIMARY KEY (directory, filename)
                                 )
                                 """))

            batch = []
            file_count = 0
            path_gen = _stream_filesystem_entries(root_list)
            try:
                async for directory, filename, stem, mtime in path_gen:
                    batch.append((directory, filename, stem, mtime))

                    if len(batch) >= batch_size:
                        _insert_fs_batch(work_conn, table_name, batch)
                        file_count += len(batch)
                        batch = []
                        if progress_callback:
                            progress_callback(file_count)
                        await asyncio.sleep(0)  # Cancellation yield point
            finally:
                await path_gen.aclose()  # Ensure subprocess is killed on cancellation

            if batch:
                _insert_fs_batch(work_conn, table_name, batch)
                file_count += len(batch)

            logger.info(f'Scanned {file_count} files from filesystem')

            work_conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {table_name}_dir_stem_idx ON {table_name}(directory, stem)"))
            work_conn.execute(text(f"""
                CREATE TEMP TABLE {groups_table} AS
                SELECT directory, stem,
                       json_group_array(filename) AS files,
                       COUNT(*) AS file_count,
                       MAX(mtime) AS mtime
                FROM {table_name}
                GROUP BY directory, stem
            """))
            work_conn.execute(text(f"CREATE INDEX IF NOT EXISTS {groups_table}_idx ON {groups_table}(directory, stem)"))
            work_conn.execute(text(f"ANALYZE {table_name}"))

            # Canonical DB row per (directory, stem).  Duplicates (rn > 1) are deleted.
            # The join runs on work_conn so it can see the TEMP tables.
            db_canonical = f'{table_name}_db'
            work_conn.execute(text(f"""
                CREATE TEMP TABLE {db_canonical} AS
                SELECT id, directory, stem, files, modification_datetime, file_count, rn
                FROM (
                    SELECT fg.id,
                           fg.directory,
                           COALESCE(fg.stem, '') AS stem,
                           fg.files,
                           fg.modification_datetime,
                           CASE
                               WHEN fg.files IS NULL OR json_type(fg.files) != 'array'
                                   THEN 0
                               ELSE json_array_length(fg.files)
                           END AS file_count,
                           ROW_NUMBER() OVER (
                               PARTITION BY fg.directory, COALESCE(fg.stem, '')
                               ORDER BY (
                                   CASE
                                       WHEN fg.files IS NULL OR json_type(fg.files) != 'array'
                                           THEN 0
                                       ELSE json_array_length(fg.files)
                                   END > 0
                               ) DESC, fg.id DESC
                           ) AS rn
                    FROM file_group fg
                    WHERE fg.directory IS NOT NULL
                      AND {roots_sql}
                )
            """), root_params)

            new = []
            deleted = []
            modified = []
            unchanged = []

            # Duplicates: extra FileGroups for the same (directory, stem).
            for row in work_conn.execute(text(f"""
                SELECT id, directory, stem, files FROM {db_canonical} WHERE rn > 1
            """)):
                deleted.append(_diff_from_sql_row(row, set(), _filenames_from_files_json(row.files)))

            # Deleted: canonical DB group with no filesystem group.
            for row in work_conn.execute(text(f"""
                SELECT c.id, c.directory, c.stem, c.files
                FROM {db_canonical} c
                LEFT JOIN {groups_table} fs ON fs.directory = c.directory AND fs.stem = c.stem
                WHERE c.rn = 1 AND fs.stem IS NULL
            """)):
                deleted.append(_diff_from_sql_row(row, set(), _filenames_from_files_json(row.files)))

            # New: filesystem group with no DB group.
            for row in work_conn.execute(text(f"""
                SELECT fs.directory, fs.stem, fs.files, NULL AS id
                FROM {groups_table} fs
                LEFT JOIN {db_canonical} c ON c.directory = fs.directory AND c.stem = fs.stem AND c.rn = 1
                WHERE c.id IS NULL
            """)):
                fs_files = set(json.loads(row.files) if isinstance(row.files, str) else (row.files or []))
                new.append(_diff_from_sql_row(row, fs_files, set()))

            # Both sides present: compare names and mtime.  Only pull file lists for these rows;
            # unchanged file contents stay in SQL.
            for row in work_conn.execute(text(f"""
                SELECT c.id, c.directory, c.stem, c.files AS db_files, c.modification_datetime,
                       fs.files AS fs_files, fs.mtime AS fs_mtime, fs.file_count AS fs_count,
                       c.file_count AS db_count
                FROM {db_canonical} c
                JOIN {groups_table} fs ON fs.directory = c.directory AND fs.stem = c.stem
                WHERE c.rn = 1
            """)):
                fs_files = set(json.loads(row.fs_files) if isinstance(row.fs_files, str) else (row.fs_files or []))
                db_files = _filenames_from_files_json(row.db_files)
                diff = FileGroupDiff(
                    directory=Path(row.directory),
                    stem=row.stem,
                    db_files=db_files,
                    fs_files=fs_files,
                    file_group_id=row.id,
                )
                db_mtime = _datetime_text_to_epoch(row.modification_datetime)
                if diff.needs_update:
                    modified.append(diff)
                elif diff.is_unchanged:
                    if float(row.fs_mtime or 0) > db_mtime + MTIME_TOLERANCE_SECONDS:
                        modified.append(diff)
                    else:
                        unchanged.append(diff)
                elif not fs_files and not db_files:
                    deleted.append(diff)

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
        finally:
            # Closing the dedicated connection drops its TEMP work table.
            try:
                work_conn.close()
            except Exception:
                logger.exception(f'Failed to close work table connection for {table_name}')
