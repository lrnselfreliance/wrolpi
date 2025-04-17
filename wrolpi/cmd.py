"""Paths for third-party commands that WROLPi may require."""
import asyncio
import dataclasses
import os
import pathlib
import shlex
import shutil
import tempfile
from asyncio import CancelledError
from pathlib import Path
from time import time
from typing import Optional

from wrolpi.common import logger, TRACE_LEVEL
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)


def is_executable(path: Path) -> bool:
    """Returns True if the file is executable."""
    return path.is_file() and os.access(path, os.X_OK)


def which(*possible_paths: str, warn: bool = False) -> Optional[Path]:
    """
    Find an executable in the system $PATH.  If the executable cannot be found in $PATH, then return the first
    executable found in possible_paths.

    Returns None if no executable can be found.
    """
    found = None
    possible_paths = list(map(Path, possible_paths))
    for path in possible_paths:
        if is_executable(path):
            # `path` was an absolute file which is executable.
            found = path
            break
        path = shutil.which(path)
        if path and (path := Path(path).absolute()) and is_executable(path):
            # `path` was a name or relative path.
            found = path

    if not found and warn and not PYTEST and not DOCKERIZED:
        logger.warning(f'Cannot find executable {possible_paths[0]}')
        return
    elif found:

        return found.absolute()


def pid_is_running(pid: int) -> bool:
    """Return True if a process with PID exists."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# Admin
SUDO_BIN = which('sudo', '/usr/bin/sudo')
NMCLI_BIN = which('nmcli', '/usr/bin/nmcli')
CPUFREQ_INFO_BIN = which('cpufreq-info', '/usr/bin/cpufreq-info')
CPUFREQ_SET_BIN = which('cpufreq-set', '/usr/bin/cpufreq-set')

# Files
WGET_BIN = which('wget', '/usr/bin/wget')

# Map
BASH_BIN = which('bash', '/bin/bash')

# Archive
SINGLE_FILE_BIN = which('single-file',
                        '/usr/bin/single-file',  # rpi os
                        '/usr/local/bin/single-file',  # debian
                        )
CHROMIUM = which('chromium-browser', 'chromium',
                 '/usr/bin/chromium-browser',  # rpi os
                 '/usr/bin/chromium',  # debian
                 )
READABILITY_BIN = which('readability-extractor',
                        '/usr/bin/readability-extractor',  # rpi os
                        '/usr/local/bin/readability-extractor',  # debian
                        )

# Videos
YT_DLP_BIN = which(
    '/opt/wrolpi/venv/bin/yt-dlp',  # Use virtual environment location
    'yt-dlp',
    '/usr/local/bin/yt-dlp',  # Location in docker container
)
FFPROBE_BIN = which('ffprobe', '/usr/bin/ffprobe')
FFMPEG_BIN = which('ffmpeg', '/usr/bin/ffmpeg')

# Documents
CATDOC_PATH = which('catdoc')
TEXTUTIL_PATH = which('textutil')


@dataclasses.dataclass
class CommandResult:
    return_code: int
    cancelled: bool
    stdout: bytes
    stderr: bytes
    elapsed: int
    pid: int = None


TESTING_RUN_COMMAND_RESULT = None


async def run_command(cmd: tuple[str | pathlib.Path, ...], cwd: pathlib.Path | str = None,
                      timeout: int = 600, log_command: bool = True) -> CommandResult:
    """Run a shell command, return the results (stdout/stderr/return code).

    :param log_command: Enable debug logging.
    """
    if not isinstance(cmd, (list, tuple)):
        raise RuntimeError('Command must be a list or tuple')

    if PYTEST and TESTING_RUN_COMMAND_RESULT:
        logger.debug('run_command: returning mock result')
        return TESTING_RUN_COMMAND_RESULT()  # call the mock

    with tempfile.NamedTemporaryFile() as stdout_fh, tempfile.NamedTemporaryFile() as stderr_fh:
        stdout_file, stderr_file = pathlib.Path(stdout_fh.name), pathlib.Path(stderr_fh.name)
        cmd = tuple(str(i) for i in cmd)
        cmd_str = ' '.join(shlex.quote(i) for i in cmd)
        if log_command:
            logger.info(f'run_command: running ({timeout=}): {cmd_str}')
        elif logger.isEnabledFor(TRACE_LEVEL):
            logger.trace(f'run_command: running ({timeout=}): {cmd_str}')
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout_fh,  # Use stdout/stderr files to avoid buffer filling up.
            stderr=stderr_fh,
            cwd=cwd,
        )
        pid = proc.pid

        cancelled = False
        start = time()
        try:
            while True:
                elapsed = int(time() - start)
                if timeout and elapsed >= timeout:
                    logger.warning(f'run_command: timeout exceeded, killing... {cmd=}')
                    proc.kill()
                    await proc.wait()
                    break

                try:
                    # Wait for the process to finish.
                    await asyncio.wait_for(proc.wait(), timeout=1)
                    break
                except asyncio.TimeoutError:
                    # Task is not done, keep waiting...
                    continue
        except CancelledError as e:
            logger.warning(f'run_command: cancelled, killing... {cmd=}', exc_info=e)
            cancelled = True
            proc.kill()
            await proc.wait()

        elapsed = int(time() - start)
        stdout = stdout_file.read_bytes() or b''
        stderr = stderr_file.read_bytes() or b''
        # Logs details of the call, but only if it took a long time or TRACE is enabled.
        if log_command:
            logger.debug(f'run_command: finished ({elapsed=}s) with stdout={len(stdout)} stderr={len(stderr)}: {cmd_str=}')
        elif logger.isEnabledFor(TRACE_LEVEL):
            logger.trace(f'run_command: finished ({elapsed=}s) with stdout={len(stdout)} stderr={len(stderr)}: {cmd_str=}')
        return CommandResult(
            return_code=proc.returncode,
            cancelled=cancelled,
            stdout=stdout,
            stderr=stderr,
            elapsed=elapsed,
            pid=pid,
        )
