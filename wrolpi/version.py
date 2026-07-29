import pathlib
import subprocess

__version__ = (pathlib.Path(__file__).parent / 'version.txt').read_text()


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
        # Not `rev-parse --abbrev-ref HEAD`: it reports "heads/release" when a stale
        # `release` tag exists alongside the branch.
        cmd = ('git', 'branch', '--show-current')
        branch = subprocess.check_output(cmd, stderr=subprocess.PIPE)
        branch = branch.decode().strip()
        # A detached HEAD prints nothing.
        return branch or 'HEAD'
    except Exception:
        return 'unknown'


def get_version_string():
    """Return a string containing the WROLPi version, git branch and git revision hash."""
    return f'{__version__} (git: {git_branch()} {git_revision()})'
