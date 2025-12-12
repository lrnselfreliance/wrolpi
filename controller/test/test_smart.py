"""
Unit tests for controller.lib.smart module.
"""

from unittest import mock

from controller.lib.smart import (
    is_smart_available,
    get_all_smart_status,
    _get_device_smart,
    _get_temperature,
    _get_attribute,
)


class TestIsSmartAvailable:
    """Tests for is_smart_available function."""

    def test_returns_false_in_docker_mode(self):
        """Should return False in Docker mode."""
        with mock.patch("controller.lib.smart.is_docker_mode", return_value=True):
            assert is_smart_available() is False

    def test_returns_false_when_pysmart_not_installed(self):
        """Should return False when pySMART not installed."""
        with mock.patch("controller.lib.smart.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.smart.SMART_AVAILABLE", False):
                assert is_smart_available() is False

    def test_returns_true_when_available(self):
        """Should return True when pySMART available and not Docker."""
        with mock.patch("controller.lib.smart.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.smart.SMART_AVAILABLE", True):
                assert is_smart_available() is True


class TestGetAllSmartStatus:
    """Tests for get_all_smart_status function."""

    def test_returns_empty_when_not_available(self):
        """Should return empty list when SMART not available."""
        with mock.patch("controller.lib.smart.is_smart_available", return_value=False):
            result = get_all_smart_status()
            assert result == []

    def test_returns_device_list(self):
        """Should return list of device statuses."""
        mock_device = mock.Mock()
        mock_device.name = "sda"
        mock_device.model = "Samsung SSD"
        mock_device.serial = "S1234"
        mock_device.capacity = "500 GB"
        mock_device.assessment = "PASS"
        mock_device.smart_enabled = True
        mock_device.attributes = []

        mock_device_list = mock.Mock()
        mock_device_list.devices = [mock_device]

        with mock.patch("controller.lib.smart.is_smart_available", return_value=True):
            with mock.patch("controller.lib.smart.DeviceList", return_value=mock_device_list):
                result = get_all_smart_status()
                assert len(result) == 1
                assert result[0]["device"] == "sda"
                assert result[0]["model"] == "Samsung SSD"


class TestGetDeviceSmart:
    """Tests for _get_device_smart function."""

    def test_extracts_device_info(self):
        """Should extract device information."""
        mock_device = mock.Mock()
        mock_device.name = "sda"
        mock_device.model = "Samsung SSD"
        mock_device.serial = "S1234"
        mock_device.capacity = "500 GB"
        mock_device.assessment = "PASS"
        mock_device.smart_enabled = True
        mock_device.attributes = []

        result = _get_device_smart(mock_device)
        assert result["device"] == "sda"
        assert result["path"] == "/dev/sda"
        assert result["model"] == "Samsung SSD"
        assert result["serial"] == "S1234"
        assert result["capacity"] == "500 GB"
        assert result["assessment"] == "PASS"
        assert result["smart_enabled"] is True


class TestGetTemperature:
    """Tests for _get_temperature function."""

    def test_returns_temperature_celsius(self):
        """Should return temperature from Temperature_Celsius attribute."""
        mock_attr = mock.Mock()
        mock_attr.name = "Temperature_Celsius"
        mock_attr.raw = "35"

        mock_device = mock.Mock()
        mock_device.attributes = [mock_attr]

        result = _get_temperature(mock_device)
        assert result == 35

    def test_falls_back_to_airflow_temperature(self):
        """Should fall back to Airflow_Temperature_Cel."""
        mock_attr = mock.Mock()
        mock_attr.name = "Airflow_Temperature_Cel"
        mock_attr.raw = "40"

        mock_device = mock.Mock()
        mock_device.attributes = [mock_attr]

        result = _get_temperature(mock_device)
        assert result == 40

    def test_returns_none_if_not_found(self):
        """Should return None if no temperature attribute."""
        mock_device = mock.Mock()
        mock_device.attributes = []

        result = _get_temperature(mock_device)
        assert result is None


class TestGetAttribute:
    """Tests for _get_attribute function."""

    def test_returns_attribute_value(self):
        """Should return attribute raw value."""
        mock_attr = mock.Mock()
        mock_attr.name = "Power_On_Hours"
        mock_attr.raw = "12345"

        mock_device = mock.Mock()
        mock_device.attributes = [mock_attr]

        result = _get_attribute(mock_device, "Power_On_Hours")
        assert result == 12345

    def test_returns_none_for_missing_attribute(self):
        """Should return None if attribute not found."""
        mock_device = mock.Mock()
        mock_device.attributes = []

        result = _get_attribute(mock_device, "Nonexistent")
        assert result is None

    def test_returns_none_if_no_attributes(self):
        """Should return None if device has no attributes."""
        mock_device = mock.Mock()
        mock_device.attributes = None

        result = _get_attribute(mock_device, "Power_On_Hours")
        assert result is None

    def test_handles_invalid_raw_value(self):
        """Should handle non-numeric raw values."""
        mock_attr = mock.Mock()
        mock_attr.name = "Power_On_Hours"
        mock_attr.raw = "invalid"

        mock_device = mock.Mock()
        mock_device.attributes = [mock_attr]

        result = _get_attribute(mock_device, "Power_On_Hours")
        assert result is None
