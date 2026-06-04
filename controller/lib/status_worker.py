"""
Background status worker for WROLPi Controller.

Periodically collects all system status and caches it in app.state
for O(1) response times on API endpoints.
"""

import asyncio
import logging
import multiprocessing
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from controller.lib.smart import build_smart_stats
from controller.lib.status import (
    get_cpu_status,
    get_disk_bandwidth_status,
    get_drive_status,
    get_iostat_status,
    get_load_status,
    get_memory_status,
    get_network_status,
    get_power_status,
    get_processes_status,
    get_uptime_status,
)

# Type alias for cached status dict
CachedStatus = dict

# SMART reads can wake spun-down USB drives, so collect them far less often
# than the fast (5s) stats.
SMART_REFRESH_SECONDS = 60


async def collect_all_status(smart_stats: Optional[dict] = None) -> CachedStatus:
    """
    Collect all status information concurrently.

    Returns a dict with all status types. Individual failures return None
    for that stat type rather than failing the entire collection.

    ``smart_stats`` is collected on a slower cadence by the worker loop (see
    ``status_worker_loop``) and passed in so it lands in the same cached
    payload as the fast 5s stats.
    """
    # Run all status collections concurrently using asyncio.to_thread
    # since the status functions are synchronous (use psutil)
    cpu, memory, load, drives, network, power, iostat, processes, disk_bandwidth, uptime = await asyncio.gather(
        asyncio.to_thread(get_cpu_status),
        asyncio.to_thread(get_memory_status),
        asyncio.to_thread(get_load_status),
        asyncio.to_thread(get_drive_status),
        asyncio.to_thread(get_network_status),
        asyncio.to_thread(get_power_status),
        asyncio.to_thread(get_iostat_status),
        asyncio.to_thread(get_processes_status),
        asyncio.to_thread(get_disk_bandwidth_status),
        asyncio.to_thread(get_uptime_status),
        return_exceptions=True,
    )

    # Handle individual failures gracefully - return None for failed stats
    status = {
        "cpu_stats": cpu if not isinstance(cpu, Exception) else None,
        "memory_stats": memory if not isinstance(memory, Exception) else None,
        "load_stats": load if not isinstance(load, Exception) else None,
        "drives_stats": drives if not isinstance(drives, Exception) else [],
        "nic_bandwidth_stats": network if not isinstance(network, Exception) else {},
        "power_stats": power if not isinstance(power, Exception) else None,
        "iostat_stats": iostat if not isinstance(iostat, Exception) else None,
        "processes_stats": processes if not isinstance(processes, Exception) else [],
        "disk_bandwidth_stats": disk_bandwidth if not isinstance(disk_bandwidth, Exception) else {},
        "uptime_stats": uptime if not isinstance(uptime, Exception) else None,
        "smart_stats": smart_stats,
        "last_status": datetime.now().isoformat(),
    }

    return status


def get_adaptive_sleep(load_stats: Optional[dict], base_sleep: float = 5.0) -> float:
    """
    Calculate adaptive sleep time based on system load.

    If system is under heavy load (load_1 > cpu_count), increase sleep time
    to reduce overhead on the system.

    Args:
        load_stats: Dict with minute_1 key (string), or None
        base_sleep: Base sleep interval in seconds

    Returns:
        Sleep time in seconds (may be > base_sleep if system is stressed)
    """
    if load_stats is None:
        return base_sleep

    try:
        load_1 = float(load_stats.get("minute_1", 0))
        cpu_count = multiprocessing.cpu_count()

        if load_1 > cpu_count:
            # System is stressed, slow down status updates
            return (base_sleep * load_1) / cpu_count
    except (ValueError, TypeError, ZeroDivisionError):
        pass

    return base_sleep


async def refresh_smart_stats(app, now: datetime) -> dict:
    """Collect SMART stats, but no more than once per SMART_REFRESH_SECONDS.

    SMART reads can wake spun-down USB drives, so this runs on a slow
    cadence independent of the fast status loop.  The result and its
    timestamp are cached on ``app.state``; between refreshes the cached
    value is returned unchanged.  ``build_smart_stats`` is given the prior
    result so it can reuse readings for drives that are now asleep.
    """
    last = getattr(app.state, "smart_last_collected", None)
    cache = getattr(app.state, "smart_cache", None)
    due = (
        cache is None
        or last is None
        or (now - last).total_seconds() >= SMART_REFRESH_SECONDS
    )
    if due:
        # build_smart_stats shells out to smartctl/hdparm; keep it off the loop.
        cache = await asyncio.to_thread(build_smart_stats, cache)
        app.state.smart_cache = cache
        app.state.smart_last_collected = now
    return cache


async def status_worker_loop(app, base_sleep: float = 5.0):
    """
    Background loop that continuously collects status data.

    Runs indefinitely until cancelled. Stores collected status in
    app.state.cached_status for fast endpoint access.

    Args:
        app: FastAPI application instance
        base_sleep: Base sleep interval in seconds (default 5s)
    """
    logger.info("Status worker started")

    while True:
        try:
            # SMART on its own slow cadence; everything else every cycle.
            smart_stats = await refresh_smart_stats(app, datetime.now())

            # Collect all status data
            status = await collect_all_status(smart_stats=smart_stats)

            # Store in app.state (thread-safe for reading in single-worker uvicorn)
            app.state.cached_status = status

            # Calculate adaptive sleep based on load
            sleep_time = get_adaptive_sleep(status.get("load_stats"), base_sleep)

        except asyncio.CancelledError:
            logger.info("Status worker cancelled")
            raise
        except Exception as e:
            logger.error("Status worker error: %s", e)
            sleep_time = base_sleep

        await asyncio.sleep(sleep_time)
