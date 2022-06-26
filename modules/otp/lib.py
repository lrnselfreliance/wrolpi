import secrets
from functools import partial
from typing import Dict

from wrolpi.common import chunks, remove_whitespace, logger
from wrolpi.errors import InvalidOTP, InvalidPlaintext, InvalidCiphertext

# These are the only characters we support.

logger = logger.getChild(__name__)

OTP_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
# The number of characters in each group, separated by spaces.
GROUP_SIZE = 5
# The groups in each row of a message, separated by newlines.  This is small to allow for mobile phones.
GROUP_COUNT = 5


def format_message(message: str, group_count: int = GROUP_COUNT) -> str:
    """
    Formats messages in the style of a One-Time-Pad.  Usually 5 characters per group.

    >>> format_message('SOMEMESSAGE')
    'SOMEM ESSAG E'
    """
    groups = [''.join(i) for i in chunks(message, GROUP_SIZE)]
    rows = chunks(groups, group_count)
    message = '\n'.join(' '.join(group for group in groups) for groups in rows)
    return message


generate_char = partial(secrets.choice, OTP_CHARS)


def generate_message():
    """
    Create a OTP message.  Format it for ease of use.
    """
    # Use 20 messages per line because this page will be printed.
    return format_message(''.join(generate_char() for _ in range(400)), 16)


PAGE_HTML = '''
<html>
<title>One Time Pad - Unique, just for you</title>
<style>
/* Remove decoration from links so they are readable when printed */
a {{ text-decoration: none; }}  // escaped for python
</style>
<body>
{messages}


Print this page and distribute the copies (along with the <a href="https://lrnsr.co/aY6m">One Time Pad Cheat Sheet
https://lrnsr.co/aY6m</a>) to all members of your group that you trust to receive your encrypted messages.  Every
person must have their OWN copy of this "One Time Pad" to encrypt and decrypt messages.
<br>
<b>Use each message ONLY ONCE.</b>  Cut off and burn each message from this paper as it is used.
<br>
If you want more One Time Pads, simply <a href=".">go here to refresh the page:
https://learningselfreliance.com/one_time_pad</a>.  The server will generate a unique page just for you. This page
is not stored on the server, and cannot be retrieved once you close this window!
<br>
To learn how to use this page, please visit: <a href="https://lrnsr.co/H7Za">https://lrnsr.co/H7Za</a>
</body>
</html>
'''


def generate_html() -> str:
    """
    Create an HTML One-Time Pad page.   This page will have instructions on how to use the OTP.
    """
    messages = [generate_message() for _ in range(9)]
    messages = '\n\n'.join(f'<pre>MESSAGE {i}</pre><pre>{j}</pre>' for i, j in enumerate(messages, 1))
    return PAGE_HTML.format(messages=messages)


def validate_message(otp, error_class):
    otp = otp.upper()
    otp = remove_whitespace(otp)

    if not all(i in OTP_CHARS for i in otp):
        raise error_class()

    return otp


CHARS_LEN = len(OTP_CHARS)


def encrypt_char(plaintext: str, otp: str) -> str:
    calculated = (OTP_CHARS.index(plaintext) + OTP_CHARS.index(otp)) % CHARS_LEN
    return OTP_CHARS[calculated]


def decrypt_char(ciphertext: str, otp: str) -> str:
    calculated = (OTP_CHARS.index(ciphertext) - OTP_CHARS.index(otp)) % CHARS_LEN
    return OTP_CHARS[calculated]


def encrypt_otp(otp: str, plaintext: str) -> Dict[str, str]:
    """
    Encrypt a plaintext message using an OTP.
    """
    otp = validate_message(otp, InvalidOTP)
    plaintext = validate_message(plaintext, InvalidPlaintext)

    if len(plaintext) > len(otp):
        raise InvalidPlaintext('Plaintext is longer than OTP')

    ciphertext = ''.join(encrypt_char(p, o) for p, o in zip(plaintext, otp))

    data = dict(
        ciphertext=format_message(ciphertext),
        otp=format_message(otp),
        plaintext=format_message(plaintext),
    )

    return data


def decrypt_otp(otp: str, ciphertext: str) -> Dict[str, str]:
    """
    Decrypt an encrypted message that was encrypted with an OTP.
    """
    otp = validate_message(otp, InvalidOTP)
    ciphertext = validate_message(ciphertext, InvalidCiphertext)

    if len(ciphertext) > len(otp):
        raise InvalidCiphertext('Ciphertext is longer than OTP')

    plaintext = ''.join(decrypt_char(c, o) for c, o in zip(ciphertext, otp))
    data = dict(
        plaintext=format_message(plaintext),
        ciphertext=format_message(ciphertext),
        otp=format_message(otp),
    )
    return data
