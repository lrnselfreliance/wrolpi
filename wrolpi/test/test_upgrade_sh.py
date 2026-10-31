"""
Tests of the root upgrade.sh, which runs as root and swaps WROLPi's code.
"""
import os
import re
import subprocess

import pytest

from wrolpi.vars import PROJECT_DIR

UPGRADE_SH = PROJECT_DIR / 'upgrade.sh'


def _function(name: str) -> str:
    match = re.search(rf'^{name}\(\) \{{\n.*?^\}}\n', UPGRADE_SH.read_text(), re.MULTILINE | re.DOTALL)
    assert match, f'{name} is not defined in upgrade.sh'
    return match.group(0)


@pytest.fixture
def repo(tmp_path):
    """A checkout on `release` at the third of three commits (versions 0.1.0 to 0.3.0), plus commits from unrelated
    history: `orphan-old` (0.1.0), `orphan-same` (0.3.0), `orphan-new` (0.4.0) and `orphan-unversioned`."""
    path = tmp_path / 'repo'
    path.mkdir()

    def git(*args):
        return subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True,
                              check=True).stdout.strip()

    git('init', '-q', '-b', 'release')
    git('config', 'user.email', 'test@test.com')
    git('config', 'user.name', 'Test')
    version = path / 'wrolpi/version.txt'
    version.parent.mkdir()

    def commit(name, version_=None):
        if version_:
            version.write_text(f'{version_}\n')
            git('add', 'wrolpi/version.txt')
        git('commit', '-q', '--allow-empty', '--no-gpg-sign', '-m', name)
        git('tag', name)

    for name, version_ in (('first', '0.1.0'), ('second', '0.2.0'), ('third', '0.3.0')):
        commit(name, version_)
    for name, version_ in (('orphan-old', '0.1.0'), ('orphan-same', '0.3.0'), ('orphan-new', '0.4.0')):
        git('checkout', '-q', '--orphan', name + '-branch')
        commit(name, version_)
    git('checkout', '-q', '--orphan', 'unversioned-branch')
    git('rm', '-q', '-r', '--cached', '.')
    version.unlink()
    commit('orphan-unversioned')
    git('checkout', '-q', '-f', 'release')
    yield path, git


def _refuse_rollback(path, branch, target, allow_downgrade=False):
    script = _function('refuse_rollback') + f'refuse_rollback "{path}" "{branch}" "{target}"\n'
    env = {**os.environ, 'ALLOW_DOWNGRADE': 'true' if allow_downgrade else 'false'}
    return subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)


def test_refuse_rollback_older_commit_of_the_same_branch(repo):
    """An older commit of the branch the device is on is a rollback, however validly it is signed."""
    path, _ = repo
    result = _refuse_rollback(path, 'release', 'second')
    assert result.returncode != 0
    assert 'Refusing to roll back' in result.stdout


@pytest.mark.parametrize('target', ['third', 'release'])
def test_refuse_rollback_allows_the_same_commit(repo, target):
    assert _refuse_rollback(repo[0], 'release', target).returncode == 0


def test_refuse_rollback_allows_a_newer_commit(repo):
    path, git = repo
    git('checkout', '-q', '-B', 'release', 'first')
    assert _refuse_rollback(path, 'release', 'third').returncode == 0


def test_refuse_rollback_allows_switching_branches(repo):
    """Moving from master to release goes back in history, and is what the user asked for."""
    path, git = repo
    git('checkout', '-q', '-b', 'master')
    assert _refuse_rollback(path, 'release', 'second').returncode == 0


def test_refuse_rollback_detached_head(repo):
    """A device built from a release image starts on a detached HEAD; it is on the branch it upgrades."""
    path, git = repo
    git('checkout', '-q', '--detach', 'third')
    assert _refuse_rollback(path, 'release', 'second').returncode != 0
    assert _refuse_rollback(path, 'release', 'third').returncode == 0


@pytest.mark.parametrize('target', ['orphan-same', 'orphan-new'])
def test_refuse_rollback_allows_rewritten_history(repo, target):
    """A force-pushed branch is not in the device's history; it is allowed when its version is not lower."""
    assert _refuse_rollback(repo[0], 'release', target).returncode == 0


@pytest.mark.parametrize('target', ['orphan-old', 'orphan-unversioned'])
def test_refuse_rollback_lower_version_from_other_history(repo, target):
    """An old signed commit from other history (an old experimental branch) is a rollback by its version."""
    result = _refuse_rollback(repo[0], 'release', target)
    assert result.returncode != 0
    assert 'Refusing to roll back' in result.stdout


def test_refuse_rollback_older_commit_with_the_same_version(repo):
    """A version spans many commits, so only ancestry catches a rollback to an earlier commit of the same version."""
    path, git = repo
    git('commit', '-q', '--allow-empty', '--no-gpg-sign', '-m', 'fourth')  # Still 0.3.0.
    result = _refuse_rollback(path, 'release', 'third')
    assert result.returncode != 0
    assert 'Refusing to roll back' in result.stdout


@pytest.mark.parametrize('head_version,target_version,refused', [
    ('0.30.3-beta', '0.30.10-beta', False),
    ('0.30.10-beta', '0.30.3-beta', True),
    ('0.9.0-beta', '0.10.0-beta', False),
])
def test_refuse_rollback_compares_versions_numerically(repo, head_version, target_version, refused):
    """Versions compare by their numbers: a plain text sort puts 0.30.10 before 0.30.3."""
    path, git = repo
    version = path / 'wrolpi/version.txt'
    for name, version_ in (('target', target_version), ('head', head_version)):
        git('checkout', '-q', '--orphan', f'{name}-version-branch')
        version.write_text(f'{version_}\n')
        git('add', 'wrolpi/version.txt')
        git('commit', '-q', '--no-gpg-sign', '-m', name)
        git('tag', f'{name}-version')
    git('checkout', '-q', '-B', 'release', 'head-version')
    assert (_refuse_rollback(path, 'release', 'target-version').returncode != 0) is refused


@pytest.mark.parametrize('target', ['second', 'orphan-old'])
def test_refuse_rollback_allow_downgrade(repo, target):
    assert _refuse_rollback(repo[0], 'release', target, allow_downgrade=True).returncode == 0


def test_upgrade_refuses_rollback_before_checkout():
    """The check runs after the fetched commit's signature is verified, and before anything is checked out."""
    text = UPGRADE_SH.read_text()
    verify = text.index('verify-commit origin/"${BRANCH}"')
    refuse = text.index('refuse_rollback /opt/wrolpi')
    checkout = text.index('git checkout -f -B "${BRANCH}" "origin/${BRANCH}"')
    assert verify < refuse < checkout


def test_allow_downgrade_reaches_the_upgrade_service():
    """upgrade.sh hands the work to wrolpi-upgrade.service, which only sees what the env file carries."""
    text = UPGRADE_SH.read_text()
    assert re.search(r'getopts ":hb:d"', text)
    assert 'echo "ALLOW_DOWNGRADE=${ALLOW_DOWNGRADE}" >>/tmp/wrolpi-upgrade.env' in text
