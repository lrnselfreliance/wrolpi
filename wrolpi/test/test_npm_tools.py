"""
Tests that the npm command-line tools WROLPi runs are installed from the committed lockfile, never resolved fresh from
the registry.
"""
import json

import pytest

from wrolpi.vars import PROJECT_DIR

NPM_TOOLS = PROJECT_DIR / 'npm-tools'
INSTALLER = 'scripts/install_npm_tools.sh'
TOOLS = {'serve': '12.0.1', 'single-file-cli': '2.0.73', 'readability-extractor': '0.0.6'}
INSTALL_SITES = [
    PROJECT_DIR / 'scripts/install_debian.sh',
    PROJECT_DIR / 'scripts/install_raspberrypios.sh',
    PROJECT_DIR / 'scripts/upgrade.sh',
    PROJECT_DIR / 'pi-gen/stage2/04-wrolpi/03-run-chroot.sh',
    PROJECT_DIR / 'debian-live-config/config/hooks/normal/9999-wrolpi.hook.chroot',
    PROJECT_DIR / 'docker/archive/Dockerfile',
]


def test_tools_are_pinned():
    """Each tool is pinned exactly in package.json, and the lockfile resolves that version."""
    package = json.loads((NPM_TOOLS / 'package.json').read_text())
    assert package['dependencies'] == TOOLS
    packages = json.loads((NPM_TOOLS / 'package-lock.json').read_text())['packages']
    for name, version in TOOLS.items():
        assert packages[f'node_modules/{name}']['version'] == version


def test_every_locked_package_has_an_integrity_hash():
    """npm ci checks each tarball against its committed sha512, so the registry's TLS is not trusted alone."""
    lock = json.loads((NPM_TOOLS / 'package-lock.json').read_text())
    assert lock['lockfileVersion'] >= 2
    packages = {k: v for k, v in lock['packages'].items() if k}
    assert len(packages) > len(TOOLS)
    for name, package in packages.items():
        assert package['integrity'].startswith('sha512-'), name
        assert package['resolved'].startswith('https://registry.npmjs.org/'), name


def test_no_tool_is_installed_globally():
    """`npm i -g` resolves the whole dependency tree fresh from the registry."""
    for directory in ('scripts', 'pi-gen', 'debian-live-config', 'docker'):
        for path in (PROJECT_DIR / directory).rglob('*'):
            if path.is_file() and 'node_modules' not in path.parts:
                text = path.read_text(errors='ignore')
                for name in TOOLS:
                    for command in (f'npm i -g {name}', f'npm install -g {name}'):
                        assert command not in text, path
                assert 'npm i -g serve' not in text and 'npm install -g serve' not in text, path


@pytest.mark.parametrize('path', INSTALL_SITES, ids=lambda i: i.parent.name + '/' + i.name)
def test_install_sites_use_the_lockfile(path):
    assert INSTALLER.split('/')[-1] in path.read_text(), path


def test_installer_uses_npm_ci():
    text = (PROJECT_DIR / INSTALLER).read_text()
    assert 'npm ci ' in text
    for command in ('serve', 'single-file', 'readability-extractor'):
        assert command in text
