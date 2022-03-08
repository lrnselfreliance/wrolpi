import asyncio
import subprocess
from multiprocessing import Event, Manager
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from modules.map.models import MapFile
from wrolpi.common import get_media_directory, walk, logger
from wrolpi.db import optional_session, get_db_session
from wrolpi.vars import PYTEST, PROJECT_DIR

logger = logger.getChild(__name__)

IMPORT_EVENT = Event()
IMPORTING = Manager().dict()
IMPORTING['pbf'] = None


def get_map_directory() -> Path:
    return get_media_directory() / 'map'


def get_pbf_directory() -> Path:
    pbf_directory = get_map_directory() / 'pbf'
    if not pbf_directory.is_dir():
        pbf_directory.mkdir(parents=True)
    return pbf_directory


def is_pbf_file(pbf: Path) -> bool:
    """Uses file command to check type of a file.  Returns True if a file is an OpenStreetMap PBF file."""
    cmd = ('/usr/bin/file', pbf)
    try:
        output = subprocess.check_output(cmd)
    except FileNotFoundError:
        return False

    return 'OpenStreetMap Protocolbuffer Binary Format' in output.decode()


def get_pbf_paths() -> List[Path]:
    """Find all PBF files in the map/pbf directory"""
    pbf_directory = get_pbf_directory()
    paths = walk(pbf_directory)
    return list(filter(lambda i: i.is_file() and str(i).endswith('.osm.pbf') and is_pbf_file(i), paths))


def get_or_create_map_file(pbf_path: Path, session: Session) -> MapFile:
    """Finds the MapFile row in the DB, or creates one."""
    map_file: MapFile = session.query(MapFile).filter_by(path=str(pbf_path)).one_or_none()
    if map_file:
        return map_file

    map_file = MapFile(path=pbf_path, size=pbf_path.stat().st_size)
    session.add(map_file)
    return map_file


async def import_pbfs(pbfs: List[str]):
    if IMPORT_EVENT.is_set():
        logger.warning('Map import already running...')
        return

    logger.warning(f'Importing: {", ".join(pbfs)}')

    any_success = False
    try:
        IMPORT_EVENT.set()
        for pbf in pbfs:
            pbf = get_media_directory() / pbf
            if not pbf.is_file():
                logger.fatal(f'PBF file does not exist! {pbf}')
                continue

            with get_db_session() as session:
                map_file = session.query(MapFile).filter_by(path=pbf).one_or_none()
                if map_file and map_file.imported:
                    # Don't import a map file twice.
                    logger.debug(f'{pbf} is already imported')
                    continue

            success = False
            try:
                IMPORTING['pbf'] = str(pbf)
                await import_pbf(pbf)
                success = True
                any_success = True
            except Exception as e:
                logger.warning('Failed to run import_pbf', exc_info=e)
            finally:
                IMPORTING['pbf'] = None

            if success:
                with get_db_session(commit=True) as session:
                    map_file = get_or_create_map_file(pbf, session)
                    map_file.imported = True

        if any_success:
            # A map was imported, remove the tile cache files.
            clear_mod_tile()
    finally:
        IMPORT_EVENT.clear()


async def import_pbf(pbf: Path):
    """Run the osm2pgsql binary to import a PBF map file."""
    cmd = f'/bin/bash {PROJECT_DIR}/scripts/import_map.sh {pbf.absolute()}'
    logger.debug(f'Running import script: {cmd}')
    proc = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        for line in stdout.decode().splitlines():
            logger.info(line)
        for line in stderr.decode().splitlines():
            logger.error(line)
        raise ValueError(f'Importing PBF failed with return code {proc.returncode}')


@optional_session
def get_pbf_import_status(session: Session = None):
    pbf_paths: List[Path] = get_pbf_paths()

    pbfs = []
    for path in pbf_paths:
        map_file = get_or_create_map_file(path, session)
        pbfs.append(map_file)
    session.commit()
    return pbfs


MOD_TILE_CACHE_DIR = Path('/var/lib/mod_tile/ajt')


def clear_mod_tile():
    """Remove all cached map tile files"""
    if PYTEST:
        return

    logger.warning('Clearing map tile cache files')

    if MOD_TILE_CACHE_DIR.is_dir():
        cmd = ('rm', '-r', MOD_TILE_CACHE_DIR)
        subprocess.check_call(cmd)
