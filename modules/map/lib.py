import asyncio
import subprocess
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from modules.map.models import MapFile
from wrolpi import flags
from wrolpi.api_utils import api_app
from wrolpi.cmd import SUDO_BIN
from wrolpi.common import get_media_directory, walk, logger, get_wrolpi_config
from wrolpi.dates import now, timedelta_to_timestamp, seconds_to_timestamp
from wrolpi.db import optional_session, get_db_session
from wrolpi.events import Events
from wrolpi.vars import PROJECT_DIR, IS_RPI5

logger = logger.getChild(__name__)


def get_map_directory() -> Path:
    map_directory = get_media_directory() / get_wrolpi_config().map_directory
    if not map_directory.is_dir():
        map_directory.mkdir(parents=True)
    return map_directory


def is_pbf_file(pbf: Path) -> bool:
    """Uses file command to check type of file.  Returns True if a file is an OpenStreetMap PBF file."""
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


async def import_files(paths: List[str]):
    if flags.map_importing.is_set():
        import_logger.error('Map import already running...')
        return

    with flags.map_importing:
        paths = [get_media_directory() / i for i in paths]
        import_logger.warning(f'Importing: {", ".join(map(str, paths))}')

        dumps = [i for i in paths if i.suffix == '.dump']
        pbfs = [i for i in paths if i.suffix == '.pbf']

        total_elapsed = 0

        any_success = False
        try:
            if pbfs:
                success = False
                try:
                    api_app.shared_ctx.map_importing.update(dict(
                        pending=list(pbfs),
                    ))
                    total_elapsed += await run_import_command(*pbfs)
                    success = True
                    any_success = True
                except Exception as e:
                    import_logger.warning('Failed to run import', exc_info=e)
                finally:
                    api_app.shared_ctx.map_importing.update(dict(
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
                    api_app.shared_ctx.map_importing.update(dict(
                        pending=str(path),
                    ))
                    total_elapsed += await run_import_command(path)
                    success = True
                    any_success = True
                except Exception as e:
                    import_logger.warning('Failed to run import', exc_info=e)
                finally:
                    api_app.shared_ctx.map_importing.update(dict(
                        pending=None,
                    ))

                if success:
                    with get_db_session(commit=True) as session:
                        map_file = get_or_create_map_file(path, session)
                        map_file.imported = True
        finally:
            if any_success:
                Events.send_map_import_complete(f'Map import completed; took {seconds_to_timestamp(total_elapsed)}')
            else:
                Events.send_map_import_failed(f'Map import failed!  See server logs.')


async def run_import_command(*paths: Path) -> int:
    """Run the map import script on the provided paths.

    Can only import a single *.dump file, or a list of *.osm.pbf files.  They cannot be mixed.

    @return: The seconds elapsed during import.
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
    # Run with sudo so renderd can be restarted.
    cmd = f'{SUDO_BIN} {PROJECT_DIR}/scripts/import_map.sh {paths}'
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

    return int(elapsed.total_seconds())


@optional_session
def get_import_status(session: Session = None) -> List[MapFile]:
    paths = get_map_paths()
    map_paths = []
    for path in paths:
        map_file = get_or_create_map_file(path, session)
        map_paths.append(map_file)

    session.commit()
    return map_paths


# Calculated using many tests on a well-cooled RPi4 (4GB).
RPI4_PBF_BYTES_PER_SECOND = 61879
RPI4_A = 7.17509261732342e-14
RPI4_B = 6.6590760410412e-5
RPI4_C = 10283
# Calculated using many tests on a well-cooled RPi5 (8GB).
RPI5_PBF_BYTES_PER_SECOND = 136003
RPI5_A = 1.6681382703586e-15
RPI5_B = 2.35907824676145e-6
RPI5_C = 53.727


def seconds_to_import_rpi4(size_in_bytes: int) -> int:
    if size_in_bytes > 1_000_000_000:
        # Use exponential curve for large files.
        a = RPI4_A * size_in_bytes ** 2
        b = RPI4_B * size_in_bytes
        return int(a - b + RPI4_C)
    # Use simpler equation for small files.
    return max(int(size_in_bytes // RPI4_PBF_BYTES_PER_SECOND), 0)


def seconds_to_import_rpi5(size_in_bytes: int) -> int:
    if size_in_bytes > 5_000_000_000:
        # Use exponential curve for large files.
        a = RPI5_A * size_in_bytes ** 2
        b = RPI5_B * size_in_bytes
        return int(a - b + RPI5_C)
    # Use simpler equation for small files.
    return max(int(size_in_bytes // RPI5_PBF_BYTES_PER_SECOND), 0)


def seconds_to_import(size_in_bytes: int, is_rpi_5: bool = IS_RPI5) -> int:
    """Attempt to predict how long it will take an RPi4 to import a given PBF file."""
    if is_rpi_5:
        return seconds_to_import_rpi5(size_in_bytes)

    # Default to RPi4, because it's the most conservative estimate.
    return seconds_to_import_rpi4(size_in_bytes)
