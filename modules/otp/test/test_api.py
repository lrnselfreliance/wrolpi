import json
from http import HTTPStatus

import pytest


@pytest.mark.asyncio
async def test_encrypt(async_client):
    body = dict(otp='asdf', plaintext='asdf')
    request, response = await async_client.post('/api/otp/encrypt_otp', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(
        ciphertext='AAGK',
        otp='ASDF',
        plaintext='ASDF',
    )


@pytest.mark.asyncio
async def test_decrypt(async_client):
    body = dict(otp='asdf', ciphertext='aagk')
    request, response = await async_client.post('/api/otp/decrypt_otp', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(
        ciphertext='AAGK',
        otp='ASDF',
        plaintext='ASDF',
    )


@pytest.mark.asyncio
async def test_get_html(async_client):
    request, response = await async_client.get('/api/otp/html')
    assert response.status_code == HTTPStatus.OK
