import asyncio
import datetime
import glob
import pathlib
import re
import subprocess
from asyncio import Task
from functools import wraps
from pathlib import Path
from typing import List, Tuple, Union

import psycopg2
from sqlalchemy.orm import Session

from wrolpi.cmd import which
from wrolpi.common import get_media_directory, wrol_mode_check, logger, limit_concurrent, \
    get_files_and_directories, apply_modelers, apply_after_refresh, get_model_by_table_name, chunks_by_name, \
    background_task
from wrolpi.dates import now
from wrolpi.db import get_db_session, get_db_curs, get_ranked_models
from wrolpi.errors import InvalidFile
from wrolpi.files.models import File
from wrolpi.vars import PYTEST, FILE_REFRESH_CHUNK_SIZE

try:
    import magic

    mime = magic.Magic(mime=True)

    no_magic = False
except ImportError:
    # Magic is not installed
    no_magic = True

logger = logger.getChild(__name__)

__all__ = ['list_files', 'delete_file', 'split_path_stem_and_suffix', 'refresh_files', 'file_search', 'get_mimetype']


def filter_parent_directories(directories: List[Path]) -> List[Path]:
    """
    Remove parent directories if their children are in the list.

    >>> filter_parent_directories([Path('foo'), Path('foo/bar'), Path('baz')])
    [Path('foo/bar'), Path('baz')]
    """
    unique_children = set()
    for directory in sorted(directories):
        for parent in directory.parents:
            # Remove any parent of this child.
            if parent in unique_children:
                unique_children.remove(parent)
        unique_children.add(directory)

    # Restore the original order.
    new_directories = [i for i in directories if i in unique_children]
    return new_directories


def list_files(directories: List[str]) -> List[Path]:
    """List all files down to the directories provided.  This includes all parent directories of the directories."""
    media_directory = get_media_directory()

    # Always display the media_directory files.
    paths = list(media_directory.iterdir())

    if directories:
        directories = [media_directory / i for i in directories if i]
        directories = filter_parent_directories(directories)
        for directory in directories:
            directory = media_directory / directory
            for parent in directory.parents:
                is_relative_to = str(media_directory).startswith(str(parent))
                if parent == Path('') or is_relative_to:
                    continue
                paths.extend(parent.iterdir())
            paths.extend(directory.iterdir())

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


def get_mimetype(path: Path) -> str:
    """Get the mimetype of a file, prefer using `magic`, fallback to builtin `file` command."""
    if no_magic:
        # This method is slow, prefer the speedier `magic` module.
        cmd = (FILE_BIN, '--mime-type', str(path.absolute()))
        output = subprocess.check_output(cmd)
        output = output.decode()
        mimetype = output.split(' ')[-1].strip()
        return mimetype
    else:
        return mime.from_file(path)


# Special suffixes within WROLPi.
SUFFIXES = {
    '.info.json',
    '.en.vtt',
    '.en.srt',
    '.readability.json',
    '.readability.txt',
    '.readability.html',
}


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

    for idx, chunk in enumerate(map(set, chunks_by_name(paths, FILE_REFRESH_CHUNK_SIZE))):
        with get_db_session(commit=True) as session:
            existing_files = list(session.query(File).filter(File.path.in_(chunk)))
            existing_paths = {i.path for i in existing_files}
            # Add any new files into the database.
            new_files = []
            if new_paths := (chunk - existing_paths):
                new_files = [File(path=i, idempotency=idempotency, mimetype=get_mimetype(i)) for i in new_paths]
                session.add_all(new_files)
                session.flush(new_files)
            # Apply models to all files.  Many files will have no model.
            all_files = existing_files + new_files
            apply_modelers(all_files, session)

            # Update idempotency for existing files after modelers.  Otherwise SQLAlchemy forgets.
            for existing_file in existing_files:
                existing_file.idempotency = idempotency

        if idx > 0:
            parent = all_files[0].path.parent
            refresh_logger.debug(f'Committed chunk of {len(chunk)} files in {parent}')

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


REFRESH_TASKS: List[Task] = []


async def cancel_refresh_tasks():
    """Cancel all refresh tasks, if any."""
    if REFRESH_TASKS:
        refresh_logger.warning(f'Canceling {len(REFRESH_TASKS)} refreshes')
        for task in REFRESH_TASKS:
            task.cancel()
        await asyncio.gather(*REFRESH_TASKS)


def cancelable_wrapper(func: callable):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        if PYTEST:
            return await func(*args, **kwargs)

        task = background_task(func(*args, **kwargs))
        REFRESH_TASKS.append(task)

    return wrapped


@limit_concurrent(1)  # Only one refresh at a time.
@wrol_mode_check
@cancelable_wrapper
async def refresh_files():
    """Find, model, and index all files in the media directory."""
    refresh_logger.warning('Refreshing all files')

    # TODO remove this later when everyone has migrated their files.
    from modules.archive.lib import migrate_archive_files
    migrate_archive_files()

    idempotency = now()

    # Add all files in the media directory to the DB.
    await _refresh_directory_files_recursively(get_media_directory(), idempotency)

    # Remove any records where the file no longer exists.
    with get_db_curs(commit=True) as curs:
        curs.execute('DELETE FROM file WHERE idempotency < %s OR idempotency is null RETURNING path', (idempotency,))
        deleted = list(curs.fetchall())
        logger.debug(f'{deleted=}')
        logger.warning(f'Removed {len(deleted)} missing files')

    apply_after_refresh()

    refresh_logger.warning('Done refreshing Files')


@limit_concurrent(1)
@wrol_mode_check
@cancelable_wrapper
async def refresh_directory_files_recursively(directory: Union[pathlib.Path, str]):
    """Upsert and index all files within a directory (recursively).

    Any records of the files that are no longer in the directory will be removed."""
    if isinstance(directory, str):
        directory = pathlib.Path(directory)
    if not directory.is_dir():
        raise ValueError(f'Cannot refresh files of a file: {directory=}')

    # All Files older than this will be removed.
    idempotency = now()

    refresh_logger.warning(f'Recursively refreshing all files in {directory}')

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

    refresh_logger.info(f'Done refreshing files in {directory}')


def file_search(search_str: str, limit: int, offset: int, mimetype: str = None, model: str = None) -> Tuple[
    List[dict], int]:
    """
    Search the Files table.  Order the returned Files by their rank if `search_str` is provided.  Return all files if
    `search_str` is empty.

    Parameters:
        search_str: Search the ts_vector of the file.  Returns all files if this is empty.
        limit: Return only this many files.
        offset: Offset the query.
        mimetype: Only return files that match this mimetype.
        model: Only return files that match this model.
    """
    params = dict(offset=offset, limit=limit)
    wheres = []
    selects = []
    order_by = 'associated, 1 ASC'

    if search_str:
        params['search_str'] = search_str
        wheres.append('textsearch @@ websearch_to_tsquery(%(search_str)s)')
        selects.append('ts_rank(textsearch, websearch_to_tsquery(%(search_str)s))')
        order_by = 'associated, 2 DESC'

    if mimetype and len(mimetype.split('/')) == 1:
        params['mimetype'] = f'{mimetype}/%'
        wheres.append('mimetype LIKE %(mimetype)s')
    elif mimetype:
        wheres.append('mimetype = %(mimetype)s')
        params['mimetype'] = mimetype

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

    with get_db_session() as session:
        results = get_ranked_models(ranked_paths, File, session=session)
        try:
            results = assign_file_prefetched_models(results)
        except Exception as e:
            logger.error(f'Failed to assign file prefetched models', exc_info=e)
            if PYTEST:
                raise
        results = [i.__json__() for i in results]

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
