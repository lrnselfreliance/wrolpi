import json
from http import HTTPStatus
from itertools import zip_longest

import mock


def assert_map_file_status(test_client, expected, status_code=HTTPStatus.OK):
    request, response = test_client.get('/api/map/files')
    assert response.status_code == status_code
    for pbf, expected_ in zip_longest(response.json['files'], expected):
        imported = 'to be imported' if expected_['imported'] else 'to NOT be imported'
        if not pbf['imported'] == expected_['imported']:
            raise AssertionError(f'Expected {pbf["path"]} {imported}')
        assert pbf['path'].endswith(expected_['path'])
    assert response.json['pending'] is None


@mock.patch('modules.map.lib.is_pbf_file', lambda i: True)
@mock.patch('modules.map.lib.is_dump_file', lambda i: True)
def test_status_and_import(test_client, test_session, make_files_structure, mock_run_command):
    """PBF files can be imported, and the status of the import can be monitored."""
    pbf1, pbf2, dump1 = make_files_structure([
        'map/pbf/some-country.osm.pbf',
        'map/pbf/other-country.osm.pbf',
        'map/dump/dumpy.dump',
    ])

    # The PBF files can be found, but have not yet been imported.
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)

    body = {'files': [str(pbf1), str(pbf2)]}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Can import multiple pbf files.
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': True, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)

    body = {'files': [str(pbf1), ], }
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Importing one pbf resets the import statuses.
    expected = [
        {'imported': False, 'path': 'map/dump/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)

    body = {'files': [str(dump1), ]}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Importing a dump also resets statuses.
    expected = [
        {'imported': True, 'path': 'map/dump/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/other-country.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/some-country.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)


@mock.patch('modules.map.lib.is_pbf_file', lambda i: True)
@mock.patch('modules.map.lib.is_dump_file', lambda i: True)
def test_multiple_import(test_client, test_session, test_directory, make_files_structure, mock_run_command):
    """Multiple PBFs can be imported.  Importing a second time overwrites the previous imports."""
    pbf1, pbf2, pbf3, dump = make_files_structure([
        'map/pbf/country1.osm.pbf',
        'map/pbf/country2.osm.pbf',
        'map/pbf/country3.osm.pbf',
        'map/dumpy.dump',
    ])

    body = {'files': [str(pbf2), str(pbf1)]}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Two PBFs can be merged and imported.
    expected = [
        {'imported': False, 'path': 'map/dumpy.dump'},
        {'imported': True, 'path': 'map/pbf/country1.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/country2.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/country3.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)

    body = {'files': [str(pbf3), ]}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # New imports overwrite old imports.
    expected = [
        {'imported': False, 'path': 'map/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/country1.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/country2.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/country3.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)

    # Can't mix PBF and dump.
    body = {'files': [str(dump), ]}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Dump does not overwrite.
    expected = [
        {'imported': True, 'path': 'map/dumpy.dump'},
        {'imported': False, 'path': 'map/pbf/country1.osm.pbf'},
        {'imported': False, 'path': 'map/pbf/country2.osm.pbf'},
        {'imported': True, 'path': 'map/pbf/country3.osm.pbf'},
    ]
    assert_map_file_status(test_client, expected)


def test_empty_import(test_client, test_session, test_directory):
    """Some files must be requested."""
    body = {'files': []}
    request, response = test_client.post('/api/map/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'validate' in response.json['message']
