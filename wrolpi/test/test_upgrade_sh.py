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
    """A checkout on `release` at the third of three commits, plus an unrelated `orphan` commit."""
    path = tmp_path / 'repo'
    path.mkdir()

    def git(*args):
        return subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True,
                              check=True).stdout.strip()

    git('init', '-q', '-b', 'release')
    git('config', 'user.email', 'test@test.com')
    git('config', 'user.name', 'Test')
    for name in ('first', 'second', 'third'):
        git('commit', '-q', '--allow-empty', '--no-gpg-sign', '-m', name)
        git('tag', name)
    git('checkout', '-q', '--orphan', 'unrelated')
    git('commit', '-q', '--allow-empty', '--no-gpg-sign', '-m', 'orphan')
    git('tag', 'orphan')
    git('checkout', '-q', 'release')
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


def test_refuse_rollback_allows_unrelated_history(repo):
    """A Debian 12 device is pinned to debian12-final, which is not in release's history."""
    assert _refuse_rollback(repo[0], 'release', 'orphan').returncode == 0


def test_refuse_rollback_allow_downgrade(repo):
    assert _refuse_rollback(repo[0], 'release', 'second', allow_downgrade=True).returncode == 0


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
