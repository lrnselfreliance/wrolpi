import json
from http import HTTPStatus

import pytest
from sanic_openapi import swagger_blueprint

from api.api import api_app
from api.test.common import TestAPI


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
