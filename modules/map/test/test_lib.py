from unittest import mock

import pytest

from modules.map import lib


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
