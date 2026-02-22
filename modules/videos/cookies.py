"""
Encrypted cookies management for yt-dlp video downloads.

This module provides secure storage and retrieval of browser cookies for use with yt-dlp.
Cookies are encrypted using Fernet (AES-128-CBC + HMAC-SHA256) with PBKDF2 key derivation.

Security features:
- Encryption: Fernet (AES-128-CBC + HMAC-SHA256)
- Key derivation: PBKDF2-SHA256 with 480k iterations (OWASP 2024 minimum)
- Password handling: Decrypt once to memory, forget password immediately
- In-memory storage: Decrypted cookies in shared memory across workers
- Per-download temp files: Unique file per download, deleted immediately after
- Temp file permissions: chmod 600 (owner only)
- Secure deletion: Overwrite temp file with zeros before unlinking
"""
import base64
import os
import pathlib
import secrets
import tempfile
from contextlib import contextmanager
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from wrolpi import flags
from wrolpi.common import get_media_directory, logger

logger = logger.getChild(__name__)

# OWASP 2024 minimum iterations for PBKDF2-SHA256
PBKDF2_ITERATIONS = 480_000
SALT_SIZE = 16
MIN_PASSWORD_LENGTH = 8

# Encrypted cookies file path relative to config directory
COOKIES_FILENAME = 'cookies.txt.enc'

def _get_shared_cookies() -> Optional[bytes]:
    """Get cookies from shared context."""
    from wrolpi.root_api import api_app
    return api_app.shared_ctx.secure_cookies.get('content')


def _set_shared_cookies(content: bytes) -> None:
    """Store cookies in shared context for cross-worker access."""
    from wrolpi.root_api import api_app
    with api_app.shared_ctx.secure_cookies_lock:
        api_app.shared_ctx.secure_cookies['content'] = content


def _clear_shared_cookies() -> None:
    """Clear cookies from shared context."""
    from wrolpi.root_api import api_app
    with api_app.shared_ctx.secure_cookies_lock:
        api_app.shared_ctx.secure_cookies.clear()


def get_cookies_file_path() -> pathlib.Path:
    """Get the path to the encrypted cookies file."""
    config_dir = get_media_directory() / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / COOKIES_FILENAME


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
    return key


def encrypt_cookies(content: str, password: str) -> bytes:
    """
    Encrypt cookies content with password.

    Args:
        content: The plain text cookies content (Netscape format)
        password: User-provided password (min 8 chars)

    Returns:
        Encrypted bytes: [16 bytes salt][Fernet encrypted content]

    Raises:
        ValueError: If password is too short
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')

    # Generate random salt
    salt = secrets.token_bytes(SALT_SIZE)

    # Derive key from password
    key = _derive_key(password, salt)

    # Encrypt content
    fernet = Fernet(key)
    encrypted = fernet.encrypt(content.encode('utf-8'))

    # Prepend salt to encrypted content
    return salt + encrypted


def decrypt_cookies(encrypted: bytes, password: str) -> str:
    """
    Decrypt cookies content with password.

    Args:
        encrypted: Encrypted bytes from encrypt_cookies()
        password: User-provided password

    Returns:
        Decrypted cookies content string

    Raises:
        ValueError: If data is corrupted or password is wrong
    """
    if len(encrypted) < SALT_SIZE:
        raise ValueError('Encrypted data is too short')

    # Extract salt and encrypted content
    salt = encrypted[:SALT_SIZE]
    ciphertext = encrypted[SALT_SIZE:]

    # Derive key from password
    key = _derive_key(password, salt)

    # Decrypt content
    fernet = Fernet(key)
    try:
        decrypted = fernet.decrypt(ciphertext)
        return decrypted.decode('utf-8')
    except InvalidToken:
        raise ValueError('Invalid password or corrupted data')


def validate_cookies_format(content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that the content appears to be valid Netscape cookies format.

    Args:
        content: The cookies content to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not content or not content.strip():
        return False, 'Cookies content is empty'

    lines = content.strip().split('\n')
    valid_cookie_lines = 0

    for line in lines:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip comments (lines starting with #)
        if line.startswith('#'):
            continue

        # Each cookie line should have at least 7 tab-separated fields:
        # domain, flag, path, secure, expiration, name, value
        fields = line.split('\t')
        if len(fields) >= 7:
            valid_cookie_lines += 1
        else:
            # Allow some flexibility - some formats use fewer fields
            # But should have at least domain and name
            if len(fields) < 2:
                return False, f'Invalid cookie line format: {line[:50]}...'

    if valid_cookie_lines == 0:
        return False, 'No valid cookie lines found. Expected Netscape/Mozilla cookies.txt format.'

    return True, None


def save_encrypted_cookies(content: str, password: str) -> pathlib.Path:
    """
    Validate, encrypt, and save cookies to the config directory.

    Auto-unlocks cookies after saving (user just provided password).

    Args:
        content: Plain text cookies content
        password: User-provided password

    Returns:
        Path to the saved encrypted file

    Raises:
        ValueError: If cookies format is invalid or password is too short
    """
    # Validate format
    is_valid, error = validate_cookies_format(content)
    if not is_valid:
        raise ValueError(error)

    # Encrypt
    encrypted = encrypt_cookies(content, password)

    # Save to file
    cookies_path = get_cookies_file_path()
    cookies_path.write_bytes(encrypted)

    # Set restrictive permissions (owner only)
    os.chmod(cookies_path, 0o600)

    # Set flags and auto-unlock (user just provided the password)
    flags.cookies_exist.set()
    _set_shared_cookies(content.encode('utf-8'))
    flags.cookies_unlocked.set()

    logger.info(f'Saved encrypted cookies to {cookies_path}')
    return cookies_path


def cookies_exist() -> bool:
    """Check if encrypted cookies file exists."""
    return get_cookies_file_path().is_file()


def delete_cookies() -> bool:
    """
    Securely delete the encrypted cookies file.

    Returns:
        True if file was deleted, False if it didn't exist
    """
    cookies_path = get_cookies_file_path()
    if not cookies_path.is_file():
        return False

    # Overwrite with zeros before deletion
    size = cookies_path.stat().st_size
    cookies_path.write_bytes(b'\x00' * size)
    cookies_path.unlink()

    # Clear flags
    flags.cookies_exist.clear()
    flags.cookies_unlocked.clear()

    # Also clear session if unlocked
    lock_cookies()

    logger.info('Deleted encrypted cookies file')
    return True


def unlock_cookies(password: str) -> None:
    """
    Decrypt cookies to memory for session use.

    The password is NOT stored - it goes out of scope after this function returns.

    Args:
        password: User-provided password

    Raises:
        FileNotFoundError: If no encrypted cookies file exists
        ValueError: If password is wrong or data is corrupted
    """
    cookies_path = get_cookies_file_path()
    if not cookies_path.is_file():
        raise FileNotFoundError('No encrypted cookies file found')

    encrypted = cookies_path.read_bytes()
    decrypted = decrypt_cookies(encrypted, password)

    # Store in shared context for cross-worker access
    _set_shared_cookies(decrypted.encode('utf-8'))
    flags.cookies_unlocked.set()
    logger.info('Cookies unlocked to shared memory')


def lock_cookies() -> None:
    """Clear cookies from shared memory."""
    _clear_shared_cookies()
    flags.cookies_unlocked.clear()
    logger.info('Cookies locked')


def cookies_unlocked() -> bool:
    """Check if cookies are decrypted in shared memory."""
    shared_content = _get_shared_cookies()
    return shared_content is not None and len(shared_content) > 0


def _get_secure_temp_dir() -> Optional[str]:
    """
    Get the most secure temporary directory available.

    Prefers /dev/shm (RAM-based) over /tmp (disk-based) to prevent
    decrypted cookies from ever touching persistent storage.

    Returns:
        Path to /dev/shm if available and writable, None otherwise
        (None causes tempfile to use system default).
    """
    shm_path = pathlib.Path('/dev/shm')
    if shm_path.is_dir() and os.access(shm_path, os.W_OK):
        return str(shm_path)
    # Fall back to system default (typically /tmp)
    return None


@contextmanager
def cookies_for_download():
    """
    Context manager providing a unique temp file for one download.

    Writes shared cookies to a unique temp file, yields the path for yt-dlp,
    then securely deletes the temp file.

    Uses /dev/shm (RAM-based tmpfs) when available to prevent cookies from
    ever touching persistent storage. Falls back to system temp directory.

    Usage:
        with cookies_for_download() as cookies_path:
            cmd = (*cmd, '--cookies', str(cookies_path))
            await run_download(cmd)
        # Temp file is securely deleted here

    Yields:
        pathlib.Path: Path to temporary cookies file

    Raises:
        RuntimeError: If cookies are not unlocked
    """
    if not cookies_unlocked():
        raise RuntimeError('Cookies not unlocked')

    # Get cookies from shared context
    cookies_content = _get_shared_cookies()

    # Create unique temp file, prefer /dev/shm (RAM) over /tmp (disk)
    # Use opaque prefix to avoid revealing file purpose
    fd, temp_path = tempfile.mkstemp(
        suffix='.tmp',
        prefix='w_',
        dir=_get_secure_temp_dir()
    )
    temp_file = pathlib.Path(temp_path)
    logger.trace(f'Created temp cookies file at {temp_path}')

    try:
        # Set restrictive permissions
        os.chmod(temp_path, 0o600)

        # Write cookies content
        with os.fdopen(fd, 'w') as f:
            f.write(cookies_content.decode('utf-8'))

        yield temp_file
    finally:
        # Securely delete temp file
        if temp_file.exists():
            try:
                size = temp_file.stat().st_size
                temp_file.write_bytes(b'\x00' * size)
                temp_file.unlink()
            except Exception as e:
                logger.warning(f'Failed to securely delete temp cookies file: {e}')
                # Try to delete anyway
                try:
                    temp_file.unlink()
                except Exception:
                    pass


def get_cookies_status() -> dict:
    """
    Get the current status of cookies.

    Returns:
        Dict with keys:
            - cookies_exist: bool - Whether encrypted file exists
            - cookies_unlocked: bool - Whether cookies are decrypted in memory
    """
    return {
        'cookies_exist': cookies_exist(),
        'cookies_unlocked': cookies_unlocked(),
    }
