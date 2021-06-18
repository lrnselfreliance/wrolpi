import asyncio
import json
from http import HTTPStatus
from unittest import mock
from unittest.mock import MagicMock

import pytest
from sanic_openapi import swagger_blueprint

from api.api import api_app
from api.test.common import TestAPI
from api.videos.api import refresh_queue


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

    @pytest.mark.xfail
    def test_swagger(self):
        """
        Swagger can be generated.  This test is just to assure that our spec generation hasn't broken.
        """
        # An API request is required to set things up (apparently).
        api_app.test_client.get('/')

        from sanic.response import json as json_
        json_(swagger_blueprint._spec)

    @staticmethod
    def _get_event(events, name):
        try:
            return [i for i in events if i['name'] == name][0]
        except IndexError:
            raise ValueError(f'No event named {name} in events!')

    def test_events(self):
        request, response = api_app.test_client.get('/api/events')
        self.assertOK(response)
        self.assertGreater(len(response.json['events']), 1)
        self.assertFalse(any(i['is_set'] for i in response.json['events']))

        calls = []

        async def fake_refresh_videos(*a, **kw):
            calls.append((a, kw))

        with mock.patch('api.videos.api.refresh_videos', fake_refresh_videos), \
                mock.patch('api.videos.api.refresh_event') as refresh_event:
            refresh_event: MagicMock

            # Cannot start a second refresh while one is running.
            refresh_event.is_set.return_value = True
            request, response = api_app.test_client.post('/api/videos:refresh')
            self.assertCONFLICT(response)

            # Refresh is started, a stream is created
            refresh_event.is_set.return_value = False
            request, response = api_app.test_client.post('/api/videos:refresh')
            self.assertOK(response)
            self.assertEqual(response.json['code'], 'stream-started')
            stream_url: str = response.json['stream_url']
            assert stream_url.startswith('ws://')
            assert calls == [((None,), {})]
            refresh_event.set.assert_called()

    def test_refresh_socket(self):
        refresh_queue.put({'foo': 'bar'})
        request, ws = api_app.test_client.websocket('/api/videos/feeds/refresh')
        loop = asyncio.new_event_loop()
        assert json.loads(loop.run_until_complete(ws.recv())) == {'foo': 'bar'}
        assert json.loads(loop.run_until_complete(ws.recv())) == {'code': 'stream-complete'}

        request, ws = api_app.test_client.websocket('/api/videos/feeds/refresh')
        assert json.loads(loop.run_until_complete(ws.recv())) == {'code': 'no-messages'}

    def test_get_settings(self):
        request, response = api_app.test_client.get('/api/settings')
        self.assertOK(response)
