from unittest import mock

import pytest

from modules.map import lib
from wrolpi.common import get_wrolpi_config


def test_get_map_paths(test_directory, make_files_structure):
    pbf, dump = make_files_structure([
        'map/pbf/map.osm.pbf',
        'map/pbf/map.dump',
    ])

    with mock.patch('modules.map.lib.subprocess.check_output') as mock_check_output:
        mock_check_output.return_value = b'OpenStreetMap Protocolbuffer Binary Format'
        assert lib.get_map_paths() == [pbf, ]

    with mock.patch('modules.map.lib.subprocess.check_output') as mock_check_output:
        mock_check_output.return_value = b'PostgreSQL custom database dump'
        assert lib.get_map_paths() == [dump, ]


@pytest.mark.asyncio
async def test_run_import_command(test_directory, mock_create_subprocess_shell):
    """
    Import map files.  Files to import are checked for validity before importing.  Any errors returned by
    asyncio.create_subprocess_shell are caught and reported.
    """
    pbf_file = test_directory / 'foo.osm.pbf'
    with pytest.raises(ValueError):
        await lib.run_import_command(pbf_file)

    pbf_file.touch()
    with pytest.raises(ValueError):
        await lib.run_import_command(pbf_file)

    dump_file = test_directory / 'dumpy.dump'
    dump_file.touch()

    with mock.patch('modules.map.lib.asyncio') as mock_asyncio, \
            mock.patch('modules.map.lib.is_pbf_file') as mock_is_pbf_file:
        # Run the import, it succeeds.
        mock_asyncio.create_subprocess_shell = mock_create_subprocess_shell(
            communicate_return=(b'out', b'error')
        )
        mock_is_pbf_file.return_value = True
        await lib.run_import_command(pbf_file)

    with mock.patch('modules.map.lib.asyncio') as mock_asyncio, \
            mock.patch('modules.map.lib.is_pbf_file') as mock_is_pbf_file:
        # Run the import, it fails.
        mock_asyncio.create_subprocess_shell = mock_create_subprocess_shell(
            communicate_return=(b'out', b'error'),
            return_code=1,
        )
        mock_is_pbf_file.return_value = True
        with pytest.raises(ValueError):
            await lib.run_import_command(pbf_file)

    with pytest.raises(ValueError) as e:
        await lib.run_import_command()
    assert 'Must import a file' in str(e)

    # Can't import more than one dump.
    with pytest.raises(ValueError) as e:
        await lib.run_import_command(dump_file, dump_file)
    assert 'more than one' in str(e)


@pytest.mark.parametrize('size,expected', [
    (0, 0),
    (-1, 0),
    (17737381, 286),
    (63434267, 1025),
    (87745484, 1418),
    (116318111, 1879),
    (136372996, 2203),
    (1936075318, 150308),
    (2676094489, 345922),
    (3392375001, 610106),
    (11346305075, 8491840),
])
def test_seconds_to_import_rpi4(size, expected):
    assert lib.seconds_to_import(size) == expected


@pytest.mark.parametrize('size,expected', [
    (0, 0),
    (-1, 0),
    (17737381, 130),
    (63434267, 466),
    (87745484, 645),
    (116318111, 855),
    (136372996, 1002),
    (1936075318, 14235),
    (2676094489, 19676),
    (3392375001, 24943),
    (11346305075, 188040),
])
def test_seconds_to_import_rpi5(size, expected):
    assert lib.seconds_to_import(size, True) == expected


def test_get_custom_map_directory(test_directory, test_config):
    """Custom directory can be used for map directory."""
    # Default location.
    assert lib.get_map_directory() == (test_directory / 'map')

    get_wrolpi_config().map_destination = 'custom/deep/map/directory'

    assert lib.get_map_directory() == (test_directory / 'custom/deep/map/directory')
    assert (test_directory / 'custom/deep/map/directory').is_dir()
