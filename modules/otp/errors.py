from http import HTTPStatus

from wrolpi.errors import APIError


class InvalidOTP(APIError):
    code = 'INVALID_OTP'
    summary = 'OTP has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidPlaintext(APIError):
    code = 'INVALID_PLAINTEXT'
    summary = 'Plaintext has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidCiphertext(APIError):
    code = 'INVALID_CIPHERTEXT'
    summary = 'Ciphertext has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST
