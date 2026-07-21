"""Tests for scripts/start_kiwix_serve.sh.

The script imports every *.zim in the Zim directory into a Kiwix library, then
starts kiwix-serve.  These tests exercise the script directly with fake
`kiwix-manage`/`kiwix-serve` binaries on PATH so they need no real Kiwix
installation.  Key invariants:

- A single corrupt/incomplete zim must never prevent the remaining valid zims
  from being served, nor stop the server from starting.
- The configured Zim directory (wrolpi.yaml `zims_destination`) is honored.
- When no functioning zim is found, the default Zim is served as a fallback.
"""
import os
import pathlib
import stat
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).parents[3]
SCRIPT = REPO_ROOT / 'scripts' / 'start_kiwix_serve.sh'

# Fake kiwix-manage: refuses any zim whose contents contain "CORRUPT" (mimicking
# kiwix-manage's "Cannot add zim ..." rejection of partial/corrupt files),
# otherwise appends a <book> entry to the library file.
FAKE_KIWIX_MANAGE = """#!/usr/bin/env bash
library="$1"; shift
[ "$1" = "add" ] && shift
zim="$1"
if grep -q CORRUPT "${zim}" 2>/dev/null; then
  echo "Cannot add zim ${zim}" >&2
  exit 1
fi
if [ ! -f "${library}" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\\n<library version="20110515">\\n' > "${library}"
fi
printf '  <book path="%s"/>\\n' "${zim}" >> "${library}"
exit 0
"""

# Fake kiwix-serve: records that it was started (and with which library) so the
# test can assert the server came up, then exits 0.
FAKE_KIWIX_SERVE = """#!/usr/bin/env bash
library=""
while [ $# -gt 0 ]; do
  case "$1" in
    --library) library="$2"; shift 2;;
    *) shift;;
  esac
done
echo "${library}" > "${STARTED_MARKER}"
exit 0
"""


@pytest.fixture
def kiwix_env(tmp_path):
    """Set up a fake media directory and fake kiwix binaries on PATH."""
    media = tmp_path / 'media'
    zims = media / 'zims'
    zims.mkdir(parents=True)
    (media / 'config').mkdir()

    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in (('kiwix-manage', FAKE_KIWIX_MANAGE), ('kiwix-serve', FAKE_KIWIX_SERVE)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    started_marker = tmp_path / 'started'
    # Points at a file that does not exist by default (so the fallback is a
    # no-op); the fallback test creates it.
    default_zim = tmp_path / 'blobs' / 'default.zim'

    def write_config(text: str):
        (media / 'config' / 'wrolpi.yaml').write_text(text)

    def run():
        env = {
            **os.environ,
            'MEDIA_DIRECTORY': str(media),
            'PROJECT_DIR': str(REPO_ROOT),
            'DEFAULT_ZIM': str(default_zim),
            'PATH': f'{bin_dir}:{os.environ["PATH"]}',
            'STARTED_MARKER': str(started_marker),
        }
        return subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)

    def library_text():
        lib = zims / 'library.xml'
        return lib.read_text() if lib.exists() else ''

    return dict(media=media, zims=zims, library=zims / 'library.xml', started_marker=started_marker,
                default_zim=default_zim, write_config=write_config, library_text=library_text, run=run)


def _write_zim(path: pathlib.Path, corrupt: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('CORRUPT' if corrupt else 'ZIMDATA')


def test_valid_zim_starts_server(kiwix_env):
    """A valid zim is imported and the server starts."""
    _write_zim(kiwix_env['zims'] / 'wikipedia.zim')

    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'
    assert 'wikipedia.zim' in kiwix_env['library'].read_text()


def test_corrupt_zim_does_not_prevent_serving_valid_zims(kiwix_env):
    """A corrupt zim must be skipped while the valid zims are still served."""
    _write_zim(kiwix_env['zims'] / 'good.zim')
    _write_zim(kiwix_env['zims'] / 'sudan_broken.zim', corrupt=True)

    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'
    library = kiwix_env['library'].read_text()
    assert 'good.zim' in library
    assert 'sudan_broken.zim' not in library


def test_only_corrupt_zim_still_starts_server(kiwix_env):
    """Even when the only zim is corrupt, kiwix must still start."""
    _write_zim(kiwix_env['zims'] / 'sudan_broken.zim', corrupt=True)

    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'
    assert kiwix_env['library'].exists()


def test_no_zims_still_starts_server(kiwix_env):
    """With no zim files at all, kiwix still starts with an empty library."""
    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'


def test_honors_configured_zims_destination(kiwix_env):
    """A custom zims_destination in wrolpi.yaml is used instead of the default `zims`."""
    kiwix_env['write_config']('zims_destination: mycustomzims\n')
    _write_zim(kiwix_env['media'] / 'mycustomzims' / 'wikipedia.zim')

    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'
    # The library lives in the configured directory and references the zim there.
    library = kiwix_env['media'] / 'mycustomzims' / 'library.xml'
    assert library.exists()
    assert 'mycustomzims/wikipedia.zim' in library.read_text()


def test_falls_back_to_default_zim_when_no_usable_zim(kiwix_env):
    """When no functioning zim is present, the default Zim is served."""
    # No zims in the directory; create the default Zim the script should fall back to.
    _write_zim(kiwix_env['default_zim'])

    result = kiwix_env['run']()

    assert result.returncode == 0, result.stderr
    assert kiwix_env['started_marker'].exists(), 'kiwix-serve was not started'
    assert 'default.zim' in kiwix_env['library'].read_text()
