import os
import shutil
from pathlib import Path

from wrolpi.common import logger
from wrolpi.vars import PYTEST, DOCKERIZED

logger = logger.getChild(__name__)


def is_executable(path: Path) -> bool:
    """Returns True if the file is executable."""
    return path.is_file() and os.access(path, os.X_OK)


def which(name: str, *possible_paths: str, warn: bool = False) -> Path:
    """
    Find an executable in the system $PATH.  If the executable cannot be found in $PATH, then return the first
    executable found in possible_paths.

    Returns None if no executable can be found.
    """
    path = shutil.which(name)
    if path:
        return Path(path).absolute()

    possible_paths = map(Path, possible_paths)
    for path in possible_paths:
        if is_executable(path):
            return path.absolute()

    if warn and not PYTEST and not DOCKERIZED:
        logger.warning(f'Cannot find executable {name}')
