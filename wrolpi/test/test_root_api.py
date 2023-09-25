import asyncio
import json
from http import HTTPStatus
from itertools import zip_longest

import pytest
from mock import mock

from wrolpi.admin import HotspotStatus
from wrolpi.common import get_config
from wrolpi.downloader import Download, get_download_manager_config
from wrolpi.errors import ValidationError, SearchEmpty
from wrolpi.root_api import json_error_handler
from wrolpi.test.common import skip_circleci, assert_dict_contains


@pytest.mark.asyncio
async def test_index(test_session, test_async_client):
    """
    Index should have some details in an HTML response
    """
    request, response = await test_async_client.get('/')
    assert response.status_code == HTTPStatus.OK
    assert b'html' in response.body

    request, response = await test_async_client.get('/api')
    assert response.status_code == HTTPStatus.OK
    assert b'html' in response.body


@pytest.mark.asyncio
async def test_valid_regex(test_session, test_async_client):
    """
    The endpoint should only return valid if the regex is valid.
    """
    data = {'regex': 'foo'}
    request, response = await test_async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.body) == {'valid': True, 'regex': 'foo'}

    data = {'regex': '.*(title match).*'}
    request, response = await test_async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.body) == {'valid': True, 'regex': '.*(title match).*'}

    data = {'regex': '.*(missing parenthesis.*'}
    request, response = await test_async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert json.loads(response.body) == {'valid': False, 'regex': '.*(missing parenthesis.*'}


@pytest.mark.asyncio
async def test_get_settings(test_session, test_async_client):
    with mock.patch('wrolpi.admin.CPUFREQ_INFO_BIN', '/usr/bin/cpufreq-info'), \
            mock.patch('wrolpi.admin.NMCLI_BIN', '/usr/bin/nmcli'):
        request, response = await test_async_client.get('/api/settings')
        assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_log_level(test_async_client):
    """Log level must be between 0 and 40."""
    data = {'log_level': 0}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT

    data = {'log_level': -1}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {'log_level': 40}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT

    data = {'log_level': 41}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {'log_level': None}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {}
    request, response = await test_async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_downloads(test_session, test_async_client):
    request, response = await test_async_client.get('/api/download')
    assert_dict_contains(response.json, {'once_downloads': [], 'recurring_downloads': []})

    d1 = Download(url='https://example.com/1', status='complete')
    d2 = Download(url='https://example.com/2', status='pending')
    d3 = Download(url='https://example.com/3', status='deferred')
    d4 = Download(url='https://example.com/4', status='deferred')
    d5 = Download(url='https://example.com/5', status='new')
    d6 = Download(url='https://example.com/6', status='deferred', frequency=60)
    d7 = Download(url='https://example.com/7', status='pending', frequency=60)
    test_session.add_all([d1, d2, d3, d4, d5, d6, d7])
    test_session.commit()

    request, response = await test_async_client.get('/api/download')
    expected = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/5', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
        {'url': 'https://example.com/4', 'status': 'deferred'},
        {'url': 'https://example.com/1', 'status': 'complete'},
    ]
    for download, expected in zip_longest(response.json['once_downloads'], expected):
        assert_dict_contains(download, expected)
    expected = [
        {'url': 'https://example.com/7', 'status': 'pending'},
        {'url': 'https://example.com/6', 'status': 'deferred'},
    ]
    for download, expected in zip_longest(response.json['recurring_downloads'], expected):
        assert_dict_contains(download, expected)


@pytest.mark.asyncio
async def test_downloads_sorter_recurring(test_async_client, test_session):
    downloads = [
        dict(status='complete', frequency=1),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:01+00:00'),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:02+00:00'),
        dict(status='pending', frequency=1),
        dict(status='pending', frequency=4),
        dict(status='failed', frequency=1),
        dict(status='failed', frequency=1),
    ]
    for download in downloads:
        test_session.add(Download(url='https://example.com', **download))
    test_session.commit()

    expected = [
        dict(status='pending', frequency=1),
        dict(status='pending', frequency=4),
        dict(status='failed', frequency=1),
        dict(status='failed'),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:01+00:00'),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:02+00:00'),
        dict(status='complete', frequency=1),
    ]
    request, response = await test_async_client.get('/api/download')
    recurring_downloads = response.json['recurring_downloads']
    for d1, d2 in zip_longest(expected, recurring_downloads):
        assert_dict_contains(d2, d1)


@pytest.mark.asyncio
async def test_downloads_sorter(test_async_client, test_session):
    downloads = [
        dict(status='complete', last_successful_download='2020-01-01T00:00:01+00:00'),
        dict(status='complete', last_successful_download='2020-01-01T00:00:03+00:00'),
        dict(status='complete', last_successful_download='2020-01-01T00:00:02+00:00'),
        # last_successful_download are equal, so id is used next.
        dict(status='pending', last_successful_download='2020-01-01T00:00:01+00:00', url='1'),
        dict(status='pending', last_successful_download='2020-01-01T00:00:01+00:00', url='2'),

        dict(status='pending', last_successful_download='2020-01-01T00:00:04+00:00'),
        dict(status='failed'),
        dict(status='failed', last_successful_download='2020-01-01T00:00:01+00:00'),
    ]
    for download in downloads:
        test_session.add(Download(url=download.pop('url', 'https://example.com'), **download))
    test_session.commit()

    expected = [
        dict(status='pending', last_successful_download='2020-01-01T00:00:04+00:00'),
        dict(status='pending', last_successful_download='2020-01-01T00:00:01+00:00', url='1'),
        dict(status='pending', last_successful_download='2020-01-01T00:00:01+00:00', url='2'),
        dict(status='failed'),
        dict(status='failed', last_successful_download='2020-01-01T00:00:01+00:00'),
        dict(status='complete', last_successful_download='2020-01-01T00:00:03+00:00'),
        dict(status='complete', last_successful_download='2020-01-01T00:00:02+00:00'),
        dict(status='complete', last_successful_download='2020-01-01T00:00:01+00:00'),
    ]
    request, response = await test_async_client.get('/api/download')
    once_downloads = response.json['once_downloads']
    for d1, d2 in zip_longest(expected, once_downloads):
        assert_dict_contains(d2, d1)


@pytest.mark.asyncio
async def test_echo(test_async_client):
    """
    Echo should send back a JSON object with our request details.
    """
    request, response = await test_async_client.get('/api/echo?hello=world')
    assert response.status_code == HTTPStatus.OK
    assert_dict_contains(response.json['form'], {})
    assert response.json['method'] == 'GET', 'Method was not GET'
    assert response.json['json'] is None, 'JSON was not empty'
    assert response.json['args'] == {'hello': ['world']}

    data = {'foo': 'bar'}
    request, response = await test_async_client.post('/api/echo', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert_dict_contains(response.json['form'], {})
    assert response.json['method'] == 'POST', 'Method was not POST'
    assert response.json['json'] == data, 'JSON was not data'
    assert response.json['args'] == {}


def test_hotspot_settings(test_session, test_client, test_config):
    """
    The User can toggle the Hotspot via /settings.  The Hotspot can be automatically started on startup.
    """
    config = get_config()
    assert config.hotspot_on_startup is True

    with mock.patch('wrolpi.root_api.admin') as mock_admin:
        # Turning on the hotspot succeeds.
        mock_admin.enable_hotspot.return_value = True
        request, response = test_client.patch('/api/settings', content=json.dumps({'hotspot_status': True}))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.json
        mock_admin.enable_hotspot.assert_called_once()
        mock_admin.reset_mock()

        # Turning on the hotspot fails.
        mock_admin.enable_hotspot.return_value = False
        request, response = test_client.patch('/api/settings', content=json.dumps({'hotspot_status': True}))
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, response.json
        assert response.json['code'] == 'HOTSPOT_ERROR'
        mock_admin.enable_hotspot.assert_called_once()

        # Turning off the hotspot succeeds.
        mock_admin.disable_hotspot.return_value = True
        request, response = test_client.patch('/api/settings', content=json.dumps({'hotspot_status': False}))
        assert response.status_code == HTTPStatus.NO_CONTENT, response.json
        mock_admin.disable_hotspot.assert_called_once()
        mock_admin.reset_mock()

        # Turning off the hotspot succeeds.
        mock_admin.disable_hotspot.return_value = False
        request, response = test_client.patch('/api/settings', content=json.dumps({'hotspot_status': False}))
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, response.json
        assert response.json['code'] == 'HOTSPOT_ERROR'
        mock_admin.disable_hotspot.assert_called_once()

        mock_admin.enable_hotspot.reset_mock()
        mock_admin.enable_hotspot.return_value = True
        mock_admin.hotspot_status.return_value = HotspotStatus.connected

        # Hotspot password can be changed.
        mock_admin.disable_hotspot.return_value = True
        content = {'hotspot_password': 'new password', 'hotspot_ssid': 'new ssid'}
        request, response = test_client.patch('/api/settings', content=json.dumps(content))
        assert response.status_code == HTTPStatus.NO_CONTENT
        assert config.hotspot_password == 'new password'
        assert config.hotspot_ssid == 'new ssid'
        # Changing the password restarts the hotspot.
        mock_admin.enable_hotspot.assert_called_once()

        # Hotspot password must be at least 8 characters.
        mock_admin.disable_hotspot.return_value = True
        content = {'hotspot_password': '1234567', 'hotspot_ssid': 'new ssid'}
        request, response = test_client.patch('/api/settings', content=json.dumps(content))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json == {'code': 'HOTSPOT_PASSWORD_TOO_SHORT',
                                 'error': '',
                                 'summary': 'Hotspot password must be at least 8 characters'
                                 }


@skip_circleci
def test_throttle_toggle(test_session, test_client, test_config):
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.CPUFREQ_INFO_BIN', "this value isn't even used"):
        mock_subprocess.check_output.side_effect = [
            b'wlan0: unavailable',
            b'The governor "ondemand" may decide ',
        ]
        request, response = test_client.get('/api/settings')

    # Throttle is off by default.
    assert response.status_code == HTTPStatus.OK
    assert response.json['throttle_on_startup'] is False
    assert response.json['throttle_status'] == 'ondemand'


@pytest.mark.asyncio
async def test_clear_downloads(test_session, test_async_client, test_config, test_download_manager_config):
    d1 = Download(url='https://example.com/1', status='complete')
    d2 = Download(url='https://example.com/2', status='pending')
    d3 = Download(url='https://example.com/3', status='deferred')
    d4 = Download(url='https://example.com/4', status='new')
    d5 = Download(url='https://example.com/5', status='failed')
    d6 = Download(url='https://example.com/6', status='failed', frequency=60)
    d7 = Download(url='https://example.com/7', status='complete', frequency=60)
    test_session.add_all([d1, d2, d3, d4, d5, d6, d7])
    test_session.commit()

    def check_downloads(response_, once_downloads_, recurring_downloads_, status_code=None):
        if status_code:
            assert response_.status_code == status_code

        for download, once_download in zip_longest(response_.json['once_downloads'], once_downloads_):
            assert download
            assert once_download
            assert download['url'] == once_download['url']
            assert download['status'] == once_download['status']
        for download, recurring_download in zip_longest(response_.json['recurring_downloads'], recurring_downloads_):
            assert download
            assert recurring_download
            assert download['url'] == recurring_download['url']
            assert download['status'] == recurring_download['status']

    # All created downloads are present.
    request, response = await test_async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/5', 'status': 'failed'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
        {'url': 'https://example.com/1', 'status': 'complete'},
    ]
    recurring_downloads = [
        {'url': 'https://example.com/6', 'status': 'failed'},
        {'url': 'https://example.com/7', 'status': 'complete'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Once "complete" download is removed.
    request, response = await test_async_client.post('/api/download/clear_completed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await test_async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/5', 'status': 'failed'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed "once" download is removed, recurring failed is not removed.
    request, response = await test_async_client.post('/api/download/clear_failed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await test_async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed once-downloads will not be downloaded again.
    assert get_download_manager_config().skip_urls == ['https://example.com/5', ]


@pytest.mark.asyncio
async def test_get_status(test_async_client, test_session):
    """Get the server status information."""
    request, response = await test_async_client.get('/api/status')
    assert response.status_code == HTTPStatus.OK
    assert 'cpu_info' in response.json and isinstance(response.json['cpu_info'], dict)
    assert 'load' in response.json and isinstance(response.json['load'], dict)
    assert 'drives' in response.json and isinstance(response.json['drives'], list)
    assert 'downloads' in response.json and isinstance(response.json['downloads'], dict)
    assert 'hotspot_status' in response.json and isinstance(response.json['hotspot_status'], str)
    assert 'throttle_status' in response.json and isinstance(response.json['throttle_status'], str)
    assert 'version' in response.json and isinstance(response.json['version'], str)
    assert 'memory_stats' in response.json and isinstance(response.json['memory_stats'], dict)
    assert 'flags' in response.json and isinstance(response.json['flags'], list)


def test_post_download(test_session, test_client, test_download_manager_config):
    """Test creating once-downloads and recurring downloads."""

    async def queue_downloads(*a, **kw):
        pass

    with mock.patch('wrolpi.downloader.DownloadManager.queue_downloads', queue_downloads):
        # Create a single recurring Download.
        content = dict(
            urls=['https://example.com/1', ],
            frequency=1_000,
            downloader='archive',
        )
        request, response = test_client.post('/api/download', content=json.dumps(content))
        assert response.status_code == HTTPStatus.NO_CONTENT

        assert {i.url for i in test_session.query(Download)} == {'https://example.com/1', }

        # Create to once-downloads.
        content = dict(
            urls=['https://example.com/2', 'https://example.com/3'],
            downloader='archive',
        )
        request, response = test_client.post('/api/download', content=json.dumps(content))
        assert response.status_code == HTTPStatus.NO_CONTENT

        assert {i.url for i in test_session.query(Download)} == {f'https://example.com/{i}' for i in range(1, 4)}


def test_get_downloaders(test_client):
    """A list of Downloaders the user can use can be gotten."""
    request, response = test_client.get('/api/downloaders')
    assert response.status_code == HTTPStatus.OK
    assert 'downloaders' in response.json, 'Downloaders not returned'
    assert isinstance(response.json['downloaders'], list) and len(response.json['downloaders']), \
        'No downloaders returned'


@pytest.mark.asyncio
async def test_empty_post_download(test_async_client):
    """Cannot have empty download URLs"""
    content = dict(
        urls=[''],  # Cannot have empty URLs
        frequency=1_000,
        downloader='archive',
    )
    request, response = await test_async_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['code'] == 'INVALID_DOWNLOAD'


@pytest.mark.asyncio
async def test_restart_download(test_session, test_async_client, test_download_manager, test_downloader):
    """A Download can be restarted."""
    # Create a download, fail it, it should be restarted.
    download = test_download_manager.create_download('https://example.com', test_downloader.name)
    download.fail()
    test_session.commit()
    assert test_session.query(Download).one().is_failed()

    test_downloader.set_test_failure()

    # Download is now "new" again.
    request, response = await test_async_client.post(f'/api/download/{download.id}/restart')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert test_session.query(Download).one().is_new()

    # Wait for the background download to fail.  It should be deferred.
    await asyncio.sleep(0.5)
    assert test_session.query(Download).one().is_deferred()


def test_get_global_statistics(test_session, test_client):
    request, response = test_client.get('/api/statistics')
    assert response.json['global_statistics']['db_size'] > 1


@pytest.mark.asyncio
async def test_post_vin_number_decoder(test_async_client):
    """A VIN number can be decoded."""
    # Invalid VIN number.
    content = dict(vin_number='5N1NJ01CXST00000')
    request, response = await test_async_client.post('/api/vin_number_decoder', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == dict()

    # Test VIN from vininfo.
    content = dict(vin_number='5N1NJ01CXST000001')
    request, response = await test_async_client.post('/api/vin_number_decoder', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert response.json['vin'] == {'body': 'Sedan, 4-Door, Standard Body Truck',
                                    'country': 'United States',
                                    'engine': 'VH45DE',
                                    'manufacturer': 'Nissan',
                                    'model': 'Maxima',
                                    'plant': 'Tochigi, Oppama',
                                    'region': 'North America',
                                    'serial': None,
                                    'transmission': None,
                                    'years': '1995'}


def test_search_str_estimate(test_session, test_client, test_directory, test_zim, example_pdf):
    """Get the search result estimates."""
    test_session.commit()

    request, response = test_client.post('/api/files/refresh')
    assert response.status_code == HTTPStatus.NO_CONTENT

    content = dict(search_str='example')
    request, response = test_client.post('/api/search_estimate', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK

    assert response.json['file_groups'] == 1
    assert len(response.json['zims']) == 1
    assert_dict_contains(response.json['zims'][0],
                         dict(
                             estimate=1,
                             path=str(test_zim.path.relative_to(test_directory)),
                         ))


def test_recursive_errors():
    """Errors are reported recursively."""

    def one():
        raise ValueError('Some error outside WROLPi')

    def two():
        try:
            one()
        except Exception as e:
            raise SearchEmpty('A more specific error') from e

    def three():
        try:
            two()
        except Exception as e:
            raise ValidationError('A broad error') from e

    try:
        three()
    except Exception as e:
        response = json_error_handler(None, e)
        assert json.loads(response.body.decode()) == {
            'code': 'VALIDATION_ERROR',
            'error': 'A broad error',
            'summary': 'Could not validate the contents of the request',
            'cause': {
                'code': 'SEARCH_EMPTY',
                'error': 'A more specific error',
                'summary': 'Search is empty, search_str must have content.',
                'cause': {
                    'code': None,
                    'error': 'Some error outside WROLPi',
                    'summary': None,
                },
            },
        }
