import json
from http import HTTPStatus
from itertools import zip_longest

import mock


@mock.patch('modules.map.lib.is_pbf_file', lambda i: True)
def test_pbf_status_and_import(test_client, test_session, test_directory):
    """PBF files can be imported, and the status of the import can be monitored."""
    (test_directory / 'map/pbf').mkdir(parents=True)
    pbf1 = test_directory / 'map/pbf/some-country.osm.pbf'
    pbf2 = test_directory / 'map/pbf/other-country.osm.pbf'
    pbf1.touch()
    pbf2.touch()

    def check_status(response_json, expected_):
        for pbf, expected_ in zip_longest(response_json['pbfs'], expected_):
            assert pbf['imported'] == expected_['imported']
            assert pbf['path'].endswith(expected_['path'])
        assert response.json['importing'] is None

    # The PBF files can be found, but have not yet been imported.
    request, response = test_client.get('/api/map/pbf')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)

    with mock.patch('modules.map.lib.import_pbf') as mock_import_pbf:
        body = {'pbfs': [str(pbf1), ]}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.NO_CONTENT
        # Only one import is requested.
        mock_import_pbf.assert_called_once()

    request, response = test_client.get('/api/map/pbf')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)

    with mock.patch('modules.map.lib.import_pbf') as mock_import_pbf:
        body = {'pbfs': [str(pbf1), str(pbf2)]}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.NO_CONTENT
        # Both imports are requested, but only one is performed.
        mock_import_pbf.assert_called_once()

    request, response = test_client.get('/api/map/pbf')
    assert response.status_code == HTTPStatus.OK
    expected = [
        {'imported': True, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    check_status(response.json, expected)


def test_empty_import(test_client, test_session, test_directory):
    """Some files must be requested."""
    with mock.patch('modules.map.lib.import_pbf') as mock_import_pbf:
        body = {'pbfs': []}
        request, response = test_client.post('/api/map/import', content=json.dumps(body))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        mock_import_pbf.assert_not_called()
