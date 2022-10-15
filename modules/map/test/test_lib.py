from unittest import mock

import pytest

from modules.map import lib


def test_get_map_paths(test_directory):
    pbf_dir = test_directory / 'map/pbf'
    pbf_dir.mkdir(parents=True)

    pbf = pbf_dir / 'map.osm.pbf'
    pbf.touch()
    dump = pbf_dir / 'map.dump'
    dump.touch()

    with mock.patch('modules.map.lib.subprocess.check_output') as mock_check_output:
        mock_check_output.return_value = b'OpenStreetMap Protocolbuffer Binary Format'
        assert lib.get_map_paths() == [pbf, ]

    with mock.patch('modules.map.lib.subprocess.check_output') as mock_check_output:
        mock_check_output.return_value = b'PostgreSQL custom database dump'
        assert lib.get_map_paths() == [dump, ]


@pytest.mark.asyncio
async def test_import_file(test_directory, mock_create_subprocess_shell):
    """
    Import map files.  Files to import are checked for validity before importing.  Any errors returned by
    asyncio.create_subprocess_shell are caught and reported.
    """
    pbf_file = test_directory / 'foo.osm.pbf'
    with pytest.raises(ValueError):
        await lib.import_file(pbf_file)

    pbf_file.touch()
    with pytest.raises(ValueError):
        await lib.import_file(pbf_file)

    with mock.patch('modules.map.lib.asyncio') as mock_asyncio, \
            mock.patch('modules.map.lib.is_pbf_file') as mock_is_pbf_file:
        # Run the import, it succeeds.
        mock_asyncio.create_subprocess_shell = mock_create_subprocess_shell(
            communicate_return=(b'out', b'error')
        )
        mock_is_pbf_file.return_value = True
        await lib.import_file(pbf_file)

    with mock.patch('modules.map.lib.asyncio') as mock_asyncio, \
            mock.patch('modules.map.lib.is_pbf_file') as mock_is_pbf_file:
        # Run the import, it fails.
        mock_asyncio.create_subprocess_shell = mock_create_subprocess_shell(
            communicate_return=(b'out', b'error'),
            return_code=1,
        )
        mock_is_pbf_file.return_value = True
        with pytest.raises(ValueError):
            await lib.import_file(pbf_file)
