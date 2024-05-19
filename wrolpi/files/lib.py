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
from itertools import zip_longest
from pathlib import Path
from typing import List, Tuple, Union, Dict, Generator

import cachetools.func
import psycopg2
from sqlalchemy import asc
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, wrol_mode_check, logger, limit_concurrent, \
    partition, cancelable_wrapper, \
    get_files_and_directories, chunks_by_stem, apply_modelers, apply_refresh_cleanup, background_task, walk, \
    get_wrolpi_config, \
    timer
from wrolpi.dates import now, from_timestamp, months_selector_to_where, date_range_to_where
from wrolpi.db import get_db_session, get_db_curs, mogrify, optional_session
from wrolpi.errors import InvalidFile, UnknownDirectory, UnknownFile, UnknownTag, FileConflict, FileGroupIsTagged, \
    NoPrimaryFile, InvalidDirectory
from wrolpi.events import Events
from wrolpi.files.models import FileGroup, Directory
from wrolpi.lang import ISO_639_CODES
from wrolpi.tags import TagFile, Tag, tag_append_sub_select_where
from wrolpi.vars import PYTEST

try:
    import magic

    mime = magic.Magic(mime=True)
except ImportError:
    # Magic is not installed
    magic = None
    mime = None

logger = logger.getChild(__name__)

__all__ = ['list_directories_contents', 'delete', 'split_path_stem_and_suffix', 'refresh_files', 'search_files',
           'get_mimetype', 'split_file_name_words', 'get_primary_file', 'get_file_statistics',
           'search_file_suggestion_count', 'glob_shared_stem',
           'move', 'rename', 'delete_directory', 'handle_file_group_search_results']


@optional_session
def get_file_tag_names(file: pathlib.Path, session: Session = None) -> List[str]:
    """Returns all Tag names for the provided file path."""
    tags = session.query(Tag) \
        .join(TagFile, Tag.id == TagFile.tag_id) \
        .join(FileGroup, FileGroup.id == TagFile.file_group_id) \
        .filter(FileGroup.primary_path == str(file))
    names = sorted([tag.name for tag in tags], key=lambda i: i.lower())
    return names


def _get_file_dict(file: pathlib.Path) -> Dict:
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
        tags=get_file_tag_names(file),
    )


def get_file_dict(file: str) -> Dict:
    media_directory = get_media_directory()
    return _get_file_dict(media_directory / file)


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


def _get_recursive_directory_dict(directory: pathlib.Path, directories: List[pathlib.Path]) -> Dict:
    directories_cache = str(sorted(directories))
    d = _get_directory_dict(directory, directories_cache)

    if directory in directories:
        children = dict()
        for path in directory.iterdir():
            if path.is_dir() and path in directories:
                children[f'{path.name}/'] = _get_recursive_directory_dict(path, directories)
            elif path.is_dir():
                children[f'{path.name}/'] = _get_directory_dict(path, directories_cache)
            else:
                children[path.name] = _get_file_dict(path)
        d['children'] = children
    return d


HIDDEN_DIRECTORIES = ('lost+found',)


def list_directories_contents(directories_: List[str]) -> Dict:
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
            paths[f'{path.name}/'] = _get_recursive_directory_dict(path, directories)
        else:
            paths[path.name] = _get_file_dict(path)

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
                query = query.filter(FileGroup.primary_path.like(f'{path}/%'))
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

    coro = refresh_files(paths)
    if PYTEST:
        await coro
    else:
        background_task(coro)


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
    '.readability.json',
    '.readability.txt',
    '.readability.html',
    '.live_chat.json'
}
SUFFIXES |= {f'.{i}.srt' for i in ISO_639_CODES}
SUFFIXES |= {f'.{i}.vtt' for i in ISO_639_CODES}


@functools.lru_cache(maxsize=10_000)
def split_path_stem_and_suffix(path: Union[pathlib.Path, str], full: bool = False) -> Tuple[str, str]:
    """Get the path's stem and suffix.

    This function handles WROLPi suffixes like .info.json."""
    if isinstance(path, str):
        path = pathlib.Path(path)

    full_ = str(path)  # May or may not be absolute.
    suffix = next(filter(lambda i: full_.endswith(i), SUFFIXES), path.suffix)
    if suffix and full:
        return f'{path.parent}/{path.name[:-1 * len(suffix)]}', suffix
    elif suffix:
        return path.name[:-1 * len(suffix)], suffix

    # Path has no suffix.
    if full:
        return f'{path.parent}/{path.name}', ''
    else:
        return path.name, ''


refresh_logger = logger.getChild('refresh')


def _paths_to_files_dict(group: List[pathlib.Path]) -> List[dict]:
    """This generates `FileGroup.files` from a list of files."""
    files = list()
    for file in group:
        mimetype = get_mimetype(file)
        stat = file.stat()
        modification_datetime = str(from_timestamp(stat.st_mtime))
        _, suffix = split_path_stem_and_suffix(file)
        size = stat.st_size
        files.append(dict(
            path=str(file),
            mimetype=mimetype,
            modification_datetime=modification_datetime,
            size=size,
            suffix=suffix,
        ))
    return files


def get_primary_file(files: Union[Tuple[pathlib.Path], List[pathlib.Path]]) -> pathlib.Path:
    """Given a list of files, return the file that we can model or index.

    @raise NoPrimaryFile: If not primary file can be found."""
    from modules.archive.lib import is_singlefile_file

    if len(files) == 0:
        raise ValueError(f'Cannot find primary file without any files')
    elif len(files) == 1:
        # Only one file is always the primary.
        return files[0]

    file_mimetypes = [(i, get_mimetype(i)) for i in files]
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


def _upsert_files(files: List[pathlib.Path], idempotency: datetime.datetime):
    """Insert/update all records of the provided files.

    Any inserted files will be marked with `indexed=false`.  Any existing files will only be updated if their
    size/modification_datetime changed.

    It is assumed all files exist."""
    idempotency = str(idempotency)

    non_primary_files = set()
    for chunk in chunks_by_stem(files, 100):
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
                   False,  # `indexed` is false to force indexing by default.
                   idempotency, *i) for primary_path, i in values.items()]
        with get_db_curs(commit=True) as curs:
            values = mogrify(curs, values)
            stmt = f'''
                INSERT INTO file_group
                    (primary_path, indexed, idempotency, modification_datetime, mimetype, size, files)
                VALUES {values}
                ON CONFLICT (primary_path) DO UPDATE
                SET
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
                            AND json_array_length(file_group.files) = json_array_length(EXCLUDED.files)
                            THEN file_group.files
                        ELSE EXCLUDED.files
                        END
                    ),
                    -- Preseve TRUE `indexed` only if the files have not changed.
                    indexed=(
                        file_group.indexed = true
                        AND file_group.modification_datetime = EXCLUDED.modification_datetime
                        AND file_group.size = EXCLUDED.size
                        AND json_array_length(file_group.files) = json_array_length(EXCLUDED.files)
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


def remove_files_in_ignored_directories(files: List[pathlib.Path]) -> List[pathlib.Path]:
    ignored_directories = list(map(str, get_wrolpi_config().ignored_directories))
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
            # Use LIKE to delete any children of directories that are deleted.
            wheres = ' OR '.join([curs.mogrify('primary_path LIKE %s', (f'{i}/%',)).decode() for i in paths])
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


@limit_concurrent(1)  # Only one refresh at a time.
@wrol_mode_check
@cancelable_wrapper
async def refresh_files(paths: List[pathlib.Path] = None, send_events: bool = True):
    """Find, model, and index all files in the media directory."""
    from wrolpi.api_utils import api_app
    if isinstance(paths, str):
        paths = [pathlib.Path(paths), ]
    if isinstance(paths, pathlib.Path):
        paths = [paths, ]

    idempotency = now()
    api_app.shared_ctx.refresh['idempotency'] = idempotency

    refreshing_all_files = False

    with flags.refreshing, timer('refresh_files', 'info'):
        if not paths:
            refresh_logger.warning('Refreshing all files')
            refreshing_all_files = True
        else:
            refresh_logger.warning(f'Refreshing {", ".join(list(map(str, paths)))}')
        if send_events:
            Events.send_global_refresh_started()

        # Add all files in the media directory to the DB.
        paths = paths or [get_media_directory()]

        directories = list(filter(lambda i: i.is_dir(), paths))
        found_directories = set()
        if directories:
            with flags.refresh_counting:
                while directories:
                    directory = directories.pop()
                    files, dirs = get_files_and_directories(directory)
                    directories.extend(dirs)
                    found_directories |= set(dirs)
                    api_app.shared_ctx.refresh['counted_files'] = api_app.shared_ctx.refresh.get('counted_files',
                                                                                                 0) + len(files)
                    # Sleep to catch cancel.
                    await asyncio.sleep(0)
                refresh_logger.info(f'Counted {api_app.shared_ctx.refresh["counted_files"]} files')

        with flags.refresh_discovery:
            await refresh_discover_paths(paths, idempotency)
            if send_events:
                Events.send_global_refresh_discovery_completed()

        # Model all files that have not been indexed.
        with flags.refresh_modeling:
            await apply_modelers()
            if send_events:
                Events.send_global_refresh_modeling_completed()

        # Index the rest of the files that were not indexed by modelers.
        with flags.refresh_indexing:
            await apply_indexers()
            if send_events:
                Events.send_global_refresh_indexing_completed()

        # Cleanup any outdated file data.
        with flags.refresh_cleanup:
            await apply_refresh_cleanup()

            with get_db_session() as session:
                parent_directories = {i[0] for i in session.query(Directory.path).filter(Directory.path.in_(paths))}
                parent_directories |= set(filter(lambda i: i.is_dir(), paths))
            await upsert_directories(parent_directories, found_directories)

            if send_events:
                Events.send_global_after_refresh_completed()

        refresh_logger.warning('Done refreshing Files')

        if refreshing_all_files:
            # Only set refresh_complete flag if all files have been refreshed.
            flags.refresh_complete.set()
        if send_events:
            Events.send_refresh_completed()


async def apply_indexers():
    """Indexes any Files that have not yet been indexed by Modelers, or by previous calls of this function."""
    from wrolpi.files.models import FileGroup
    refresh_logger.info('Applying indexers')

    while True:
        # Continually query for Files that have not been indexed.
        with get_db_session(commit=True) as session:
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

            if file_group:
                refresh_logger.debug(f'Indexed {processed} files near {file_group.primary_path}')

            if processed < 20:
                # Processed less than the limit, don't do the next query.
                break


async def upsert_directories(parent_directories, directories):
    """
    Insert/update/delete directories provided.  Deletes all children of `parent_directories` which are not in
    `directories`.
    """
    idempotency = now()
    directories = list(directories) + list(parent_directories)

    # Only insert directories that are children of `media_directory` and exist.
    media_directory = get_media_directory()
    directories = [i for i in directories if i.is_dir() and i != media_directory]

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


@optional_session
async def search_directories_by_name(name: str, excluded: List[str] = None, limit: int = 20, session: Session = None) \
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
                 from_year: int = None, to_year: int = None) -> \
        Tuple[List[dict], int]:
    """Search the FileGroup table.

    Order the returned Files by their rank if `search_str` is provided.  Return all files if
    `search_str` is empty.

    @param search_str: Search the ts_vector of the file.  Returns all files if this is empty.
    @param limit: Return only this many files.
    @param offset: Offset the query.
    @param mimetypes: Only return files that match these mimetypes.
    @param model: Only return files that match this model.
    @param tag_names: A list of tag names.
    @param headline: Includes Postgresql headline if True.
    @param months: A list of integers representing the index of the month of the year, starting at 1.
    """
    params = dict(offset=offset, limit=limit, search_str=search_str, url_search_str=f'%{search_str}%')
    wheres = []
    selects = []
    order_by = '1 ASC'
    joins = []

    if search_str:
        # Search by textsearch, and by matching url.
        wheres.append("(textsearch @@ websearch_to_tsquery(%(search_str)s) OR fg.url ILIKE %(url_search_str)s)")
        selects.append('ts_rank(textsearch, websearch_to_tsquery(%(search_str)s))')
        order_by = '2 DESC'

    mimetype_wheres, params = mimetypes_to_sql_wheres(mimetypes, params)
    if mimetype_wheres:
        wheres.append(mimetype_wheres)

    if model:
        params['model'] = model
        wheres.append('model = %(model)s')

    wheres, params = tag_append_sub_select_where(tag_names, wheres, params)
    wheres, params = months_selector_to_where(months, wheres, params)
    wheres, params = date_range_to_where(from_year, to_year, wheres, params)

    if search_str and headline:
        headline = ''',
           ts_headline(fg.title, websearch_to_tsquery(%(search_str)s)) AS "title_headline",
           ts_headline(fg.b_text, websearch_to_tsquery(%(search_str)s)) AS "b_headline",
           ts_headline(fg.c_text, websearch_to_tsquery(%(search_str)s)) AS "c_headline",
           ts_headline(fg.d_text, websearch_to_tsquery(%(search_str)s)) AS "d_headline"'''
    else:
        headline = ''

    wheres = '\n AND '.join(wheres)
    selects = f"{', '.join(selects)}, " if selects else ""
    join = '\n'.join(joins)
    stmt = f'''
        SELECT fg.id, {selects} COUNT(*) OVER() AS total
            {headline}
        FROM file_group fg
        {join}
        {f"WHERE {wheres}" if wheres else ""}
        GROUP BY fg.id
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
        # Order FileGroups by their location in ordered_ids.
        file_groups: List[Tuple[FileGroup, Video]] = sorted(results, key=lambda i: ordered_ids.index(i[0].id))
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
    if isinstance(path, str):
        path = pathlib.Path(path)

    stem, suffix = split_path_stem_and_suffix(path)
    escaped_stem = glob.escape(stem)
    paths = [pathlib.Path(i) for i in path.parent.glob(f'{escaped_stem}*') if
             split_path_stem_and_suffix(i)[0] == stem]
    return paths


def get_matching_directories(path: Union[str, Path]) -> List[str]:
    """
    Return a list of directory strings that start with the provided path.  If the path is a directory, return it's
    subdirectories, if the directory contains no subdirectories, return the directory.
    """
    path = str(path)

    ignored_directories = {}

    if os.path.isdir(path):
        # The provided path is a directory, return its subdirectories, or itself if no subdirectories exist
        paths = [os.path.join(path, i) for i in os.listdir(path)]
        paths = sorted(i for i in paths if os.path.isdir(i) and i not in ignored_directories)
        if len(paths) == 0:
            return [path]
        return paths

    head, tail = os.path.split(path)
    paths = os.listdir(head)
    paths = [os.path.join(head, i) for i in paths]
    pattern = path.lower()
    paths = sorted(
        i for i in paths if os.path.isdir(i) and i.lower().startswith(pattern) and i not in ignored_directories)

    return paths


WHITESPACE = re.compile(r'[\s_]')


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

        words = ' '.join(words)
        return words
    except Exception as e:
        logger.error(f'Failed to split filename into words: {name}', exc_info=e)
        return name


def get_file_statistics():
    with get_db_curs() as curs:
        curs.execute('''
        SELECT
            -- All items in file_group.files are real individual files.
            SUM(json_array_length(files)) AS "total_count",
            COUNT(id) FILTER (WHERE file_group.mimetype = 'application/pdf') AS "pdf_count",
            COUNT(id) FILTER (WHERE file_group.mimetype = 'application/zip') AS "zip_count",
            COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'video/%') AS "video_count",
            COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'image/%') AS "image_count",
            COUNT(id) FILTER (WHERE file_group.mimetype LIKE 'audio/%') AS "audio_count",
            COUNT(id) FILTER (WHERE file_group.mimetype = 'application/epub+zip' OR file_group.mimetype = 'application/x-mobipocket-ebook') AS "ebook_count",
            (SELECT COUNT(DISTINCT tag_file.file_group_id) FROM tag_file) AS "tagged_files",
            (SELECT COUNT(DISTINCT tag_zim.zim_entry) FROM tag_zim) AS "tagged_zims",
            (SELECT COUNT(*) FROM tag) AS "tags_count",
            SUM(size)::BIGINT AS "total_size",
            (SELECT COUNT(*) FROM archive) AS archive_count
        FROM
            file_group
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


async def _get_tag_and_file_group(file_group_id: int, file_group_primary_path: str, tag_name: str, tag_id: int,
                                  session: Session):
    if file_group_id:
        file_group: FileGroup = session.query(FileGroup).filter_by(id=file_group_id).one_or_none()
        if not file_group:
            raise UnknownFile(f'Cannot find FileGroup with id {file_group_id}')
    elif file_group_primary_path:
        path = get_media_directory() / file_group_primary_path
        file_group: FileGroup = session.query(FileGroup).filter_by(primary_path=str(path)).one_or_none()
        if not file_group and path.is_file():
            # File may not have been refreshed.
            await refresh_discover_paths([path])
            session.flush()
            file_group: FileGroup = session.query(FileGroup).filter_by(primary_path=str(path)).one_or_none()
            background_task(refresh_files([path]))

        if not file_group:
            raise UnknownFile(f'Cannot find FileGroup with primary_path {repr(str(file_group_primary_path))}')
    else:
        raise UnknownFile(f'Cannot find FileGroup without id or primary_path')

    if tag_id:
        tag: Tag = session.query(Tag).filter_by(id=tag_id).one_or_none()
        if not tag:
            raise UnknownTag(f'Cannot find Tag with id {tag_id}')
    elif tag_name:
        tag: Tag = Tag.find_by_name(tag_name, session)
        if not tag:
            raise UnknownTag(f'Cannot find Tag with name {tag_name}')
    else:
        raise UnknownTag('Cannot find Tag without id or name')

    return file_group, tag


@optional_session(commit=True)
async def add_file_group_tag(file_group_id: int, file_group_primary_path: str, tag_name: str, tag_id: int,
                             session: Session = None) -> TagFile:
    file_group, tag = await _get_tag_and_file_group(file_group_id, file_group_primary_path, tag_name, tag_id, session)
    tag_file = file_group.add_tag(tag, session)
    return tag_file


@optional_session(commit=True)
async def remove_file_group_tag(file_group_id: int, file_group_primary_path: str, tag_name: str, tag_id: int,
                                session: Session = None):
    file_group, tag = await _get_tag_and_file_group(file_group_id, file_group_primary_path, tag_name, tag_id, session)
    file_group.remove_tag(tag, session)


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

    def __json__(self):
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
                SUM(json_array_length(files)) FILTER (WHERE idempotency=%(idempotency)s) AS "total_file_groups",
                COUNT(id) FILTER (WHERE indexed IS TRUE AND idempotency=%(idempotency)s) AS "indexed",
                COUNT(id) FILTER (WHERE indexed IS FALSE) AS "unindexed",
                COUNT(id) FILTER (WHERE model IS NOT NULL AND idempotency=%(idempotency)s) AS "modeled"
            FROM file_group
        '''
    else:
        # Idempotency has not yet been declared.
        stmt = '''
            SELECT
                -- Sum all the files in each FileGroup.
                SUM(json_array_length(files)) AS "total_file_groups",
                COUNT(id) FILTER (WHERE indexed IS TRUE) AS "indexed",
                COUNT(id) FILTER (WHERE indexed IS FALSE) AS "unindexed",
                COUNT(id) FILTER (WHERE model IS NOT NULL) AS "modeled"
            FROM file_group
        '''

    with get_db_curs() as curs:
        curs.execute(stmt, dict(idempotency=idempotency))
        results = dict(curs.fetchone())
        # TODO counts are wrong if we are not refreshing all files.

        progress = RefreshProgress(
            counted_files=api_app.shared_ctx.refresh.get('counted_files', 0),
            counting=flags.refresh_counting.is_set(),
            discovery=flags.refresh_discovery.is_set(),
            indexed=int(results['indexed'] or 0),
            indexing=flags.refresh_indexing.is_set(),
            modeled=int(results['modeled'] or 0),
            modeling=flags.refresh_modeling.is_set(),
            cleanup=flags.refresh_cleanup.is_set(),
            refreshing=flags.refreshing.is_set(),
            total_file_groups=int(results['total_file_groups'] or 0),
            unindexed=int(results['unindexed'] or 0),
        )

    return progress


def mimetypes_to_sql_wheres(mimetypes: List[str], params: dict):
    if mimetypes:
        wheres = list()
        for idx, mimetype in enumerate(mimetypes):
            key = f'mimetype{idx}'
            if len(mimetype.split('/')) == 1:
                params[key] = f'{mimetype}/%'
            else:
                params[key] = f'{mimetype}%'
            wheres.append(f'mimetype LIKE %({key})s')
        return f'({" OR ".join(wheres)})', params
    return '', params


async def search_file_suggestion_count(search_str: str, tag_names: List[str], mimetypes: List[str],
                                       months: List[int] = None, from_year: int = None, to_year: int = None):
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

    wheres, params = tag_append_sub_select_where(tag_names, wheres, params)

    mimetype_wheres, params = mimetypes_to_sql_wheres(mimetypes, params)
    if mimetype_wheres:
        wheres.append(mimetype_wheres)
    wheres, params = months_selector_to_where(months, wheres, params)
    wheres, params = date_range_to_where(from_year, to_year, wheres, params)

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


def _move(destination: pathlib.Path, *sources: pathlib.Path) -> List[Tuple[pathlib.Path, pathlib.Path]]:
    media_directory = get_media_directory()
    for source in sources:
        if not str(source).startswith(str(media_directory)):
            raise FileNotFoundError(f'{source} is not within the media directory')
    if not str(destination).startswith(str(media_directory)):
        raise FileNotFoundError(f'{destination} is not within the media directory')

    destination_existed = destination.is_dir()

    # [ (pathlib.Path('source'), pathlib.Path('destination')), ... ]
    plan = list()
    unique_paths = set()
    # Get all files that need to be moved.  Check for destination conflicts.
    for source in sources:
        if source.is_dir():
            # Recursively move the directory's files.
            for path in walk(source):
                # Preserve the directory structure that contains this file.
                new_file = destination / source.name / path.relative_to(source)
                if new_file.exists():
                    raise FileConflict(f'Cannot move {path} to {new_file} because it already exists')
                if path not in unique_paths:
                    plan.append((path, new_file))
                    unique_paths.add(path)
        elif source.is_file():
            # Move all files associated with the source file.
            for file in glob_shared_stem(source):
                new_file = destination / file.name
                if new_file.exists():
                    raise FileConflict(f'Cannot move {file} to {new_file} because it already exists')
                if file not in unique_paths:
                    plan.append((file, new_file))
                    unique_paths.add(file)

    logger.info(f'Executing move plan with {len(plan)} steps.')

    # Track the steps performed so they can be reversed.
    revert_plan = list()

    def do_plan(plan_):
        # Move deepest files first.
        plan_ = sorted(plan_, key=lambda i: (len(i[0].parents), i[0].name), reverse=True)
        for old_file, new_file in plan_:  # noqa
            new_file.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f'Moving {old_file} to {new_file}')
            # if not new_file.exists():
            shutil.move(str(old_file), str(new_file))
            logger.debug(f'Moved {old_file} to {new_file}')
            revert_plan.append((new_file, old_file))
        # Move is complete.
        return plan_

    try:
        plan = do_plan(plan)
        for source in sources:
            if source.is_dir():
                delete_directory(source)
        logger.info(f'Move execution completed')
        return plan
    except Exception as e:
        logger.error(f'Move failed', exc_info=e)
        # Move files back.
        do_plan(revert_plan)
        # Delete the directories that were created.
        directories = sorted(walk(destination), key=lambda i: len(i.parents), reverse=True)
        for path in directories:
            if path.is_dir():
                delete_directory(path)
        # Remove destination only if it did not exist at the start.
        if destination.is_dir() and destination_existed is False:
            delete_directory(destination)
        raise


def delete_directory(directory: pathlib.Path, recursive: bool = False):
    """Remove a directory, remove it's Directory record.

    Will refuse to delete a directory if it contains Tagged Files."""
    if recursive:
        with get_db_session() as session:
            tagged = session.query(FileGroup) \
                .filter(FileGroup.primary_path.like(f'{directory}/%')) \
                .join(TagFile, TagFile.file_group_id == FileGroup.id) \
                .limit(1).one_or_none()
            if tagged:
                raise FileGroupIsTagged()
        shutil.rmtree(directory)
    else:
        directory.rmdir()
    with get_db_curs(commit=True) as curs:
        stmt = 'DELETE FROM directory WHERE path=%s'
        curs.execute(stmt, (str(directory),))


async def move(destination: pathlib.Path, *sources: pathlib.Path) -> List[Tuple[pathlib.Path, pathlib.Path]]:
    """Moves a file or directory (recursively), preserving applied Tags.

    If the move fails at any point, the files will be returned to their previous locations.

    Returns a list of tuples, the first Path in the tuple is the file's old location, the second Path is where the file
    was moved.
    """
    # Move the files first, if this fails it will revert itself and raise an error.
    plan = _move(destination, *sources)

    # Files were moved, migrate any Tags.
    plan_map = {old: new for old, new in plan}
    with get_db_session(commit=True) as session:
        old_file_paths = list(plan_map.keys())
        old_files: List[Tuple[FileGroup, TagFile]] = session.query(FileGroup, TagFile) \
            .filter(FileGroup.primary_path.in_(old_file_paths)) \
            .join(TagFile, TagFile.file_group_id == FileGroup.id).all()
        logger.info(f'Moving {len(old_files)} tagged files')
        for old_file, _ in old_files:
            try:
                new_file_path = plan_map[old_file.primary_path]
                logger.info(f'Moving tagged file {old_file.primary_path} to {new_file_path}')
                old_file.move(new_file_path, move_files=False)
            except KeyError as e:
                # Got a duplicate?
                logger.error('Error during tag migration', exc_info=e)
        session.commit()

    if PYTEST:
        await refresh_files([destination, *sources])
    else:
        background_task(refresh_files([destination, *sources]))

    return plan


async def rename_file(path: pathlib.Path, new_name: str) -> pathlib.Path:
    """Rename a file (and it's associated files).  Preserve any tags."""
    new_path = path.with_name(new_name)
    if not path.exists():
        raise FileNotFoundError(f'Cannot find {path} to rename')
    if new_path.exists():
        raise FileConflict(f'Cannot rename {path} because {new_path} already exists')

    with get_db_session(commit=True) as session:
        fg = session.query(FileGroup).filter(FileGroup.primary_path == path).one_or_none()
        if not fg:
            # File wasn't yet in the DB.
            fg = FileGroup.from_paths(session, path)
        fg.move(new_path)

    return new_path


async def rename_directory(directory: pathlib.Path, new_name: str) -> pathlib.Path:
    """Rename a directory.  This is done by moving all files into the new directory, and removing the old directory."""
    new_directory = directory.with_name(new_name)
    if new_directory.exists():
        raise FileConflict(f'Cannot rename {directory} to {new_directory} because it already exists.')

    # Move all paths into the new directory.
    paths = list(directory.iterdir())
    await move(new_directory, *paths)
    # Remove the old directory.
    delete_directory(directory)

    return new_directory


async def rename(path: pathlib.Path, new_name: str) -> pathlib.Path:
    """Rename a directory or file.  Preserve any tags."""
    if path.is_dir():
        return await rename_directory(path, new_name)

    return await rename_file(path, new_name)


def add_ignore_directory(directory: Union[pathlib.Path, str]):
    """Add a directory to the `ignored_directories` in the WROLPi config.  This directory will be ignored when
    refreshing."""
    media_directory = get_media_directory()

    directory = pathlib.Path(directory)

    from modules.videos.common import get_videos_directory
    from modules.archive.lib import get_archive_directory
    from modules.map.lib import get_map_directory
    from modules.zim.lib import get_zim_directory
    from modules.videos.common import get_no_channel_directory
    special_directories = [
        get_media_directory(),
        get_videos_directory(),
        get_archive_directory(),
        get_map_directory(),
        get_zim_directory(),
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
