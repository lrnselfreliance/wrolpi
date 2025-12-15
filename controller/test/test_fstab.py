"""
Unit tests for controller.lib.fstab module.
"""

from unittest import mock

from controller.lib.fstab import (
    parse_fstab,
    add_fstab_entry,
    remove_fstab_entry,
    get_wrolpi_fstab_entries,
)


class TestParseFstab:
    """Tests for parse_fstab function."""

    def test_parses_mount_entries(self):
        """Should parse mount entries from fstab."""
        fstab_content = """\
# /etc/fstab
UUID=1234-5678 / ext4 defaults 0 1
UUID=abcd-efgh /media/wrolpi ext4 defaults,nofail 0 2
"""
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = parse_fstab()
            mounts = [e for e in result if e["type"] == "mount"]
            assert len(mounts) == 2
            assert mounts[0]["device"] == "UUID=1234-5678"
            assert mounts[0]["mount_point"] == "/"
            assert mounts[1]["mount_point"] == "/media/wrolpi"

    def test_preserves_comments(self):
        """Should preserve comments and blank lines."""
        fstab_content = """\
# This is a comment

UUID=1234 / ext4 defaults 0 1
"""
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = parse_fstab()
            comments = [e for e in result if e["type"] == "comment"]
            assert len(comments) == 2

    def test_handles_minimal_entries(self):
        """Should handle entries with minimal fields."""
        fstab_content = "UUID=1234 /media/data ext4 defaults\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = parse_fstab()
            mount = [e for e in result if e["type"] == "mount"][0]
            assert mount["dump"] == "0"
            assert mount["pass"] == "0"


class TestAddFstabEntry:
    """Tests for add_fstab_entry function."""

    def test_blocked_in_wrol_mode(self):
        """Should be blocked in WROL mode."""
        with mock.patch("controller.lib.fstab.require_normal_mode", side_effect=PermissionError("WROL")):
            result = add_fstab_entry("/dev/sda1", "/media/test", "ext4")
            assert result["success"] is False
            assert "WROL" in result["error"]

    def test_validates_mount_point(self):
        """Should validate mount point."""
        with mock.patch("controller.lib.fstab.require_normal_mode"):
            result = add_fstab_entry("/dev/sda1", "/mnt/test", "ext4")
            assert result["success"] is False
            assert "must be under /media" in result["error"]

    def test_converts_device_to_uuid(self):
        """Should convert device path to UUID."""
        fstab_content = "# empty\n"
        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.get_uuid", return_value="1234-5678"):
                with mock.patch("controller.lib.fstab.backup_fstab"):
                    with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
                        with mock.patch("subprocess.run"):
                            result = add_fstab_entry("/dev/sda1", "/media/test", "ext4")
                            assert result["success"] is True
                            assert result["device"] == "UUID=1234-5678"

    def test_adds_entry_to_fstab(self):
        """Should add entry to fstab."""
        fstab_content = "# existing\n"
        written_content = []

        def mock_write(content):
            written_content.append(content)

        mock_file = mock.mock_open(read_data=fstab_content)
        mock_file().write = mock_write

        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.get_uuid", return_value=None):
                with mock.patch("controller.lib.fstab.backup_fstab"):
                    with mock.patch("builtins.open", mock_file):
                        with mock.patch("subprocess.run"):
                            result = add_fstab_entry("/dev/sda1", "/media/test", "ext4")
                            assert result["success"] is True
                            # Check that something was written
                            assert len(written_content) > 0

    def test_replaces_entry_without_duplicating_comments(self):
        """Should remove old WROLPi comment when replacing an entry."""
        fstab_content = """\
# /etc/fstab
UUID=1234 / ext4 defaults 0 1
# WROLPi managed mount - added 2025-12-15T15:57:37.675757
UUID=5678 /media/test ext4 defaults,nofail 0 2
"""
        written_content = []

        def mock_write(content):
            written_content.append(content)

        mock_file = mock.mock_open(read_data=fstab_content)
        mock_file().write = mock_write

        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.get_uuid", return_value="5678"):
                with mock.patch("controller.lib.fstab.backup_fstab"):
                    with mock.patch("builtins.open", mock_file):
                        with mock.patch("subprocess.run"):
                            result = add_fstab_entry("/dev/sda1", "/media/test", "ext4")
                            assert result["success"] is True
                            written_str = "".join(written_content)
                            # Should have exactly ONE WROLPi comment (the new one)
                            assert written_str.count("WROLPi managed mount") == 1
                            # The old timestamp should NOT be there
                            assert "2025-12-15T15:57:37.675757" not in written_str


class TestRemoveFstabEntry:
    """Tests for remove_fstab_entry function."""

    def test_blocked_in_wrol_mode(self):
        """Should be blocked in WROL mode."""
        with mock.patch("controller.lib.fstab.require_normal_mode", side_effect=PermissionError("WROL")):
            result = remove_fstab_entry("/media/test")
            assert result["success"] is False

    def test_validates_mount_point(self):
        """Should validate mount point."""
        with mock.patch("controller.lib.fstab.require_normal_mode"):
            result = remove_fstab_entry("/mnt/test")
            assert result["success"] is False

    def test_returns_error_if_not_found(self):
        """Should return error if entry not found."""
        fstab_content = "UUID=1234 / ext4 defaults 0 1\n"
        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.backup_fstab"):
                with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
                    result = remove_fstab_entry("/media/nonexistent")
                    assert result["success"] is False
                    assert "No entry found" in result["error"]

    def test_removes_wrolpi_comment_with_entry(self):
        """Should remove WROLPi comment when removing its associated entry."""
        fstab_content = """\
# /etc/fstab
UUID=1234 / ext4 defaults 0 1
# WROLPi managed mount - added 2025-12-15T15:57:37.675757
UUID=5678 /media/test ext4 defaults,nofail 0 2
"""
        written_content = []

        def mock_write(content):
            written_content.append(content)

        mock_file = mock.mock_open(read_data=fstab_content)
        mock_file().write = mock_write

        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.backup_fstab"):
                with mock.patch("builtins.open", mock_file):
                    with mock.patch("subprocess.run"):
                        result = remove_fstab_entry("/media/test")
                        assert result["success"] is True
                        # WROLPi comment should NOT be in written content
                        written_str = "".join(written_content)
                        assert "WROLPi managed mount" not in written_str
                        # Regular comment should still be there
                        assert "# /etc/fstab" in written_str

    def test_preserves_non_wrolpi_comments(self):
        """Should preserve comments that are not WROLPi managed mount comments."""
        fstab_content = """\
# /etc/fstab
UUID=1234 / ext4 defaults 0 1
# User added this mount manually
UUID=5678 /media/test ext4 defaults,nofail 0 2
"""
        written_content = []

        def mock_write(content):
            written_content.append(content)

        mock_file = mock.mock_open(read_data=fstab_content)
        mock_file().write = mock_write

        with mock.patch("controller.lib.fstab.require_normal_mode"):
            with mock.patch("controller.lib.fstab.backup_fstab"):
                with mock.patch("builtins.open", mock_file):
                    with mock.patch("subprocess.run"):
                        result = remove_fstab_entry("/media/test")
                        assert result["success"] is True
                        # User's manual comment should still be there
                        written_str = "".join(written_content)
                        assert "# User added this mount manually" in written_str


class TestGetWrolpiFstabEntries:
    """Tests for get_wrolpi_fstab_entries function."""

    def test_returns_all_media_entries(self):
        """Should return all entries under /media, not just /media/wrolpi."""
        fstab_content = """\
UUID=1234 / ext4 defaults 0 1
UUID=5678 /media/wrolpi ext4 defaults 0 2
UUID=9abc /media/wrolpi/data ext4 defaults 0 2
UUID=defg /media/usb vfat defaults 0 0
UUID=hijk /media/roland/64GB exfat defaults 0 0
"""
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = get_wrolpi_fstab_entries()
            # Should include all /media/* entries
            assert len(result) == 4
            mount_points = [e["mount_point"] for e in result]
            assert "/media/wrolpi" in mount_points
            assert "/media/wrolpi/data" in mount_points
            assert "/media/usb" in mount_points
            assert "/media/roland/64GB" in mount_points
            # Root should NOT be included
            assert "/" not in mount_points

    def test_excludes_non_media_mounts(self):
        """Should exclude mounts outside /media."""
        fstab_content = """\
UUID=1234 / ext4 defaults 0 1
UUID=5678 /home ext4 defaults 0 2
UUID=9abc /media/wrolpi ext4 defaults 0 2
"""
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = get_wrolpi_fstab_entries()
            assert len(result) == 1
            assert result[0]["mount_point"] == "/media/wrolpi"

    def test_returns_empty_if_no_media_entries(self):
        """Should return empty list if no entries under /media."""
        fstab_content = "UUID=1234 / ext4 defaults 0 1\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=fstab_content)):
            result = get_wrolpi_fstab_entries()
            assert result == []
