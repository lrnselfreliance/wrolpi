"""
Background status worker for WROLPi Controller.

Periodically collects all system status and caches it in app.state
for O(1) response times on API endpoints.
"""

import asyncio
import multiprocessing
from datetime import datetime
from typing import Optional

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
)

# Type alias for cached status dict
CachedStatus = dict


async def collect_all_status() -> CachedStatus:
    """
    Collect all status information concurrently.

    Returns a dict with all status types. Individual failures return None
    for that stat type rather than failing the entire collection.
    """
    # Run all status collections concurrently using asyncio.to_thread
    # since the status functions are synchronous (use psutil)
    cpu, memory, load, drives, network, power, iostat, processes, disk_bandwidth = await asyncio.gather(
        asyncio.to_thread(get_cpu_status),
        asyncio.to_thread(get_memory_status),
        asyncio.to_thread(get_load_status),
        asyncio.to_thread(get_drive_status),
        asyncio.to_thread(get_network_status),
        asyncio.to_thread(get_power_status),
        asyncio.to_thread(get_iostat_status),
        asyncio.to_thread(get_processes_status),
        asyncio.to_thread(get_disk_bandwidth_status),
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


async def status_worker_loop(app, base_sleep: float = 5.0):
    """
    Background loop that continuously collects status data.

    Runs indefinitely until cancelled. Stores collected status in
    app.state.cached_status for fast endpoint access.

    Args:
        app: FastAPI application instance
        base_sleep: Base sleep interval in seconds (default 5s)
    """
    print("Status worker started")

    while True:
        try:
            # Collect all status data
            status = await collect_all_status()

            # Store in app.state (thread-safe for reading in single-worker uvicorn)
            app.state.cached_status = status

            # Calculate adaptive sleep based on load
            sleep_time = get_adaptive_sleep(status.get("load_stats"), base_sleep)

        except asyncio.CancelledError:
            print("Status worker cancelled")
            raise
        except Exception as e:
            print(f"Status worker error: {e}")
            sleep_time = base_sleep

        await asyncio.sleep(sleep_time)
