from decimal import Decimal
from unittest import mock

import pytest

from wrolpi import status
from wrolpi.test.common import skip_circleci, skip_macos
from wrolpi.vars import IS_MACOS


@pytest.mark.asyncio
async def test_get_load(async_client):
    """Test reading load information from /proc/loadavg."""
    load = await status.get_load_stats()
    assert isinstance(load, status.SystemLoad)

    assert isinstance(load.minute_1, Decimal) and load.minute_1 >= 0
    assert isinstance(load.minute_5, Decimal) and load.minute_5 >= 0
    assert isinstance(load.minute_15, Decimal) and load.minute_15 >= 0


@skip_circleci
@pytest.mark.asyncio
async def test_get_cpu_stats(async_client):
    """Minimum CPU info testing because this will fail in docker, etc."""
    info = await status.get_cpu_stats()
    assert isinstance(info, status.CPUInfo)
    assert isinstance(info.percent, int)
    if not IS_MACOS:
        assert isinstance(info.temperature, int)


@pytest.mark.asyncio
@skip_macos
async def test_iostat_stats(async_client):
    info = await status.get_iostat_stats()
    assert isinstance(info, status.IostatInfo)
    assert isinstance(info.percent_idle, float)


@pytest.mark.asyncio
async def test_power_stats(async_client):
    info = await status.get_power_stats()
    assert isinstance(info, status.PowerStats)
    assert info.under_voltage is False
    assert info.over_current is False


@skip_circleci
@skip_macos
@pytest.mark.asyncio
async def test_get_drives_stats(async_client):
    """Minimum drives info testing because this will fail in docker, etc."""
    info = await status.get_drives_stats()
    assert isinstance(info, list)
    assert len(info) >= 1
    assert isinstance(info[0], status.DriveInfo)

    with mock.patch('wrolpi.status.get_drives_info_psutil') as mock_get_drives_stats_psutil:
        # Fallback to subprocess when psutil is not available.
        mock_get_drives_stats_psutil.side_effect = Exception('testing no psutil')
        info = await status.get_drives_stats()
        assert isinstance(info, list)
        assert len(info) >= 1
        assert isinstance(info[0], status.DriveInfo)


@skip_circleci
@pytest.mark.asyncio
async def test_status_worker(async_client, start_status_worker):
    """Status worker calls itself perpetually, but can be limited during testing."""
    from wrolpi.api_utils import api_app
    assert async_client.sanic_app.shared_ctx.status['cpu_stats'] == dict()

    # Status worker fills out stats as it goes along.
    await status.status_worker(count=2)
    assert api_app.shared_ctx.status['nic_bandwidth_stats']
    assert 'bytes_recv' in list(api_app.shared_ctx.status['nic_bandwidth_stats'].values())[0]
    assert api_app.shared_ctx.status['disk_bandwidth_stats']
    assert 'bytes_read' in list(api_app.shared_ctx.status['disk_bandwidth_stats'].values())[0]

    assert isinstance(api_app.shared_ctx.status.get('cpu_stats'), dict)
    assert isinstance(api_app.shared_ctx.status.get('load_stats'), dict)
    assert isinstance(api_app.shared_ctx.status.get('drives_stats'), list)
    assert isinstance(api_app.shared_ctx.status.get('processes_stats'), list)
    assert isinstance(api_app.shared_ctx.status.get('memory_stats'), dict)
    assert isinstance(api_app.shared_ctx.status.get('iostat_stats'), dict)
    assert isinstance(api_app.shared_ctx.status.get('power_stats'), dict)
