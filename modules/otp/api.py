from sanic import response
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.root_api import get_blueprint
from . import lib, schema

bp = get_blueprint('OTP', '/api/otp')


@bp.post('/encrypt_otp')
@openapi.definition(
    summary='Encrypt a message with OTP.',
    body=schema.EncryptOTPRequest,
)
@validate(schema.EncryptOTPRequest)
async def post_encrypt_otp(_: Request, body: schema.EncryptOTPRequest):
    data = lib.encrypt_otp(body.otp, body.plaintext)
    return response.json(data)


@bp.post('/decrypt_otp')
@openapi.definition(
    summary='Decrypt a message with OTP.',
    body=schema.DecryptOTPRequest,
)
@validate(schema.DecryptOTPRequest)
async def post_decrypt_otp(_: Request, body: schema.DecryptOTPRequest):
    data = lib.decrypt_otp(body.otp, body.ciphertext)
    return response.json(data)


@bp.get('/html')
async def get_new_otp_html(_: Request):
    body = lib.generate_html()
    return response.html(body)
