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
FIREFOX = which('firefox', 'firefox-esr',
                '/usr/bin/firefox',
                '/usr/bin/firefox-esr',
                )
READABILITY_BIN = which('readability-extractor',
                        '/usr/bin/readability-extractor',  # rpi os
                        '/usr/local/bin/readability-extractor',  # debian
                        )

# Known browser definitions for SingleFile
KNOWN_BROWSERS = {
    'chromium': {
        'paths': ['chromium-browser', 'chromium', '/usr/bin/chromium-browser', '/usr/bin/chromium'],
        'name': 'Chromium',
    },
    'firefox': {
        'paths': ['firefox', 'firefox-esr', '/usr/bin/firefox', '/usr/bin/firefox-esr'],
        'name': 'Firefox',
    },
    'brave': {
        'paths': ['brave-browser', '/usr/bin/brave-browser'],
        'name': 'Brave',
    }
}


def get_installed_browsers() -> list:
    """
    Detect browsers installed on the system that can be used with SingleFile.

    Returns a list of dicts with:
        - key: The browser identifier (e.g., 'chromium', 'firefox')
        - name: Human-readable name (e.g., 'Chromium', 'Firefox')
        - path: Absolute path to the executable
    """
    browsers = []

    for key, info in KNOWN_BROWSERS.items():
        path = which(*info['paths'])
        if path:
            browsers.append({
                'key': key,
                'name': info['name'],
                'path': str(path),
            })

    return browsers


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
                      timeout: int = 600, log_command: bool = True,
                      stdout_callback: callable = None, env: dict = None) -> CommandResult:
    """Run a shell command, return the results (stdout/stderr/return code).

    When stdout_callback is provided, stdout is piped and each line is passed to the callback
    in real-time.  Otherwise, stdout is written to a temporary file.

    :param log_command: Enable debug logging.
    :param stdout_callback: Called with each decoded stdout line (str). May be None.
    :param env: Environment variables for the subprocess. If None, inherits the current environment.
    """
    if not isinstance(cmd, (list, tuple)):
        raise RuntimeError('Command must be a list or tuple')

    if PYTEST and TESTING_RUN_COMMAND_RESULT:
        logger.debug('run_command: returning mock result')
        return TESTING_RUN_COMMAND_RESULT()  # call the mock

    streaming = stdout_callback is not None

    with tempfile.NamedTemporaryFile() as stderr_fh:
        stderr_file = pathlib.Path(stderr_fh.name)
        cmd = tuple(str(i) for i in cmd)
        cmd_str = ' '.join(shlex.quote(i) for i in cmd)
        if log_command:
            logger.info(f'run_command: running ({timeout=}): {cmd_str}')
        elif __debug__ and logger.isEnabledFor(TRACE_LEVEL):
            logger.trace(f'run_command: running ({timeout=}): {cmd_str}')

        stdout_fh = None
        stdout_file = None
        reader_task = None
        stdout_buf = None

        if streaming:
            stdout_arg = asyncio.subprocess.PIPE
            stdout_buf = bytearray()
        else:
            stdout_fh = tempfile.NamedTemporaryFile()
            stdout_file = pathlib.Path(stdout_fh.name)
            stdout_arg = stdout_fh

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=stdout_arg,
                stderr=stderr_fh,
                cwd=cwd,
                env=env,
            )
            pid = proc.pid

            if streaming:
                async def _read_stdout():
                    buf = ''
                    while True:
                        chunk = await proc.stdout.read(4096)
                        if not chunk:
                            # Flush remaining buffer.
                            if buf.strip():
                                try:
                                    stdout_callback(buf.strip())
                                except Exception as e:
                                    logger.warning(f'run_command: stdout_callback error: {e}')
                            break
                        stdout_buf.extend(chunk)
                        buf += chunk.decode(errors='replace')
                        # Split on both \n and \r to handle progress bars.
                        while '\n' in buf or '\r' in buf:
                            # Find the earliest delimiter.
                            ni = buf.find('\n')
                            ri = buf.find('\r')
                            if ni == -1:
                                idx, skip = ri, 1
                            elif ri == -1:
                                idx, skip = ni, 1
                            else:
                                idx, skip = min(ni, ri), 1
                            line = buf[:idx]
                            buf = buf[idx + skip:]
                            if line.strip():
                                try:
                                    stdout_callback(line.strip())
                                except Exception as e:
                                    logger.warning(f'run_command: stdout_callback error: {e}')

                reader_task = asyncio.create_task(_read_stdout())

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
                        await asyncio.wait_for(proc.wait(), timeout=1)
                        break
                    except asyncio.TimeoutError:
                        continue
            except CancelledError as e:
                logger.warning(f'run_command: cancelled, killing... {cmd=}', exc_info=e)
                cancelled = True
                proc.kill()
                await proc.wait()

            if reader_task:
                reader_task.cancel()
                try:
                    await reader_task
                except (CancelledError, asyncio.CancelledError):
                    pass

            elapsed = int(time() - start)
            if streaming:
                stdout = bytes(stdout_buf)
            else:
                stdout = stdout_file.read_bytes() or b''
            stderr = stderr_file.read_bytes() or b''
            if log_command:
                logger.debug(
                    f'run_command: finished ({elapsed=}s) with stdout={len(stdout)} stderr={len(stderr)}: {cmd_str=}')
            elif __debug__ and logger.isEnabledFor(TRACE_LEVEL):
                logger.trace(
                    f'run_command: finished ({elapsed=}s) with stdout={len(stdout)} stderr={len(stderr)}: {cmd_str=}')
            return CommandResult(
                return_code=proc.returncode,
                cancelled=cancelled,
                stdout=stdout,
                stderr=stderr,
                elapsed=elapsed,
                pid=pid,
            )
        finally:
            if stdout_fh:
                stdout_fh.close()
