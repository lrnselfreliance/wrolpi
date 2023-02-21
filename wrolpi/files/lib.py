import asyncio
import datetime
import functools
import glob
import os
import pathlib
import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Union, Dict

import cachetools.func
import psycopg2
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, wrol_mode_check, logger, limit_concurrent, \
    get_files_and_directories, apply_modelers, apply_after_refresh, get_model_by_table_name, chunks_by_stem, \
    partition, ordered_unique_list, chunks, cancelable_wrapper, get_relative_to_media_directory
from wrolpi.dates import now
from wrolpi.db import get_db_session, get_db_curs, get_ranked_models
from wrolpi.errors import InvalidFile
from wrolpi.events import Events
from wrolpi.files.models import File
from wrolpi.vars import PYTEST, FILE_REFRESH_CHUNK_SIZE

try:
    import magic

    mime = magic.Magic(mime=True)
except ImportError:
    # Magic is not installed
    magic = None
    mime = None

logger = logger.getChild(__name__)

__all__ = ['list_directories_contents', 'delete_file', 'split_path_stem_and_suffix', 'refresh_files', 'search_files',
           'get_mimetype', 'split_file_name_words']


@cachetools.func.ttl_cache(10_000, 30.0)
def _get_file_dict(file: pathlib.Path,
                   directories_cache: str,  # Used to cache by requested directories.
                   ) -> Dict:
    media_directory = get_media_directory()
    return dict(
        path=file.relative_to(media_directory),
        size=file.stat().st_size,
        mimetype=get_mimetype(file),
    )


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
                children[path.name] = _get_file_dict(path, directories_cache)
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
            paths[path.name] = _get_file_dict(path, str(directories))

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
    if mimetype == 'application/octet-stream' and suffix.endswith('.mobi'):
        return MOBI_MIMETYPE
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
    return mimetype


@functools.lru_cache(maxsize=1000)
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
    '.en.vtt',
    '.en.srt',
    '.readability.json',
    '.readability.txt',
    '.readability.html',
}


@functools.lru_cache()
def split_path_stem_and_suffix(path: Union[pathlib.Path, str]) -> Tuple[str, str]:
    """Get the path's stem and suffix.

    This function handles WROLPi suffixes like .info.json."""
    if isinstance(path, str):
        path = pathlib.Path(path)

    full = str(path)  # May or may not be absolute.
    suffix = next(filter(lambda i: full.endswith(i), SUFFIXES), path.suffix)
    if suffix:
        return path.name[:-1 * len(suffix)], suffix
    # Path has no suffix.
    return path.name, ''


refresh_logger = logger.getChild('refresh')


@wrol_mode_check
async def _refresh_files_list(paths: List[pathlib.Path], idempotency: datetime.datetime):
    """Upsert, index, and model all provided paths."""
    # Update the idempotency if any files already in the DB.
    if not paths:
        return

    for idx, chunk in enumerate(map(set, chunks_by_stem(paths, FILE_REFRESH_CHUNK_SIZE))):
        with get_db_session(commit=True) as session:
            existing_files = list(session.query(File).filter(File.path.in_(chunk)))
            existing_paths = {i.path for i in existing_files}
            # Add any new files into the database.
            new_files = []
            if new_paths := (chunk - existing_paths):
                new_files = [File(path=i, idempotency=idempotency) for i in new_paths]
                session.add_all(new_files)
            # Apply models to all files.  Many files will have no model.
            all_files = existing_files + new_files
            apply_modelers(all_files, session)

            # Update idempotency for existing files after modelers.  Otherwise SQLAlchemy forgets.
            for existing_file in existing_files:
                existing_file.idempotency = idempotency

        if idx > 0:
            parent = all_files[0].path.parent
            refresh_logger.debug(f'Committed chunk of {len(chunk)} files.  Refreshing near {parent}')

        # Sleep between chunks to catch cancel.
        await asyncio.sleep(0)


async def _refresh_directory_files_recursively(directory: pathlib.Path, idempotency: datetime):
    """Refresh all files in a directory, recursively refresh all files in subdirectories."""
    directories = [directory, ]
    while directories:
        directory = directories.pop(0)
        try:
            files, new_directories = get_files_and_directories(directory)
            directories.extend(new_directories)
            if files:
                refresh_logger.info(f'Refreshing {len(files)} files in {directory}')
                await _refresh_files_list(files, idempotency)
        except Exception as e:
            refresh_logger.error(f'Failed to refresh files in {directory}', exc_info=e)
        except asyncio.CancelledError:
            refresh_logger.error(f'Refresh canceled during {directory}')
            raise


@cancelable_wrapper
async def apply_indexers():
    """Finds all Files that have not been indexed and indexes them."""
    from wrolpi.files.models import File
    from wrolpi.db import get_db_session, get_db_curs

    with get_db_curs() as curs:
        curs.execute('SELECT path FROM file WHERE indexed = false AND associated = false')
        missing_index = [pathlib.Path(i[0]) for i in curs.fetchall()]

    refresh_logger.info(f'Indexing {len(missing_index)} files')

    # Indexing can be slow, commit when its been too long.
    last_commit = now()
    max_seconds_between_commits = 30

    for chunk in chunks(missing_index, 100):
        with get_db_session(commit=True) as session:
            files = session.query(File).filter(File.path.in_(chunk))
            for file in files:
                try:
                    file.do_index()
                except Exception as e:
                    refresh_logger.error(f'Failed to index {file=}', exc_info=e)
                    if PYTEST:
                        raise

                if (now() - last_commit).total_seconds() > max_seconds_between_commits:
                    refresh_logger.debug('Committing because its been too long.')
                    session.commit()
                    last_commit = now()

                # Sleep to catch cancel.
                await asyncio.sleep(0)
        last_commit = now()

        refresh_logger.info(f'Indexed chunk of {len(chunk)} files')


@wrol_mode_check
async def refresh_files_list(paths: List[str], include_files_near: bool = True):
    """Refresh a list of files.  Will not refresh directories or subdirectories.

    Parameters:
        paths: A list of files that need to be refreshed.  If not absolute, they are assumed to be relative to the
               media directory.
        include_files_near: If true, will also refresh files that share the stem of the provided files.
    """
    refresh_logger.info(f'Refreshing {len(paths)} files list')

    media_directory = get_media_directory()

    # Convert all paths to absolute paths in the media directory.
    paths = [pathlib.Path(i) for i in paths]
    paths = [media_directory / i if not i.is_absolute() else i for i in paths]

    if not paths:
        raise FileNotFoundError('No files to refresh')

    if include_files_near:
        new_paths = []
        for path in paths:
            new_paths.extend(glob_shared_stem(path))
        paths.extend(new_paths)

    paths, deleted_paths = partition(lambda i: i.exists(), paths)

    idempotency = now()
    await _refresh_files_list(paths, idempotency)

    # Delete any files near the paths that no longer exist.
    paths_stems = [split_path_stem_and_suffix(i)[0] for i in paths]
    paths_stems = [str(media_directory / i) for i in paths_stems]
    with get_db_curs(commit=True) as curs:
        # Get all paths that match the stems of these refreshed files.
        params = dict(paths_stems=paths_stems, idempotency=idempotency)
        curs.execute('''
            UPDATE file SET idempotency = %(idempotency)s
            WHERE full_stem = ANY (%(paths_stems)s)
            RETURNING path
        ''', params)
        existing_paths = [pathlib.Path(i[0]) for i in curs.fetchall()]
        # Delete any files which no longer exist.
        deleted_paths.extend([i for i in existing_paths if not i.exists()])
        deleted_paths = list(map(str, deleted_paths))
        curs.execute('DELETE FROM file WHERE path = ANY(%(deleted_paths)s)', dict(deleted_paths=deleted_paths))

    apply_after_refresh()
    await apply_indexers()

    refresh_logger.info('Done refreshing files list')


@limit_concurrent(1)  # Only one refresh at a time.
@wrol_mode_check
@cancelable_wrapper
async def refresh_files():
    """Find, model, and index all files in the media directory."""
    with flags.refreshing:
        refresh_logger.warning('Refreshing all files')
        Events.send_global_refresh_started()

        # TODO remove this later when everyone has migrated their files.
        from modules.archive.lib import migrate_archive_files
        migrate_archive_files()

        idempotency = now()

        # Add all files in the media directory to the DB.
        await _refresh_directory_files_recursively(get_media_directory(), idempotency)

        Events.send_global_refresh_modeling_completed()

        # Remove any records where the file no longer exists.
        with get_db_curs(commit=True) as curs:
            curs.execute('DELETE FROM file WHERE idempotency < %s OR idempotency is null RETURNING path',
                         (idempotency,))
            deleted = list(curs.fetchall())
            logger.debug(f'{deleted=}')
            logger.warning(f'Removed {len(deleted)} missing files')

        Events.send_global_refresh_delete_completed()

        apply_after_refresh()
        await apply_indexers()
        Events.send_global_refresh_indexing_completed()

        Events.send_global_refresh_completed()
        refresh_logger.warning('Done refreshing Files')

        flags.refresh_complete.set()


@limit_concurrent(1)
@wrol_mode_check
@cancelable_wrapper
async def refresh_directory_files_recursively(directory: Union[pathlib.Path, str], send_events: bool = True):
    """Upsert and index all files within a directory (recursively).

    Any records of the files that are no longer in the directory will be removed."""
    if isinstance(directory, str):
        directory = pathlib.Path(directory)
    if directory.is_file():
        raise ValueError(f'Cannot refresh files of a file: {directory=}')

    with flags.refreshing_directory:
        relative_path = str(get_relative_to_media_directory(directory))
        if send_events:
            Events.send_directory_refresh_started(f'Refresh of {repr(relative_path)} has started.')

        # All Files older than this will be removed.
        idempotency = now()

        refresh_logger.info(f'Recursively refreshing all files in {directory}')

        await _refresh_directory_files_recursively(directory, idempotency)

        # Remove any records where the file no longer exists.
        with get_db_curs(commit=True) as curs:
            refresh_logger.debug(f'Deleting files no longer in {directory}')
            params = dict(
                directory=f'{directory}/%',  # trailing / is important!
                idempotency=idempotency,
            )
            stmt = '''
            DELETE FROM file
            WHERE
             (idempotency < %(idempotency)s OR idempotency IS NULL)
             AND path LIKE %(directory)s'''
            curs.execute(stmt, params)

        apply_after_refresh()
        await apply_indexers()

        if send_events:
            Events.send_directory_refresh_completed(f'Refresh of {repr(relative_path)} has completed.')
        refresh_logger.info(f'Done refreshing files in {directory}')


def search_files(search_str: str, limit: int, offset: int, mimetypes: List[str] = None, model: str = None) -> \
        Tuple[List[dict], int]:
    """Search the Files table.

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
    wheres = ['associated = false']
    selects = []
    order_by = '1 ASC'

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

    wheres = '\n AND '.join(wheres)
    selects = f"{', '.join(selects)}, " if selects else ""
    stmt = f'''
        SELECT path, {selects} COUNT(*) OVER() AS total
        FROM file
        {f"WHERE {wheres}" if wheres else ""}
        ORDER BY {order_by}
        OFFSET %(offset)s LIMIT %(limit)s
    '''

    results, total = handle_search_results(stmt, params)
    return results, total


def handle_search_results(statement: str, params):
    """
    Execute the provided SQL statement and fetch the Files returned.

    WARNING: This expects specific queries to be executed and shouldn't be used for things not related to search.

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
        ranked_paths = [pathlib.Path(i['path']) for i in results]
        try:
            ranks = [i['ts_rank'] for i in results]
        except KeyError:
            # No `ts_rank`, probably not searching `file.textsearch`.
            ranks = []

    with get_db_session() as session:
        results = get_ranked_models(ranked_paths, File, session=session)
        try:
            results = assign_file_prefetched_models(results)
        except Exception as e:
            logger.error(f'Failed to assign file prefetched models', exc_info=e)
            if PYTEST:
                raise
        results = [i.__json__() for i in results]
        # Preserve the ts_ranks, if any.
        for idx, rank in enumerate(ranks):
            results[idx]['ts_rank'] = rank

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


def assign_file_prefetched_models(files: List[File]) -> List[File]:
    """
    Prefetch the sub-models (matching `File.model`) in bulk to avoid issuing a query for every File.

    >>> f = File(path='something', model='video')
    >>> v = Video(video_path='something')
    >>> results = assign_file_prefetched_models([f])
    >>> results[0]
    File(path='something', model='video')
    >>> results[0].prefetched_model == v
    True
    """
    if not files:
        return files

    files = files.copy()
    files_index = {i.path: files.index(i) for i in files}
    session = Session.object_session(files[0])

    files_by_model = dict()
    for file in files:
        if not file.model:
            continue
        try:
            files_by_model[file.model].append(file)
        except KeyError:
            files_by_model[file.model] = [file, ]

    logger.debug(f'Prefetching file models: {list(files_by_model.keys())}')
    table_map = {i: get_model_by_table_name(i) for i in {j.model for j in files}}
    for model, model_files in files_by_model.items():
        table = table_map[model]
        try:
            sub_models = table.find_by_paths([i.path for i in model_files], session)
            for sub_model in sub_models:
                file: File = files[files_index[sub_model.primary_path]]
                file.prefetched_model = sub_model
        except NotImplementedError:
            # Model has not defined the necessary methods.
            pass

    return files


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


def split_file_name_words(name: str) -> List[str]:
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

        words = ordered_unique_list(words)
        return words
    except Exception as e:
        logger.error(f'Failed to split filename into words: {name}', exc_info=e)
        return [name]


def get_file_statistics():
    with get_db_curs() as curs:
        curs.execute('''
        SELECT
            COUNT(path) AS "total_count",
            COUNT(path) FILTER (WHERE file.mimetype = 'application/pdf') AS "pdf_count",
            COUNT(path) FILTER (WHERE file.mimetype = 'application/zip') AS "zip_count",
            COUNT(path) FILTER (WHERE file.mimetype LIKE 'video/%') AS "video_count",
            COUNT(path) FILTER (WHERE file.mimetype LIKE 'image/%' AND file.associated = FALSE) AS "image_count",
            COUNT(path) FILTER (WHERE file.mimetype LIKE 'audio/%' AND file.associated = FALSE) AS "audio_count",
            SUM(size)::BIGINT AS "total_size"
        FROM
            file
        ''')
        statistics = dict(curs.fetchall()[0])
        statistics['total_size'] = statistics['total_size'] or 0

        curs.execute('SELECT COUNT(*) FROM archive')
        statistics['archive_count'] = curs.fetchall()[0][0]

        curs.execute('SELECT COUNT(*) FROM ebook')
        statistics['ebook_count'] = curs.fetchall()[0][0]

        return statistics
