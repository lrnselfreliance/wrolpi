"""
Tests that Caddy's apt repository is trusted through the key committed with WROLPi, never a key downloaded over TLS.
"""
import re
import subprocess

import pytest

from wrolpi.vars import PROJECT_DIR

CADDY_KEY = PROJECT_DIR / 'debian-live-config/config/archives/caddy-stable.key'
CADDY_FINGERPRINT = '65760C51EDEA2017CEA2CA15155B6D79CA56EA34'
HELPER = PROJECT_DIR / 'scripts/add_caddy_apt_repo.sh'
CADDY_INSTALLERS = [
    PROJECT_DIR / 'scripts/install_debian.sh',
    PROJECT_DIR / 'scripts/install_raspberrypios.sh',
    PROJECT_DIR / 'scripts/upgrade.sh',
    PROJECT_DIR / 'pi-gen/stage2/04-wrolpi/03-run-chroot.sh',
]


def test_committed_caddy_key_fingerprint():
    output = subprocess.run(['gpg', '--batch', '--show-keys', '--with-colons', str(CADDY_KEY)],
                            capture_output=True, text=True, check=True).stdout
    fingerprints = [line.split(':')[9] for line in output.splitlines() if line.startswith('fpr:')]
    assert fingerprints[0] == CADDY_FINGERPRINT


def test_no_caddy_key_is_downloaded():
    """A key fetched over TLS could be swapped for one that signs other caddy packages."""
    for directory in ('scripts', 'pi-gen', 'debian-live-config', 'docker'):
        for path in (PROJECT_DIR / directory).rglob('*'):
            if path.is_file():
                text = path.read_text(errors='ignore')
                assert 'caddy/stable/gpg.key' not in text, path
                assert 'caddy/stable/debian.deb.txt' not in text, path


@pytest.mark.parametrize('path', CADDY_INSTALLERS, ids=lambda i: i.name)
def test_caddy_installers_use_the_committed_key(path):
    lines = path.read_text().splitlines()
    helper = next(i for i, line in enumerate(lines) if 'scripts/add_caddy_apt_repo.sh' in line)
    # `apt-get install ... caddy`, possibly continued onto the next line.
    install = next(i for i, line in enumerate(lines) if line.rstrip().endswith(' caddy')
                   and ('apt-get install' in line or 'apt-get install' in lines[i - 1]))
    assert helper < install


def test_caddy_repo_is_signed_by_the_installed_key():
    """apt only trusts the key named by signed-by for this repository, and the helper installs that file."""
    text = HELPER.read_text()
    keyring = re.search(r'install -m 644 \S+caddy-stable\.key"? (\S+)$', text, re.MULTILINE).group(1)
    assert keyring.endswith('.asc'), 'apt reads an armored key only from a .asc file'
    assert f'deb [signed-by={keyring}] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main' \
           in text
