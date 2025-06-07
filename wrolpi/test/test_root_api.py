import json
from http import HTTPStatus
from itertools import zip_longest

import pytest
from mock import mock
from sanic import Request

from wrolpi.admin import HotspotStatus
from wrolpi.api_utils import json_error_handler
from wrolpi.common import get_wrolpi_config
from wrolpi.downloader import Download, get_download_manager_config
from wrolpi.errors import ValidationError, SearchEmpty
from wrolpi.test.common import skip_circleci, assert_dict_contains, skip_macos


@pytest.mark.asyncio
async def test_index(test_session, async_client):
    """
    Index should have some details in an HTML response
    """
    request, response = await async_client.get('/')
    assert response.status_code == HTTPStatus.OK
    assert b'html' in response.body

    request, response = await async_client.get('/api')
    assert response.status_code == HTTPStatus.OK
    assert b'html' in response.body


@pytest.mark.asyncio
async def test_valid_regex(test_session, async_client):
    """
    The endpoint should only return valid if the regex is valid.
    """
    data = {'regex': 'foo'}
    request, response = await async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.body) == {'valid': True, 'regex': 'foo'}

    data = {'regex': '.*(title match).*'}
    request, response = await async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.body) == {'valid': True, 'regex': '.*(title match).*'}

    data = {'regex': '.*(missing parenthesis.*'}
    request, response = await async_client.post('/api/valid_regex', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert json.loads(response.body) == {'valid': False, 'regex': '.*(missing parenthesis.*'}


@pytest.mark.asyncio
async def test_get_settings(test_session, async_client):
    get_wrolpi_config().ignored_directories = list()

    with mock.patch('wrolpi.admin.CPUFREQ_INFO_BIN', '/usr/bin/cpufreq-info'), \
            mock.patch('wrolpi.admin.NMCLI_BIN', '/usr/bin/nmcli'):
        request, response = await async_client.get('/api/settings')
        assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_log_level(async_client):
    """Log level must be between 0 and 40."""
    data = {'log_level': 0}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT

    data = {'log_level': -1}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {'log_level': 40}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT

    data = {'log_level': 41}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {'log_level': None}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = {}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_downloads(test_session, async_client):
    request, response = await async_client.get('/api/download')
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

    request, response = await async_client.get('/api/download')
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
async def test_downloads_sorter_recurring(async_client, test_session):
    downloads = [
        dict(status='complete', frequency=1),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:01+00:00'),
        dict(status='complete', frequency=2, next_download='2020-01-01T00:00:02+00:00'),
        dict(status='pending', frequency=1),
        dict(status='pending', frequency=4),
        dict(status='failed', frequency=1),
        dict(status='failed', frequency=1),
    ]
    for idx, download in enumerate(downloads):
        test_session.add(Download(url=f'https://example.com/{idx}', **download))
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
    request, response = await async_client.get('/api/download')
    recurring_downloads = response.json['recurring_downloads']
    for d1, d2 in zip_longest(expected, recurring_downloads):
        assert_dict_contains(d2, d1)


@pytest.mark.asyncio
async def test_downloads_sorter(async_client, test_session):
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
    for idx, download in enumerate(downloads):
        test_session.add(Download(url=download.pop('url', f'https://example.com/{idx}'), **download))
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
    request, response = await async_client.get('/api/download')
    once_downloads = response.json['once_downloads']
    for d1, d2 in zip_longest(expected, once_downloads):
        assert_dict_contains(d2, d1)


@pytest.mark.asyncio
async def test_echo(async_client):
    """
    Echo should send back a JSON object with our request details.
    """
    request, response = await async_client.get('/api/echo?hello=world')
    assert response.status_code == HTTPStatus.OK
    assert_dict_contains(response.json['form'], {})
    assert response.json['method'] == 'GET', 'Method was not GET'
    assert response.json['json'] is None, 'JSON was not empty'
    assert response.json['args'] == {'hello': ['world']}

    data = {'foo': 'bar'}
    request, response = await async_client.post('/api/echo', content=json.dumps(data))
    assert response.status_code == HTTPStatus.OK
    assert_dict_contains(response.json['form'], {})
    assert response.json['method'] == 'POST', 'Method was not POST'
    assert response.json['json'] == data, 'JSON was not data'
    assert response.json['args'] == {}


def test_hotspot_settings(test_session, test_client, test_wrolpi_config):
    """
    The User can toggle the Hotspot via /settings.  The Hotspot can be automatically started on startup.
    """
    config = get_wrolpi_config()
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
                                 'error': 'Bad Request',
                                 'message': 'Hotspot password must be at least 8 characters'
                                 }


@skip_macos
@skip_circleci
def test_throttle_toggle(test_session, test_client, test_wrolpi_config):
    get_wrolpi_config().ignored_directories = list()

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
async def test_clear_downloads(test_session, async_client, test_wrolpi_config, test_download_manager_config):
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
    request, response = await async_client.get('/api/download')
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
    request, response = await async_client.post('/api/download/clear_completed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/5', 'status': 'failed'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed "once" download is removed, recurring failed is not removed.
    request, response = await async_client.post('/api/download/clear_failed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed once-downloads will not be downloaded again.
    assert get_download_manager_config().skip_urls == ['https://example.com/5', ]

    # Downloads can be retried.
    request, response = await async_client.post('/api/download/retry_once')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'new'},
        {'url': 'https://example.com/4', 'status': 'new'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # "Delete All" button deletes all once-downloads.
    request, response = await async_client.post('/api/download/delete_once')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/download')
    check_downloads(response, [], recurring_downloads, status_code=HTTPStatus.OK)

    # Failed once-downloads will not be downloaded again.
    assert get_download_manager_config().skip_urls == ['https://example.com/5', ]


@pytest.mark.asyncio
async def test_retry_downloads(test_session, async_client, test_wrolpi_config, assert_downloads):
    """Downloads that are pending or deferred can be retried, and their attempts reset."""
    d1 = Download(url='https://example.com/1', status='complete', attempts=1)
    d2 = Download(url='https://example.com/2', status='pending', attempts=1)
    d3 = Download(url='https://example.com/3', status='deferred', attempts=1)
    d4 = Download(url='https://example.com/4', status='new', attempts=1)
    d5 = Download(url='https://example.com/5', status='failed', attempts=1)
    d6 = Download(url='https://example.com/6', status='failed', frequency=60, attempts=1)
    d7 = Download(url='https://example.com/7', status='complete', frequency=60, attempts=1)
    test_session.add_all([d1, d2, d3, d4, d5, d6, d7])
    test_session.commit()

    # Retry all once-downloads.
    request, response = await async_client.post('/api/download/retry_once')
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert_downloads([
        dict(url='https://example.com/1', status='complete', attempts=1),  # complete is not retried.
        dict(url='https://example.com/2', status='new', attempts=0),  # pending is retried.
        dict(url='https://example.com/3', status='new', attempts=0),  # deferred is retried.
        dict(url='https://example.com/4', status='new', attempts=1),  # new does not need to be retried.
        dict(url='https://example.com/5', status='failed', attempts=1),  # failed has been given up on.
        dict(url='https://example.com/6', status='failed', frequency=60, attempts=1, ),  # recurring is always retried.
        dict(url='https://example.com/7', status='complete', frequency=60, attempts=1),  # recurring is always retried.
    ])


@pytest.mark.asyncio
async def test_get_status(async_client, test_session):
    """Get the server status information."""
    request, response = await async_client.get('/api/status')
    assert response.status_code == HTTPStatus.OK
    assert isinstance(response.json.get('cpu_stats'), dict), 'cpu_stats should be a dict'
    assert isinstance(response.json.get('load_stats'), dict), 'load_stats should be a dict'
    assert isinstance(response.json.get('drives_stats'), list), 'drive_stats should be a dict'
    assert isinstance(response.json.get('downloads'), dict), 'downloads should be a dict'
    assert isinstance(response.json.get('hotspot_status'), str), 'hotspot_status should be a str'
    assert isinstance(response.json.get('throttle_status'), str), 'throttle_status should be a str'
    assert isinstance(response.json.get('version'), str), 'version should be a str'
    assert isinstance(response.json.get('memory_stats'), dict), 'memory_stats should be a dict'
    assert isinstance(response.json.get('flags'), dict), 'flags should be a dict'
    assert isinstance(response.json.get('sanic_workers'), dict), 'Sanic worker status should be a dict'


@pytest.mark.asyncio
async def test_download_crud(test_session, async_client, test_download_manager_config, tag_factory, test_directory):
    """Test creating once-downloads and recurring downloads."""
    tag1, tag2 = await tag_factory(), await tag_factory()

    async def dispatch_downloads(*a, **kw):
        pass

    with mock.patch('wrolpi.downloader.DownloadManager.dispatch_downloads', dispatch_downloads):
        # Create a single recurring Download.
        body = dict(
            urls=['https://example.com/1', ],
            frequency=1_000,
            downloader='archive',
            destination='archives/example.com',
            tag_names=None,  # tag_names can be a None.
        )
        request, response = await async_client.post('/api/download', content=json.dumps(body))
        assert response.status_code == HTTPStatus.CREATED

        assert {i.url for i in test_session.query(Download)} == {'https://example.com/1', }
        # Assert that the config has been saved
        config = get_download_manager_config()
        assert len(config.downloads) == 1
        assert config.downloads[0]['url'] == 'https://example.com/1'
        assert config.downloads[0]['frequency'] == 1_000
        assert config.downloads[0]['downloader'] == 'archive'

        # Create two once-downloads.
        body = dict(
            urls=['https://example.com/2', 'https://example.com/3'],
            downloader='archive',
            # tag_names=None,  # tag_names can be missing.
        )
        request, response = await async_client.post('/api/download', json=body)
        assert response.status_code == HTTPStatus.CREATED

        assert {i.url for i in test_session.query(Download)} == {f'https://example.com/{i}' for i in range(1, 4)}
        # Assert that the config has been saved
        config = get_download_manager_config()
        assert len(config.downloads) == 3
        assert {d['url'] for d in config.downloads} == {f'https://example.com/{i}' for i in range(1, 4)}

        download1, download2, download3 = test_session.query(Download).order_by(Download.url).all()
        assert not download1.settings
        # destination is absolute
        assert download1.destination == test_directory / 'archives/example.com'
        expected_download = dict(download1.__json__()).copy()

        # Update a download.
        body = dict(
            urls=['https://example.com/1'],
            downloader='archive',
            frequency=1_000,
            tag_names=[tag1.name, tag2.name],
        )
        expected_download.update(
            {'url': 'https://example.com/1', 'tag_names': [tag1.name, tag2.name], 'destination': None})
        request, response = await async_client.put(f'/api/download/{download1.id}', json=body)
        assert response.status_code == HTTPStatus.NO_CONTENT
        test_session.flush([download2])
        download2 = test_session.query(Download).filter_by(id=expected_download['id']).first()
        assert download2.__json__() == expected_download
        assert download2.tag_names == [tag1.name, tag2.name]
        # Assert that the config has been saved
        config = get_download_manager_config()
        assert len(config.downloads) == 3
        download_config = next(d for d in config.downloads if d['url'] == 'https://example.com/1')
        assert download_config['tag_names'] == [tag1.name, tag2.name]


def test_get_downloaders(test_client):
    """A list of Downloaders the user can use can be gotten."""
    request, response = test_client.get('/api/downloaders')
    assert response.status_code == HTTPStatus.OK
    assert 'downloaders' in response.json, 'Downloaders not returned'
    assert isinstance(response.json['downloaders'], list) and len(response.json['downloaders']), \
        'No downloaders returned'


@pytest.mark.asyncio
async def test_empty_post_download(async_client):
    """Cannot have empty download URLs"""
    content = dict(
        urls=[''],  # Cannot have empty URLs
        frequency=1_000,
        downloader='archive',
    )
    request, response = await async_client.post('/api/download', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['code'] == 'INVALID_DOWNLOAD'


@pytest.mark.asyncio
async def test_restart_download(test_session, async_client, test_download_manager, test_downloader, await_switches):
    """A Download can be restarted."""
    # Create a download, fail it, it should be restarted.
    download = test_download_manager.create_download('https://example.com', test_downloader.name)
    download.fail()
    test_session.commit()
    await await_switches()
    assert test_session.query(Download).one().is_failed

    test_downloader.set_test_failure()

    # Download is now "new" again.
    request, response = await async_client.post(f'/api/download/{download.id}/restart')
    assert response.status_code == HTTPStatus.NO_CONTENT
    download = test_session.query(Download).one()
    assert download.is_new, download.status

    # Wait for the background download to fail.  It should be deferred.
    await test_download_manager.wait_for_all_downloads()
    download = test_session.query(Download).one()
    assert download.is_deferred, download.status


def test_get_global_statistics(test_session, test_client):
    request, response = test_client.get('/api/statistics')
    assert response.json['global_statistics']['db_size'] > 1


@pytest.mark.asyncio
async def test_post_vin_number_decoder(async_client):
    """A VIN number can be decoded."""
    # Invalid VIN number.
    content = dict(vin_number='5N1NJ01CXST00000')
    request, response = await async_client.post('/api/vin_number_decoder', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json == dict()

    # Test VIN from vininfo.
    content = dict(vin_number='5N1NJ01CXST000001')
    request, response = await async_client.post('/api/vin_number_decoder', content=json.dumps(content))
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
                                    'years': '2025,1995'}


@pytest.mark.asyncio
async def test_search_suggestions(test_session, async_client, channel_factory, archive_factory, video_factory):
    # WARNING results are cached, this test uses unique queries to avoid conflicts.
    channel_factory(name='Foo')
    channel_factory(name='Fool')
    channel_factory(name='Bar')
    archive_factory(domain='foo.com')
    archive_factory(domain='bar.com')
    video_factory(channel_id=2)  # Channel "Fool" will be first in results because it has the most videos.
    test_session.commit()

    async def assert_results(body: dict, expected_channels=None, expected_domains=None):
        expected_channels = expected_channels or []
        expected_domains = expected_domains or []

        request, response = await async_client.post('/api/search_suggestions', json=body)
        assert response.status_code == HTTPStatus.OK
        if expected_channels:
            for channel, expected_channel in zip_longest(response.json['channels'], expected_channels):
                assert_dict_contains(channel, expected_channel)
        assert response.json['domains'] == expected_domains

    await assert_results(
        dict(search_str='foo'),
        [
            {'directory': 'videos/Fool', 'id': 2, 'name': 'Fool', 'url': 'https://example.com/Fool', 'downloads': []},
            {'directory': 'videos/Foo', 'id': 1, 'name': 'Foo', 'url': 'https://example.com/Foo', 'downloads': []},
        ],
        [{'directory': 'archive/foo.com', 'domain': 'foo.com', 'id': 1}],
    )

    # Channel name "Fool" is matched because spaces are stripped in addition to only
    await assert_results(
        dict(search_str='foo l'),
        [
            {'directory': 'videos/Fool', 'id': 2, 'name': 'Fool', 'url': 'https://example.com/Fool', 'downloads': []}],
        [],
    )

    await assert_results(
        dict(search_str='bar'),
        [
            {'directory': 'videos/Bar', 'id': 3, 'name': 'Bar', 'url': 'https://example.com/Bar', 'downloads': []}
        ],
        [{'directory': 'archive/bar.com', 'domain': 'bar.com', 'id': 2}],
    )


@pytest.mark.asyncio
async def test_search_file_estimates(test_session, async_client, archive_factory, tag_factory, video_factory):
    """Can quickly get count of possible files when searching."""
    body_ = dict(search_str='can search with no files')
    request_, response_ = await async_client.post('/api/search_file_estimates', json=body_)
    assert response_.status_code == HTTPStatus.OK

    tag1, tag2, tag3 = await tag_factory(), await tag_factory(), await tag_factory()
    archive_factory(domain='foo.com', contents='contents of foo with bunny', tag_names=[tag1.name, ])
    archive_factory(domain='bar.com', contents='contents of bar', tag_names=[tag2.name, ])
    video_factory(with_caption_file=True, tag_names=[tag1.name, tag2.name])
    test_session.commit()

    async def assert_results(body: dict, expected_file_groups=None):
        expected_file_groups = expected_file_groups or 0

        request, response = await async_client.post('/api/search_file_estimates', json=body)
        assert response.status_code == HTTPStatus.OK
        assert response.json['file_groups'] == expected_file_groups or 0

    await assert_results(dict(search_str='foo'), 1)

    # Channel name "Fool" is matched because spaces are stripped in addition to only
    await assert_results(dict(search_str='foo l'), 0)

    await assert_results(dict(search_str='bar'), 1)

    # "foo" archive and video both contain bunny.
    await assert_results(dict(search_str='bunny'), 2)

    # Filtering with mimetypes removes archive result.
    await assert_results(dict(search_str='bunny', mimetypes=['video']), 1)

    # tag1 has been used twice
    await assert_results(dict(tag_names=[tag1.name, ]), 2)

    # archive2 was tagged with tag2, but only video contains bunny.
    await assert_results(dict(search_str='bunny', tag_names=[tag2.name, ]), 1)

    # tag2 has been used twice
    await assert_results(dict(tag_names=[tag2.name, ]), 2)

    # tag2 has been used twice, but filter by video mimetype.
    await assert_results(dict(tag_names=[tag2.name], mimetypes=['video']), 1)

    # Can use all filters simultaneously.
    await assert_results(dict(search_str='bunny', tag_names=[tag2.name], mimetypes=['video']), 1)

    # Only the video has been tagged with both tag1 and tag2.
    await assert_results(dict(tag_names=[tag1.name, tag2.name]), 1)

    # tag3 was never used
    await assert_results(dict(tag_names=[tag3.name]))

    await assert_results(dict(search_str='Does not exist.'))

    # No PDFs.
    await assert_results(dict(mimetypes=['application/pdf']))

    # Can filter by published datetime.
    await assert_results(dict(months=[1, ]), 2)
    await assert_results(dict(months=[2, ]), 0)
    await assert_results(dict(from_year=2000, to_year=2000), 2)


@pytest.mark.asyncio
async def test_search_file_estimates_any_tag(test_session, async_client, archive_factory, tag_factory,
                                             video_factory):
    """File estimates can be filtered by any_tag."""
    tag1 = await tag_factory()
    archive_factory(domain='foo.com', contents='contents of foo with bunny', tag_names=[tag1.name, ])
    archive_factory(domain='bar.com', contents='contents of bar bunny')
    test_session.commit()

    async def assert_results(body: dict, expected_file_groups=None):
        expected_file_groups = expected_file_groups or 0

        request, response = await async_client.post('/api/search_file_estimates', json=body)
        assert response.status_code == HTTPStatus.OK
        assert response.json['file_groups'] == expected_file_groups or 0

    await assert_results(dict(search_str='bunny'), 2)
    await assert_results(dict(search_str='bunny', any_tag=True), 1)
    await assert_results(dict(search_str='bar'), 1)
    await assert_results(dict(search_str='bar', any_tag=True), 0)

    body_ = dict(search_str='bunny', tag_names=[tag1.name, ], any_tag=True)
    request_, response_ = await async_client.post('/api/search_file_estimates', json=body_)
    assert response_.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_external_error(async_client):
    """A non-SanicException error is handled as an Internal Server Error."""

    @async_client.sanic_app.get('/error')
    async def error(_: Request):
        raise RuntimeError('Oh no!')

    request, response = await async_client.get('/error')
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json == {'code': 'RuntimeError', 'error': 'Oh no!', 'message': None}


def test_recursive_errors():
    """Errors are reported recursively."""

    def one():
        raise ValueError('Some error outside WROLPi')

    def two():
        try:
            one()
        except Exception as e1:
            raise SearchEmpty('A more specific error') from e1

    def three():
        try:
            two()
        except Exception as e2:
            raise ValidationError() from e2

    try:
        three()
    except Exception as e:
        response = json_error_handler(None, e)
        assert json.loads(response.body.decode()) == {
            'code': 'VALIDATION_ERROR',
            'error': 'Bad Request',  # Fallback when no message is passed on exception creation.
            'message': 'Could not validate the contents of the request',
            'cause': {
                'code': 'SEARCH_EMPTY',
                'error': 'A more specific error',
                'message': 'Search is empty, search_str must have content.',
                'cause': {
                    'code': 'ValueError',  # Code falls back to Exception type.
                    'error': 'Some error outside WROLPi',
                    'message': None,
                },
            },
        }


@pytest.mark.asyncio
async def test_settings_special_directories(async_client, test_wrolpi_config):
    """Maintainer can change special directories."""
    request, response = await async_client.get('/api/settings')
    assert response.status_code == HTTPStatus.OK
    assert response.json['archive_destination'] == 'archive/%(domain)s'
    assert response.json['map_destination'] == 'map'
    assert response.json['videos_destination'] == 'videos/%(channel_tag)s/%(channel_name)s'
    assert response.json['zims_destination'] == 'zims'

    data = {'archive_destination': 'archives'}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert get_wrolpi_config().archive_destination == 'archives'

    data = {'archive_destination': '/absolute/not/allowed'}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = {'videos_destination': '/absolute/not/allowed'}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = {'map_destination': '/absolute/not/allowed'}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = {'zims_destination': '/absolute/not/allowed'}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Empty directory restores default.
    data = {'archive_destination': ''}
    request, response = await async_client.patch('/api/settings', content=json.dumps(data))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert get_wrolpi_config().archive_destination == 'archive/%(domain)s'


@pytest.mark.asyncio
async def test_search_other_estimates(async_client, test_session, channel_factory, tag_factory):
    # Can search without Tags or Channels.
    body = dict(tag_names=[])
    request, response = await async_client.post('/api/search_other_estimates', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['others']['channel_count'] == 0, 'Only one Channel is tagged.'

    tag = await tag_factory()
    channel1 = channel_factory(tag_name=tag.name)
    channel2 = channel_factory()
    test_session.commit()

    # One Channel is tagged.
    body = dict(tag_names=[tag.name, ])
    request, response = await async_client.post('/api/search_other_estimates', json=body)
    assert response.status_code == HTTPStatus.OK
    assert response.json['others']['channel_count'] == 1, 'Only one Channel is tagged.'
