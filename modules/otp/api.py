import random
from http import HTTPStatus
from string import ascii_letters

from sanic import response
from sanic.request import Request

from wrolpi.schema import validate_doc
from wrolpi.root_api import get_blueprint
from .common import generate_html, generate_pdf, encrypt_otp, decrypt_otp
from .schema import EncryptOTPRequest, DecryptOTPRequest

bp = get_blueprint('OTP', '/api/otp')


@bp.post(':encrypt_otp')
@validate_doc(
    summary='Encrypt a message with OTP',
    consumes=EncryptOTPRequest,
)
async def post_encrypt_otp(_: Request, data: dict):
    data = encrypt_otp(data['otp'], data['plaintext'])
    return response.json(data)


@bp.post(':decrypt_otp')
@validate_doc(
    summary='Decrypt a message with OTP',
    consumes=DecryptOTPRequest,
)
async def post_decrypt_otp(_: Request, data: dict):
    data = decrypt_otp(data['otp'], data['ciphertext'])
    return response.json(data)


@bp.get('/html')
async def get_new_otp(_: Request):
    return response.html(generate_html())


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
