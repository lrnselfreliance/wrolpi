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
IMPORTING = Manager().dict(dict(
    pending=None,
))


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


import_logger = logger.getChild('import')

OSMIUM_BIN = which('osmium', '/usr/bin/osmium')


async def import_files(paths: List[str]):
    if IMPORT_EVENT.is_set():
        import_logger.error('Map import already running...')
        return

    paths = [get_media_directory() / i for i in paths]
    import_logger.warning(f'Importing: {", ".join(map(str, paths))}')

    dumps = [i for i in paths if i.suffix == '.dump']
    pbfs = [i for i in paths if i.suffix == '.pbf']

    any_success = False
    try:
        IMPORT_EVENT.set()
        if pbfs:
            success = False
            try:
                IMPORTING.update(dict(
                    pending=list(pbfs),
                ))
                await run_import_command(*pbfs)
                success = True
                any_success = True
            except Exception as e:
                import_logger.warning('Failed to run import', exc_info=e)
            finally:
                IMPORTING.update(dict(
                    pending=None,
                ))

            if success:
                with get_db_session(commit=True) as session:
                    # Any previously imported PBFs are no longer imported.
                    for pbf_path in pbfs:
                        pbf_file = get_or_create_map_file(pbf_path, session)
                        pbf_file.imported = True
                    for pbf_file in session.query(MapFile):
                        pbf_file.imported = pbf_file.path in pbfs

        for path in dumps:
            # Import each dump individually.
            if not path.is_file():
                import_logger.fatal(f'Map file does not exist! {path}')
                continue

            with get_db_session() as session:
                map_file = session.query(MapFile).filter_by(path=path).one_or_none()
                if map_file and map_file.imported:
                    # Don't import a map file twice.
                    import_logger.debug(f'{path} is already imported')
                    continue

            success = False
            try:
                IMPORTING.update(dict(
                    pending=str(path),
                ))
                await run_import_command(path)
                success = True
                any_success = True
            except Exception as e:
                import_logger.warning('Failed to run import', exc_info=e)
            finally:
                IMPORTING.update(dict(
                    pending=None,
                ))

            if success:
                with get_db_session(commit=True) as session:
                    map_file = get_or_create_map_file(path, session)
                    map_file.imported = True
    finally:
        if any_success:
            # A map was imported, remove the tile cache files.
            await clear_mod_tile()
        IMPORT_EVENT.clear()


BASH_BIN = which('bash', '/bin/bash', warn=True)


async def run_import_command(*paths: Path):
    """Run the map import script on the provided paths.

    Can only import a single *.dump file, or a list of *.osm.pbf files.  They cannot be mixed.
    """
    paths = [i.absolute() for i in paths]
    dumps = [i for i in paths if i.suffix == '.dump']
    pbfs = [i for i in paths if i.suffix == '.pbf']

    # Only import a single dump, or a list of pbfs.  No other combinations acceptable.
    if not paths:
        raise ValueError('Must import a file')
    if not dumps and not pbfs:
        raise ValueError('Cannot import unknown file!')
    if dumps and pbfs:
        raise ValueError('Cannot import mixed dumps and pbfs.')
    if len(dumps) > 1:
        raise ValueError('Cannot import more than one dump')
    if dumps and not is_dump_file(dumps[0]):
        import_logger.warning(f'Could not import non-dump file: {dumps}')
        raise ValueError('Invalid dump file')
    if pbfs:
        for path in pbfs:
            if not is_pbf_file(path):
                import_logger.warning(f'Could not import non-pbf file: {path}')
                raise ValueError('Invalid PBF file')

    paths = ' '.join(str(i) for i in paths)
    cmd = f'{BASH_BIN} {PROJECT_DIR}/scripts/import_map.sh {paths}'
    import_logger.warning(f'Running map import command: {cmd}')
    start = now()
    proc = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    elapsed = now() - start
    success = 'Successful' if proc.returncode == 0 else 'Unsuccessful'
    import_logger.info(f'{success} import of {repr(paths)} took {timedelta_to_timestamp(elapsed)}')
    if proc.returncode != 0:
        # Log all lines.  Truncate long lines.
        for line in stdout.decode().splitlines():
            import_logger.debug(line[:500])
        for line in stderr.decode().splitlines():
            import_logger.error(line[:500])
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
async def clear_mod_tile():
    """Remove all cached map tile files"""
    if PYTEST:
        return

    logger.warning('Clearing map tile cache files')

    if MOD_TILE_CACHE_DIR.is_dir():
        await asyncio.create_subprocess_shell(f'rm -r {MOD_TILE_CACHE_DIR}')
