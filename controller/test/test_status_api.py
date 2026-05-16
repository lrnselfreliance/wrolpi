"""
Integration tests for Controller stats API endpoints.

The stats endpoints return system statistics (CPU, memory, etc).
Note: These are separate from the main WROLPi API's /api/status endpoint.
"""

import pytest


class TestStatsEndpoints:
    """Tests for /api/stats/* endpoints — status code, payload shape, field set."""

    @pytest.mark.parametrize("endpoint,expected_type,required_fields", [
        ("/api/stats/cpu", dict, [
            "percent", "cores",
            "cur_frequency", "max_frequency", "min_frequency",
            "temperature", "high_temperature", "critical_temperature",
        ]),
        ("/api/stats/memory", dict, ["total", "used", "free", "cached"]),
        ("/api/stats/load", dict, ["minute_1", "minute_5", "minute_15"]),
        ("/api/stats/drives/primary", dict, ["mounted"]),
        ("/api/stats/network", dict, []),
        ("/api/stats/power", dict, ["under_voltage", "over_current"]),
    ])
    def test_endpoint_shape(self, test_client, endpoint, expected_type, required_fields):
        """Each stats endpoint should return 200 with the expected payload shape and fields."""
        response = test_client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, expected_type)
        for field in required_fields:
            assert field in data, f"{endpoint} missing field {field!r}"


class TestStatsValueSemantics:
    """Tests that verify value ranges/types — not just presence."""

    def test_cpu_percent_valid_range(self, test_client):
        """CPU percent should be between 0 and 100."""
        data = test_client.get("/api/stats/cpu").json()
        assert 0 <= data["percent"] <= 100

    def test_memory_total_positive(self, test_client):
        """Memory total should be positive."""
        data = test_client.get("/api/stats/memory").json()
        assert data["total"] > 0

    def test_load_values_non_negative(self, test_client):
        """Load values are strings in main API format; all should be non-negative numbers."""
        data = test_client.get("/api/stats/load").json()
        for key in ("minute_1", "minute_5", "minute_15"):
            assert float(data[key]) >= 0

    def test_network_excludes_loopback(self, test_client):
        """Network should not include the loopback interface."""
        data = test_client.get("/api/stats/network").json()
        assert "lo" not in data

    def test_power_values_are_bool(self, test_client):
        """Power flags should be booleans."""
        data = test_client.get("/api/stats/power").json()
        assert isinstance(data["under_voltage"], bool)
        assert isinstance(data["over_current"], bool)
