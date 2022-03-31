import json
from http import HTTPStatus
from itertools import zip_longest

import mock


@mock.patch('modules.map.lib.is_pbf_file', lambda i: True)
@mock.patch('modules.map.lib.is_dump_file', lambda i: True)
def test_status_and_import(test_client, test_session, test_directory):
    """PBF files can be imported, and the status of the import can be monitored."""
    (test_directory / 'map/pbf').mkdir(parents=True)
    (test_directory / 'map/dump').mkdir()
    pbf1 = test_directory / 'map/pbf/some-country.osm.pbf'
    pbf2 = test_directory / 'map/pbf/other-country.osm.pbf'
    pbf1.touch()
    pbf2.touch()
    dump1 = test_directory / 'map/dump/dumpy.dump'
    dump1.touch()

    def check_status(response_json, expected_):
        for pbf, expected_ in zip_longest(response_json['files'], expected_):
            assert pbf['imported'] == expected_['imported']
            assert pbf['path'].endswith(expected_['path'])
        assert response.json['importing'] is None

    # The PBF files can be found, but have not yet been imported.
    request, response = test_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)

    with mock.patch('modules.map.lib.import_file') as mock_import_file:
        body = {'files': [str(pbf1), ], }
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.NO_CONTENT
        # Only one PBF import is requested.
        mock_import_file.assert_called_once()

    request, response = test_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)

    with mock.patch('modules.map.lib.import_file') as mock_import_file:
        body = {'files': [str(pbf1), str(pbf2)]}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.NO_CONTENT
        # Both PBF imports are requested, but only one is performed.
        mock_import_file.assert_called_once()

    request, response = test_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': True, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)

    with mock.patch('modules.map.lib.import_file') as mock_import_file:
        body = {'files': [str(dump1), ]}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.NO_CONTENT
        # Dump is imported.
        mock_import_file.assert_called_once()

    request, response = test_client.get('/api/map/files')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': True, 'path': 'map/dump/dumpy.dump'},
        {'imported': True, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)


def test_empty_import(test_client, test_session, test_directory):
    """Some files must be requested."""
    with mock.patch('modules.map.lib.import_file') as mock_import_file:
        body = {'pbfs': []}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_import_file.assert_not_called()

        body = {'dumps': []}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_import_file.assert_not_called()

        body = {'pbfs': [], 'dumps': []}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_import_file.assert_not_called()
