"""
Unit tests for controller.lib.smart module.
"""

from unittest import mock

import pytest

from controller.lib.smart import (
    is_smart_available,
    get_all_smart_status,
    build_smart_stats,
    _get_device_smart,
    _get_temperature,
    _get_attribute,
    _parse_raw_int,
    _derive_health,
    _drive_is_asleep,
    HDD_HIGH_TEMPERATURE,
    HDD_CRITICAL_TEMPERATURE,
)


def _attr(name, raw):
    a = mock.Mock()
    a.name = name
    a.raw = raw
    a.when_failed = ''
    return a


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
        assert result["health"] == "PASS"
        assert result["smart_enabled"] is True

    def test_warns_on_pending_sectors_despite_pass(self):
        """A drive self-assessing PASS with pending sectors must surface a
        WARN health while leaving the raw assessment untouched."""
        mock_device = mock.Mock()
        mock_device.name = "sdc"
        mock_device.model = "WDC WD140EDGZ"
        mock_device.serial = "9LJ0BM0G"
        mock_device.capacity = "14.0 TB"
        mock_device.assessment = "PASS"
        mock_device.smart_enabled = True
        mock_device.attributes = [
            _attr("Current_Pending_Sector", "80"),
            _attr("Offline_Uncorrectable", "51"),
            _attr("Reallocated_Sector_Ct", "1"),
        ]

        result = _get_device_smart(mock_device)
        assert result["assessment"] == "PASS"
        assert result["health"] == "WARN"
        assert result["pending_sectors"] == 80
        assert result["offline_uncorrectable"] == 51


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
        mock_device.temperature = None
        mock_device.attributes = []

        result = _get_temperature(mock_device)
        assert result is None

    def test_prefers_pysmart_temperature_property(self):
        """Real drives report raw values like '52 (Min/Max 16/57)' which
        int() cannot parse; pySMART's temperature property handles them."""
        mock_attr = mock.Mock()
        mock_attr.name = "Temperature_Celsius"
        mock_attr.raw = "52 (Min/Max 16/57)"

        mock_device = mock.Mock()
        mock_device.temperature = 52
        mock_device.attributes = [mock_attr]

        result = _get_temperature(mock_device)
        assert result == 52

    def test_pysmart_temperature_property_for_nvme(self):
        """NVMe devices have no ATA attribute table, only the property."""
        mock_device = mock.Mock()
        mock_device.temperature = 38
        mock_device.attributes = None

        result = _get_temperature(mock_device)
        assert result == 38

    def test_ignores_non_int_temperature_property(self):
        """A missing/bogus temperature property falls back to attributes."""
        mock_attr = mock.Mock()
        mock_attr.name = "Temperature_Celsius"
        mock_attr.raw = "35"

        mock_device = mock.Mock()  # .temperature is a Mock, not an int
        mock_device.attributes = [mock_attr]

        result = _get_temperature(mock_device)
        assert result == 35


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

    def test_parses_seagate_power_on_hours_format(self):
        """Seagate reports Power_On_Hours as 'NNNNNh+00m+00.000s'; the leading
        integer must be extracted rather than discarded to None."""
        mock_device = mock.Mock()
        mock_device.attributes = [_attr("Power_On_Hours", "50287h+00m+00.000s")]

        result = _get_attribute(mock_device, "Power_On_Hours")
        assert result == 50287


class TestParseRawInt:
    """Tests for _parse_raw_int — vendor-specific raw value parsing."""

    @pytest.mark.parametrize("raw, expected", [
        ("80", 80),                       # plain string integer
        (22225, 22225),                   # already an int
        ("50287h+00m+00.000s", 50287),    # Seagate Power_On_Hours
        ("56 (Min/Max 17/66)", 56),       # WD temperature decoration
        ("53 (0 17 0 0 0)", 53),          # Seagate temperature tuple
        (None, None),                     # missing value
        ("invalid", None),                # no leading integer
    ])
    def test_parse_raw_int(self, raw, expected):
        assert _parse_raw_int(raw) == expected


class TestDeriveHealth:
    """Tests for _derive_health — the verdict shown in the navbar/UIs."""

    @pytest.mark.parametrize("assessment, pending, uncorrectable, expected", [
        ("PASS", 0, 0, "PASS"),       # clean drive stays PASS
        ("FAIL", 0, 0, "FAIL"),       # self-assessed failure stays FAIL
        ("PASS", 80, 0, "WARN"),      # pending sectors downgrade PASS -> WARN
        ("PASS", 0, 51, "WARN"),      # uncorrectable sectors downgrade -> WARN
        ("PASS", 0, 0, "PASS"),       # reallocated is not a trigger (clean here)
        ("FAIL", 80, 51, "FAIL"),     # FAIL takes priority over sector WARN
        (None, None, None, None),     # unsupported drive passes through unknown
        (None, 5, 0, "WARN"),         # unknown assessment + pending -> WARN
    ])
    def test_derive_health(self, assessment, pending, uncorrectable, expected):
        assert _derive_health(assessment, pending, uncorrectable) == expected


class TestDriveIsAsleep:
    """Tests for _drive_is_asleep function (smartctl -n standby)."""

    def test_returns_true_for_standby(self):
        completed = mock.Mock(stdout="Device is in STANDBY mode, exit(2)\n")
        with mock.patch("controller.lib.smart.subprocess.run", return_value=completed):
            assert _drive_is_asleep("/dev/sda") is True

    def test_returns_true_for_sleep(self):
        # smartctl -n standby also bails on the deeper SLEEP power mode;
        # that drive must NOT be woken for a read either.
        completed = mock.Mock(stdout="Device is in SLEEP mode, exit(2)\n")
        with mock.patch("controller.lib.smart.subprocess.run", return_value=completed):
            assert _drive_is_asleep("/dev/sda") is True

    def test_returns_false_for_active(self):
        # A normal `-i` read on an awake drive never mentions STANDBY.
        completed = mock.Mock(stdout="Model Family: WDC\nDevice Model: WD100EMAZ\n")
        with mock.patch("controller.lib.smart.subprocess.run", return_value=completed):
            assert _drive_is_asleep("/dev/sda") is False

    def test_returns_false_on_error(self):
        """smartctl missing / errors out → treat as awake (safe fallback)."""
        with mock.patch("controller.lib.smart.subprocess.run",
                        side_effect=OSError("boom")):
            assert _drive_is_asleep("/dev/sda") is False


class TestBuildSmartStats:
    """Tests for build_smart_stats — the navbar/Disk Management payload."""

    def test_returns_thresholds_when_unavailable(self):
        """Docker / no pySMART → empty drive list but thresholds present."""
        with mock.patch("controller.lib.smart.is_smart_available", return_value=False):
            stats = build_smart_stats()
        assert stats["drives"] == []
        assert stats["high_temperature"] == HDD_HIGH_TEMPERATURE
        assert stats["critical_temperature"] == HDD_CRITICAL_TEMPERATURE

    def test_reads_awake_drives(self):
        fake_device = mock.Mock()
        fake_device.name = "sda"
        fake_device.model = "WDC WD100EMAZ"
        fake_device.serial = "S1"
        fake_device.capacity = "10.0 TB"
        fake_device.assessment = "PASS"
        fake_device.smart_enabled = True
        fake_device.temperature = 52
        fake_device.attributes = []

        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart._scan_devices",
                           return_value=[("/dev/sda", "sat")]), \
                mock.patch("controller.lib.smart._drive_is_asleep", return_value=False), \
                mock.patch("controller.lib.smart.Device", return_value=fake_device) as Dev:
            stats = build_smart_stats()

        Dev.assert_called_once_with("/dev/sda", interface="sat")
        assert len(stats["drives"]) == 1
        assert stats["drives"][0]["device"] == "sda"
        assert stats["drives"][0]["temperature"] == 52

    def test_sleeping_drive_is_not_read_and_reuses_previous(self):
        """A standby drive must NOT be read (would wake it); reuse old data."""
        previous = {
            "drives": [{"device": "sda", "path": "/dev/sda", "temperature": 49}],
            "high_temperature": HDD_HIGH_TEMPERATURE,
            "critical_temperature": HDD_CRITICAL_TEMPERATURE,
        }
        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart._scan_devices",
                           return_value=[("/dev/sda", "sat")]), \
                mock.patch("controller.lib.smart._drive_is_asleep", return_value=True), \
                mock.patch("controller.lib.smart.Device") as Dev:
            stats = build_smart_stats(previous=previous)

        Dev.assert_not_called()
        assert stats["drives"] == [{"device": "sda", "path": "/dev/sda", "temperature": 49}]

    def test_sleeping_drive_without_previous_is_skipped(self):
        """Standby drive with no prior reading is simply omitted (not hot)."""
        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart._scan_devices",
                           return_value=[("/dev/sda", "sat")]), \
                mock.patch("controller.lib.smart._drive_is_asleep", return_value=True), \
                mock.patch("controller.lib.smart.Device") as Dev:
            stats = build_smart_stats(previous=None)

        Dev.assert_not_called()
        assert stats["drives"] == []
