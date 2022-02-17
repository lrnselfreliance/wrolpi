import json
from http import HTTPStatus


def test_encrypt(test_client):
    body = dict(otp='asdf', plaintext='asdf')
    request, response = test_client.post('/api/otp/encrypt_otp', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(
        ciphertext='AAGK',
        otp='ASDF',
        plaintext='ASDF',
    )


def test_decrypt(test_client):
    body = dict(otp='asdf', ciphertext='aagk')
    request, response = test_client.post('/api/otp/decrypt_otp', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(
        ciphertext='AAGK',
        otp='ASDF',
        plaintext='ASDF',
    )


def test_get_pdf(test_client):
    request, response = test_client.get('/api/otp/pdf')
    assert response.status_code == HTTPStatus.OK
