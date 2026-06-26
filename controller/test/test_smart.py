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
    _read_scsi_limited,
    _limited_device_smart,
    _drive_is_asleep,
    HDD_HIGH_TEMPERATURE,
    HDD_CRITICAL_TEMPERATURE,
)

# Real smartctl output from a Seagate Expansion USB enclosure that rejects
# ATA pass-through.  The health (`-d scsi -H`) and identity (`-d scsi -i`)
# reads MUST be separate calls: combining `-i` makes smartctl suppress the
# health line.
SCSI_HEALTH_OUTPUT = """\
=== START OF READ SMART DATA SECTION ===
SMART Health Status: OK
"""

SCSI_IDENTITY_OUTPUT = """\
=== START OF INFORMATION SECTION ===
Vendor:               Seagate
Product:              Expansion HDD
Revision:             1802
User Capacity:        26,000,658,267,648 bytes [26.0 TB]
Serial number:        00000000NT17S4W2
Device type:          disk
SMART support is:     Unavailable - device lacks SMART capability.
"""


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

        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart.DeviceList", return_value=mock_device_list), \
                mock.patch("controller.lib.smart._scan_devices", return_value=[]):
            result = get_all_smart_status()
            assert len(result) == 1
            assert result[0]["device"] == "sda"
            assert result[0]["model"] == "Samsung SSD"

    def test_supplements_with_scsi_health_for_bridge_drive(self):
        """A scan-visible drive that pySMART/DeviceList cannot read (USB
        enclosure) is added via the coarse SCSI health fallback."""
        ata = mock.Mock()
        ata.name = "sdc"
        ata.model = "WDC"
        ata.serial = "S2"
        ata.capacity = "14.0 TB"
        ata.assessment = "PASS"
        ata.smart_enabled = True
        ata.attributes = []

        device_list = mock.Mock()
        device_list.devices = [ata]
        limited = {"device": "sda", "path": "/dev/sda", "health": "PASS",
                   "smart_limited": True}

        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart.DeviceList", return_value=device_list), \
                mock.patch("controller.lib.smart._scan_devices",
                           return_value=[("/dev/sdc", "sat"), ("/dev/sda", "sat")]), \
                mock.patch("controller.lib.smart._limited_device_smart",
                           return_value=limited) as limited_fn:
            result = get_all_smart_status()

        # sdc came from DeviceList (covered); only sda hits the fallback.
        limited_fn.assert_called_once_with("/dev/sda")
        devices = {d["device"] for d in result}
        assert devices == {"sdc", "sda"}

    def test_supplement_failure_preserves_pysmart_results(self):
        """An error in the SCSI supplement must not discard the drives already
        collected from pySMART."""
        ata = mock.Mock()
        ata.name = "sdb"
        ata.model = "Seagate"
        ata.serial = "S1"
        ata.capacity = "8.0 TB"
        ata.assessment = "PASS"
        ata.smart_enabled = True
        ata.attributes = []

        device_list = mock.Mock()
        device_list.devices = [ata]

        with mock.patch("controller.lib.smart.is_smart_available", return_value=True), \
                mock.patch("controller.lib.smart.DeviceList", return_value=device_list), \
                mock.patch("controller.lib.smart._scan_devices",
                           side_effect=RuntimeError("scan blew up")):
            result = get_all_smart_status()

        assert [d["device"] for d in result] == ["sdb"]


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


class TestReadScsiLimited:
    """Tests for _read_scsi_limited — coarse health for USB-bridge drives.

    Health and identity are two separate smartctl calls (combining `-H -i`
    suppresses the health line on these bridges), so subprocess.run is mocked
    with a side_effect sequence: first the `-H` read, then the `-i` read.
    """

    def test_parses_ok_health_and_identity(self):
        runs = [mock.Mock(stdout=SCSI_HEALTH_OUTPUT),
                mock.Mock(stdout=SCSI_IDENTITY_OUTPUT)]
        with mock.patch("controller.lib.smart.subprocess.run", side_effect=runs):
            health, model, serial, capacity = _read_scsi_limited("/dev/sda")
        assert health == "PASS"
        assert model == "Seagate Expansion HDD"
        assert serial == "00000000NT17S4W2"
        assert capacity == "26.0 TB"

    def test_parses_failed_health(self):
        runs = [mock.Mock(stdout="SMART Health Status: FAILED\n"),
                mock.Mock(stdout=SCSI_IDENTITY_OUTPUT)]
        with mock.patch("controller.lib.smart.subprocess.run", side_effect=runs):
            health, _model, _serial, _capacity = _read_scsi_limited("/dev/sda")
        assert health == "FAIL"

    def test_no_health_line_skips_identity_and_returns_none(self):
        """No health line → don't bother reading identity; report nothing."""
        run = mock.Mock(stdout="Vendor:               WD\nProduct:   Thing\n")
        with mock.patch("controller.lib.smart.subprocess.run",
                        return_value=run) as run_fn:
            result = _read_scsi_limited("/dev/sda")
        assert result == (None, None, None, None)
        # Only the health read happened; identity was skipped.
        run_fn.assert_called_once()

    def test_unrecognised_status_is_treated_as_unreadable(self):
        """A non-standard bridge status (e.g. UNKNOWN) must NOT show as a red
        FAIL; treat it as unreadable so the drive is omitted, not falsely
        failed."""
        run = mock.Mock(stdout="SMART Health Status: UNKNOWN\n")
        with mock.patch("controller.lib.smart.subprocess.run",
                        return_value=run) as run_fn:
            result = _read_scsi_limited("/dev/sda")
        assert result == (None, None, None, None)
        run_fn.assert_called_once()

    def test_smartctl_error_returns_all_none(self):
        with mock.patch("controller.lib.smart.subprocess.run",
                        side_effect=OSError("boom")):
            assert _read_scsi_limited("/dev/sda") == (None, None, None, None)


class TestLimitedDeviceSmart:
    """Tests for _limited_device_smart — the limited payload shape."""

    def test_builds_limited_payload(self):
        with mock.patch("controller.lib.smart._read_scsi_limited",
                        return_value=("PASS", "Seagate Expansion HDD",
                                      "NT17S4W2", "26.0 TB")):
            payload = _limited_device_smart("/dev/sda")
        assert payload["device"] == "sda"
        assert payload["path"] == "/dev/sda"
        assert payload["health"] == "PASS"
        assert payload["model"] == "Seagate Expansion HDD"
        assert payload["smart_limited"] is True
        # Attributes are unreachable through the bridge.
        assert payload["assessment"] is None
        assert payload["temperature"] is None
        assert payload["pending_sectors"] is None

    def test_returns_none_when_health_unavailable(self):
        """No SCSI health → nothing useful to show, omit the drive."""
        with mock.patch("controller.lib.smart._read_scsi_limited",
                        return_value=(None, None, None, None)):
            assert _limited_device_smart("/dev/sda") is None
