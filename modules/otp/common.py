import secrets
import subprocess
from functools import partial
from typing import Dict

from wrolpi.common import chunks, remove_whitespace, logger, temporary_directory_path
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


ONE_TIME_PAD_TEX = r'''
\documentclass{article}
\usepackage{hyperref}
\usepackage[margin=0.3in]{geometry}
\usepackage{mathptmx}

\title{One Time Pad}

\begin{document}

\begin{verbatim}
%s
\end{verbatim}

Print this page and distribute the copies (along with the \href{https://lrnsr.co/aY6m}{One Time Pad Cheat Sheet
https://lrnsr.co/aY6m}) to all members of your group that you trust to receive your encrypted messages.  Every person
must have their OWN copy of this “One Time Pad” to encrypt and decrypt messages.
\\

\textbf{Use each message ONLY ONCE}.  Cut off and burn each message from this paper as it is used.
\\

To learn how to use this page, please visit: \href{https://lrnsr.co/H7Za}{https://lrnsr.co/H7Za}

\end{document}
'''


def generate_pdf() -> bytes:
    """
    Create a PDF One Time Pad.
    """
    messages = '\n\n'.join(f'MESSAGE {i}\n{generate_message()}' for i in range(1, 8))
    with temporary_directory_path() as d:
        tex_path = d / 'otp.tex'
        tex_path.write_text(ONE_TIME_PAD_TEX % messages)
        cmd = ('pdflatex', tex_path)
        try:
            subprocess.check_output(cmd, cwd=d)
            # Output path is chosen by `pdflatex`.
            pdf_path = tex_path.with_suffix('.pdf')
            contents = pdf_path.read_bytes()
        except Exception as e:
            logger.fatal(f'Failed to generate One Time Pad PDF!', exc_info=e)
            raise
    # Files are cleaned up.
    assert not d.is_dir()
    return contents


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
