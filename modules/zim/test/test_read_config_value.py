"""Tests for wrolpi/scripts/read_config_value.sh.

The reader extracts a top-level scalar from wrolpi.yaml with zero dependencies
so non-Python scripts (e.g. start_kiwix_serve.sh, the Docker Zim entrypoint) can
read config values.  Exercised directly via bash.
"""
import os
import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).parents[3]
READER = REPO_ROOT / 'wrolpi' / 'scripts' / 'read_config_value.sh'


def _read(media: pathlib.Path, key: str, default: str = '') -> str:
    env = {**os.environ, 'MEDIA_DIRECTORY': str(media)}
    result = subprocess.run(['bash', str(READER), key, default], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip('\n')


@pytest.fixture
def media_with_config(tmp_path):
    media = tmp_path / 'media'
    (media / 'config').mkdir(parents=True)

    def write(text: str):
        (media / 'config' / 'wrolpi.yaml').write_text(text)

    return media, write


def test_reads_scalar_value(media_with_config):
    media, write = media_with_config
    write('zims_destination: mycustomzims\nvideos_destination: videos\n')
    assert _read(media, 'zims_destination', 'zims') == 'mycustomzims'


def test_strips_surrounding_quotes(media_with_config):
    media, write = media_with_config
    write('videos_destination: "quoted videos"\n')
    assert _read(media, 'videos_destination', 'x') == 'quoted videos'


def test_missing_key_returns_default(media_with_config):
    media, write = media_with_config
    write('videos_destination: videos\n')
    assert _read(media, 'zims_destination', 'zims') == 'zims'


def test_empty_value_returns_default(media_with_config):
    media, write = media_with_config
    write('zims_destination:\n')
    assert _read(media, 'zims_destination', 'zims') == 'zims'


@pytest.mark.parametrize('null_repr', ['null', 'Null', 'NULL', '~'])
def test_yaml_null_returns_default(media_with_config, null_repr):
    """An unquoted YAML null means "unset" -> default, matching the Python config layer."""
    media, write = media_with_config
    write(f'zims_destination: {null_repr}\n')
    assert _read(media, 'zims_destination', 'zims') == 'zims'


def test_quoted_null_is_literal_string(media_with_config):
    """A quoted "null" is the string null, not YAML null."""
    media, write = media_with_config
    write('zims_destination: "null"\n')
    assert _read(media, 'zims_destination', 'zims') == 'null'


def test_missing_config_file_returns_default(tmp_path):
    # No config directory/file at all (fresh install) -> default, no error.
    assert _read(tmp_path / 'media', 'zims_destination', 'zims') == 'zims'


def test_ignores_indented_nested_keys(media_with_config):
    media, write = media_with_config
    # A nested key with the same name must not be matched at the top level.
    write('some_section:\n  zims_destination: nested\ntop: value\n')
    assert _read(media, 'zims_destination', 'zims') == 'zims'
