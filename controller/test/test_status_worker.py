"""
Tests for the status worker background task and aggregated stats endpoint.
"""

from datetime import datetime
from unittest import mock

import pytest


class TestCollectAllStatus:
    """Tests for collect_all_status function."""

    @pytest.mark.asyncio
    async def test_collects_all_stats_and_iso_timestamp(self):
        """Should collect every status type and include a parseable ISO timestamp."""
        from controller.lib.status_worker import collect_all_status

        status = await collect_all_status()

        for key in (
            "cpu_stats", "memory_stats", "load_stats", "drives_stats",
            "nic_bandwidth_stats", "power_stats", "last_status",
        ):
            assert key in status
        datetime.fromisoformat(status["last_status"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("collector,result_key,failure_value", [
        ("get_cpu_status", "cpu_stats", None),
        ("get_memory_status", "memory_stats", None),
        ("get_drive_status", "drives_stats", []),
        ("get_network_status", "nic_bandwidth_stats", {}),
    ])
    async def test_individual_collector_failure(self, collector, result_key, failure_value):
        """A single collector raising should leave the failed key at its fallback value
        and let the other collectors still populate the result."""
        from controller.lib.status_worker import collect_all_status

        with mock.patch(
            f"controller.lib.status_worker.{collector}",
            side_effect=Exception(f"{collector} error"),
        ):
            status = await collect_all_status()
        assert status[result_key] == failure_value
        # At least one other collector should still have produced real data.
        other_keys = [k for k in ("cpu_stats", "memory_stats") if k != result_key]
        assert any(status[k] is not None for k in other_keys)


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
    """Tests for the /api/stats aggregated endpoint."""

    def test_aggregated_stats_payload(self, test_client):
        """Endpoint should return 200 with every status key and the expected sub-shapes."""
        response = test_client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()

        for key in (
            "cpu_stats", "memory_stats", "load_stats", "drives_stats",
            "nic_bandwidth_stats", "power_stats", "last_status",
        ):
            assert key in data
        # last_status is an ISO timestamp.
        datetime.fromisoformat(data["last_status"])
        # Sub-field shape spot-checks.
        for field in ("percent", "cores"):
            assert field in data["cpu_stats"]
        for field in ("total", "used", "free"):
            assert field in data["memory_stats"]
        for field in ("minute_1", "minute_5", "minute_15"):
            assert field in data["load_stats"]
        assert isinstance(data["drives_stats"], list)
        assert isinstance(data["nic_bandwidth_stats"], dict)

    def test_aggregated_stats_trailing_slash(self, test_client):
        """Aggregated stats should work with trailing slash."""
        response = test_client.get("/api/stats/")
        assert response.status_code == 200
