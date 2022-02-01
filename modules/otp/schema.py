from dataclasses import dataclass


@dataclass
class EncryptOTPRequest:
    otp: str
    plaintext: str


@dataclass
class DecryptOTPRequest:
    otp: str
    ciphertext: str
