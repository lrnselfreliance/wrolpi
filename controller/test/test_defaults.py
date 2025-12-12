"""
Unit tests for controller.defaults module.
"""
import pytest

from controller.defaults import DEFAULT_CONFIG


class TestDefaultConfig:
    """Tests for DEFAULT_CONFIG structure."""

    def test_default_config_is_dict(self):
        """DEFAULT_CONFIG should be a dictionary."""
        assert isinstance(DEFAULT_CONFIG, dict)

    def test_default_port(self):
        """Default port should be 8087."""
        assert DEFAULT_CONFIG["port"] == 8087

    def test_default_media_directory(self):
        """Default media directory should be /media/wrolpi."""
        assert DEFAULT_CONFIG["media_directory"] == "/media/wrolpi"


class TestDrivesConfig:
    """Tests for drives configuration."""

    def test_drives_config_exists(self):
        """Drives config should exist."""
        assert "drives" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["drives"], dict)

    @pytest.mark.parametrize("filesystem", ["ext4", "btrfs", "vfat", "exfat"])
    def test_supported_filesystem(self, filesystem):
        """Should have expected filesystems in supported list."""
        filesystems = DEFAULT_CONFIG["drives"]["supported_filesystems"]
        assert isinstance(filesystems, list)
        assert filesystem in filesystems

    def test_auto_mount_default(self):
        """Auto mount should be True by default."""
        assert DEFAULT_CONFIG["drives"]["auto_mount"] is True

    def test_mounts_empty_by_default(self):
        """Mounts list should be empty by default."""
        assert DEFAULT_CONFIG["drives"]["mounts"] == []


class TestManagedServicesConfig:
    """Tests for managed services configuration."""

    def test_managed_services_exists(self):
        """Managed services config should exist."""
        assert "managed_services" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["managed_services"], list)

    def test_managed_services_count(self):
        """Should have expected number of managed services."""
        services = DEFAULT_CONFIG["managed_services"]
        assert len(services) == 10

    @pytest.mark.parametrize("name,expected", [
        ("wrolpi-api",
         {"systemd_name": "wrolpi-api", "port": 8081, "viewable": True, "description": "Python API (Sanic)"}),
        ("wrolpi-app", {"port": 3000, "viewable": False}),
        ("nginx", {"port": 80}),
        ("postgresql", {"port": 5432, "viewable": False}),
        ("wrolpi-upgrade", {"port": None, "viewable": False, "show_only_when_running": True}),
    ])
    def test_service_config(self, name, expected):
        """Should have service configured with expected values."""
        services = DEFAULT_CONFIG["managed_services"]
        service = next((s for s in services if s["name"] == name), None)
        assert service is not None, f"Service {name} not found"
        for key, value in expected.items():
            assert service[key] == value, f"Service {name} has {key}={service.get(key)}, expected {value}"

    @pytest.mark.parametrize("name,use_https", [
        ("wrolpi-help", True),
        ("wrolpi-kiwix", True),
        ("apache2", True),
        ("wrolpi-api", False),
        ("wrolpi-app", False),
        ("postgresql", False),
    ])
    def test_service_use_https(self, name, use_https):
        """HTTPS services should have use_https=True, others should have False."""
        services = DEFAULT_CONFIG["managed_services"]
        service = next((s for s in services if s["name"] == name), None)
        assert service is not None, f"Service {name} not found"
        assert service.get("use_https", False) == use_https, \
            f"Service {name} should have use_https={use_https}"

    def test_all_services_have_required_fields(self):
        """All services should have required fields."""
        required_fields = ["name", "systemd_name", "port", "viewable", "use_https", "description"]
        for service in DEFAULT_CONFIG["managed_services"]:
            for field in required_fields:
                assert field in service, f"Service {service.get('name')} missing {field}"


class TestHotspotConfig:
    """Tests for hotspot configuration."""

    def test_hotspot_config_exists(self):
        """Hotspot config should exist."""
        assert "hotspot" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["hotspot"], dict)

    @pytest.mark.parametrize("key,expected", [
        ("device", "wlan0"),
        ("ssid", "WROLPi"),
        ("password", "wrolpi hotspot"),
    ])
    def test_hotspot_defaults(self, key, expected):
        """Hotspot should have expected default values."""
        assert DEFAULT_CONFIG["hotspot"][key] == expected


class TestThrottleConfig:
    """Tests for throttle configuration."""

    def test_throttle_config_exists(self):
        """Throttle config should exist."""
        assert "throttle" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["throttle"], dict)

    def test_default_governor(self):
        """Default governor should be ondemand."""
        assert DEFAULT_CONFIG["throttle"]["default_governor"] == "ondemand"
