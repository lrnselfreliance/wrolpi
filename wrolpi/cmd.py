import os
import shutil
from pathlib import Path

from wrolpi.common import logger
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)


def is_executable(path: Path) -> bool:
    """Returns True if the file is executable."""
    return path.is_file() and os.access(path, os.X_OK)


def which(*possible_paths: str, warn: bool = False) -> Path:
    """
    Find an executable in the system $PATH.  If the executable cannot be found in $PATH, then return the first
    executable found in possible_paths.

    Returns None if no executable can be found.
    """
    possible_paths = map(Path, possible_paths)
    for path in possible_paths:
        if is_executable(path):
            # `path` was an absolute file which is executable.
            return path.absolute()
        path = shutil.which(path)
        if path and (path := Path(path).absolute()) and is_executable(path):
            # `path` was a name or relative path.
            return path

    if warn and not PYTEST and not DOCKERIZED:
        logger.warning(f'Cannot find executable {possible_paths[0]}')
