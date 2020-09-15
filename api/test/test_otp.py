import pytest

from api.otp import encrypt_otp, decrypt_otp, format_message


@pytest.mark.parametrize(
    'otp,plaintext,ciphertext',
    [
        ('', '', ''),
        ('A', 'A', 'A'),
        ('B', 'B', 'C'),
        ('9', '9', '8'),
        ('W', 'H', '3'),
        ('W', 'H', '3'),
        ('W8JD7', 'HELLO', '3CUOL'),
        ('XMCKL', 'HELLO', '4QNVZ'),
        (
                # This message says: TEST THE ENCRYPTION OF A LONG MESSAGE THE SPACES SHOULDNT MATTER
                # The message is shorter than the OTP, this is fine.  The ciphertext should be the same
                # length as the message.
                'V4YPT RCJLZ QZVSD 0U2E6 OOKNU\nZDH8F 4XQ76 OR6EK J0TRG 0G0HU\nS4BUJ',
                'TESTT HEENC RYPTI ONOFA LONGM\nESSAG ETHES PACES SHOUL DNTMA\nTTER',
                'E8G8C YGNY1 7NABL E7GJ6 Z2XT6\n3VZ8L 8GXBO 3R8I2 177BR 3TJTU\nBNFB'
        ),
    ],
)
def test_encrypt_otp(otp, plaintext, ciphertext):
    result = encrypt_otp(otp, plaintext)
    expected = dict(
        otp=otp,
        plaintext=plaintext,
        ciphertext=ciphertext,
    )
    assert result == expected

    # Whitespace is ignored
    plaintext = f'\t   {plaintext}'
    otp = f'\n {otp} '
    result = encrypt_otp(otp, plaintext)
    expected = dict(
        otp=otp.strip(),
        plaintext=plaintext.strip(),
        ciphertext=ciphertext,
    )
    assert result == expected


@pytest.mark.parametrize(
    'otp,ciphertext,plaintext',
    [
        ('', '', ''),
        ('A', 'A', 'A'),
        ('B', 'C', 'B'),
        ('W', '3', 'H'),
        ('9', '8', '9'),
        ('W8JD7', '3CUOL', 'HELLO'),
        ('XMCKL', '4QNVZ', 'HELLO'),
        (
                'V4YPT RCJLZ QZVSD 0U2E6 OOKNU\nZDH8F 4XQ76 OR6EK J0TRG 0G0HU\nS4BUJ',
                'E8G8C YGNY1 7NABL E7GJ6 Z2XT6\n3VZ8L 8GXBO 3R8I2 177BR 3TJTU\nBNFB',
                'TESTT HEENC RYPTI ONOFA LONGM\nESSAG ETHES PACES SHOUL DNTMA\nTTER',
        ),
    ],
)
def test_decrypt_otp(otp, ciphertext, plaintext):
    result = decrypt_otp(otp, ciphertext)
    expected = dict(
        otp=otp,
        plaintext=plaintext,
        ciphertext=ciphertext,
    )
    assert result == expected


@pytest.mark.parametrize(
    'message,expected',
    [
        ('ABC', 'ABC'),
        ('ABCDEFG', 'ABCDE FG'),
        ('SOMEMESSAGE', 'SOMEM ESSAG E'),
        (
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890',
                'ABCDE FGHIJ KLMNO PQRST UVWXY\nZ0123 45678 90',
        ),
    ]
)
def test_format_message(message, expected):
    result = format_message(message)
    assert result == expected
