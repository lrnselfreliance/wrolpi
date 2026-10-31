"""
Tests that every path which installs WROLPi checks the checkout is signed by the WROLPi release key.
"""
import os
import re
import subprocess

import pytest

from wrolpi.test.test_common import gpg_test_key  # noqa: F401 (fixture)
from wrolpi.vars import PROJECT_DIR

VERIFIER = PROJECT_DIR / 'wrolpi/scripts/verify_wrolpi_commit.sh'
WROLPI_KEY = PROJECT_DIR / 'wrolpi/roland@learningselfreliance.com.gpg'
INSTALL_SH = PROJECT_DIR / 'install.sh'
PI_GEN_CHROOT = PROJECT_DIR / 'pi-gen/stage2/04-wrolpi/03-run-chroot.sh'
ISO_HOOK = PROJECT_DIR / 'debian-live-config/config/hooks/normal/9999-wrolpi.hook.chroot'


def _fingerprint(key_path, env=None) -> str:
    output = subprocess.run(['gpg', '--batch', '--show-keys', '--with-colons', str(key_path)],
                            env=env, capture_output=True, text=True, check=True).stdout
    return next(line.split(':')[9] for line in output.splitlines() if line.startswith('fpr:'))


def _function(path) -> str:
    """The text of `verify_wrolpi_commit() { ... }` in a script."""
    match = re.search(r'^verify_wrolpi_commit\(\) \{\n.*?^\}\n', path.read_text(), re.MULTILINE | re.DOTALL)
    assert match, f'verify_wrolpi_commit is not defined in {path}'
    return match.group(0)


@pytest.fixture
def signed_repo(tmp_path, gpg_test_key):
    """A git repository whose `signed` commit is signed by the test key, and whose `unsigned` commit is not."""
    env, test_pubkey, _ = gpg_test_key
    repo = tmp_path / 'repo'
    repo.mkdir()

    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], env=env, capture_output=True, text=True,
                              check=True).stdout.strip()

    git('init', '-q')
    git('config', 'user.email', 'test@test.com')
    git('config', 'user.name', 'Test')
    git('config', 'user.signingkey', 'test@test.com')
    (repo / 'a.txt').write_text('a')
    git('add', 'a.txt')
    git('commit', '-q', '-S', '-m', 'signed')
    git('tag', 'signed')
    (repo / 'b.txt').write_text('b')
    git('add', 'b.txt')
    git('commit', '-q', '--no-gpg-sign', '-m', 'unsigned')
    git('tag', 'unsigned')
    yield repo, test_pubkey, _fingerprint(test_pubkey, env)


def _verify(repo, rev, key, fingerprint=None):
    env = {k: v for k, v in os.environ.items() if k != 'GNUPGHOME'}
    if fingerprint:
        env['WROLPI_SIGNING_FINGERPRINT'] = fingerprint
    return subprocess.run(['bash', str(VERIFIER), str(repo), rev, str(key)], env=env, capture_output=True, text=True)


def test_verify_signed_commit(signed_repo):
    """A commit signed by the trusted key, from the pinned fingerprint, verifies."""
    repo, key, fingerprint = signed_repo
    result = _verify(repo, 'signed', key, fingerprint)
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_unsigned_commit(signed_repo):
    repo, key, fingerprint = signed_repo
    assert _verify(repo, 'unsigned', key, fingerprint).returncode != 0


def test_verify_commit_signed_by_another_key(signed_repo, tmp_path):
    """The signature must come from the key file given; the WROLPi key cannot vouch for the test signature."""
    repo, _, fingerprint = signed_repo
    assert _verify(repo, 'signed', WROLPI_KEY, fingerprint).returncode != 0


def test_verify_swapped_key_file(signed_repo):
    """A key file swapped along with the code is rejected because its fingerprint is not the pinned one."""
    repo, key, _ = signed_repo
    assert _verify(repo, 'signed', key).returncode != 0


def test_pinned_fingerprint_is_the_wrolpi_key():
    """The fingerprint the verifier pins is the committed WROLPi key's."""
    fingerprint = _fingerprint(WROLPI_KEY)
    assert f':-{fingerprint}}}' in _function(VERIFIER)


def test_install_sh_has_the_same_verifier():
    """install.sh runs before any verified checkout exists, so it carries a copy of the function; they must match."""
    assert _function(INSTALL_SH) == _function(VERIFIER)


def test_install_sh_verifies_before_running_the_checkout():
    text = INSTALL_SH.read_text()
    verify = text.index('verify_wrolpi_commit /opt/wrolpi HEAD')
    assert text.index('git reset --hard') < verify < text.index('scripts/install_debian.sh')
    assert re.search(r'^apt install -y git gnupg$', text, re.MULTILINE)


@pytest.mark.parametrize('path', [PI_GEN_CHROOT, ISO_HOOK])
def test_image_builds_verify_the_clone(path):
    """Each image build verifies the clone with the key from the build checkout, before using it."""
    lines = path.read_text().splitlines()
    clone = next(i for i, line in enumerate(lines) if 'git clone' in line and 'lrnselfreliance/wrolpi' in line)
    verify = next(i for i, line in enumerate(lines) if 'verify_wrolpi_commit.sh /opt/wrolpi HEAD' in line)
    assert clone < verify
    # Nothing from the clone runs before it is verified.
    assert not any('/opt/wrolpi/' in line and not line.lstrip().startswith('#') and 'verify' not in line
                   for line in lines[clone + 1:verify]), lines[clone + 1:verify]
