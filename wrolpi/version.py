__version__ = '0.1-b'

import subprocess


def git_commit():
    try:
        cmd = ['git', 'log', '-1', '--format="%H"']
        git_version = subprocess.check_output(cmd)
        git_version = git_version.decode().strip().strip('"')
    except Exception:
        # Could not find git version...
        return 'unknown'

    return git_version
