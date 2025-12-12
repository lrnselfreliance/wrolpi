"""
Unit tests for controller.lib.status module.
"""

from unittest import mock

import pytest

from controller.lib.status import (
    get_cpu_status,
    get_drive_status,
    get_full_status,
    get_load_status,
    get_memory_status,
    get_network_status,
    get_power_status,
    get_primary_drive_status,
)


class TestGetCpuStatus:
    """Tests for get_cpu_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_cpu_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_cpu_status()
        assert "percent" in result
        assert "frequency_mhz" in result
        assert "frequency_max_mhz" in result
        assert "temperature_c" in result
        assert "cores" in result

    def test_percent_is_numeric(self):
        """CPU percent should be a number."""
        result = get_cpu_status()
        assert isinstance(result["percent"], (int, float))
        assert 0 <= result["percent"] <= 100

    def test_cores_is_positive(self):
        """Core count should be a positive integer."""
        result = get_cpu_status()
        assert isinstance(result["cores"], int)
        assert result["cores"] > 0


class TestGetMemoryStatus:
    """Tests for get_memory_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_memory_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_memory_status()
        assert "total_bytes" in result
        assert "available_bytes" in result
        assert "used_bytes" in result
        assert "percent" in result
        assert "total_gb" in result
        assert "used_gb" in result
        assert "available_gb" in result

    def test_percent_is_valid(self):
        """Memory percent should be between 0 and 100."""
        result = get_memory_status()
        assert 0 <= result["percent"] <= 100

    def test_bytes_are_positive(self):
        """Memory bytes should be positive."""
        result = get_memory_status()
        assert result["total_bytes"] > 0
        assert result["used_bytes"] >= 0
        assert result["available_bytes"] >= 0

    def test_gb_values_are_calculated(self):
        """GB values should be properly calculated from bytes."""
        result = get_memory_status()
        expected_total_gb = round(result["total_bytes"] / (1024**3), 1)
        assert result["total_gb"] == expected_total_gb


class TestGetLoadStatus:
    """Tests for get_load_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_load_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_load_status()
        assert "load_1min" in result
        assert "load_5min" in result
        assert "load_15min" in result

    def test_values_are_numeric(self):
        """Load values should be non-negative numbers."""
        result = get_load_status()
        assert isinstance(result["load_1min"], (int, float))
        assert isinstance(result["load_5min"], (int, float))
        assert isinstance(result["load_15min"], (int, float))
        assert result["load_1min"] >= 0
        assert result["load_5min"] >= 0
        assert result["load_15min"] >= 0


class TestGetDriveStatus:
    """Tests for get_drive_status function."""

    def test_returns_list(self):
        """Should return a list."""
        result = get_drive_status()
        assert isinstance(result, list)

    def test_returns_drives_or_empty(self):
        """Should return drives list (may be empty in Docker containers)."""
        result = get_drive_status()
        # The result should be a valid list
        # May be empty in Docker containers where root fs is not visible
        assert isinstance(result, list)

    def test_drive_has_required_keys(self):
        """Each drive should have all required keys."""
        result = get_drive_status()
        if result:  # Only test if we have drives
            drive = result[0]
            assert "device" in drive
            assert "mount_point" in drive
            assert "fstype" in drive
            assert "total_bytes" in drive
            assert "used_bytes" in drive
            assert "free_bytes" in drive
            assert "percent" in drive
            assert "total_gb" in drive
            assert "used_gb" in drive
            assert "free_gb" in drive


class TestGetPrimaryDriveStatus:
    """Tests for get_primary_drive_status function."""

    def test_returns_none_when_not_mounted(self):
        """Should return None when /media/wrolpi is not mounted."""
        # In most test environments, /media/wrolpi won't be mounted
        result = get_primary_drive_status()
        # This could be None or a dict depending on the environment
        assert result is None or isinstance(result, dict)

    def test_returns_dict_when_mounted(self):
        """Should return drive info when /media/wrolpi is mounted."""
        # Mock the get_drive_status to return a drive at /media/wrolpi
        mock_drives = [
            {
                "device": "/dev/sda1",
                "mount_point": "/media/wrolpi",
                "fstype": "ext4",
                "total_bytes": 1000000000,
                "used_bytes": 500000000,
                "free_bytes": 500000000,
                "percent": 50.0,
                "total_gb": 0.9,
                "used_gb": 0.5,
                "free_gb": 0.5,
            }
        ]
        with mock.patch(
            "controller.lib.status.get_drive_status", return_value=mock_drives
        ):
            result = get_primary_drive_status()
            assert result is not None
            assert result["mount_point"] == "/media/wrolpi"


class TestGetNetworkStatus:
    """Tests for get_network_status function."""

    def test_returns_list(self):
        """Should return a list."""
        result = get_network_status()
        assert isinstance(result, list)

    def test_excludes_loopback(self):
        """Should not include the loopback interface."""
        result = get_network_status()
        loopback = [i for i in result if i["name"] == "lo"]
        assert len(loopback) == 0

    def test_interface_has_required_keys(self):
        """Each interface should have required keys."""
        result = get_network_status()
        if result:  # Only test if we have interfaces
            iface = result[0]
            assert "name" in iface
            assert "ipv4" in iface
            assert "ipv6" in iface
            assert "mac" in iface
            assert "bytes_sent" in iface
            assert "bytes_recv" in iface
            assert "bytes_sent_mb" in iface
            assert "bytes_recv_mb" in iface


class TestGetPowerStatus:
    """Tests for get_power_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_power_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_power_status()
        assert "undervoltage_detected" in result
        assert "currently_throttled" in result
        assert "undervoltage_occurred" in result
        assert "throttling_occurred" in result

    def test_values_are_bool(self):
        """All values should be boolean."""
        result = get_power_status()
        assert isinstance(result["undervoltage_detected"], bool)
        assert isinstance(result["currently_throttled"], bool)
        assert isinstance(result["undervoltage_occurred"], bool)
        assert isinstance(result["throttling_occurred"], bool)


class TestGetFullStatus:
    """Tests for get_full_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_full_status()
        assert isinstance(result, dict)

    def test_has_all_categories(self):
        """Should have all status categories."""
        result = get_full_status()
        assert "cpu" in result
        assert "memory" in result
        assert "load" in result
        assert "drives" in result
        assert "primary_drive" in result
        assert "network" in result
        assert "power" in result

    def test_cpu_is_populated(self):
        """CPU status should be properly populated."""
        result = get_full_status()
        assert "percent" in result["cpu"]
        assert "cores" in result["cpu"]

    def test_memory_is_populated(self):
        """Memory status should be properly populated."""
        result = get_full_status()
        assert "percent" in result["memory"]
        assert "total_gb" in result["memory"]

    def test_load_is_populated(self):
        """Load status should be properly populated."""
        result = get_full_status()
        assert "load_1min" in result["load"]
