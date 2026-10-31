"""
Tests that WROLPi's Python packages are installed from hash-locked requirements, except yt-dlp, which is upgraded
separately so devices get YouTube fixes as soon as they are released.
"""
import re

import pytest
from packaging.requirements import Requirement

from wrolpi.vars import PROJECT_DIR

HELPER = PROJECT_DIR / 'scripts/install_python_requirements.sh'
REQUIREMENTS = [
    PROJECT_DIR / 'requirements.txt',
    PROJECT_DIR / 'controller/requirements.txt',
    PROJECT_DIR / 'docker/archive/requirements.txt',
]
FLOATING = {'yt-dlp', 'yt-dlp-ejs'}


def _name(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def _requirements(path) -> list[Requirement]:
    lines = (line.split('#')[0].strip() for line in path.read_text().splitlines())
    return [Requirement(line) for line in lines if line]


def _locked(path) -> dict[str, str]:
    """{name: version} of a lock, asserting each entry is pinned exactly and carries a hash."""
    entries = re.split(r'\n(?=\S)', path.read_text())
    locked = {}
    for entry in entries:
        if not entry.strip() or entry.startswith('#'):
            continue
        match = re.match(r'([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)', entry)
        assert match, f'{path.name}: not pinned with ==: {entry.splitlines()[0]}'
        assert '--hash=sha256:' in entry, f'{path.name}: no hash for {match.group(1)}'
        locked[_name(match.group(1))] = match.group(2)
    return locked


@pytest.mark.parametrize('requirements', REQUIREMENTS, ids=lambda i: str(i.relative_to(PROJECT_DIR)))
def test_lock_satisfies_its_requirements(requirements):
    """Each lock is generated from its requirements.txt; a version bumped there (e.g. by dependabot) without
    regenerating the lock (scripts/lock_requirements.sh) fails here."""
    locked = _locked(requirements.with_suffix('.lock'))
    for requirement in _requirements(requirements):
        name = _name(requirement.name)
        if name in FLOATING:
            assert name not in locked, f'{name} is upgraded separately and must not be locked'
            continue
        assert name in locked, f'{name} is missing from the lock'
        assert requirement.specifier.contains(locked[name], prereleases=True), \
            f'{name}=={locked[name]} does not satisfy {requirement}'


def test_yt_dlp_dependencies_are_locked():
    """Only yt-dlp itself floats; the packages it needs are installed with hashes first."""
    locked = _locked(PROJECT_DIR / 'requirements.lock')
    for name in ('certifi', 'requests', 'urllib3', 'websockets', 'curl-cffi', 'brotli', 'mutagen', 'pycryptodomex'):
        assert name in locked, name


def _files():
    for directory in ('scripts', 'pi-gen', 'debian-live-config', 'docker', '.github'):
        for path in (PROJECT_DIR / directory).rglob('*'):
            if path.is_file() and 'node_modules' not in path.parts and path.suffix != '.lock':
                yield path, path.read_text(errors='ignore')


def test_requirements_are_installed_with_hashes():
    """No WROLPi requirements.txt is installed directly; installs go through the hash-locked helper."""
    for path, text in _files():
        for line in text.splitlines():
            if re.search(r'pip3? install\b.*-r\s+\S*requirements\.txt', line) and 'wrolpi-help' not in line:
                pytest.fail(f'{path}: {line.strip()}')


def test_pip_is_not_upgraded_unpinned():
    """`pip install --upgrade pip` fetches whatever pip is newest; the venvs' own pip supports --require-hashes."""
    for path, text in _files():
        for line in text.splitlines():
            if 'install --upgrade pip' in line and 'wrolpi-help' not in line:
                pytest.fail(f'{path}: {line.strip()}')


@pytest.mark.parametrize('path', [
    'scripts/install_debian.sh',
    'scripts/install_raspberrypios.sh',
    'scripts/upgrade.sh',
    'scripts/reset_virtual_environments.sh',
    'pi-gen/stage2/04-wrolpi/03-run-chroot.sh',
    'debian-live-config/config/hooks/normal/9999-wrolpi.hook.chroot',
    'docker/api/Dockerfile',
    'docker/controller/Dockerfile',
    'docker/archive/Dockerfile',
    '.github/workflows/backend.yml',
    '.github/workflows/controller-tests.yml',
])
def test_install_sites_use_the_helper(path):
    assert 'install_python_requirements.sh' in (PROJECT_DIR / path).read_text()


def test_helper_requires_hashes_and_floats_only_yt_dlp():
    text = HELPER.read_text()
    assert '--require-hashes' in text
    assert re.search(r"grep -E '\^yt-dlp'", text)
