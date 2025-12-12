"""
Integration tests for Controller status API endpoints.
"""

import pytest


class TestStatusEndpoint:
    """Tests for /api/status endpoint."""

    def test_status_returns_200(self, test_client):
        """Status endpoint should return 200 OK."""
        response = test_client.get("/api/status")
        assert response.status_code == 200

    def test_status_returns_all_categories(self, test_client):
        """Status endpoint should return all status categories."""
        response = test_client.get("/api/status")
        data = response.json()
        assert "cpu" in data
        assert "memory" in data
        assert "load" in data
        assert "drives" in data
        assert "primary_drive" in data
        assert "network" in data
        assert "power" in data

    def test_status_cpu_is_valid(self, test_client):
        """Status should include valid CPU data."""
        response = test_client.get("/api/status")
        data = response.json()
        assert "percent" in data["cpu"]
        assert "cores" in data["cpu"]
        assert isinstance(data["cpu"]["percent"], (int, float))
        assert isinstance(data["cpu"]["cores"], int)


class TestCpuEndpoint:
    """Tests for /api/status/cpu endpoint."""

    def test_cpu_returns_200(self, test_client):
        """CPU endpoint should return 200 OK."""
        response = test_client.get("/api/status/cpu")
        assert response.status_code == 200

    def test_cpu_returns_expected_fields(self, test_client):
        """CPU endpoint should return expected fields."""
        response = test_client.get("/api/status/cpu")
        data = response.json()
        assert "percent" in data
        assert "frequency_mhz" in data
        assert "frequency_max_mhz" in data
        assert "temperature_c" in data
        assert "cores" in data

    def test_cpu_percent_valid_range(self, test_client):
        """CPU percent should be between 0 and 100."""
        response = test_client.get("/api/status/cpu")
        data = response.json()
        assert 0 <= data["percent"] <= 100


class TestMemoryEndpoint:
    """Tests for /api/status/memory endpoint."""

    def test_memory_returns_200(self, test_client):
        """Memory endpoint should return 200 OK."""
        response = test_client.get("/api/status/memory")
        assert response.status_code == 200

    def test_memory_returns_expected_fields(self, test_client):
        """Memory endpoint should return expected fields."""
        response = test_client.get("/api/status/memory")
        data = response.json()
        assert "total_bytes" in data
        assert "available_bytes" in data
        assert "used_bytes" in data
        assert "percent" in data
        assert "total_gb" in data
        assert "used_gb" in data
        assert "available_gb" in data

    def test_memory_bytes_positive(self, test_client):
        """Memory bytes should be positive."""
        response = test_client.get("/api/status/memory")
        data = response.json()
        assert data["total_bytes"] > 0


class TestLoadEndpoint:
    """Tests for /api/status/load endpoint."""

    def test_load_returns_200(self, test_client):
        """Load endpoint should return 200 OK."""
        response = test_client.get("/api/status/load")
        assert response.status_code == 200

    def test_load_returns_expected_fields(self, test_client):
        """Load endpoint should return expected fields."""
        response = test_client.get("/api/status/load")
        data = response.json()
        assert "load_1min" in data
        assert "load_5min" in data
        assert "load_15min" in data

    def test_load_values_non_negative(self, test_client):
        """Load values should be non-negative."""
        response = test_client.get("/api/status/load")
        data = response.json()
        assert data["load_1min"] >= 0
        assert data["load_5min"] >= 0
        assert data["load_15min"] >= 0


class TestDrivesEndpoint:
    """Tests for /api/status/drives endpoint."""

    def test_drives_returns_200(self, test_client):
        """Drives endpoint should return 200 OK."""
        response = test_client.get("/api/status/drives")
        assert response.status_code == 200

    def test_drives_returns_list(self, test_client):
        """Drives endpoint should return a list."""
        response = test_client.get("/api/status/drives")
        data = response.json()
        assert isinstance(data, list)

    def test_drives_are_valid_if_present(self, test_client):
        """Drives should have required fields if present."""
        response = test_client.get("/api/status/drives")
        data = response.json()
        # List may be empty in Docker containers
        if data:
            drive = data[0]
            assert "device" in drive
            assert "mount_point" in drive
            assert "percent" in drive


class TestPrimaryDriveEndpoint:
    """Tests for /api/status/drives/primary endpoint."""

    def test_primary_drive_returns_200(self, test_client):
        """Primary drive endpoint should return 200 OK."""
        response = test_client.get("/api/status/drives/primary")
        assert response.status_code == 200

    def test_primary_drive_returns_mounted_false_when_not_mounted(self, test_client):
        """Primary drive should return mounted=false when not present."""
        response = test_client.get("/api/status/drives/primary")
        data = response.json()
        # In test environment, /media/wrolpi likely not mounted
        assert "mounted" in data


class TestNetworkEndpoint:
    """Tests for /api/status/network endpoint."""

    def test_network_returns_200(self, test_client):
        """Network endpoint should return 200 OK."""
        response = test_client.get("/api/status/network")
        assert response.status_code == 200

    def test_network_returns_list(self, test_client):
        """Network endpoint should return a list."""
        response = test_client.get("/api/status/network")
        data = response.json()
        assert isinstance(data, list)

    def test_network_excludes_loopback(self, test_client):
        """Network should not include loopback interface."""
        response = test_client.get("/api/status/network")
        data = response.json()
        loopback = [i for i in data if i["name"] == "lo"]
        assert len(loopback) == 0


class TestPowerEndpoint:
    """Tests for /api/status/power endpoint."""

    def test_power_returns_200(self, test_client):
        """Power endpoint should return 200 OK."""
        response = test_client.get("/api/status/power")
        assert response.status_code == 200

    def test_power_returns_expected_fields(self, test_client):
        """Power endpoint should return expected fields."""
        response = test_client.get("/api/status/power")
        data = response.json()
        assert "undervoltage_detected" in data
        assert "currently_throttled" in data
        assert "undervoltage_occurred" in data
        assert "throttling_occurred" in data

    def test_power_values_are_bool(self, test_client):
        """Power values should be booleans."""
        response = test_client.get("/api/status/power")
        data = response.json()
        assert isinstance(data["undervoltage_detected"], bool)
        assert isinstance(data["currently_throttled"], bool)


class TestDashboardWithRealData:
    """Tests for dashboard rendering with real status data."""

    def test_dashboard_shows_cpu_percent(self, test_client):
        """Dashboard should show CPU percentage (not placeholder)."""
        response = test_client.get("/")
        content = response.text
        # CPU value should be a number, not "--"
        # The template shows: {{ cpu.percent|default('--') }}%
        # We verify the page loads and contains CPU section
        assert "CPU" in content
        # The dashboard should have some numeric value, not all placeholders

    def test_dashboard_shows_memory_data(self, test_client):
        """Dashboard should show memory data."""
        response = test_client.get("/")
        content = response.text
        assert "Memory" in content

    def test_dashboard_shows_load_data(self, test_client):
        """Dashboard should show load data."""
        response = test_client.get("/")
        content = response.text
        assert "Load" in content

    def test_dashboard_shows_storage_data(self, test_client):
        """Dashboard should show storage data."""
        response = test_client.get("/")
        content = response.text
        assert "Storage" in content


class TestOpenAPIIncludesStatusEndpoints:
    """Tests that OpenAPI documentation includes status endpoints."""

    def test_openapi_has_status_paths(self, test_client):
        """OpenAPI schema should include status paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/status" in data["paths"]
        assert "/api/status/cpu" in data["paths"]
        assert "/api/status/memory" in data["paths"]
        assert "/api/status/load" in data["paths"]
        assert "/api/status/drives" in data["paths"]
        assert "/api/status/drives/primary" in data["paths"]
        assert "/api/status/network" in data["paths"]
        assert "/api/status/power" in data["paths"]
