import json
from http import HTTPStatus
from itertools import zip_longest

from mock import mock

from wrolpi.common import get_config
from wrolpi.dates import strptime
from wrolpi.db import get_db_session
from wrolpi.downloader import Download
from wrolpi.root_api import api_app
from wrolpi.test.common import TestAPI, wrap_test_db, skip_circleci


class TestRootAPI(TestAPI):

    def test_index(self):
        """
        Index should have some details in an HTML response
        """
        request, response = api_app.test_client.get('/')
        assert response.status_code == HTTPStatus.OK
        assert b'html' in response.body

    def test_echo(self):
        """
        Echo should send back a JSON object with our request details.
        """
        request, response = api_app.test_client.get('/api/echo?hello=world')
        assert response.status_code == HTTPStatus.OK
        self.assertDictContains(response.json['form'], {})
        assert response.json['method'] == 'GET', 'Method was not GET'
        assert response.json['json'] is None, 'JSON was not empty'
        assert response.json['args'] == {'hello': ['world']}

        data = {'foo': 'bar'}
        request, response = api_app.test_client.post('/api/echo', content=json.dumps(data))
        assert response.status_code == HTTPStatus.OK
        self.assertDictContains(response.json['form'], {})
        assert response.json['method'] == 'POST', 'Method was not POST'
        assert response.json['json'] == data, 'JSON was not data'
        assert response.json['args'] == {}

    def test_valid_regex(self):
        """
        The endpoint should only return valid if the regex is valid.
        """
        data = {'regex': 'foo'}
        request, response = api_app.test_client.post('/api/valid_regex', content=json.dumps(data))
        assert response.status_code == HTTPStatus.OK
        assert json.loads(response.body) == {'valid': True, 'regex': 'foo'}

        data = {'regex': '.*(title match).*'}
        request, response = api_app.test_client.post('/api/valid_regex', content=json.dumps(data))
        assert response.status_code == HTTPStatus.OK
        assert json.loads(response.body) == {'valid': True, 'regex': '.*(title match).*'}

        data = {'regex': '.*(missing parenthesis.*'}
        request, response = api_app.test_client.post('/api/valid_regex', content=json.dumps(data))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert json.loads(response.body) == {'valid': False, 'regex': '.*(missing parenthesis.*'}

    def test_get_settings(self):
        with mock.patch('wrolpi.admin.CPUFREQ_INFO', '/usr/bin/cpufreq-info'), \
                mock.patch('wrolpi.admin.NMCLI', '/usr/bin/nmcli'):
            request, response = api_app.test_client.get('/api/settings')
            self.assertOK(response)

    @wrap_test_db
    def test_get_downloads(self):
        request, response = api_app.test_client.get('/api/download')
        self.assertDictContains(response.json, {'once_downloads': [], 'recurring_downloads': []})

        with get_db_session(commit=True) as session:
            d1 = Download(url='https://example.com/1', status='complete')
            d2 = Download(url='https://example.com/2', status='pending')
            d3 = Download(url='https://example.com/3', status='deferred')
            d4 = Download(url='https://example.com/4', status='deferred')
            d5 = Download(url='https://example.com/5', status='new')
            d6 = Download(url='https://example.com/6', status='deferred', frequency=60)
            d7 = Download(url='https://example.com/7', status='pending', frequency=60)
            session.add_all([d1, d2, d3, d4, d5, d6, d7])

        request, response = api_app.test_client.get('/api/download')
        expected = [
            {'url': 'https://example.com/2', 'status': 'pending'},
            {'url': 'https://example.com/5', 'status': 'new'},
            {'url': 'https://example.com/3', 'status': 'deferred'},
            {'url': 'https://example.com/4', 'status': 'deferred'},
            {'url': 'https://example.com/1', 'status': 'complete'},
        ]
        for download, expected in zip_longest(response.json['once_downloads'], expected):
            self.assertDictContains(download, expected)
        expected = [
            {'url': 'https://example.com/7', 'status': 'pending'},
            {'url': 'https://example.com/6', 'status': 'deferred'},
        ]
        for download, expected in zip_longest(response.json['recurring_downloads'], expected):
            self.assertDictContains(download, expected)

    @wrap_test_db
    def test_downloads_sorter(self):
        with get_db_session(commit=True) as session:
            downloads = [
                dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:01')),
                dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:03')),
                dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:02')),
                # last_successful_download are equal, so id is used next.
                dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:01'), url='1'),
                dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:01'), url='2'),

                dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:04')),
                dict(status='failed'),
                dict(status='failed', last_successful_download=strptime('2020-01-01 00:00:01')),
            ]
            for download in downloads:
                session.add(Download(url=download.pop('url', 'https://example.com'), **download))

        expected = [
            dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:04').timestamp()),
            dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:01').timestamp(), url='1'),
            dict(status='pending', last_successful_download=strptime('2020-01-01 00:00:01').timestamp(), url='2'),
            dict(status='failed'),
            dict(status='failed', last_successful_download=strptime('2020-01-01 00:00:01').timestamp()),
            dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:03').timestamp()),
            dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:02').timestamp()),
            dict(status='complete', last_successful_download=strptime('2020-01-01 00:00:01').timestamp()),
        ]
        request, response = api_app.test_client.get('/api/download')
        once_downloads = response.json['once_downloads']
        for d1, d2 in zip_longest(expected, once_downloads):
            self.assertDictContains(d2, d1)

    @wrap_test_db
    def test_downloads_sorter_recurring(self):
        with get_db_session(commit=True) as session:
            downloads = [
                dict(status='complete', frequency=1),
                dict(status='complete', frequency=2, next_download=strptime('2020-01-01 00:00:01')),
                dict(status='complete', frequency=2, next_download=strptime('2020-01-01 00:00:02')),
                dict(status='pending', frequency=1),
                dict(status='pending', frequency=4),
                dict(status='failed', frequency=1),
                dict(status='failed', frequency=1),
            ]
            for download in downloads:
                session.add(Download(url='https://example.com', **download))

        expected = [
            dict(status='pending', frequency=1),
            dict(status='pending', frequency=4),
            dict(status='failed', frequency=1),
            dict(status='failed'),
            dict(status='complete', frequency=2, next_download=strptime('2020-01-01 00:00:01').timestamp()),
            dict(status='complete', frequency=2, next_download=strptime('2020-01-01 00:00:02').timestamp()),
            dict(status='complete', frequency=1),
        ]
        request, response = api_app.test_client.get('/api/download')
        recurring_downloads = response.json['recurring_downloads']
        for d1, d2 in zip_longest(expected, recurring_downloads):
            self.assertDictContains(d2, d1)


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
        assert response.json['code'] == 35
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
        assert response.json['code'] == 35
        mock_admin.disable_hotspot.assert_called_once()

        config = get_config()
        assert config.hotspot_on_startup is True

        # Hotspot password can be changed.
        mock_admin.disable_hotspot.return_value = True
        content = {'hotspot_password': 'new password', 'hotspot_ssid': 'new ssid'}
        request, response = test_client.patch('/api/settings', content=json.dumps(content))
        assert response.status_code == HTTPStatus.NO_CONTENT
        assert config.hotspot_password == 'new password'
        assert config.hotspot_ssid == 'new ssid'


@skip_circleci
def test_throttle_toggle(test_session, test_client, test_config):
    with mock.patch('wrolpi.admin.subprocess') as mock_subprocess, \
            mock.patch('wrolpi.admin.CPUFREQ_INFO', "this value isn't even used"):
        mock_subprocess.check_output.side_effect = [
            b'wlan0: unavailable',
            b'The governor "ondemand" may decide ',
        ]
        request, response = test_client.get('/api/settings')

    # Throttle is off by default.
    assert response.status_code == HTTPStatus.OK
    assert response.json['throttle_on_startup'] is False
    assert response.json['throttle_status'] == 'ondemand'


def test_clear_downloads(test_session, test_client, test_config):
    from wrolpi.downloader import DOWNLOAD_MANAGER_CONFIG

    with get_db_session(commit=True) as session:
        d1 = Download(url='https://example.com/1', status='complete')
        d2 = Download(url='https://example.com/2', status='pending')
        d3 = Download(url='https://example.com/3', status='deferred')
        d4 = Download(url='https://example.com/4', status='new')
        d5 = Download(url='https://example.com/5', status='failed')
        d6 = Download(url='https://example.com/6', status='failed', frequency=60)
        d7 = Download(url='https://example.com/7', status='complete', frequency=60)
        session.add_all([d1, d2, d3, d4, d5, d6, d7])

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
    request, response = api_app.test_client.get('/api/download')
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
    request, response = api_app.test_client.post('/api/download/clear_completed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = api_app.test_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/5', 'status': 'failed'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed "once" download is removed, recurring failed is not removed.
    request, response = api_app.test_client.post('/api/download/clear_failed')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = api_app.test_client.get('/api/download')
    once_downloads = [
        {'url': 'https://example.com/2', 'status': 'pending'},
        {'url': 'https://example.com/4', 'status': 'new'},
        {'url': 'https://example.com/3', 'status': 'deferred'},
    ]
    check_downloads(response, once_downloads, recurring_downloads, status_code=HTTPStatus.OK)

    # Failed once-downloads will not be downloaded again.
    assert DOWNLOAD_MANAGER_CONFIG.skip_urls == ['https://example.com/5', ]
