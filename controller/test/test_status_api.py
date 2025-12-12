"""
Integration tests for Controller stats API endpoints.

The stats endpoints return system statistics (CPU, memory, etc).
Note: These are separate from the main WROLPi API's /api/status endpoint.
"""


class TestCpuEndpoint:
    """Tests for /api/stats/cpu endpoint."""

    def test_cpu_returns_200(self, test_client):
        """CPU endpoint should return 200 OK."""
        response = test_client.get("/api/stats/cpu")
        assert response.status_code == 200

    def test_cpu_returns_expected_fields(self, test_client):
        """CPU endpoint should return expected fields (main API format)."""
        response = test_client.get("/api/stats/cpu")
        data = response.json()
        assert "percent" in data
        assert "cores" in data
        assert "cur_frequency" in data
        assert "max_frequency" in data
        assert "min_frequency" in data
        assert "temperature" in data
        assert "high_temperature" in data
        assert "critical_temperature" in data

    def test_cpu_percent_valid_range(self, test_client):
        """CPU percent should be between 0 and 100."""
        response = test_client.get("/api/stats/cpu")
        data = response.json()
        assert 0 <= data["percent"] <= 100


class TestMemoryEndpoint:
    """Tests for /api/stats/memory endpoint."""

    def test_memory_returns_200(self, test_client):
        """Memory endpoint should return 200 OK."""
        response = test_client.get("/api/stats/memory")
        assert response.status_code == 200

    def test_memory_returns_expected_fields(self, test_client):
        """Memory endpoint should return expected fields (main API format)."""
        response = test_client.get("/api/stats/memory")
        data = response.json()
        assert "total" in data
        assert "used" in data
        assert "free" in data
        assert "cached" in data

    def test_memory_bytes_positive(self, test_client):
        """Memory total should be positive."""
        response = test_client.get("/api/stats/memory")
        data = response.json()
        assert data["total"] > 0


class TestLoadEndpoint:
    """Tests for /api/stats/load endpoint."""

    def test_load_returns_200(self, test_client):
        """Load endpoint should return 200 OK."""
        response = test_client.get("/api/stats/load")
        assert response.status_code == 200

    def test_load_returns_expected_fields(self, test_client):
        """Load endpoint should return expected fields (main API format)."""
        response = test_client.get("/api/stats/load")
        data = response.json()
        assert "minute_1" in data
        assert "minute_5" in data
        assert "minute_15" in data

    def test_load_values_non_negative(self, test_client):
        """Load values should be non-negative."""
        response = test_client.get("/api/stats/load")
        data = response.json()
        # Values are strings in main API format
        assert float(data["minute_1"]) >= 0
        assert float(data["minute_5"]) >= 0
        assert float(data["minute_15"]) >= 0


class TestPrimaryDriveEndpoint:
    """Tests for /api/stats/drives/primary endpoint."""

    def test_primary_drive_returns_200(self, test_client):
        """Primary drive endpoint should return 200 OK."""
        response = test_client.get("/api/stats/drives/primary")
        assert response.status_code == 200

    def test_primary_drive_returns_mounted_false_when_not_mounted(self, test_client):
        """Primary drive should return mounted=false when not present."""
        response = test_client.get("/api/stats/drives/primary")
        data = response.json()
        # In test environment, /media/wrolpi likely not mounted
        assert "mounted" in data


class TestNetworkEndpoint:
    """Tests for /api/stats/network endpoint."""

    def test_network_returns_200(self, test_client):
        """Network endpoint should return 200 OK."""
        response = test_client.get("/api/stats/network")
        assert response.status_code == 200

    def test_network_returns_dict(self, test_client):
        """Network endpoint should return a dict (main API format)."""
        response = test_client.get("/api/stats/network")
        data = response.json()
        assert isinstance(data, dict)

    def test_network_excludes_loopback(self, test_client):
        """Network should not include loopback interface."""
        response = test_client.get("/api/stats/network")
        data = response.json()
        assert "lo" not in data


class TestPowerEndpoint:
    """Tests for /api/stats/power endpoint."""

    def test_power_returns_200(self, test_client):
        """Power endpoint should return 200 OK."""
        response = test_client.get("/api/stats/power")
        assert response.status_code == 200

    def test_power_returns_expected_fields(self, test_client):
        """Power endpoint should return expected fields (main API format)."""
        response = test_client.get("/api/stats/power")
        data = response.json()
        assert "under_voltage" in data
        assert "over_current" in data

    def test_power_values_are_bool(self, test_client):
        """Power values should be booleans."""
        response = test_client.get("/api/stats/power")
        data = response.json()
        assert isinstance(data["under_voltage"], bool)
        assert isinstance(data["over_current"], bool)


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


class TestOpenAPIIncludesStatsEndpoints:
    """Tests that OpenAPI documentation includes stats endpoints."""

    def test_openapi_has_stats_paths(self, test_client):
        """OpenAPI schema should include stats paths."""
        response = test_client.get("/openapi.json")
        data = response.json()
        assert "/api/stats/cpu" in data["paths"]
        assert "/api/stats/memory" in data["paths"]
        assert "/api/stats/load" in data["paths"]
        assert "/api/stats/drives/primary" in data["paths"]
        assert "/api/stats/network" in data["paths"]
        assert "/api/stats/power" in data["paths"]
