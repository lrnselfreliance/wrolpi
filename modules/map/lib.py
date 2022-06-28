import asyncio
import subprocess
from multiprocessing import Event, Manager
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from modules.map.models import MapFile
from wrolpi.cmd import which
from wrolpi.common import get_media_directory, walk, logger, wrol_mode_check
from wrolpi.dates import now, timedelta_to_timestamp
from wrolpi.db import optional_session, get_db_session
from wrolpi.vars import PYTEST, PROJECT_DIR

logger = logger.getChild(__name__)

IMPORT_EVENT = Event()
IMPORTING = Manager().dict()
IMPORTING['path'] = None


def get_map_directory() -> Path:
    map_directory = get_media_directory() / 'map'
    if not map_directory.is_dir():
        map_directory.mkdir()
    return map_directory


def is_pbf_file(pbf: Path) -> bool:
    """Uses file command to check type of a file.  Returns True if a file is an OpenStreetMap PBF file."""
    cmd = ('/usr/bin/file', pbf)
    try:
        output = subprocess.check_output(cmd)
    except FileNotFoundError:
        return False

    return 'OpenStreetMap Protocolbuffer Binary Format' in output.decode()


def is_dump_file(path: Path) -> bool:
    """Uses file command to check type of a file.  Returns True if a file is a Postgresql dump file."""
    cmd = ('/usr/bin/file', path)
    try:
        output = subprocess.check_output(cmd)
    except FileNotFoundError:
        return False

    return 'PostgreSQL custom database dump' in output.decode()


def get_map_paths() -> List[Path]:
    """Find all pbf/dump files in the map directory."""
    map_directory = get_map_directory()
    paths = walk(map_directory)

    def is_valid(path: Path) -> bool:
        if path.is_file():
            if str(path).endswith('.osm.pbf') and is_pbf_file(path):
                return True
            elif path.suffix == '.dump' and is_dump_file(path):
                return True
        return False

    return list(filter(is_valid, paths))


def get_or_create_map_file(pbf_path: Path, session: Session) -> MapFile:
    """Finds the MapFile row in the DB, or creates one."""
    map_file: MapFile = session.query(MapFile).filter_by(path=str(pbf_path)).one_or_none()
    if map_file:
        return map_file

    map_file = MapFile(path=pbf_path, size=pbf_path.stat().st_size)
    session.add(map_file)
    return map_file


async def import_files(files: List[str]):
    if IMPORT_EVENT.is_set():
        logger.warning('Map import already running...')
        return

    # Import dumps, then pbfs.
    import_order = ('.dump', '.pbf')
    files = [get_media_directory() / i for i in files]
    files = sorted(files, key=lambda i: import_order.index(i.suffix))

    logger.warning(f'Importing: {", ".join(map(str, files))}')

    any_success = False
    try:
        IMPORT_EVENT.set()
        for path in files:
            if not path.is_file():
                logger.fatal(f'Map file does not exist! {path}')
                continue

            with get_db_session() as session:
                map_file = session.query(MapFile).filter_by(path=path).one_or_none()
                if map_file and map_file.imported:
                    # Don't import a map file twice.
                    logger.debug(f'{path} is already imported')
                    continue

            success = False
            try:
                IMPORTING['path'] = str(path)
                await import_file(path)
                success = True
                any_success = True
            except Exception as e:
                logger.warning('Failed to run import', exc_info=e)
            finally:
                IMPORTING['path'] = None

            if success:
                with get_db_session(commit=True) as session:
                    map_file = get_or_create_map_file(path, session)
                    map_file.imported = True
    finally:
        if any_success:
            # A map was imported, remove the tile cache files.
            clear_mod_tile()
        IMPORT_EVENT.clear()


BASH_BIN = which('bash', '/bin/bash', warn=True)


async def import_file(path: Path):
    """Run the map import script on the provided path.

    Supports *.osm.pbf and *.dump files."""
    if str(path).endswith('.osm.pbf'):
        if not is_pbf_file(path):
            logger.warning(f'Could not import non-pbf file: {path}')
            raise ValueError('Invalid PBF file')
    elif path.suffix == '.dump':
        if not is_dump_file(path):
            logger.warning(f'Could not import non-dump file: {path}')
            raise ValueError('Invalid dump file')
    else:
        raise ValueError(f'Cannot import unknown file! {path}')

    cmd = f'{BASH_BIN} {PROJECT_DIR}/scripts/import_map.sh {path.absolute()}'
    logger.debug(f'Running import script: {cmd}')
    start = now()
    proc = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    elapsed = now() - start
    success = 'Successful' if proc.returncode == 0 else 'Unsuccessful'
    logger.info(f'{success} import of {path.name} took {timedelta_to_timestamp(elapsed)}')
    if proc.returncode != 0:
        # Log all lines.  Truncate long lines.
        for line in stdout.decode().splitlines():
            logger.debug(line[:500])
        for line in stderr.decode().splitlines():
            logger.error(line[:500])
        raise ValueError(f'Importing map file failed with return code {proc.returncode}')


@optional_session
def get_import_status(session: Session = None) -> List[MapFile]:
    paths = get_map_paths()
    map_paths = []
    for path in paths:
        map_file = get_or_create_map_file(path, session)
        map_paths.append(map_file)

    session.commit()
    return map_paths


MOD_TILE_CACHE_DIR = Path('/var/lib/mod_tile/ajt')


@wrol_mode_check
def clear_mod_tile():
    """Remove all cached map tile files"""
    if PYTEST:
        return

    logger.warning('Clearing map tile cache files')

    if MOD_TILE_CACHE_DIR.is_dir():
        cmd = ('rm', '-r', MOD_TILE_CACHE_DIR)
        subprocess.check_call(cmd)
