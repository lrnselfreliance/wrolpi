"""
Tests for the status worker background task and aggregated stats endpoint.
"""

from datetime import datetime
from unittest import mock

import pytest


class TestCollectAllStatus:
    """Tests for collect_all_status function."""

    @pytest.mark.asyncio
    async def test_collects_all_stats(self):
        """Should collect all status types."""
        from controller.lib.status_worker import collect_all_status

        status = await collect_all_status()

        assert "cpu_stats" in status
        assert "memory_stats" in status
        assert "load_stats" in status
        assert "drives_stats" in status
        assert "nic_bandwidth_stats" in status
        assert "power_stats" in status
        assert "last_status" in status

    @pytest.mark.asyncio
    async def test_last_status_is_iso_timestamp(self):
        """Should include a valid ISO timestamp."""
        from controller.lib.status_worker import collect_all_status

        status = await collect_all_status()

        # Should be parseable as ISO datetime
        datetime.fromisoformat(status["last_status"])

    @pytest.mark.asyncio
    async def test_handles_cpu_failure(self):
        """Should handle failures in CPU stat collector."""
        from controller.lib.status_worker import collect_all_status

        with mock.patch(
            "controller.lib.status_worker.get_cpu_status",
            side_effect=Exception("CPU error")
        ):
            status = await collect_all_status()

            # CPU should be None but others should work
            assert status["cpu_stats"] is None
            assert status["memory_stats"] is not None

    @pytest.mark.asyncio
    async def test_handles_memory_failure(self):
        """Should handle failures in memory stat collector."""
        from controller.lib.status_worker import collect_all_status

        with mock.patch(
            "controller.lib.status_worker.get_memory_status",
            side_effect=Exception("Memory error")
        ):
            status = await collect_all_status()

            assert status["memory_stats"] is None
            assert status["cpu_stats"] is not None

    @pytest.mark.asyncio
    async def test_drives_stats_is_list_on_failure(self):
        """Should return empty list for drives on failure."""
        from controller.lib.status_worker import collect_all_status

        with mock.patch(
            "controller.lib.status_worker.get_drive_status",
            side_effect=Exception("Drive error")
        ):
            status = await collect_all_status()

            assert status["drives_stats"] == []

    @pytest.mark.asyncio
    async def test_nic_stats_is_dict_on_failure(self):
        """Should return empty dict for network on failure."""
        from controller.lib.status_worker import collect_all_status

        with mock.patch(
            "controller.lib.status_worker.get_network_status",
            side_effect=Exception("Network error")
        ):
            status = await collect_all_status()

            assert status["nic_bandwidth_stats"] == {}


class TestGetAdaptiveSleep:
    """Tests for adaptive sleep calculation."""

    def test_returns_base_sleep_when_load_is_low(self):
        """Should return base sleep when load is below CPU count."""
        from controller.lib.status_worker import get_adaptive_sleep

        with mock.patch("multiprocessing.cpu_count", return_value=4):
            load_stats = {"minute_1": "0.5"}
            sleep = get_adaptive_sleep(load_stats, base_sleep=5.0)
            assert sleep == 5.0

    def test_returns_base_sleep_when_load_equals_cpu_count(self):
        """Should return base sleep when load equals CPU count."""
        from controller.lib.status_worker import get_adaptive_sleep

        with mock.patch("multiprocessing.cpu_count", return_value=4):
            load_stats = {"minute_1": "4.0"}
            sleep = get_adaptive_sleep(load_stats, base_sleep=5.0)
            assert sleep == 5.0

    def test_increases_sleep_when_load_exceeds_cpu_count(self):
        """Should increase sleep when load exceeds CPU count."""
        from controller.lib.status_worker import get_adaptive_sleep

        with mock.patch("multiprocessing.cpu_count", return_value=4):
            load_stats = {"minute_1": "8.0"}  # 2x CPU count
            sleep = get_adaptive_sleep(load_stats, base_sleep=5.0)
            # Expected: (5.0 * 8.0) / 4 = 10.0
            assert sleep == 10.0

    def test_handles_none_load_stats(self):
        """Should return base sleep when load_stats is None."""
        from controller.lib.status_worker import get_adaptive_sleep

        sleep = get_adaptive_sleep(None, base_sleep=5.0)
        assert sleep == 5.0

    def test_handles_empty_load_stats(self):
        """Should return base sleep when load_stats is empty dict."""
        from controller.lib.status_worker import get_adaptive_sleep

        sleep = get_adaptive_sleep({}, base_sleep=5.0)
        assert sleep == 5.0

    def test_handles_invalid_load_value(self):
        """Should return base sleep when load value is invalid."""
        from controller.lib.status_worker import get_adaptive_sleep

        load_stats = {"minute_1": "invalid"}
        sleep = get_adaptive_sleep(load_stats, base_sleep=5.0)
        assert sleep == 5.0

    def test_handles_missing_minute_1_key(self):
        """Should return base sleep when minute_1 key is missing."""
        from controller.lib.status_worker import get_adaptive_sleep

        load_stats = {"minute_5": "2.0"}
        sleep = get_adaptive_sleep(load_stats, base_sleep=5.0)
        assert sleep == 5.0


class TestAggregatedStatsEndpoint:
    """Tests for the new /api/stats aggregated endpoint."""

    def test_aggregated_stats_returns_200(self, test_client):
        """Aggregated stats endpoint should return 200 OK."""
        response = test_client.get("/api/stats")
        assert response.status_code == 200

    def test_aggregated_stats_returns_all_fields(self, test_client):
        """Aggregated stats should include all status types."""
        response = test_client.get("/api/stats")
        data = response.json()

        assert "cpu_stats" in data
        assert "memory_stats" in data
        assert "load_stats" in data
        assert "drives_stats" in data
        assert "nic_bandwidth_stats" in data
        assert "power_stats" in data
        assert "last_status" in data

    def test_aggregated_stats_has_valid_timestamp(self, test_client):
        """Should include a timestamp of when data was collected."""
        response = test_client.get("/api/stats")
        data = response.json()

        assert "last_status" in data
        # Should be ISO format timestamp
        datetime.fromisoformat(data["last_status"])

    def test_aggregated_stats_cpu_has_expected_fields(self, test_client):
        """CPU stats should have expected fields."""
        response = test_client.get("/api/stats")
        data = response.json()

        cpu = data["cpu_stats"]
        assert cpu is not None
        assert "percent" in cpu
        assert "cores" in cpu

    def test_aggregated_stats_memory_has_expected_fields(self, test_client):
        """Memory stats should have expected fields."""
        response = test_client.get("/api/stats")
        data = response.json()

        memory = data["memory_stats"]
        assert memory is not None
        assert "total" in memory
        assert "used" in memory
        assert "free" in memory

    def test_aggregated_stats_load_has_expected_fields(self, test_client):
        """Load stats should have expected fields."""
        response = test_client.get("/api/stats")
        data = response.json()

        load = data["load_stats"]
        assert load is not None
        assert "minute_1" in load
        assert "minute_5" in load
        assert "minute_15" in load

    def test_aggregated_stats_drives_is_list(self, test_client):
        """Drives stats should be a list."""
        response = test_client.get("/api/stats")
        data = response.json()

        assert isinstance(data["drives_stats"], list)

    def test_aggregated_stats_network_is_dict(self, test_client):
        """Network stats should be a dict."""
        response = test_client.get("/api/stats")
        data = response.json()

        assert isinstance(data["nic_bandwidth_stats"], dict)

    def test_aggregated_stats_trailing_slash(self, test_client):
        """Aggregated stats should work with trailing slash."""
        response = test_client.get("/api/stats/")
        assert response.status_code == 200


class TestOpenAPIIncludesAggregatedStats:
    """Test that OpenAPI includes the new aggregated endpoint."""

    def test_openapi_has_aggregated_stats_path(self, test_client):
        """OpenAPI schema should include /api/stats path."""
        response = test_client.get("/openapi.json")
        data = response.json()
        # Check for either with or without trailing slash
        has_path = "/api/stats" in data["paths"] or "/api/stats/" in data["paths"]
        assert has_path, f"Expected /api/stats in paths, got: {list(data['paths'].keys())}"
