"""Paths for third-party commands that WROLPi may require."""
import os
import shutil
from pathlib import Path
from typing import Optional

from wrolpi import flags
from wrolpi.common import logger
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)


def is_executable(path: Path) -> bool:
    """Returns True if the file is executable."""
    return path.is_file() and os.access(path, os.X_OK)


def which(*possible_paths: str, warn: bool = False, flag: str = None) -> Optional[Path]:
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
        if flag:
            # Mark the command as installed.
            try:
                getattr(flags, flag).set()
            except AttributeError as e:
                logger.error(f'Unable to set flag {flag}', exc_info=e)

        return found.absolute()


# Admin
SUDO_BIN = which('sudo', '/usr/bin/sudo')
NMCLI_BIN = which('nmcli', '/usr/bin/nmcli', flag='nmcli_installed')
CPUFREQ_INFO_BIN = which('cpufreq-info', '/usr/bin/cpufreq-info')
CPUFREQ_SET_BIN = which('cpufreq-set', '/usr/bin/cpufreq-set')

# Map
BASH_BIN = which('bash', '/bin/bash', warn=True)

# Archive
SINGLE_FILE_BIN = which('single-file',
                        '/usr/bin/single-file',  # rpi os
                        '/usr/local/bin/single-file',  # debian
                        warn=True,
                        flag='singlefile_installed',
                        )
CHROMIUM = which('chromium-browser', 'chromium',
                 '/usr/bin/chromium-browser',  # rpi os
                 '/usr/bin/chromium',  # debian
                 warn=True,
                 flag='chromium_installed',
                 )
READABILITY_BIN = which('readability-extractor',
                        '/usr/bin/readability-extractor',  # rpi os
                        '/usr/local/bin/readability-extractor',  # debian
                        warn=True,
                        flag='readability_installed',
                        )

# Videos
YT_DLP_BIN = which(
    'yt-dlp',
    '/usr/local/bin/yt-dlp',  # Location in docker container
    '/opt/wrolpi/venv/bin/yt-dlp',  # Use virtual environment location
    warn=True,
    flag='yt_dlp_installed',
)
FFPROBE_BIN = which('ffprobe', '/usr/bin/ffprobe', warn=True, flag='ffprobe_installed')
FFMPEG_BIN = which('ffmpeg', '/usr/bin/ffmpeg', flag='ffmpeg_installed')
