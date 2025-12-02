"""
WROLPi upgrade system.

This module provides functionality to check for available updates by comparing the local git HEAD
with the remote origin branch, and to trigger the upgrade process.
"""
import pathlib
import subprocess

from wrolpi.common import logger, wrol_mode_check
from wrolpi.vars import DOCKERIZED, PROJECT_DIR

logger = logger.getChild(__name__)

# Path to the upgrade script.
UPGRADE_SCRIPT = PROJECT_DIR / 'upgrade.sh'


def git_fetch() -> bool:
    """
    Run `git fetch` in the WROLPi directory.

    Returns True if successful, False otherwise.
    """
    if not PROJECT_DIR.is_dir():
        logger.warning(f'WROLPi directory does not exist: {PROJECT_DIR}')
        return False

    try:
        result = subprocess.run(
            ['git', 'fetch'],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning(f'git fetch failed: {result.stderr.decode()}')
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning('git fetch timed out')
        return False
    except Exception as e:
        logger.error('git fetch failed', exc_info=e)
        return False


def get_current_branch() -> str | None:
    """
    Get the current git branch name (e.g., 'release', 'master').

    Returns None if unable to determine.
    """
    if not PROJECT_DIR.is_dir():
        return None

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.decode().strip()
    except Exception as e:
        logger.error('Failed to get current branch', exc_info=e)

    return None


def get_local_commit() -> str | None:
    """
    Get the current local HEAD commit hash (short form).

    Returns None if unable to determine.
    """
    if not PROJECT_DIR.is_dir():
        return None

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.decode().strip()
    except Exception as e:
        logger.error('Failed to get local commit', exc_info=e)

    return None


def get_remote_commit(branch: str) -> str | None:
    """
    Get the latest commit hash on origin/{branch} (short form).

    Note: Requires `git fetch` to be run first to have up-to-date remote refs.

    Returns None if unable to determine.
    """
    if not PROJECT_DIR.is_dir():
        return None

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', f'origin/{branch}'],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.decode().strip()
    except Exception as e:
        logger.error(f'Failed to get remote commit for origin/{branch}', exc_info=e)

    return None


def get_commits_behind(branch: str) -> int:
    """
    Get the number of commits the local branch is behind origin/{branch}.

    Returns 0 if unable to determine or if up-to-date.
    """
    if not PROJECT_DIR.is_dir():
        return 0

    try:
        # Count commits that are in origin/branch but not in HEAD
        result = subprocess.run(
            ['git', 'rev-list', '--count', f'HEAD..origin/{branch}'],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.decode().strip())
    except Exception as e:
        logger.error(f'Failed to get commits behind for origin/{branch}', exc_info=e)

    return 0


@wrol_mode_check
def check_for_update(fetch: bool = True) -> dict:
    """
    Check if an update is available by comparing local HEAD with origin/{branch}.

    Args:
        fetch: If True, run `git fetch` first to get latest remote refs.

    Returns a dict with:
        - update_available: bool
        - current_commit: str (short hash) or None
        - latest_commit: str (short hash) or None
        - branch: str or None
        - commits_behind: int
    """
    result = {
        'update_available': False,
        'current_commit': None,
        'latest_commit': None,
        'branch': None,
        'commits_behind': 0,
    }

    # Don't check for updates in Docker environments
    if DOCKERIZED:
        return result

    # Check if WROLPi directory exists
    if not PROJECT_DIR.is_dir():
        logger.debug(f'WROLPi directory does not exist: {PROJECT_DIR}')
        return result

    # Get current branch
    branch = get_current_branch()
    if not branch:
        logger.warning('Could not determine current branch')
        return result

    result['branch'] = branch

    # Fetch latest from remote if requested
    if fetch:
        if not git_fetch():
            logger.warning('git fetch failed, using cached remote refs')

    # Get local and remote commits
    local_commit = get_local_commit()
    remote_commit = get_remote_commit(branch)

    result['current_commit'] = local_commit
    result['latest_commit'] = remote_commit

    if not local_commit or not remote_commit:
        return result

    # Check if update is available
    if local_commit != remote_commit:
        commits_behind = get_commits_behind(branch)
        result['commits_behind'] = commits_behind
        result['update_available'] = commits_behind > 0

    return result


async def start_upgrade():
    """
    Start the WROLPi upgrade process.

    This executes /opt/wrolpi/upgrade.sh in a detached subprocess so it survives
    the API shutdown (upgrade.sh stops the API service).

    The upgrade will use the currently checked out branch (e.g., 'release' or 'master').

    The frontend should redirect to the maintenance page after calling this.
    """
    from wrolpi.events import Events

    if DOCKERIZED:
        logger.warning('Cannot start upgrade in Docker environment')
        return

    if not UPGRADE_SCRIPT.is_file():
        logger.error(f'Upgrade script not found: {UPGRADE_SCRIPT}')
        return

    # Get current branch to upgrade from the same branch
    branch = get_current_branch()
    if not branch:
        logger.error('Could not determine current branch, defaulting to release')
        branch = 'release'

    logger.warning(f'Starting WROLPi upgrade on branch: {branch}')

    # Send event to notify frontend
    Events.send_upgrade_started(f'WROLPi upgrade is starting on branch {branch}. Please wait...')

    # Write branch to environment file for the systemd service to read.
    env_file = pathlib.Path('/tmp/wrolpi-upgrade.env')
    env_file.write_text(f'BRANCH={branch}\n')

    # Use systemd to run the upgrade service. This ensures the upgrade process
    # survives when the API is stopped, as systemd manages it independently.
    subprocess.Popen(
        ['sudo', 'systemctl', 'start', 'wrolpi-upgrade.service'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    logger.warning(f'Upgrade process started on branch {branch}, API will be stopped shortly...')
