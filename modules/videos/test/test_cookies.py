"""Tests for the encrypted cookies module."""
import os
import pathlib
import tempfile

import pytest

from modules.videos import cookies
from modules.videos.cookies import (
    encrypt_cookies,
    decrypt_cookies,
    validate_cookies_format,
    save_encrypted_cookies,
    delete_cookies,
    cookies_exist,
    unlock_cookies,
    lock_cookies,
    cookies_unlocked,
    cookies_for_download,
    get_cookies_status,
    get_cookies_file_path,
    MIN_PASSWORD_LENGTH,
)


# Sample valid Netscape format cookies
VALID_COOKIES_CONTENT = """# Netscape HTTP Cookie File
# This is a generated file! Do not edit.

.youtube.com\tTRUE\t/\tTRUE\t1735689600\tLOGIN_INFO\tABC123
.youtube.com\tTRUE\t/\tFALSE\t0\tSID\txyz789
.google.com\tTRUE\t/\tTRUE\t1735689600\tNID\tdef456
"""

VALID_COOKIES_SIMPLE = """.example.com\tTRUE\t/\tFALSE\t0\tsession_id\tabc123"""


class TestEncryptDecrypt:
    """Tests for basic encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Content can be encrypted and decrypted back to original."""
        password = 'testpassword123'
        content = VALID_COOKIES_CONTENT

        encrypted = encrypt_cookies(content, password)
        decrypted = decrypt_cookies(encrypted, password)

        assert decrypted == content

    def test_encrypt_produces_different_output_each_time(self):
        """Each encryption uses a unique salt, producing different ciphertext."""
        password = 'testpassword123'
        content = VALID_COOKIES_CONTENT

        encrypted1 = encrypt_cookies(content, password)
        encrypted2 = encrypt_cookies(content, password)

        assert encrypted1 != encrypted2

    def test_password_too_short(self):
        """Password must be at least MIN_PASSWORD_LENGTH characters."""
        short_password = 'a' * (MIN_PASSWORD_LENGTH - 1)
        content = VALID_COOKIES_CONTENT

        with pytest.raises(ValueError, match='at least'):
            encrypt_cookies(content, short_password)

    def test_wrong_password_fails(self):
        """Decryption with wrong password raises ValueError."""
        password = 'testpassword123'
        wrong_password = 'wrongpassword456'
        content = VALID_COOKIES_CONTENT

        encrypted = encrypt_cookies(content, password)

        with pytest.raises(ValueError, match='Invalid password'):
            decrypt_cookies(encrypted, wrong_password)

    def test_corrupted_data_fails(self):
        """Decryption of corrupted data raises ValueError."""
        password = 'testpassword123'

        # Random bytes that aren't valid encrypted data
        corrupted = os.urandom(100)

        with pytest.raises(ValueError):
            decrypt_cookies(corrupted, password)

    def test_truncated_data_fails(self):
        """Decryption of truncated data raises ValueError."""
        password = 'testpassword123'

        # Data too short to contain salt
        truncated = b'short'

        with pytest.raises(ValueError, match='too short'):
            decrypt_cookies(truncated, password)


class TestValidateCookiesFormat:
    """Tests for cookies format validation."""

    def test_valid_netscape_format(self):
        """Valid Netscape format cookies pass validation."""
        is_valid, error = validate_cookies_format(VALID_COOKIES_CONTENT)
        assert is_valid is True
        assert error is None

    def test_valid_simple_format(self):
        """Simple single-line cookies pass validation."""
        is_valid, error = validate_cookies_format(VALID_COOKIES_SIMPLE)
        assert is_valid is True
        assert error is None

    def test_empty_content_fails(self):
        """Empty content fails validation."""
        is_valid, error = validate_cookies_format('')
        assert is_valid is False
        assert 'empty' in error.lower()

    def test_whitespace_only_fails(self):
        """Whitespace-only content fails validation."""
        is_valid, error = validate_cookies_format('   \n\t  \n  ')
        assert is_valid is False
        assert 'empty' in error.lower()

    def test_comments_only_fails(self):
        """Content with only comments fails validation."""
        content = """# This is a comment
# Another comment
# Netscape HTTP Cookie File
"""
        is_valid, error = validate_cookies_format(content)
        assert is_valid is False
        assert 'No valid cookie lines' in error

    def test_invalid_format_fails(self):
        """Content without proper tab-separated format fails."""
        content = """This is not a valid cookies file
Just some random text
"""
        is_valid, error = validate_cookies_format(content)
        assert is_valid is False


class TestSaveAndDelete:
    """Tests for saving and deleting encrypted cookies."""

    def test_save_and_exists(self, test_directory):
        """Saving cookies creates the encrypted file."""
        password = 'testpassword123'

        # Initially no cookies exist
        assert not cookies_exist()

        # Save cookies
        path = save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        assert cookies_exist()
        assert path.is_file()
        assert path.name == 'cookies.txt.enc'

    def test_save_sets_restrictive_permissions(self, test_directory):
        """Saved cookies file has restrictive permissions (owner only)."""
        password = 'testpassword123'

        path = save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        # Check file permissions (should be 0o600 - owner read/write only)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_save_invalid_format_fails(self, test_directory):
        """Saving invalid cookies format raises ValueError."""
        password = 'testpassword123'
        invalid_content = 'not valid cookies format'

        with pytest.raises(ValueError):
            save_encrypted_cookies(invalid_content, password)

    def test_delete_removes_file(self, test_directory):
        """Delete removes the encrypted cookies file."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        assert cookies_exist()

        result = delete_cookies()

        assert result is True
        assert not cookies_exist()

    def test_delete_nonexistent_returns_false(self, test_directory):
        """Delete returns False when no file exists."""
        assert not cookies_exist()

        result = delete_cookies()

        assert result is False

    def test_delete_clears_session(self, test_directory):
        """Deleting cookies also clears the session."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        # save_encrypted_cookies auto-unlocks, but call unlock_cookies for clarity
        unlock_cookies(password)

        assert cookies_unlocked()

        delete_cookies()

        assert not cookies_unlocked()

    def test_save_auto_unlocks(self, test_directory):
        """Saving cookies automatically unlocks them (user just provided password)."""
        password = 'testpassword123'

        assert not cookies_unlocked()

        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        # Cookies should be auto-unlocked after save
        assert cookies_unlocked()


class TestUnlockLock:
    """Tests for session unlock/lock functionality."""

    def test_unlock_success(self, test_directory):
        """Unlock decrypts cookies to memory."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        # save_encrypted_cookies auto-unlocks, so lock first to test unlock
        lock_cookies()
        assert not cookies_unlocked()

        unlock_cookies(password)

        assert cookies_unlocked()

    def test_unlock_no_file_fails(self, test_directory):
        """Unlock fails when no encrypted file exists."""
        with pytest.raises(FileNotFoundError):
            unlock_cookies('anypassword1')

    def test_unlock_wrong_password_fails(self, test_directory):
        """Unlock with wrong password raises ValueError."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        with pytest.raises(ValueError, match='Invalid password'):
            unlock_cookies('wrongpassword')

    def test_lock_clears_memory(self, test_directory):
        """Lock clears decrypted cookies from memory."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        assert cookies_unlocked()

        lock_cookies()

        assert not cookies_unlocked()

    def test_lock_idempotent(self, test_directory):
        """Lock can be called multiple times without error."""
        lock_cookies()
        lock_cookies()
        lock_cookies()

        assert not cookies_unlocked()


class TestCookiesForDownload:
    """Tests for the per-download temp file context manager."""

    def test_provides_temp_file(self, test_directory):
        """Context manager provides a readable temp file."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        with cookies_for_download() as cookies_path:
            assert cookies_path.is_file()
            content = cookies_path.read_text()
            assert content == VALID_COOKIES_CONTENT

    def test_temp_file_deleted_after(self, test_directory):
        """Temp file is deleted after context manager exits."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        with cookies_for_download() as cookies_path:
            temp_path = cookies_path  # Save reference

        assert not temp_path.exists()

    def test_temp_file_deleted_on_exception(self, test_directory):
        """Temp file is deleted even if exception occurs."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        temp_path = None
        try:
            with cookies_for_download() as cookies_path:
                temp_path = cookies_path
                raise RuntimeError('Test exception')
        except RuntimeError:
            pass

        assert temp_path is not None
        assert not temp_path.exists()

    def test_fails_when_not_unlocked(self, test_directory):
        """Raises RuntimeError when cookies not unlocked."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        # save_encrypted_cookies auto-unlocks, so lock first
        lock_cookies()

        with pytest.raises(RuntimeError, match='not unlocked'):
            with cookies_for_download():
                pass

    def test_unique_files_for_concurrent_downloads(self, test_directory):
        """Each call creates a unique temp file."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        paths = []

        # Start multiple contexts
        with cookies_for_download() as path1:
            paths.append(str(path1))
            with cookies_for_download() as path2:
                paths.append(str(path2))
                with cookies_for_download() as path3:
                    paths.append(str(path3))

        # All paths should be unique
        assert len(paths) == len(set(paths))

    def test_temp_file_has_restrictive_permissions(self, test_directory):
        """Temp file has restrictive permissions."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        with cookies_for_download() as cookies_path:
            mode = cookies_path.stat().st_mode & 0o777
            assert mode == 0o600


class TestGetCookiesStatus:
    """Tests for status reporting."""

    def test_status_no_cookies(self, test_directory):
        """Status shows no cookies when file doesn't exist."""
        status = get_cookies_status()

        assert status['cookies_exist'] is False
        assert status['cookies_unlocked'] is False

    def test_status_locked(self, test_directory):
        """Status shows locked when cookies exist but not unlocked."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)

        # save_encrypted_cookies auto-unlocks, so lock first
        lock_cookies()

        status = get_cookies_status()

        assert status['cookies_exist'] is True
        assert status['cookies_unlocked'] is False

    def test_status_unlocked(self, test_directory):
        """Status shows unlocked when cookies are in memory."""
        password = 'testpassword123'
        save_encrypted_cookies(VALID_COOKIES_CONTENT, password)
        unlock_cookies(password)

        status = get_cookies_status()

        assert status['cookies_exist'] is True
        assert status['cookies_unlocked'] is True


# Fixture to reset module state between tests
@pytest.fixture(autouse=True)
def reset_cookies_state():
    """Reset cookies module state before and after each test."""
    lock_cookies()
    yield
    lock_cookies()
