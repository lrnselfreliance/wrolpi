import asyncio
import datetime
import functools
import glob
import json
import multiprocessing
import os
import pathlib
import re
import subprocess
from itertools import zip_longest
from pathlib import Path
from typing import List, Tuple, Union, Dict, Generator

import cachetools.func
import psycopg2
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, wrol_mode_check, logger, limit_concurrent, \
    partition, cancelable_wrapper, \
    get_files_and_directories, chunks_by_stem, apply_modelers, apply_refresh_cleanup, background_task
from wrolpi.dates import now, from_timestamp
from wrolpi.db import get_db_session, get_db_curs, mogrify, optional_session
from wrolpi.errors import InvalidFile, UnknownDirectory, UnknownFile, UnknownTag
from wrolpi.events import Events
from wrolpi.files.models import FileGroup
from wrolpi.lang import ISO_639_CODES
from wrolpi.tags import TagFile, Tag
from wrolpi.vars import PYTEST

try:
    import magic

    mime = magic.Magic(mime=True)
except ImportError:
    # Magic is not installed
    magic = None
    mime = None

logger = logger.getChild(__name__)

__all__ = ['list_directories_contents', 'delete_file', 'split_path_stem_and_suffix', 'refresh_files', 'search_files',
           'get_mimetype', 'split_file_name_words', 'get_primary_file']


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
    return dict(
        path=file.relative_to(media_directory),
        size=file.stat().st_size,
        mimetype=get_mimetype(file),
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
    return dict(
        path=f'{directory.relative_to(media_directory)}/',
        is_empty=not next(directory.iterdir(), False),
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


IGNORED_DIRECTORIES = ('lost+found',)


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
        if path.is_dir() and path.name in IGNORED_DIRECTORIES:
            # Never show ignored directories.
            continue
        if path.is_dir():
            paths[f'{path.name}/'] = _get_recursive_directory_dict(path, directories)
        else:
            paths[path.name] = _get_file_dict(path)

    return paths


@wrol_mode_check
def delete_file(file: str):
    """Delete a file in the media directory."""
    file = get_media_directory() / file
    if file.is_dir() or not file.is_file():
        raise InvalidFile(f'Invalid file {file}')
    file.unlink()


FILE_NAME_REGEX = re.compile(r'[_ .]')

FILE_BIN = which('file', '/usr/bin/file')


def _mimetype_suffix_map(path: Path, mimetype: str):
    """Special handling for mimetypes.  Python Magic may not return the correct mimetype."""
    from wrolpi.files.ebooks import MOBI_MIMETYPE
    suffix = path.suffix.lower()
    if mimetype == 'application/octet-stream':
        if suffix.endswith('.mobi'):
            return MOBI_MIMETYPE
        if suffix.endswith('.stl'):
            return 'model/stl'
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
    return mimetype


@functools.lru_cache(maxsize=10_000)
def get_mimetype(path: Path) -> str:
    """Get the mimetype of a file, prefer using `magic`, fallback to builtin `file` command."""
    if magic is None:
        # This method is slow, prefer the speedier `magic` module.
        cmd = (FILE_BIN, '--mime-type', str(path.absolute()))
        output = subprocess.check_output(cmd)
        output = output.decode()
        mimetype = output.split(' ')[-1].strip()
        return mimetype
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


def get_primary_file(files: Union[Tuple[pathlib.Path], List[pathlib.Path]]) -> Union[pathlib.Path, List[pathlib.Path]]:
    """Given a list of files, return the file that we can model or index."""
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

    logger.debug(f'Cannot find primary file for group: {files}')

    # Can't find a typical primary file.
    return files


def _upsert_files(files: List[pathlib.Path], idempotency: datetime.datetime):
    """Insert/update all records of the provided files.

    Any inserted files will be marked with `indexed=false`.  Any existing files will only be updated if their
    size/modification_datetime changed.

    It is assumed all files exist."""
    idempotency = str(idempotency)

    for chunk in chunks_by_stem(files, 100):
        # Group all files by their shared full-stem.  `chunk_by_stem` already sorted the files.
        grouped = group_files_by_stem(chunk, pre_sorted=True)
        # Convert the groups into file_groups.  Extract common information into `file_group.data`.
        values = dict()
        for group in grouped:
            # The primary file is the video/SingleFile/epub, etc.
            primary_path_or_paths = get_primary_file(group)
            if isinstance(primary_path_or_paths, list) or isinstance(primary_path_or_paths, tuple):
                # Cannot find primary path, create group for each file.
                for primary_path in primary_path_or_paths:
                    primary_path: pathlib.Path
                    # The primary mimetype allows modelers to find its file_groups.
                    mimetype = get_mimetype(primary_path)
                    modification_datetime = from_timestamp(primary_path.stat().st_mtime)
                    size = primary_path.stat().st_size
                    files = json.dumps(_paths_to_files_dict([primary_path]))
                    values[primary_path] = (modification_datetime, mimetype, size, files)
            else:
                # Multiple files in this group.
                primary_path: pathlib.Path = primary_path_or_paths
                # The primary mimetype allows modelers to find its file_groups.
                mimetype = get_mimetype(primary_path)
                # The group uses a common modification_datetime so the group will be re-indexed when any of it's files
                # are modified.
                modification_datetime = from_timestamp(max(i.stat().st_mtime for i in group))
                size = sum(i.stat().st_size for i in group)
                files = json.dumps(_paths_to_files_dict(group))
                values[primary_path] = (modification_datetime, mimetype, size, files)

        # `False` is the `indexed` which is false to force indexing by default.
        values = [(str(primary_path), False, idempotency, *i) for primary_path, i in values.items()]
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
                RETURNING id, indexed
            '''
            curs.execute(stmt)
            need_index = [i[0] for i in curs.fetchall() if i[1] is False]
            if need_index:
                refresh_logger.info(f'Invalidated indexes of {len(need_index)} file groups')


async def refresh_discover_paths(paths: List[pathlib.Path], idempotency: datetime.datetime = None):
    """Discover all files in the directories provided in paths, as well as all files in paths.

    All records for files in `paths` that do not exist will be deleted.

    Will refuse to refresh when the media directory is empty."""
    try:
        next(get_media_directory().iterdir())
    except:
        # We don't want to delete a bunch of files which would exist if the drive was mounted.
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
            new_files, new_directories = get_files_and_directories(directory)
            directories.extend(new_directories)
            files.extend(new_files)
            if len(files) >= 100:
                # Wait until there are enough files to perform the upsert.
                _upsert_files(files, idempotency)
                files = list()
            # Sleep to catch cancel.
            await asyncio.sleep(0)
        if files:
            # Not enough files for the chunks above, finish what is left.
            _upsert_files(files, idempotency)

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


REFRESH = multiprocessing.Manager().dict()


@limit_concurrent(1)  # Only one refresh at a time.
@wrol_mode_check
@cancelable_wrapper
async def refresh_files(paths: List[pathlib.Path] = None, send_events: bool = True):
    """Find, model, and index all files in the media directory."""
    if isinstance(paths, str):
        paths = [pathlib.Path(paths), ]
    if isinstance(paths, pathlib.Path):
        paths = [paths, ]

    refreshing_all_files = False

    with flags.refreshing:
        if not paths:
            refresh_logger.warning('Refreshing all files')
            refreshing_all_files = True
        else:
            refresh_logger.warning(f'Refreshing {", ".join(list(map(str, paths)))}')
        if send_events:
            Events.send_global_refresh_started()

        idempotency = now()

        # Add all files in the media directory to the DB.
        paths = paths or [get_media_directory()]
        with flags.refresh_discovery:
            from wrolpi.count_files import count_files
            total_count = sum(count_files(i) for i in paths)
            REFRESH['total_files'] = total_count
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
        with flags.cleanup:
            await apply_refresh_cleanup()
        if send_events:
            Events.send_global_after_refresh_completed()

        if send_events:
            Events.send_global_refresh_completed()
        refresh_logger.warning('Done refreshing Files')

        if refreshing_all_files:
            # Only set refresh_complete flag if all files have been refreshed.
            flags.refresh_complete.set()


async def apply_indexers():
    """Indexes any Files that have not yet been indexed by Modelers, or by previous calls of this function."""
    from wrolpi.files.models import FileGroup
    refresh_logger.info('Applying indexers')

    while True:
        # Continually query for Files that have not been indexed.
        with get_db_session(commit=True) as session:
            file_groups = session.query(FileGroup).filter(FileGroup.indexed != True).limit(20)
            file_groups: List[FileGroup] = list(file_groups)

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

            refresh_logger.debug(f'Indexed {processed} files')

            if processed < 20:
                # Processed less than the limit, don't do the next query.
                break


def search_files(search_str: str, limit: int, offset: int, mimetypes: List[str] = None, model: str = None,
                 tags: List[str] = None) -> \
        Tuple[List[dict], int]:
    """Search the FileGroup table.

    Order the returned Files by their rank if `search_str` is provided.  Return all files if
    `search_str` is empty.

    Parameters:
        search_str: Search the ts_vector of the file.  Returns all files if this is empty.
        limit: Return only this many files.
        offset: Offset the query.
        mimetypes: Only return files that match these mimetypes.
        model: Only return files that match this model.
    """
    params = dict(offset=offset, limit=limit)
    wheres = []
    selects = []
    order_by = '1 ASC'
    joins = []

    if search_str:
        params['search_str'] = search_str
        wheres.append('textsearch @@ websearch_to_tsquery(%(search_str)s)')
        selects.append('ts_rank(textsearch, websearch_to_tsquery(%(search_str)s))')
        order_by = '2 DESC'

    if mimetypes:
        mimetype_wheres = []
        for idx, mimetype in enumerate(mimetypes):
            key = f'mimetype{idx}'
            if len(mimetype.split('/')) == 1:
                params[key] = f'{mimetype}/%'
            else:
                params[key] = f'{mimetype}%'
            mimetype_wheres.append(f'mimetype LIKE %({key})s')
        mimetype_wheres = ' OR '.join(mimetype_wheres)
        wheres.append(f'({mimetype_wheres})')

    if model:
        params['model'] = model
        wheres.append('model = %(model)s')

    if tags:
        where_, params_, join_ = tag_names_to_clauses(tags)
        wheres.append(where_)
        params.update(params_)
        joins.append(join_)

    wheres = '\n AND '.join(wheres)
    selects = f"{', '.join(selects)}, " if selects else ""
    join = '\n'.join(joins)
    stmt = f'''
        SELECT fg.id, {selects} COUNT(*) OVER() AS total
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


def tag_names_to_clauses(tags: List[str]):
    """Create the SQL necessary to filter the `file_group` table by the provided Tag names."""
    params = dict()

    if not tags:
        return '', params, ''

    where_tags = []
    joins = []
    for idx, tag_name in enumerate(tags):
        where_tags.append(f't{idx}.name = %(tag_name{idx})s')
        params[f'tag_name{idx}'] = tag_name
        joins.append(f'LEFT JOIN tag_file tf{idx} ON tf{idx}.file_group_id = fg.id '
                     f'LEFT JOIN tag t{idx} ON t{idx}.id = tf{idx}.tag_id')
    where_tags = ' AND '.join(where_tags)
    wheres = f'({where_tags})'
    join = '\n'.join(joins)
    return wheres, params, join


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
            ranks = [i['ts_rank'] for i in results]
        except KeyError:
            # No `ts_rank`, probably not searching `file_group.textsearch`.
            ranks = []

    with get_db_session() as session:
        from modules.videos.models import Video
        results = session.query(FileGroup, Video) \
            .filter(FileGroup.id.in_(ordered_ids)) \
            .outerjoin(Video, Video.file_group_id == FileGroup.id)
        # Order FileGroups by their location in ordered_ids.
        file_groups: List[Tuple[FileGroup, Video]] = sorted(results, key=lambda i: ordered_ids.index(i[0].id))
        results = list()
        for rank, (file_group, video) in zip_longest(ranks, file_groups):
            video: Video
            if video:
                results.append(video.__json__())
            else:
                results.append(file_group.__json__())
            # Preserve the ts_ranks, if any.
            if rank:
                results[-1]['ts_rank'] = rank

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
    files = sorted(files) if not pre_sorted else files
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


def get_refresh_progress():
    with get_db_curs() as curs:
        curs.execute('''
            SELECT
                COUNT(id) AS "total_file_groups",
                COUNT(id) FILTER (WHERE indexed IS TRUE) AS "indexed",
                COUNT(id) FILTER (WHERE indexed IS FALSE) AS "unindexed",
                COUNT(id) FILTER (WHERE model IS NOT NULL) AS "modeled"
            FROM file_group
        ''')
        results = dict(curs.fetchone())

        status = dict(
            cleanup=flags.cleanup.is_set(),
            discovery=flags.refresh_discovery.is_set(),
            indexed=results['indexed'],
            indexing=flags.refresh_indexing.is_set(),
            modeled=results['modeled'],
            modeling=flags.refresh_modeling.is_set(),
            refreshing=flags.refreshing.is_set(),
            total_files=REFRESH.get('total_files', 0),
            total_file_groups=results['total_file_groups'],
            unindexed=results['unindexed'],
        )

    return status
