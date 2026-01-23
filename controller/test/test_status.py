"""
Unit tests for controller.lib.status module.

The status module now returns formats compatible with the main WROLPi API
so the React app can seamlessly use either source.
"""

from unittest import mock

from controller.lib.status import (
    get_cpu_status,
    get_disk_bandwidth_status,
    get_drive_status,
    get_load_status,
    get_memory_status,
    get_network_status,
    get_power_status,
    get_primary_drive_status,
    reset_bandwidth_stats,
)


class TestGetCpuStatus:
    """Tests for get_cpu_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_cpu_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys (main API format)."""
        result = get_cpu_status()
        assert "percent" in result
        assert "cores" in result
        assert "cur_frequency" in result
        assert "max_frequency" in result
        assert "min_frequency" in result
        assert "temperature" in result
        assert "high_temperature" in result
        assert "critical_temperature" in result

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
        """Should have all required keys (main API format)."""
        result = get_memory_status()
        assert "total" in result
        assert "used" in result
        assert "free" in result
        assert "cached" in result

    def test_total_is_positive(self):
        """Memory total should be positive."""
        result = get_memory_status()
        assert result["total"] > 0

    def test_bytes_are_non_negative(self):
        """Memory bytes should be non-negative."""
        result = get_memory_status()
        assert result["used"] >= 0
        assert result["free"] >= 0
        assert result["cached"] >= 0


class TestGetLoadStatus:
    """Tests for get_load_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_load_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys (main API format)."""
        result = get_load_status()
        assert "minute_1" in result
        assert "minute_5" in result
        assert "minute_15" in result

    def test_values_are_strings(self):
        """Load values should be string representations of numbers (main API format)."""
        result = get_load_status()
        # Values are strings in the main API format
        assert isinstance(result["minute_1"], str)
        assert isinstance(result["minute_5"], str)
        assert isinstance(result["minute_15"], str)
        # But they should be parseable as floats
        assert float(result["minute_1"]) >= 0
        assert float(result["minute_5"]) >= 0
        assert float(result["minute_15"]) >= 0


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
        """Each drive should have all required keys (main API format)."""
        result = get_drive_status()
        if result:  # Only test if we have drives
            drive = result[0]
            assert "mount" in drive
            assert "percent" in drive
            assert "size" in drive
            assert "used" in drive


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
                "mount": "/media/wrolpi",
                "percent": 50,
                "size": 1000000000,
                "used": 500000000,
            }
        ]
        with mock.patch(
                "controller.lib.status.get_drive_status", return_value=mock_drives
        ):
            result = get_primary_drive_status()
            assert result is not None
            assert result["mount"] == "/media/wrolpi"


class TestGetNetworkStatus:
    """Tests for get_network_status function."""

    def test_returns_dict(self):
        """Should return a dict (main API format: dict of interface name -> stats)."""
        result = get_network_status()
        assert isinstance(result, dict)

    def test_excludes_loopback(self):
        """Should not include the loopback interface."""
        result = get_network_status()
        assert "lo" not in result

    def test_interface_has_required_keys(self):
        """Each interface should have required keys (main API format)."""
        result = get_network_status()
        if result:  # Only test if we have interfaces
            iface = list(result.values())[0]
            assert "name" in iface
            assert "bytes_sent" in iface
            assert "bytes_recv" in iface
            assert "speed" in iface
            assert "now" in iface


class TestGetPowerStatus:
    """Tests for get_power_status function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_power_status()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys (main API format)."""
        result = get_power_status()
        assert "under_voltage" in result
        assert "over_current" in result

    def test_values_are_bool(self):
        """All values should be boolean."""
        result = get_power_status()
        assert isinstance(result["under_voltage"], bool)
        assert isinstance(result["over_current"], bool)


class TestNetworkBandwidthRates:
    """Tests for network bandwidth per-second rate calculations."""

    def test_first_call_returns_zero_rates(self):
        """First call should return zero rates (no previous data)."""
        reset_bandwidth_stats()
        result = get_network_status()
        if result:
            iface = list(result.values())[0]
            assert iface['bytes_recv_ps'] == 0
            assert iface['bytes_sent_ps'] == 0
            assert iface['elapsed'] == 0

    def test_second_call_has_elapsed_time(self):
        """Second call should have non-zero elapsed time."""
        import time
        reset_bandwidth_stats()
        get_network_status()
        time.sleep(1.1)  # Wait > 1 second since elapsed is int (truncated)
        result = get_network_status()
        if result:
            iface = list(result.values())[0]
            assert iface['elapsed'] >= 1


class TestDiskBandwidthRates:
    """Tests for disk bandwidth per-second rate calculations."""

    def test_first_call_returns_zero_rates(self):
        """First call should return zero rates."""
        reset_bandwidth_stats()
        result = get_disk_bandwidth_status()
        if result:
            disk = list(result.values())[0]
            assert disk['bytes_read_ps'] == 0
            assert disk['bytes_write_ps'] == 0
            assert disk['elapsed'] == 0

    def test_second_call_has_elapsed_time(self):
        """Second call should have non-zero elapsed time."""
        import time
        reset_bandwidth_stats()
        get_disk_bandwidth_status()
        time.sleep(1.1)  # Wait > 1 second since elapsed is int (truncated)
        result = get_disk_bandwidth_status()
        if result:
            disk = list(result.values())[0]
            assert disk['elapsed'] >= 1
            assert 'speed' in disk
