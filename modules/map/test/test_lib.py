from unittest import mock

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
