import random
from http import HTTPStatus
from string import ascii_letters

from sanic import response
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.root_api import get_blueprint
from .common import generate_pdf, encrypt_otp, decrypt_otp
from .schema import EncryptOTPRequest, DecryptOTPRequest

bp = get_blueprint('OTP', '/api/otp')


@bp.post('/encrypt_otp')
@openapi.definition(
    summary='Encrypt a message with OTP.',
    body=EncryptOTPRequest,
)
@validate(EncryptOTPRequest)
async def post_encrypt_otp(_: Request, data: dict):
    data = encrypt_otp(data['otp'], data['plaintext'])
    return response.json(data)


@bp.post('/decrypt_otp')
@openapi.definition(
    summary='Decrypt a message with OTP.',
    body=DecryptOTPRequest,
)
@validate(DecryptOTPRequest)
async def post_decrypt_otp(_: Request, data: dict):
    data = decrypt_otp(data['otp'], data['ciphertext'])
    return response.json(data)


@bp.get('/pdf')
async def get_new_otp_pdf(_: Request):
    random_name = ''.join(random.choice(ascii_letters) for _ in range(8))
    filename = f'one-time-pad-{random_name}.pdf'
    headers = {
        'Content-type': 'application/pdf',
        'Content-Disposition': f'attachment;filename={filename}'
    }
    contents = generate_pdf()
    return response.raw(contents, HTTPStatus.OK, headers)
