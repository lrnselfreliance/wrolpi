import asyncio
import dataclasses
import datetime
import functools
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import urllib.parse
from itertools import zip_longest
from pathlib import Path
from typing import Callable, List, Tuple, Union, Dict, Generator, Iterable, Set

import cachetools.func
import psycopg2
from sqlalchemy import asc, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, wrol_mode_check, logger, \
    partition, \
    get_files_and_directories, chunks_by_stem, walk, \
    get_wrolpi_config, \
    unique_by_predicate, get_paths_in_media_directory, TRACE_LEVEL, get_relative_to_media_directory
from wrolpi.dates import now, from_timestamp, months_selector_to_where, date_range_to_where
from wrolpi.db import get_db_session, get_db_curs, mogrify
from wrolpi.downloader import download_manager, Download
from wrolpi.errors import InvalidFile, UnknownDirectory, UnknownFile, UnknownTag, FileConflict, FileGroupIsTagged, \
    NoPrimaryFile, InvalidDirectory, IgnoredDirectoryError
from wrolpi.events import Events
from wrolpi.files.models import FileGroup, Directory
from wrolpi.lang import ISO_639_CODES, ISO_3166_CODES
from wrolpi.tags import TagFile, Tag, tag_append_sub_select_where, save_tags_config, sync_tags_directory
from wrolpi.vars import PYTEST, IS_MACOS

try:
    import magic

    mime = magic.Magic(mime=True)
except ImportError:
    # Magic is not installed
    magic = None
    mime = None

logger = logger.getChild(__name__)

__all__ = ['list_directories_contents', 'delete', 'split_path_stem_and_suffix', 'search_files',
           'get_mimetype', 'split_file_name_words', 'get_primary_file', 'get_file_statistics',
           'search_file_suggestion_count', 'glob_shared_stem', 'upsert_file', 'get_unique_files_by_stem',
           'rename', 'delete_directory', 'handle_file_group_search_results', 'get_file_location_href']


def get_file_tag_names(session: Session, file: pathlib.Path) -> List[str]:
    """Returns all Tag names for the provided file path."""
    tags = session.query(Tag) \
        .join(TagFile, Tag.id == TagFile.tag_id) \
        .join(FileGroup, FileGroup.id == TagFile.file_group_id) \
        .filter(FileGroup.primary_path == str(file))
    names = sorted([tag.name for tag in tags], key=lambda i: i.lower())
    return names


def sanitize_filename_surrogates(path: pathlib.Path) -> pathlib.Path:
    """
    Check if a path contains invalid UTF-8 surrogates. If so, rename the file
    on disk to replace them with underscores.

    Linux filesystems store filenames as bytes. Python represents invalid UTF-8
    sequences as surrogates. These surrogates cannot be stored in PostgreSQL.

    Returns the (possibly new) path.
    """
    path_str = str(path)

    # Check for surrogates by trying to encode as UTF-8
    try:
        path_str.encode('utf-8')
        return path  # Path is valid
    except UnicodeEncodeError:
        pass

    # Get raw bytes from filesystem and decode, replacing invalid sequences
    raw_bytes = os.fsencode(path)
    # Replace invalid UTF-8 sequences with underscore
    sanitized_name = raw_bytes.decode('utf-8', errors='replace').replace('\ufffd', '_')
    sanitized_path = pathlib.Path(sanitized_name)

    if path.exists() and sanitized_path != path:
        if sanitized_path.exists():
            # Target already exists, add a suffix
            stem = sanitized_path.stem
            suffix = sanitized_path.suffix
            counter = 1
            while sanitized_path.exists():
                sanitized_path = sanitized_path.with_name(f'{stem}_{counter}{suffix}')
                counter += 1

        logger.warning(f'Renaming file with invalid UTF-8 characters: {path!r} -> {sanitized_path}')
        path.rename(sanitized_path)
        return sanitized_path

    return path


def _get_file_dict(session: Session, file: pathlib.Path) -> Dict:
    media_directory = get_media_directory()
    try:
        size = file.stat().st_size
    except PermissionError:
        size = None
    try:
        mimetype = get_mimetype(file)
    except PermissionError:
        mimetype = None
    return dict(
        path=file.relative_to(media_directory),
        size=size,
        mimetype=mimetype,
        tags=get_file_tag_names(session, file),
    )


def get_file_dict(session: Session, file: str) -> Dict:
    media_directory = get_media_directory()
    return _get_file_dict(session, media_directory / file)


async def set_file_viewed(session: Session, file: pathlib.Path):
    """Change FileGroup.viewed to the current datetime."""
    try:
        fg = FileGroup.find_by_path(session, file)
    except UnknownFile:
        fg = FileGroup.from_paths(session, file)
        fg.do_model(session)
    fg.set_viewed()
    session.commit()


@cachetools.func.ttl_cache(10_000, 30.0)
def _get_directory_dict(directory: pathlib.Path,
                        directories_cache: str,  # Used to cache by requested directories.
                        ) -> Dict:
    media_directory = get_media_directory()
    try:
        is_empty = not next(directory.iterdir(), False)
    except PermissionError:
        is_empty = False
    return dict(
        path=f'{directory.relative_to(media_directory)}/',
        is_empty=is_empty,
    )


def _get_recursive_directory_dict(session: Session, directory: pathlib.Path, directories: List[pathlib.Path]) -> Dict:
    directories_cache = str(sorted(directories))
    d = _get_directory_dict(directory, directories_cache)

    if directory in directories:
        children = dict()
        for path in directory.iterdir():
            if path.is_dir() and path in directories:
                children[f'{path.name}/'] = _get_recursive_directory_dict(session, path, directories)
            elif path.is_dir():
                children[f'{path.name}/'] = _get_directory_dict(path, directories_cache)
            else:
                children[path.name] = _get_file_dict(session, path)
        d['children'] = children
    return d


HIDDEN_DIRECTORIES = ('lost+found',)


def list_directories_contents(session: Session, directories_: List[str]) -> Dict:
    """List all files down to (and within) the directories provided.

    This should only be used by the frontend for it's FileBrowser."""
    media_directory = get_media_directory()
    # Convert all directories to pathlib.Path.
    directories = {media_directory / i for i in directories_}
    if invalid_directories := [i for i in directories if not i.is_dir()]:
        raise FileNotFoundError(f'Invalid directories: {invalid_directories}')

    # Get all unique parents for each directory, but not if they are above the media directory.
    parents = {j for i in directories for j in i.parents if j not in media_directory.parents}
    # Add unique parents onto the requested directories.
    directories = list(directories | parents)

    paths = dict()
    for path in media_directory.iterdir():
        if path.is_dir() and path.name in HIDDEN_DIRECTORIES:
            # Never show ignored directories.
            continue
        if path.is_dir():
            paths[f'{path.name}/'] = _get_recursive_directory_dict(session, path, directories)
        else:
            paths[path.name] = _get_file_dict(session, path)

    return paths


@wrol_mode_check
async def delete(*paths: Union[str, pathlib.Path]):
    """
    Delete a file or directory in the media directory.

    This will refuse to delete any files (or files in the directories) that have been tagged."""
    media_directory = get_media_directory()
    paths = [media_directory / i for i in paths]
    if any(i == media_directory for i in paths):
        raise InvalidFile(f'Cannot delete the media directory')
    for path in paths:
        if not path.is_dir() and not path.is_file():
            raise InvalidFile(f'Cannot delete {path} because it is not a file or a directory.')
    if len(paths) > 1:
        for p1 in paths:
            for p2 in paths:
                if p1 == p2:
                    continue
                if str(p2).startswith(str(p1)):
                    raise InvalidFile(f'Cannot deleted nested paths')
    with get_db_session() as session:
        # Search for any files that have been tagged.
        for path in paths:
            query = session.query(FileGroup, TagFile) \
                .join(TagFile, TagFile.file_group_id == FileGroup.id)
            if path.is_file():
                # Could be deleting a file in a FileGroup that has been tagged.
                stem, _ = split_path_stem_and_suffix(path)
                query = query.filter(FileGroup.primary_path.like(f'{path.parent}/{stem}%'))
            else:
                # Search for any FileGroups that have been tagged under this directory.
                # Use indexed directory column for efficient lookup
                path_str = str(path)
                query = query.filter(or_(
                    FileGroup.directory == path_str,
                    FileGroup.directory.like(f'{path_str}/%')
                ))
            for (file_group, tag_file) in query:
                if any(i for i in paths if i in file_group.my_paths()):
                    # File that will be deleted is in a Tagged FileGroup.
                    raise FileGroupIsTagged(f"Cannot delete {file_group} because it is tagged")
    for path in paths:
        ignored_directories = get_wrolpi_config().ignored_directories
        if ignored_directories and str(path) in ignored_directories:
            remove_ignored_directory(path)
        if path.is_dir():
            delete_directory(path, recursive=True)
        else:
            path.unlink()

    # Refresh synchronously to clean up DB before returning.
    # This ensures deleted FileGroups are removed before the caller continues
    # (e.g., upload API recreating the file).
    from wrolpi.files.worker import file_worker
    await file_worker.refresh_sync(list(paths))


def _mimetype_suffix_map(path: Path, mimetype: str):
    """Special handling for mimetypes.  Python Magic may not return the correct mimetype."""
    from wrolpi.files.ebooks import MOBI_MIMETYPE
    suffix = path.suffix.lower()
    if mimetype == 'application/octet-stream':
        if suffix.endswith('.mobi'):
            return MOBI_MIMETYPE
        if suffix.endswith('.stl'):
            return 'model/stl'
        if suffix.endswith('.mp4'):
            return 'video/mp4'
    if suffix.endswith('.hgt'):
        return 'application/octet-stream'
    if mimetype == 'text/plain':
        if suffix.endswith('.json'):
            return 'application/json'
        if suffix.endswith('.vtt'):
            return 'text/vtt'
        if suffix.endswith('.csv'):
            return 'text/csv'
        if suffix.endswith('.html') or suffix.endswith('.htm'):
            return 'text/html'
        if suffix.endswith('.stl'):
            return 'model/stl'
        if suffix.endswith('.scad'):
            return 'application/x-openscad'
        if suffix.endswith('.js'):
            return 'application/javascript'
        if suffix.endswith('.css'):
            return 'text/css'
        if suffix.endswith('.srt'):
            return 'text/srt'
        if suffix.endswith('.yaml') or suffix.endswith('.yml'):
            return 'text/yaml'
        if suffix.endswith('.azw3'):
            return 'application/vnd.amazon.mobi8-ebook'
        if suffix.endswith('.obj'):
            return 'model/obj'
    if mimetype == 'application/x-subrip':
        # Fallback to old mimetype.
        return 'text/srt'
    if mimetype == 'application/zip' and suffix == '.docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if mimetype == 'video/x-ms-asf' and suffix == '.wma':
        return 'audio/x-ms-wma'
    return mimetype


FILE_BIN = which('file', '/usr/bin/file')


@functools.lru_cache(maxsize=10_000)
def get_mimetype(path: Path) -> str:
    """Get the mimetype of a file, prefer using `magic`, fallback to builtin `file` command."""
    if magic is None:
        # This method is slow, prefer the speedier `magic` module.
        cmd = (FILE_BIN, '--mime-type', str(path.absolute()))
        output = subprocess.check_output(cmd)
        output = output.decode()
        mimetype = output.split(' ')[-1].strip()
    else:
        mimetype = mime.from_file(path)
    mimetype = _mimetype_suffix_map(path, mimetype)
    return mimetype


# Special suffixes within WROLPi.
SUFFIXES = {
    '.info.json',
    '.ffprobe.json',
    '.live_chat.json',
    '.readability.html',
    '.readability.json',
    '.readability.txt',
}
SUFFIXES |= {f'.{i}.srt' for i in ISO_639_CODES}
SUFFIXES |= {f'.{i}.vtt' for i in ISO_639_CODES}
EXTRA_SUFFIXES = set()
for six_ in ISO_639_CODES.keys():
    EXTRA_SUFFIXES |= {f'.{six_}-{i}.srt' for i in ISO_3166_CODES}
    EXTRA_SUFFIXES |= {f'.{six_}-{i}.vtt' for i in ISO_3166_CODES}
# Add auto suffixes once (these don't depend on the loop variable)
EXTRA_SUFFIXES |= {f'.{i}-auto.srt' for i in ISO_639_CODES}
EXTRA_SUFFIXES |= {f'.{i}-auto.vtt' for i in ISO_639_CODES}

# Convert to lowercase frozensets for O(1) case-insensitive lookup
_SUFFIXES_LOWER = frozenset(s.lower() for s in SUFFIXES)
_EXTRA_SUFFIXES_LOWER = frozenset(s.lower() for s in EXTRA_SUFFIXES)
_HARDCODED_SUFFIXES = frozenset(
    {'.info.json', '.ffprobe.json', '.live_chat.json', '.readability.html', '.readability.json', '.readability.txt'})

PART_PARSER = re.compile(r'(.+?)(\.f[\d]{2,3})?(\.info)?(\.\w{3,4})(\.part)', re.IGNORECASE)


def _extract_candidate_suffixes(name_lower: str) -> List[str]:
    """Extract potential suffixes from filename (last 1, 2, 3 dot-parts).

    Returns suffixes in order from shortest to longest.
    """
    parts = name_lower.rsplit('.', 3)
    if len(parts) == 1:
        return []
    candidates = []
    append_candidate = candidates.append
    suffix = ''
    for i in range(len(parts) - 1, 0, -1):
        suffix = '.' + parts[i] + suffix
        append_candidate(suffix)
    return candidates


@functools.lru_cache(maxsize=5_000)
def _get_suffix_length(name_lower: str) -> int:
    """Get length of matching suffix using O(1) set lookups.

    Returns 0 if no suffix matches.
    """
    # Fast path: check hardcoded multi-part suffixes first
    for suffix in _HARDCODED_SUFFIXES:
        if name_lower.endswith(suffix):
            return len(suffix)

    candidates = _extract_candidate_suffixes(name_lower)
    if not candidates:
        return 0

    # Check SUFFIXES (longest first for most specific match)
    for suffix in reversed(candidates):
        if suffix in _SUFFIXES_LOWER:
            return len(suffix)

    # Only check EXTRA_SUFFIXES for .srt/.vtt files
    simple_suffix = candidates[0] if candidates else ''
    if simple_suffix in {'.srt', '.vtt'}:
        for suffix in reversed(candidates):
            if suffix in _EXTRA_SUFFIXES_LOWER:
                return len(suffix)

    return len(simple_suffix)


@functools.lru_cache(maxsize=10_000)
def split_path_stem_and_suffix(path: Union[pathlib.Path, str], full: bool = False) -> Tuple[str, str]:
    """Get the path's stem and suffix.

    This function handles WROLPi suffixes like .info.json.

    >>> split_path_stem_and_suffix('/foo/bar.txt')
    ('bar', '.txt')
    >>> split_path_stem_and_suffix('/foo/bar.txt', full=True)
    ('/foo/bar', '.txt')
    >>> split_path_stem_and_suffix('/foo/bar.info.json', full=True)
    ('/foo/bar', '.info.json')
    """
    path = pathlib.Path(path) if isinstance(path, str) else path

    if path.suffix == '.part':
        # yt-dlp uses part files while downloading, include those in a FileGroup.
        stem, info, format_num, suffix, part = PART_PARSER.match(path.name).groups()
        info = info or ''
        format_num = format_num or ''
        stem = f'{path.parent}/{stem}' if full else stem
        return stem, f'{info}{format_num}{suffix}{part}'

    name = path.name
    name_lower = name.lower()

    # Get suffix length using O(1) set lookups instead of O(n) linear search
    suffix_len = _get_suffix_length(name_lower)

    if suffix_len > 0:
        idx = -suffix_len
        if full:
            return f'{path.parent}/{name[:idx]}', name[idx:]
        else:
            return name[:idx], name[idx:]

    # Path has no suffix.
    if full:
        return f'{path.parent}/{path.name}', ''
    else:
        return path.name, ''


def get_unique_files_by_stem(files: List[pathlib.Path] | Tuple[pathlib.Path, ...] | Set[pathlib.Path]) \
        -> List[pathlib.Path]:
    """Returns the first of each Path with a unique stem.  Used to detect if a group of files share a stem."""
    results = unique_by_predicate(files, lambda i: split_path_stem_and_suffix(i)[0])
    if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
        logger.trace(f'get_unique_files_by_stem {files=}')
        logger.trace(f'get_unique_files_by_stem {results=}')
    return results


refresh_logger = logger.getChild('refresh')


def _paths_to_files_dict(group: List[pathlib.Path]) -> List[dict]:
    """This generates `FileGroup.files` from a list of files.

    Paths are stored as filenames only (relative to FileGroup.directory).
    """
    files = list()
    for file in group:
        mimetype = get_mimetype(file)
        stat = file.stat()
        modification_datetime = str(from_timestamp(stat.st_mtime))
        _, suffix = split_path_stem_and_suffix(file)
        size = stat.st_size
        files.append(dict(
            path=file.name,  # Store filename only, not full path
            mimetype=mimetype,
            modification_datetime=modification_datetime,
            size=size,
            suffix=suffix,
        ))
    return files


def get_primary_file(files: Union[Tuple[pathlib.Path], Iterable[pathlib.Path]]) -> pathlib.Path:
    """Given a list of files, return the file that we can model or index.

    @raise NoPrimaryFile: If not primary file can be found."""
    from modules.archive.lib import is_singlefile_file

    if len(files) == 0:
        raise ValueError(f'Cannot find primary file without any files')
    elif len(files) == 1:
        # Only one file is always the primary.
        return files[0]

    file_mimetypes = list()
    for idx, i in enumerate(files):
        try:
            file_mimetypes.append((i, get_mimetype(i)))
        except FileNotFoundError:
            # File was deleted.
            pass

    if not file_mimetypes:
        raise FileNotFoundError(f'Cannot find primary file.  All files are no longer accessible: {files[0]}')

    # EPUB has high priority.
    mimetypes = {i[1] for i in file_mimetypes}
    has_epub = any(i.startswith('application/epub') for i in mimetypes)
    for file, mimetype in file_mimetypes:
        # These are the files that can be modeled.
        if is_singlefile_file(file):
            return file
        if mimetype.startswith('video/'):
            return file
        if mimetype.startswith('application/epub'):
            return file
        if mimetype.startswith('application/pdf') and not has_epub:
            return file
        if mimetype.startswith('application/x-mobipocket-ebook') and not has_epub:
            # Only return a MOBI if no EPUB is present.
            return file

    # Secondary file types.
    for file, mimetype in file_mimetypes:
        if mimetype.startswith('image/'):
            return file

    raise NoPrimaryFile(f'Cannot find primary file for group: {files}')


def _upsert_files(files: List[pathlib.Path], idempotency: datetime.datetime,
                  progress_callback: Callable[[int, int], None] = None):
    """Insert/update all records of the provided files.

    Any inserted files will be marked with `indexed=false`.  Any existing files will only be updated if their
    size/modification_datetime changed.

    Args:
        files: List of file paths to upsert
        idempotency: Timestamp used to track which files were processed in this refresh
        progress_callback: Optional callback(processed, total) called after each chunk is processed

    It is assumed all files exist."""
    idempotency = str(idempotency)
    total_files = len(files)
    processed_count = 0

    non_primary_files = set()
    for chunk in chunks_by_stem(files, 500):
        # Group all files by their shared full-stem.  `chunk_by_stem` already sorted the files.
        grouped = group_files_by_stem(chunk, pre_sorted=True)
        # Convert the groups into file_groups.  Extract common information into `file_group.data`.
        values = dict()
        for group in grouped:
            # The primary file is the video/SingleFile/epub, etc.
            try:
                primary_path = get_primary_file(group)
                # Multiple files in this group.
                primary_path: pathlib.Path = primary_path
                # The primary mimetype allows modelers to find its file_groups.
                mimetype = get_mimetype(primary_path)
                # The group uses a common modification_datetime so the group will be re-indexed when any of it's files
                # are modified.
                modification_datetime = from_timestamp(max(i.stat().st_mtime for i in group))
                size = sum(i.stat().st_size for i in group)
                files = json.dumps(_paths_to_files_dict(group))
                values[primary_path] = (modification_datetime, mimetype, size, files)
                non_primary_files = {i for i in group if i != primary_path}
            except NoPrimaryFile:
                # Cannot find primary path, create a `file_group` for each file.
                for primary_path in group:
                    primary_path: pathlib.Path
                    # The primary mimetype allows modelers to find its file_groups.
                    mimetype = get_mimetype(primary_path)
                    modification_datetime = from_timestamp(primary_path.stat().st_mtime)
                    size = primary_path.stat().st_size
                    files = json.dumps(_paths_to_files_dict([primary_path]))
                    values[primary_path] = (modification_datetime, mimetype, size, files)

        values = [(str(primary_path),
                   str(primary_path.parent),  # directory
                   False,  # `indexed` is false to force indexing by default.
                   idempotency, *i) for primary_path, i in values.items()]
        with get_db_curs(commit=True) as curs:
            values = mogrify(curs, values)
            stmt = f'''
                INSERT INTO file_group
                    (primary_path, directory, indexed, idempotency, modification_datetime, mimetype, size, files)
                VALUES {values}
                ON CONFLICT (primary_path) DO UPDATE
                SET
                    directory=EXCLUDED.directory,
                    idempotency=EXCLUDED.idempotency,
                    modification_datetime=EXCLUDED.modification_datetime,
                    mimetype=EXCLUDED.mimetype,
                    size=EXCLUDED.size,
                    files=(
                        -- Do not overwrite files unless the files have changed and need to be re-indexed.
                        CASE
                        WHEN
                            file_group.modification_datetime = EXCLUDED.modification_datetime
                            AND file_group.size = EXCLUDED.size
                            AND jsonb_array_length(file_group.files) = jsonb_array_length(EXCLUDED.files)
                            THEN file_group.files
                        ELSE EXCLUDED.files
                        END
                    ),
                    -- Preseve TRUE `indexed` only if the files have not changed.
                    indexed=(
                        file_group.indexed = true
                        AND file_group.modification_datetime = EXCLUDED.modification_datetime
                        AND file_group.size = EXCLUDED.size
                        AND jsonb_array_length(file_group.files) = jsonb_array_length(EXCLUDED.files)
                    )
                RETURNING id, file_group.indexed AS old_indexed, indexed
            '''
            curs.execute(stmt)
            results = list(curs.fetchall())
            # Count the files that used to be indexed, but need to be re-indexed.
            invalidated_files = len([i['id'] for i in results if i['old_indexed'] and not i['indexed']])
            if invalidated_files:
                refresh_logger.info(f'Invalidated indexes of {invalidated_files} file groups near {chunk[0]}')
            else:
                refresh_logger.debug(f'Upserted {len(chunk)} files near {chunk[0]}')

            if non_primary_files:
                # New files may have been added which change what primary paths exist.  Delete any file_groups which
                # use paths which are not primary.
                curs.execute('DELETE FROM file_group WHERE primary_path = ANY(%s)',
                             (list(map(str, non_primary_files)),))

        # Report progress after each chunk
        processed_count += len(chunk)
        if progress_callback:
            progress_callback(processed_count, total_files)


def remove_files_in_ignored_directories(files: List[pathlib.Path]) -> List[pathlib.Path]:
    """Return a new list which does not contain any file paths that are in ignored directories."""
    ignored_directories = list(map(str, get_wrolpi_config().ignored_directories))
    for idx, ignored_directory in enumerate(ignored_directories):
        ignored_directory = pathlib.Path(ignored_directory)
        if not ignored_directory.is_absolute():
            ignored_directories[idx] = str(get_media_directory() / ignored_directory)
    files = [i for i in files if not any(str(i).startswith(j) for j in ignored_directories)]
    return files


async def refresh_discover_paths(paths: List[pathlib.Path], idempotency: datetime.datetime = None):
    """Discover all files in the directories provided in paths, as well as all files in paths.

    All records for files in `paths` that do not exist will be deleted.

    Will refuse to refresh when the media directory is empty."""
    try:
        next(get_media_directory().iterdir())
    except StopIteration:
        # We don't want to delete a bunch of files which would exist if the drive was mounted.
        raise UnknownDirectory(f'Refusing to refresh because media directory is empty or does not exist.')
    except FileNotFoundError:
        raise UnknownDirectory(f'Refusing to refresh because media directory is empty or does not exist.')

    if not paths:
        raise ValueError('Must provide some paths to refresh.')

    idempotency = idempotency or now()

    exists, deleted = partition(lambda i: i.exists(), paths)

    # DISCOVER all files, upsert their records.

    if exists:
        # Recursively upsert all files that exist, and files in the existing directories.
        directories, files = partition(lambda i: i.is_dir(), exists)
        while directories:
            directory = directories.pop(0)
            try:
                new_files, new_directories = get_files_and_directories(directory)
            except FileNotFoundError as e:
                # Directory may have been deleted during refresh.
                logger.warning(f'Cannot refresh directory because it is missing: {directory}', exc_info=e)
                continue
            except PermissionError as e:
                # Directory may have been deleted during refresh.
                logger.warning(f'Do not have permission to refresh directory: {directory}', exc_info=e)
                continue
            directories.extend(new_directories)
            files.extend(new_files)

            # Remove any files in ignored directories.
            files = remove_files_in_ignored_directories(files)

            refresh_logger.debug(f'Discovered {len(new_files)} files in {directory}')
            if len(files) >= 100:
                # Wait until there are enough files to perform the upsert.
                try:
                    _upsert_files(files, idempotency)
                except Exception as e:
                    refresh_logger.error(f'Failed to upsert files', exc_info=e)
                files = list()
            # Sleep to catch cancel.
            await asyncio.sleep(0)
        if files:
            # Not enough files for the chunks above, finish what is left.
            try:
                _upsert_files(files, idempotency)
            except Exception as e:
                refresh_logger.error(f'Failed to upsert files', exc_info=e)

        refresh_logger.info('Finished discovering files.  Will now remove deleted files from DB...')

    with get_db_curs(commit=True) as curs:
        wheres = ''
        if paths:
            # Use indexed directory column to delete any children of directories that are deleted.
            # Match exact directory or subdirectories
            conditions = []
            for p in paths:
                p_str = str(p)
                conditions.append(curs.mogrify('(directory = %s OR directory LIKE %s)', (p_str, f'{p_str}/%')).decode())
            wheres = ' OR '.join(conditions)
        deleted_files = ''
        if deleted:
            # Delete any paths that do not exist.
            deleted_files = ' OR '.join([curs.mogrify('primary_path = %s', (str(i),)).decode() for i in deleted])

        idempotency = curs.mogrify('%s', (idempotency,)).decode()
        wheres = f' ( (idempotency != {idempotency} OR idempotency is null) AND ({wheres}))' if wheres else ''
        stmt = f'''
            DELETE FROM file_group
            WHERE
                -- Delete all known-deleted files.
                {deleted_files}
                -- Delete any files in the refreshed paths that were not updated.
                {" OR " + wheres if deleted_files else wheres}
        '''
        refresh_logger.debug(stmt)
        curs.execute(stmt)


async def apply_indexers(progress_callback: Callable[[int, int], None] = None):
    """Indexes any Files that have not yet been indexed by Modelers, or by previous calls of this function.

    Args:
        progress_callback: Optional callback(processed, total) called after each batch.
    """
    from wrolpi.files.models import FileGroup
    refresh_logger.info('Applying indexers')

    # Get initial count for progress tracking
    total_to_index = 0
    total_indexed = 0
    if progress_callback:
        with get_db_session() as session:
            total_to_index = session.query(FileGroup).filter(FileGroup.indexed != True).count()
        progress_callback(0, total_to_index)

    while True:
        # Continually query for Files that have not been indexed.
        with get_db_session(commit=False) as session:
            file_groups = session.query(FileGroup).filter(FileGroup.indexed != True).limit(20)
            file_groups: List[FileGroup] = list(file_groups)

            file_group = None
            processed = 0
            for file_group in file_groups:
                processed += 1
                try:
                    file_group.do_index()
                except Exception:
                    # Error has already been logged in .do_index.
                    if PYTEST:
                        raise
                # Always mark the FileGroup as indexed.  We won't try to index it again.
                file_group.indexed = True

                # Sleep to catch cancel.
                await asyncio.sleep(0)

            # Commit may fail due to invalid UTF-8 surrogates in paths
            try:
                session.commit()
            except UnicodeEncodeError as e:
                session.rollback()
                refresh_logger.warning(f'UnicodeEncodeError during indexer commit, attempting to fix: {e}')
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
                            refresh_logger.info(f'Sanitized primary_path: {fg.primary_path} -> {sanitized}')
                            fg.primary_path = sanitized

                        # Check if files JSON has surrogates
                        if fg.files:
                            new_files = []
                            for f in fg.files:
                                path_val = f.get('path', '')
                                # Convert to string if it's a Path object
                                path_str = str(path_val) if path_val else ''
                                try:
                                    path_str.encode('utf-8')
                                    new_files.append(f)
                                except UnicodeEncodeError:
                                    sanitized = sanitize_filename_surrogates(pathlib.Path(path_str))
                                    refresh_logger.info(f'Sanitized file path: {path_str} -> {sanitized}')
                                    new_files.append({**f, 'path': str(sanitized)})
                            fg.files = new_files
                    except Exception as fix_error:
                        refresh_logger.error(f'Failed to sanitize path for FileGroup {fg.id}: {fix_error}',
                                             exc_info=fix_error)
                    # Re-mark as indexed (rollback undid this)
                    fg.indexed = True

                # Retry commit after fixing
                try:
                    session.commit()
                except UnicodeEncodeError as e2:
                    # Still failing - skip these files and continue
                    session.rollback()
                    refresh_logger.error(f'Failed to fix UnicodeEncodeError, skipping batch: {e2}')
                    # Mark as indexed in a separate transaction so we don't loop forever
                    with get_db_curs(commit=True) as curs:
                        curs.execute('UPDATE file_group SET indexed = TRUE WHERE id = ANY(%s)', (fg_ids,))
                    continue

            if file_group:
                refresh_logger.debug(f'Indexed {processed} files near {file_group.primary_path}')

            # Update progress
            total_indexed += processed
            if progress_callback and total_to_index > 0:
                progress_callback(total_indexed, total_to_index)

            if processed < 20:
                # Processed less than the limit, don't do the next query.
                break


def upsert_directories(parent_directories, directories):
    """
    Insert/update/delete directories provided.  Deletes all children of `parent_directories` which are not in
    `directories`.
    """
    idempotency = now()
    directories = list(directories) + list(parent_directories)

    # Only insert directories that are children of `media_directory` and exist.
    directories = get_paths_in_media_directory([i for i in directories if i.is_dir()])

    if directories:
        # Insert any directories that were created, update any directories which previously existed.
        with get_db_curs(commit=True) as curs:
            values = [(str(i.absolute()), i.name, idempotency) for i in directories]
            values = mogrify(curs, values)
            stmt = f'''
                INSERT INTO directory (path, name, idempotency) VALUES {values}
                ON CONFLICT (path) DO UPDATE
                SET idempotency = EXCLUDED.idempotency
            '''
            curs.execute(stmt)

    with get_db_curs(commit=True) as curs:
        # Delete the children of any parent directory which no longer exists.
        for directory in parent_directories:
            stmt = f'DELETE FROM directory WHERE path LIKE %(directory)s AND idempotency != %(idempotency)s'
            curs.execute(stmt, dict(directory=f'{directory.absolute()}%', idempotency=idempotency))


async def search_directories_by_name(session: Session, name: str, excluded: List[str] = None, limit: int = 20) \
        -> List[Directory]:
    """Find the Directories whose names contain the `name` string."""
    excluded = excluded or []
    directories = session.query(Directory) \
        .filter(Directory.name.ilike(f'%{name}%')) \
        .filter(Directory.path.notin_(excluded)) \
        .order_by(asc(Directory.name)) \
        .limit(limit).all()
    return directories


def search_files(search_str: str, limit: int, offset: int, mimetypes: List[str] = None, model: str = None,
                 tag_names: List[str] = None, headline: bool = False, months: List[int] = None,
                 from_year: int = None, to_year: int = None, any_tag: bool = False, order: str = None) -> \
        Tuple[List[dict], int]:
    """Search the FileGroup table.

    Order the returned Files by their rank if `search_str` is provided.  Return all files if
    `search_str` is empty.

    @param any_tag: The file must have some tag.
    @param to_year: The file must be published on or before this year.
    @param from_year: The file must be published on or after this year.
    @param search_str: Search the ts_vector of the file.  Returns all files if this is empty.
    @param limit: Return only this many files.
    @param offset: Offset the query.
    @param mimetypes: Only return files that match these mimetypes.
    @param model: Only return files that match this model.
    @param tag_names: A list of tag names.
    @param headline: Includes Postgresql headline if True.
    @param months: A list of integers representing the index of the month of the year, starting at 1.
    @param order: Used to change results from most relevant to recently viewed.
    """
    params = dict(offset=offset, limit=limit, search_str=search_str, url_search_str=f'%{search_str}%')
    wheres = []
    selects = []
    order_by = '1 ASC'
    joins = []

    if search_str:
        # Search by textsearch column.
        wheres.append('textsearch @@ websearch_to_tsquery(%(search_str)s)')
        selects.append('ts_rank(textsearch, websearch_to_tsquery(%(search_str)s))')
        order_by = '2 DESC'

    wheres, params = mimetypes_to_sql_wheres(wheres, params, mimetypes)
    if model:
        params['model'] = model
        wheres.append('model = %(model)s')

    wheres, params = tag_append_sub_select_where(wheres, params, tag_names, any_tag)
    wheres, params = months_selector_to_where(wheres, params, months)
    wheres, params = date_range_to_where(wheres, params, from_year, to_year)

    if search_str and headline:
        headline = ''',
           ts_headline(fg.title, websearch_to_tsquery(%(search_str)s)) AS "title_headline",
           ts_headline(fg.b_text, websearch_to_tsquery(%(search_str)s)) AS "b_headline",
           ts_headline(fg.c_text, websearch_to_tsquery(%(search_str)s)) AS "c_headline",
           ts_headline(fg.d_text, websearch_to_tsquery(%(search_str)s)) AS "d_headline"'''
    else:
        headline = ''

    if order == 'viewed':
        order_by = 'viewed DESC NULLS LAST, 1 ASC'
    elif order == '-viewed':
        order_by = 'viewed ASC NULLS LAST, 1 ASC'

    if order and not search_str:
        # Only filter out unviewed files if search_str is not provided.
        wheres.append('viewed IS NOT NULL')

    wheres = '\n AND '.join(wheres)
    selects = f"{', '.join(selects)}, " if selects else ""
    join = '\n'.join(joins)
    stmt = f'''
        SELECT fg.id, {selects} COUNT(*) OVER() AS total
            {headline}
        FROM file_group fg
        {join}
        {f"WHERE {wheres}" if wheres else ""}
        ORDER BY {order_by}
        OFFSET %(offset)s LIMIT %(limit)s
    '''
    logger.debug(stmt)

    results, total = handle_file_group_search_results(stmt, params)
    return results, total


def handle_file_group_search_results(statement: str, params: dict) -> Tuple[List[dict], int]:
    """
    Execute the provided SQL statement and fetch the Files returned.

    WARNING: This expects specific queries to be executed and shouldn't be used for things not related to file search.

    See: `search`
    """
    with get_db_curs() as curs:
        curs.execute(statement, params)
        try:
            results = [dict(i) for i in curs.fetchall()]
        except psycopg2.ProgrammingError:
            # No videos
            return [], 0
        total = results[0]['total'] if results else 0
        ordered_ids = [i['id'] for i in results]
        try:
            extras = [dict(
                ts_rank=i.get('ts_rank'),
                title_headline=i.get('title_headline'),
                b_headline=i.get('b_headline'),
                c_headline=i.get('c_headline'),
                d_headline=i.get('d_headline'),
            ) for i in results]
        except KeyError:
            # No `ts_rank`, probably not searching `file_group.textsearch`.
            extras = []

    with get_db_session() as session:
        from modules.videos.models import Video
        results = session.query(FileGroup, Video) \
            .filter(FileGroup.id.in_(ordered_ids)) \
            .outerjoin(Video, Video.file_group_id == FileGroup.id)
        # Order FileGroups by their location in ordered_ids.  Use dict for O(1) lookups instead of O(n) list.index().
        id_to_order = {id_: idx for idx, id_ in enumerate(ordered_ids)}
        file_groups: List[Tuple[FileGroup, Video]] = sorted(results, key=lambda i: id_to_order.get(i[0].id, 0))
        results = list()
        for extra, (file_group, video) in zip_longest(extras, file_groups):
            video: Video
            if video:
                results.append(video.__json__())
            else:
                results.append(file_group.__json__())
            # Preserve the ts_ranks, if any.
            if extra:
                results[-1]['ts_rank'] = extra['ts_rank']
                results[-1]['title_headline'] = extra['title_headline']
                results[-1]['b_headline'] = extra['b_headline']
                results[-1]['c_headline'] = extra['c_headline']
                results[-1]['d_headline'] = extra['d_headline']

    return results, total


def glob_shared_stem(path: pathlib.Path) -> List[pathlib.Path]:
    """Return all paths that share the same stem and parent path as the provided path.

    Example paths: foo.mp4, foo.png, foo.info.json, foobar.txt
    >>> glob_shared_stem(pathlib.Path('foo.mp4'))
    ['foo.mp4', 'foo.png', 'foo.info.json']
    """
    path = path if isinstance(path, pathlib.Path) else pathlib.Path(path)

    stem, suffix = split_path_stem_and_suffix(path)
    escaped_stem = glob.escape(stem)
    paths = [pathlib.Path(i) for i in path.parent.glob(f'{escaped_stem}*')
             if i == path or i.name.startswith(f'{stem}.')]
    return paths


def get_matching_directories(path: Union[str, Path]) -> List[pathlib.Path]:
    """
    Return a list of directory strings that start with the provided path. If the path is a directory, return its
    subdirectories, if the directory contains no subdirectories, return the directory.
    """
    path: pathlib.Path = pathlib.Path(path) if isinstance(path, str) else path
    path = path.resolve()

    ignored_directories = {pathlib.Path(i).resolve() for i in get_wrolpi_config().ignored_directories}

    if path.is_dir():
        # The provided path is a directory, return its subdirectories, or itself if no subdirectories exist
        paths = list(path.iterdir())
        paths = sorted(i for i in paths if i.is_dir() and i not in ignored_directories)
        if len(paths) == 0:
            return [get_real_path_name(path.resolve())]
        return paths

    paths = path.parent.iterdir()
    prefix = path.name.lower()
    paths = sorted(
        i for i in paths if i.is_dir() and i.name.lower().startswith(prefix) and i.resolve() not in ignored_directories
    )
    paths = unique_by_predicate(paths, None)

    return paths


WHITESPACE = re.compile(r'[\s_\[\]()]')


def split_file_name_words(name: str) -> str:
    """Split words in a filename.

    Words are assumed to be separated by underscore, dash, or space.  Words with a dash are included as a group, and
    individually ('self-reliance' -> ['self', 'reliance', 'self-reliance']).

    >>> split_file_name_words('this self-reliance_split.txt')
    ['this', 'self', 'reliance', 'self-reliance', 'split', 'txt']
    """
    if not name:
        raise ValueError(f'Invalid filename: {name}')

    try:
        stem, suffix = split_path_stem_and_suffix(name)
        words = []
        for word1 in WHITESPACE.split(stem):
            if '-' in word1[1:]:
                words.extend(word1.split('-'))
            words.append(word1)
        # Include the suffix so the user can search without the "."
        if suffix:
            words.append(suffix.lstrip('.'))

        words = ' '.join(i for i in words if i)
        return words
    except Exception as e:
        logger.error(f'Failed to split filename into words: {name}', exc_info=e)
        return name


def get_file_statistics():
    with get_db_curs() as curs:
        curs.execute('''
                     SELECT
                         -- All items in file_group.files are real individual files.
                         SUM(jsonb_array_length(files))                                                                            AS "total_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype = 'application/pdf')                                          AS "pdf_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype = 'application/zip')                                          AS "zip_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'video/%')                                               AS "video_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'image/%')                                               AS "image_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'audio/%')                                               AS "audio_count",
                         COUNT(id) FILTER (WHERE file_group.mimetype = 'application/epub+zip' OR file_group.mimetype =
                                                                                                 'application/x-mobipocket-ebook') AS "ebook_count",
                         (SELECT COUNT(DISTINCT tag_file.file_group_id) FROM tag_file)                                             AS "tagged_files",
                         (SELECT COUNT(DISTINCT tag_zim.zim_entry) FROM tag_zim)                                                   AS "tagged_zims",
                         (SELECT COUNT(*) FROM tag)                                                                                AS "tags_count",
                         SUM(size)::BIGINT                                                                                         AS "total_size",
                         (SELECT COUNT(*) FROM archive)                                                                            AS archive_count
                     FROM file_group
                     ''')
        statistics = dict(curs.fetchall()[0])
        statistics['total_count'] = statistics['total_count'] or 0
        statistics['total_size'] = statistics['total_size'] or 0

        return statistics


def group_files_by_stem(files: List[pathlib.Path], pre_sorted: bool = False) -> \
        Generator[List[pathlib.Path], None, None]:
    """
    Return lists of paths, each list contains only paths that share a common stem.

    >>> a = ['foo.txt', 'foo.mp4', 'bar.txt']
    >>> group_files_by_stem(list(map((pathlib.Path, a))))
    # Generator(['foo.mp4', 'foo.txt'], ['bar.txt'])

    @param files: A list of paths to be grouped.  All paths must be in the same directory!
    @param pre_sorted: This function requires the files to be sorted, it will sort them by default.
    """
    files = sorted(files) if not pre_sorted else files.copy()
    file = files.pop(0)
    group = [file, ]
    prev_stem, _ = split_path_stem_and_suffix(file)
    for file in files:
        stem, suffix = split_path_stem_and_suffix(file)
        if stem == prev_stem:
            group.append(file)
            continue
        # Stem has changed, group is finished.
        yield group
        group = [file, ]
        prev_stem = stem
    yield group


async def _get_tag_and_file_group(session: Session, file_group_id: int, file_group_primary_path: str, tag_name: str,
                                  tag_id: int):
    if file_group_id:
        file_group: FileGroup = session.query(FileGroup).filter_by(id=file_group_id).one_or_none()
        if not file_group:
            raise UnknownFile(f'Cannot find FileGroup with id {file_group_id}')
    elif file_group_primary_path:
        path = get_media_directory() / file_group_primary_path

        file_group = FileGroup.get_by_path(session, path)
        # Create the FileGroup, if possible.
        if not file_group and path.is_file():
            file_group = FileGroup.from_paths(session, path)

        if not file_group:
            raise UnknownFile(f'Cannot find FileGroup with primary_path {repr(str(file_group_primary_path))}')
    else:
        raise UnknownFile(f'Cannot find FileGroup without id or primary_path')

    if tag_id:
        tag: Tag = session.query(Tag).filter_by(id=tag_id).one_or_none()
        if not tag:
            raise UnknownTag(f'Cannot find Tag with id {tag_id}')
    elif tag_name:
        tag: Tag = Tag.get_by_name(session, tag_name)
        if not tag:
            raise UnknownTag(f'Cannot find Tag with name {tag_name}')
    else:
        raise UnknownTag('Cannot find Tag without id or name')

    return file_group, tag


async def add_file_group_tag(session: Session, file_group_id: int, file_group_primary_path: str, tag_name: str,
                             tag_id: int) -> TagFile:
    file_group, tag = await _get_tag_and_file_group(session, file_group_id, file_group_primary_path, tag_name, tag_id)
    tag_file = file_group.add_tag(session, tag.id)
    return tag_file


async def remove_file_group_tag(session: Session, file_group_id: int, file_group_primary_path: str, tag_name: str,
                                tag_id: int):
    file_group, tag = await _get_tag_and_file_group(session, file_group_id, file_group_primary_path, tag_name, tag_id)
    file_group.untag(session, tag.id)


@dataclasses.dataclass
class RefreshProgress:
    counted_files: int = 0
    counting: bool = False
    discovery: bool = False
    indexed: int = 0
    indexing: bool = False
    modeled: int = 0
    modeling: bool = False
    cleanup: bool = False
    refreshing: bool = False
    total_file_groups: int = 0
    unindexed: int = 0

    def __json__(self) -> dict:
        d = dict(
            counted_files=self.counted_files,
            counting=self.counting,
            discovery=self.discovery,
            indexed=self.indexed,
            indexing=self.indexing,
            modeled=self.modeled,
            modeling=self.modeling,
            cleanup=self.cleanup,
            refreshing=self.refreshing,
            total_file_groups=self.total_file_groups,
            unindexed=self.unindexed,
        )
        return d


def get_refresh_progress() -> RefreshProgress:
    from wrolpi.api_utils import api_app

    idempotency = api_app.shared_ctx.refresh.get('idempotency')
    if idempotency:
        stmt = '''
               SELECT
                   -- Sum all the files in each FileGroup.
                   SUM(jsonb_array_length(files)) FILTER (WHERE idempotency = %(idempotency)s)  AS "total_file_groups",
                   COUNT(id) FILTER (WHERE indexed IS TRUE AND idempotency = %(idempotency)s)   AS "indexed",
                   COUNT(id) FILTER (WHERE indexed IS FALSE AND idempotency = %(idempotency)s)  AS "unindexed",
                   COUNT(id) FILTER (WHERE model IS NOT NULL AND idempotency = %(idempotency)s) AS "modeled"
               FROM file_group \
               '''
    else:
        # Idempotency has not yet been declared.
        stmt = '''
               SELECT
                   -- Sum all the files in each FileGroup.
                   SUM(jsonb_array_length(files))             AS "total_file_groups",
                   COUNT(id) FILTER (WHERE indexed IS TRUE)   AS "indexed",
                   COUNT(id) FILTER (WHERE indexed IS FALSE)  AS "unindexed",
                   COUNT(id) FILTER (WHERE model IS NOT NULL) AS "modeled"
               FROM file_group \
               '''

    with get_db_curs() as curs:
        curs.execute(stmt, dict(idempotency=idempotency))
        results = dict(curs.fetchone())
        # TODO counts are wrong if we are not refreshing all files.

        progress = RefreshProgress(
            counted_files=api_app.shared_ctx.refresh.get('counted_files', 0),
            counting=flags.file_worker_counting.is_set(),
            discovery=flags.file_worker_discovery.is_set(),
            indexed=int(results['indexed'] or 0),
            indexing=flags.file_worker_indexing.is_set(),
            modeled=int(results['modeled'] or 0),
            modeling=flags.file_worker_modeling.is_set(),
            cleanup=flags.file_worker_cleanup.is_set(),
            refreshing=flags.file_worker_busy.is_set(),
            total_file_groups=int(results['total_file_groups'] or 0),
            unindexed=int(results['unindexed'] or 0),
        )

    return progress


def mimetypes_to_sql_wheres(wheres: List[str], params: dict, mimetypes: List[str]) -> Tuple[List[str], dict]:
    if mimetypes:
        local_wheres = list()
        for idx, mimetype in enumerate(mimetypes):
            key = f'mimetype{idx}'
            if len(mimetype.split('/')) == 1:
                params[key] = f'{mimetype}/%'
            else:
                params[key] = f'{mimetype}%'
            local_wheres.append(f'mimetype LIKE %({key})s')
        wheres.append(f'({" OR ".join(local_wheres)})')
    return wheres, params


async def search_file_suggestion_count(search_str: str, tag_names: List[str], mimetypes: List[str],
                                       months: List[int] = None, from_year: int = None, to_year: int = None,
                                       any_tag: bool = False):
    """
    Return FileGroup count of what will be returned if the search is actually performed.
    """
    wheres = []
    joins = list()
    params = dict(search_str=search_str, tag_names=tag_names, mimetypes=mimetypes)
    group_by = ''
    having = ''

    if search_str:
        # Search by textsearch, and by matching url.
        wheres.append('fg.textsearch @@ websearch_to_tsquery(%(search_str)s)')

    wheres, params = tag_append_sub_select_where(wheres, params, tag_names, any_tag)
    wheres, params = mimetypes_to_sql_wheres(wheres, params, mimetypes)
    wheres, params = months_selector_to_where(wheres, params, months)
    wheres, params = date_range_to_where(wheres, params, from_year, to_year)

    joins = "\n".join(joins)
    wheres = 'WHERE ' + "\nAND ".join(wheres) if wheres else ''
    stmt = f'''
        SELECT COUNT(*) OVER() AS estimate
        FROM file_group fg
            {joins}
        {wheres}
        {group_by}
        {having}
    '''
    logger.debug(stmt, params)

    with get_db_curs() as curs:
        curs.execute(stmt, params)
        result = curs.fetchone()
        if result:
            return int(result['estimate'])
        return 0


MOVE_CHUNK_SIZE = 100


def _move_file_group_files(file_group: FileGroup, new_primary_path: pathlib.Path) -> None:
    """Move all physical files of a FileGroup to a new directory.

    For directory moves where filenames are preserved, this moves each file from
    the old directory to the new directory keeping the same filename.

    Args:
        file_group: The FileGroup whose files should be moved
        new_primary_path: The new path for the primary file
    """
    new_directory = new_primary_path.parent
    new_stem, _ = split_path_stem_and_suffix(new_primary_path, full=True)

    # Move each file in the FileGroup
    for file_info in file_group.files:
        relative_name = file_info['path']
        old_path = file_group.directory / relative_name
        # Calculate new path: new_stem + original suffix
        _, suffix = split_path_stem_and_suffix(relative_name)
        new_path = pathlib.Path(f'{new_stem}{suffix}')

        if old_path.is_file():
            shutil.move(old_path, new_path)
            logger.debug(f'Moved file: {old_path} -> {new_path}')


def _bulk_update_file_groups_db(session: Session, chunk_plan: Dict[pathlib.Path, pathlib.Path]):
    """Batch UPDATE FileGroups using raw SQL after physical files have been moved.

    Only updates directory and primary_path. Other fields (files, title, a_text) remain unchanged
    because filenames are preserved in directory moves - only the parent directory changes.

    Args:
        session: Database session
        chunk_plan: Mapping of old_primary_path -> new_primary_path
    """
    if not chunk_plan:
        return

    # Use psycopg2 cursor for safe SQL building via mogrify
    with get_db_curs(commit=True) as curs:
        # Build VALUES list for the update: (old_path, new_dir, new_path)
        values = [
            (str(old_path), str(new_path.parent), str(new_path))
            for old_path, new_path in chunk_plan.items()
        ]
        values_sql = mogrify(curs, values)

        # Use UPDATE FROM VALUES pattern for efficient batch update
        sql = f'''
            UPDATE file_group AS fg SET
                directory = v.new_dir,
                primary_path = v.new_path,
                indexed = CASE WHEN fg.data IS NULL THEN FALSE ELSE fg.indexed END
            FROM (VALUES {values_sql}) AS v(old_path, new_dir, new_path)
            WHERE fg.primary_path = v.old_path
        '''
        curs.execute(sql)


def _json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    import datetime
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _bulk_update_file_groups_reorganize(updates: List[dict]):
    """Batch UPDATE FileGroups for reorganization using raw SQL.

    Unlike _bulk_update_file_groups_db, this also updates the files and data JSON fields
    since reorganization changes filenames, not just directories.

    Args:
        updates: List of dicts with keys: id, directory, primary_path, files, data
    """
    if not updates:
        return

    with get_db_curs(commit=True) as curs:
        for update in updates:
            # Don't change indexed - reorganization only moves files, content unchanged
            curs.execute('''
                UPDATE file_group
                SET directory = %s,
                    primary_path = %s,
                    files = %s,
                    data = %s
                WHERE id = %s
            ''', (
                update['directory'],
                update['primary_path'],
                json.dumps(update['files'], default=_json_serial),
                json.dumps(update['data'], default=_json_serial) if update.get('data') else None,
                update['id'],
            ))

    # Expire SQLAlchemy's session cache so subsequent queries see the raw SQL updates.
    # This is necessary because get_db_curs uses the same connection as get_db_session
    # during tests, but SQLAlchemy's identity map doesn't know about raw SQL updates.
    with get_db_session() as session:
        session.expire_all()


def delete_directory(directory: pathlib.Path, recursive: bool = False):
    """Remove a directory, remove it's Directory record.

    Will refuse to delete a directory if it contains Tagged Files.

    This function is idempotent - safe to call even if the directory was already deleted."""
    if directory.exists():
        if recursive:
            with get_db_session() as session:
                # Use indexed directory column for efficient lookup
                directory_str = str(directory)
                tagged = session.query(FileGroup) \
                    .filter(or_(
                    FileGroup.directory == directory_str,
                    FileGroup.directory.like(f'{directory_str}/%')
                )) \
                    .join(TagFile, TagFile.file_group_id == FileGroup.id) \
                    .limit(1).one_or_none()
                if tagged:
                    raise FileGroupIsTagged(f'Cannot delete {tagged} because it is tagged')
            shutil.rmtree(directory)
        else:
            directory.rmdir()
    # Always clean up DB record even if directory was already deleted
    with get_db_curs(commit=True) as curs:
        stmt = 'DELETE FROM directory WHERE path=%s'
        curs.execute(stmt, (str(directory),))


async def rename_file(path: pathlib.Path, new_name: str) -> pathlib.Path:
    """Rename a file (and it's associated files).  Preserve any tags.

    If the path is a non-primary file in a FileGroup (e.g., a poster or subtitle),
    the entire FileGroup will be renamed.
    """
    new_path = path.with_name(new_name)
    if not path.exists():
        raise FileNotFoundError(f'Cannot find {path} to rename')
    if new_path.exists():
        raise FileConflict(f'Cannot rename {path} because {new_path} already exists')

    with get_db_session(commit=True) as session:
        # Find the FileGroup - it may be the primary path or a secondary file
        fg: FileGroup = FileGroup.get_by_any_file_path(session, path)
        if not fg:
            # File wasn't yet in the DB.
            fg = FileGroup.from_paths(session, path)

        # If this is not the primary file, calculate the new primary path
        if fg.primary_path != path:
            # Extract the new stem and apply it to the primary file's suffix
            new_stem, _ = split_path_stem_and_suffix(new_path, full=True)
            _, primary_suffix = split_path_stem_and_suffix(fg.primary_path, full=False)
            new_primary_path = pathlib.Path(f'{new_stem}{primary_suffix}')
            fg.move(new_primary_path)
        else:
            fg.move(new_path)

    return new_path


async def rename_directory(session: Session, directory: pathlib.Path, new_name: str, send_events: bool = False) \
        -> pathlib.Path:
    """Rename a directory.  This is done by moving all files into the new directory, and removing the old directory."""
    from wrolpi.files.worker import file_worker

    new_directory = directory.with_name(new_name)
    if new_directory.exists():
        raise FileConflict(f'Cannot rename {directory} to {new_directory} because it already exists.')

    # Check if this directory is a Collection's directory
    from wrolpi.collections.models import Collection
    collection: Collection = session.query(Collection).filter(Collection.directory == directory).one_or_none()

    if collection:
        # Use Collection's move method which handles files, config saves, and cleanup
        new_directory.mkdir(parents=True, exist_ok=True)
        await collection.move_collection(new_directory, session, send_events=send_events)
    else:
        # Regular directory rename - move all paths into the new directory.
        paths = list(directory.iterdir())
        try:
            job_id = file_worker.queue_move(new_directory, paths)
            await file_worker.wait_for_job(job_id)
            if send_events:
                Events.send_file_move_completed(f'Directory has been renamed: {directory}')
        except Exception:
            if send_events:
                Events.send_file_move_failed(f'Directory rename has failed: {directory}')
            raise

        # Update nested Collections (files already moved by file_worker above)
        directory_str = str(directory)
        nested_collections = session.query(Collection).filter(
            Collection.directory.like(f'{directory_str}/%')
        ).all()
        for coll in nested_collections:
            relative = coll.directory.relative_to(directory)
            new_coll_dir = new_directory / relative
            await coll.move_collection(new_coll_dir, session, send_events=send_events, with_files=False)

        # Remove the old directory (recursive=True to clean up any empty subdirectories
        # that remained after files were moved out).
        delete_directory(directory, recursive=True)

    return new_directory


async def rename(session: Session, path: pathlib.Path, new_name: str, send_events: bool = False) -> pathlib.Path:
    """Rename a directory or file.  Preserve any tags."""
    if path.is_dir():
        return await rename_directory(session, path, new_name, send_events=send_events)

    return await rename_file(path, new_name)


def add_ignore_directory(directory: Union[pathlib.Path, str]):
    """Add a directory to the `ignored_directories` in the WROLPi config.  This directory will be ignored when
    refreshing."""
    media_directory = get_media_directory()

    directory = pathlib.Path(directory)

    from modules.videos.common import get_videos_directory
    from modules.archive.lib import get_archive_directory
    from modules.videos.common import get_no_channel_directory
    special_directories = [
        get_media_directory(),
        get_videos_directory(),
        get_archive_directory(),
        get_no_channel_directory(),
    ]

    if directory in special_directories:
        raise InvalidDirectory('Refusing to ignore special directory')

    if not str(directory).startswith(str(media_directory)):
        raise InvalidDirectory('Cannot ignore directory not in media directory')

    wrolpi_config = get_wrolpi_config()
    ignored_directories = wrolpi_config.ignored_directories if wrolpi_config.ignored_directories else list()

    if str(directory) in ignored_directories:
        logger.warning(f'Directory is already ignored: {directory}')
        return

    ignored_directories.append(str(directory))
    wrolpi_config.ignored_directories = ignored_directories


def remove_ignored_directory(directory: Union[pathlib.Path, str]):
    """Remove a directory from the `ignored_directories` in the WROLPi config."""
    directory = str(pathlib.Path(directory)).rstrip('/')
    ignored_directories = get_wrolpi_config().ignored_directories
    if directory in ignored_directories:
        ignored_directories.remove(directory)
        get_wrolpi_config().ignored_directories = ignored_directories
    else:
        raise UnknownDirectory('Directory is not ignored')


async def upsert_file(file: pathlib.Path | str, tag_names: List[str] = None) -> FileGroup:
    """Insert/update all files in the provided file's FileGroup."""
    if not file or not file.is_file():
        raise InvalidFile(f'Cannot upsert file that does not exist: {file}')

    # Update/Insert all files in the FileGroup.
    paths = glob_shared_stem(pathlib.Path(file))
    # Remove any ignored files.
    paths = remove_files_in_ignored_directories(paths)
    if not paths:
        logger.warning('upsert_file called, but all files are in ignored directories!')
        raise IgnoredDirectoryError(f'all files are in ignored directories: {file}')

    # Use a single session context for all database operations
    with get_db_session(commit=True) as session:
        # Create/update FileGroup with retry logic
        file_group = None
        for i in range(2):
            try:
                file_group = FileGroup.from_paths(session, *paths)
                session.flush([file_group])
                break
            except IntegrityError:
                # Another process inserted this FileGroup.
                logger.error(f'upsert_file failed because FileGroup already exists, trying again... {file}')
                session.rollback()
                if i == 1:
                    raise RuntimeError(f'upsert_file failed to create FileGroup every try! {file}')
                continue

        if not file_group:
            raise RuntimeError(f'upsert_file failed to create FileGroup! {file}')

        logger.debug(f'upsert_file: {file_group}')

        # Model the FileGroup (creates Archive/Video/etc. and sets indexed=True)
        try:
            file_group.do_model(session)
        except Exception as e:
            logger.error(f'Failed to model FileGroup: {file_group}', exc_info=e)
            if PYTEST:
                raise

        # If user uploads a file, then remove it from the download skip list so comments can be downloaded.
        # Modify the download (if any) so that the user can click on it and view the uploaded file.
        if file_group.url:
            if download_manager.is_skipped(file_group.url):
                download_manager.remove_from_skip_list(file_group.url)
            if download := Download.get_by_url(session, file_group.url):
                # Mark download as completed
                download.complete()
                # Link the download to the location of the uploaded file.
                model = file_group.get_model_record()
                download.location = model.location if model else file_group.location

        # Add tags if provided
        if tag_names:
            for tag_name in tag_names:
                if tag_name not in file_group.tag_names:
                    tag = Tag.get_by_name(session, tag_name)
                    file_group.add_tag(session, tag.id)

        # Commit all changes in one transaction
        session.commit()

    # Upsert directories after FileGroup is committed
    upsert_directories([], file.parents)

    return file_group


def get_file_location_href(file: pathlib.Path) -> str:
    """Return the location a file can be viewed at on the UI."""
    parent = str(get_relative_to_media_directory(file.parent))
    preview = str(get_relative_to_media_directory(file))
    if parent == '.':
        # File is in the top of the media directory, App already shows top directory open.
        query = urllib.parse.urlencode(dict(preview=str(preview)))
    else:
        query = urllib.parse.urlencode(dict(folders=str(parent), preview=str(preview)))
    return f'/files?{query}'


def get_real_path_name(path: pathlib.Path) -> pathlib.Path:
    """Return the real path name of a file.  This is used to get the real path of a file on macOS."""
    if IS_MACOS:
        for path_ in path.parent.iterdir():
            if path_.name.lower() == path.name.lower():
                return path_
    return path


@dataclasses.dataclass
class BulkTagPreview:
    """Preview information for a bulk tagging operation."""
    file_count: int = 0
    shared_tag_names: List[str] = dataclasses.field(default_factory=list)

    def __json__(self) -> dict:
        return dict(
            file_count=self.file_count,
            shared_tag_names=self.shared_tag_names,
        )


def get_bulk_tag_preview(paths: List[str]) -> BulkTagPreview:
    """Get preview information for bulk tagging operation.

    Returns the count of files that will be tagged and the tags that are shared by ALL files.
    """
    media_directory = get_media_directory()
    absolute_paths = [media_directory / p for p in paths]

    # Collect all file paths (expanding directories recursively)
    all_file_paths: List[pathlib.Path] = []
    for path in absolute_paths:
        if path.is_file():
            all_file_paths.append(path)
        elif path.is_dir():
            for file in walk(path):
                if file.is_file():
                    all_file_paths.append(file)

    # Remove files in ignored directories
    all_file_paths = remove_files_in_ignored_directories(all_file_paths)

    if not all_file_paths:
        return BulkTagPreview(file_count=0, shared_tag_names=[])

    # Get unique files by stem (each FileGroup counted once)
    unique_files = get_unique_files_by_stem(all_file_paths)
    file_count = len(unique_files)

    if file_count == 0:
        return BulkTagPreview(file_count=0, shared_tag_names=[])

    # Find tags shared by ALL files
    # First, get all FileGroups and their tags
    # We query by stem prefix because unique_files may contain non-primary files
    # (e.g., .readability.json) but FileGroups are stored with primary_path (e.g., .html)
    with get_db_session() as session:
        from sqlalchemy import or_
        stems = [split_path_stem_and_suffix(f, full=True)[0] for f in unique_files]
        file_groups = session.query(FileGroup).filter(
            or_(*[FileGroup.primary_path.like(f'{stem}%') for stem in stems])
        ).all()

        if not file_groups:
            # No FileGroups exist yet, no shared tags
            return BulkTagPreview(file_count=file_count, shared_tag_names=[])

        # Get tag names for each FileGroup
        tag_sets = []
        for fg in file_groups:
            tag_sets.append(set(fg.tag_names))

        # Find intersection of all tag sets (tags shared by ALL files)
        if tag_sets:
            shared_tags = tag_sets[0]
            for tag_set in tag_sets[1:]:
                shared_tags = shared_tags.intersection(tag_set)
            shared_tag_names = sorted(list(shared_tags))
        else:
            shared_tag_names = []

    return BulkTagPreview(file_count=file_count, shared_tag_names=shared_tag_names)


@dataclasses.dataclass
class BulkTagProgress:
    """Progress information for bulk tagging operation."""
    status: str = 'idle'  # 'idle', 'running'
    total: int = 0
    completed: int = 0
    add_tag_names: List[str] = dataclasses.field(default_factory=list)
    remove_tag_names: List[str] = dataclasses.field(default_factory=list)
    error: str = None
    queued_jobs: int = 0

    def __json__(self) -> dict:
        return dict(
            status=self.status,
            total=self.total,
            completed=self.completed,
            add_tag_names=self.add_tag_names,
            remove_tag_names=self.remove_tag_names,
            error=self.error,
            queued_jobs=self.queued_jobs,
        )


def get_bulk_tag_progress() -> BulkTagProgress:
    """Get the current progress of bulk tagging operations."""
    from wrolpi.api_utils import api_app

    bulk_tag = api_app.shared_ctx.bulk_tag
    return BulkTagProgress(
        status=bulk_tag.get('status', 'idle'),
        total=bulk_tag.get('total', 0),
        completed=bulk_tag.get('completed', 0),
        add_tag_names=list(bulk_tag.get('add_tag_names', [])),
        remove_tag_names=list(bulk_tag.get('remove_tag_names', [])),
        error=bulk_tag.get('error'),
        queued_jobs=bulk_tag.get('queued_jobs', 0),
    )


def queue_bulk_tag_job(paths: List[str], add_tag_names: List[str], remove_tag_names: List[str]):
    """Add a bulk tagging job to the queue."""
    from wrolpi.api_utils import api_app

    job = dict(
        paths=paths,
        add_tag_names=add_tag_names,
        remove_tag_names=remove_tag_names,
    )
    api_app.shared_ctx.bulk_tag_queue.put(job)

    # Reset progress state and update queued jobs count
    try:
        current_queued = api_app.shared_ctx.bulk_tag.get('queued_jobs', 0)
        api_app.shared_ctx.bulk_tag.update(dict(
            status='idle',
            total=0,
            completed=0,
            error=None,
            queued_jobs=current_queued + 1,
        ))
    except Exception:
        pass


BULK_TAG_CHUNK_SIZE = 100  # Files per DB session
BULK_SQL_CHUNK_SIZE = 1000  # Rows per SQL statement


def _bulk_insert_tag_files(tag_files: List[Tuple[int, int]]):
    """Bulk insert TagFiles, ignoring duplicates.

    Args:
        tag_files: List of (tag_id, file_group_id) tuples
    """
    if not tag_files:
        return

    now_timestamp = now()

    # Process in chunks to avoid overly large SQL statements
    for i in range(0, len(tag_files), BULK_SQL_CHUNK_SIZE):
        chunk = tag_files[i:i + BULK_SQL_CHUNK_SIZE]
        values = [(tag_id, file_group_id, now_timestamp)
                  for tag_id, file_group_id in chunk]

        with get_db_curs(commit=True) as curs:
            values_str = mogrify(curs, values)
            stmt = f'''
                INSERT INTO tag_file (tag_id, file_group_id, created_at)
                VALUES {values_str}
                ON CONFLICT (tag_id, file_group_id) DO NOTHING
            '''
            curs.execute(stmt)
            logger.debug(f'Bulk inserted {len(chunk)} TagFiles')


def _bulk_delete_tag_files(tag_files: List[Tuple[int, int]]):
    """Bulk delete TagFiles.

    Args:
        tag_files: List of (tag_id, file_group_id) tuples
    """
    if not tag_files:
        return

    # Process in chunks
    for i in range(0, len(tag_files), BULK_SQL_CHUNK_SIZE):
        chunk = tag_files[i:i + BULK_SQL_CHUNK_SIZE]
        pairs = [(tag_id, file_group_id) for tag_id, file_group_id in chunk]

        with get_db_curs(commit=True) as curs:
            pairs_str = mogrify(curs, pairs)
            stmt = f'''
                DELETE FROM tag_file
                WHERE (tag_id, file_group_id) IN ({pairs_str})
            '''
            curs.execute(stmt)
            logger.debug(f'Bulk deleted {curs.rowcount} TagFiles')


async def _process_bulk_tag_job(job: dict):
    """Process a single bulk tagging job with batched DB operations.

    This function uses a three-phase approach for performance:
    1. Collection: Gather all files and resolve FileGroups, collecting tag operations
    2. Bulk DB operations: Execute bulk INSERT and DELETE for TagFiles
    3. Switch activation: Call save_tags_config and sync_tags_directory once at the end
    """
    from wrolpi.api_utils import api_app

    paths = job['paths']
    add_tag_names = job['add_tag_names']
    remove_tag_names = job['remove_tag_names']

    media_directory = get_media_directory()
    absolute_paths = [media_directory / p for p in paths]

    # Collect all file paths (expanding directories recursively)
    all_file_paths: List[pathlib.Path] = []
    for path in absolute_paths:
        if path.is_file():
            all_file_paths.append(path)
        elif path.is_dir():
            for file in walk(path):
                if file.is_file():
                    all_file_paths.append(file)

    # Remove files in ignored directories
    all_file_paths = remove_files_in_ignored_directories(all_file_paths)

    if not all_file_paths:
        return

    # Get unique files by stem
    unique_files = get_unique_files_by_stem(all_file_paths)

    # Update progress with total count
    api_app.shared_ctx.bulk_tag.update(dict(
        status='running',
        total=len(unique_files),
        completed=0,
        add_tag_names=add_tag_names,
        remove_tag_names=remove_tag_names,
        error=None,
    ))

    # Pre-resolve tag IDs (using cached lookups)
    add_tag_ids = set()
    remove_tag_ids = set()
    with get_db_session() as session:
        for tag_name in add_tag_names:
            try:
                add_tag_ids.add(Tag.get_id_by_name(session, tag_name))
            except UnknownTag:
                logger.warning(f'Unknown tag to add: {tag_name}')
        for tag_name in remove_tag_names:
            try:
                remove_tag_ids.add(Tag.get_id_by_name(session, tag_name))
            except UnknownTag:
                logger.warning(f'Unknown tag to remove: {tag_name}')

    if not add_tag_ids and not remove_tag_ids:
        return

    # Phase 1: Collect all file_group_ids and required operations
    tag_files_to_insert: List[Tuple[int, int]] = []  # (tag_id, file_group_id)
    tag_files_to_delete: List[Tuple[int, int]] = []  # (tag_id, file_group_id)

    completed = 0

    # Process files in chunks to balance memory and DB pressure
    for chunk_start in range(0, len(unique_files), BULK_TAG_CHUNK_SIZE):
        chunk = unique_files[chunk_start:chunk_start + BULK_TAG_CHUNK_SIZE]

        with get_db_session(commit=True) as session:
            for file_path in chunk:
                try:
                    # Get or create FileGroup
                    file_group = FileGroup.get_by_path(session, file_path)
                    if not file_group:
                        # Create FileGroup for unindexed file
                        paths_for_group = glob_shared_stem(file_path)
                        paths_for_group = remove_files_in_ignored_directories(paths_for_group)
                        if paths_for_group:
                            try:
                                file_group = FileGroup.from_paths(session, *paths_for_group)
                                file_group.do_model(session)
                                session.flush([file_group])
                            except (NoPrimaryFile, IntegrityError) as e:
                                logger.warning(f'Could not create FileGroup for {file_path}: {e}')
                                completed += 1
                                api_app.shared_ctx.bulk_tag['completed'] = completed
                                continue

                    if file_group and file_group.id:
                        # Flush to ensure file_group.id is set
                        session.flush([file_group])

                        # Get current tag_ids for this file_group
                        existing_tag_ids = {tf.tag_id for tf in file_group.tag_files}

                        # Determine tags to add (not already present)
                        for tag_id in add_tag_ids:
                            if tag_id not in existing_tag_ids:
                                tag_files_to_insert.append((tag_id, file_group.id))

                        # Determine tags to remove (currently present)
                        for tag_id in remove_tag_ids:
                            if tag_id in existing_tag_ids:
                                tag_files_to_delete.append((tag_id, file_group.id))

                except Exception as e:
                    logger.error(f'Error processing file {file_path}: {e}', exc_info=e)

                completed += 1
                api_app.shared_ctx.bulk_tag['completed'] = completed

        # Allow cancellation between chunks
        await asyncio.sleep(0)

    # Phase 2: Bulk database operations
    _bulk_insert_tag_files(tag_files_to_insert)
    _bulk_delete_tag_files(tag_files_to_delete)

    # Phase 3: Activate switches ONCE at the end
    if tag_files_to_insert or tag_files_to_delete:
        save_tags_config.activate_switch()
        sync_tags_directory.activate_switch()


DISABLE_BULK_TAG_WORKER = bool(PYTEST)


async def bulk_tag_worker():
    """Background worker that processes bulk tagging jobs from the queue."""
    import queue
    from wrolpi.api_utils import api_app

    if PYTEST and DISABLE_BULK_TAG_WORKER:
        return

    bulk_tag_ctx = api_app.shared_ctx.bulk_tag
    bulk_tag_queue = api_app.shared_ctx.bulk_tag_queue

    try:
        # Try to get a job from the queue (non-blocking)
        job = bulk_tag_queue.get_nowait()
    except queue.Empty:
        # No jobs in queue, stay idle
        bulk_tag_ctx['status'] = 'idle'
        return

    # Decrement queued jobs count
    try:
        current_queued = bulk_tag_ctx.get('queued_jobs', 1)
        bulk_tag_ctx['queued_jobs'] = max(0, current_queued - 1)
    except Exception:
        pass

    try:
        await _process_bulk_tag_job(job)
    except Exception as e:
        logger.error(f'Bulk tag worker error: {e}', exc_info=e)
        bulk_tag_ctx['error'] = str(e)
    finally:
        bulk_tag_ctx['status'] = 'idle'


# Register the worker as a perpetual signal
from wrolpi.api_utils import perpetual_signal

bulk_tag_worker = perpetual_signal(sleep=1)(bulk_tag_worker)
