from http import HTTPStatus

from wrolpi.errors import APIError


class InvalidOTP(APIError):
    code = 'INVALID_OTP'
    message = 'OTP has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidPlaintext(APIError):
    code = 'INVALID_PLAINTEXT'
    message = 'Plaintext has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidCiphertext(APIError):
    code = 'INVALID_CIPHERTEXT'
    message = 'Ciphertext has invalid characters'
    status_code = HTTPStatus.BAD_REQUEST
