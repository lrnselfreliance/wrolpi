import json
from http import HTTPStatus
from itertools import zip_longest

from wrolpi.db import get_db_session
from wrolpi.downloader import Download
from wrolpi.root_api import api_app
from wrolpi.test.common import TestAPI, wrap_test_db


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
        request, response = api_app.test_client.post('/api/echo', data=json.dumps(data))
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
        request, response = api_app.test_client.post('/api/valid_regex', data=json.dumps(data))
        assert response.status_code == HTTPStatus.OK
        assert json.loads(response.body) == {'valid': True, 'regex': 'foo'}

        data = {'regex': '.*(title match).*'}
        request, response = api_app.test_client.post('/api/valid_regex', data=json.dumps(data))
        assert response.status_code == HTTPStatus.OK
        assert json.loads(response.body) == {'valid': True, 'regex': '.*(title match).*'}

        data = {'regex': '.*(missing parenthesis.*'}
        request, response = api_app.test_client.post('/api/valid_regex', data=json.dumps(data))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert json.loads(response.body) == {'valid': False, 'regex': '.*(missing parenthesis.*'}

    def test_get_settings(self):
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
    def test_get_downloads_paged(self):
        with get_db_session(commit=True) as session:
            downloads = [Download(url=f'https://example.com/{i}') for i in range(25)]
            session.add_all(downloads)

        request, response = api_app.test_client.get('/api/download')
        self.assertEqual(len(response.json['once_downloads']), 20)
        self.assertEqual(len(response.json['recurring_downloads']), 0)
