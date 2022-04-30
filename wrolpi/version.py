__version__ = '0.4.5-beta'

import subprocess


def git_revision():
    try:
        cmd = ('git', 'log', '-1', '--format="%H"')
        revision = subprocess.check_output(cmd, stderr=subprocess.PIPE)
        revision = revision.decode().strip().strip('"')
        return revision
    except Exception:
        # Could not find git version...
        return 'unknown'


def git_branch():
    try:
        cmd = ('git', 'rev-parse', '--abbrev-ref', 'HEAD')
        branch = subprocess.check_output(cmd, stderr=subprocess.PIPE)
        branch = branch.decode().strip()
        return branch
    except Exception:
        return 'unknown'


def get_version_string():
    """Return a string containing the WROLPi version, git branch and git revision hash."""
    return f'{__version__} (git: {git_branch()} {git_revision()})'
