from sanic_openapi import doc


class EncryptOTPRequest:
    otp = doc.String(required=True)
    plaintext = doc.String(required=True)


class DecryptOTPRequest:
    otp = doc.String(required=True)
    ciphertext = doc.String(required=True)
