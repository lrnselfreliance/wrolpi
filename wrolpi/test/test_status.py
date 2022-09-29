from decimal import Decimal
from unittest import mock

import pytest

from wrolpi import status


@pytest.mark.asyncio
async def test_get_load():
    """Minimum laod testing because this will fail in docker, etc."""
    load = await status.get_load()
    assert isinstance(load, status.SystemLoad)
    assert load.minute_1 is not None and isinstance(load.minute_1, Decimal)
    assert load.minute_5 is not None and isinstance(load.minute_5, Decimal)
    assert load.minute_15 is not None and isinstance(load.minute_15, Decimal)

    with mock.patch('wrolpi.status.get_load_psutil') as mock_get_load_psutil:
        # Fallback to subprocess when psutil is not available.
        mock_get_load_psutil.side_effect = Exception('testing no psutil')
        load = await status.get_load()
        assert isinstance(load, status.SystemLoad)
        assert load.minute_1 is not None
        assert isinstance(load.minute_1, Decimal)


@pytest.mark.asyncio
async def test_get_cpu_info():
    """Minimum CPU info testing because this will fail in docker, etc."""
    info = await status.get_cpu_info()
    assert isinstance(info, status.CPUInfo)
    assert isinstance(info.percent, int)

    with mock.patch('wrolpi.status.get_cpu_info_psutil') as mock_get_cpu_info_psutil:
        # Fallback to subprocess when psutil is not available.
        mock_get_cpu_info_psutil.side_effect = Exception('testing no psutil')
        info = await status.get_cpu_info()
        assert isinstance(info, status.CPUInfo)
        assert isinstance(info.percent, int)


@pytest.mark.asyncio
async def test_get_drives_info():
    """Minimum drives info testing because this will fail in docker, etc."""
    info = await status.get_drives_info()
    assert isinstance(info, list)
    assert len(info) >= 1
    assert isinstance(info[0], status.DriveInfo)

    with mock.patch('wrolpi.status.get_drives_info_psutil') as mock_get_drives_info_psutil:
        # Fallback to subprocess when psutil is not available.
        mock_get_drives_info_psutil.side_effect = Exception('testing no psutil')
        info = await status.get_drives_info()
        assert isinstance(info, list)
        assert len(info) >= 1
        assert isinstance(info[0], status.DriveInfo)


@pytest.mark.asyncio
async def test_get_bandwidth_info():
    """Bandwidth requires psutil"""
    bandwidths = await status.get_bandwidth_info()
    assert bandwidths == []

    await status.bandwidth_worker(2)
    bandwidths = await status.get_bandwidth_info()
    assert isinstance(bandwidths, list)
    assert len(bandwidths) > 0
    assert isinstance(bandwidths[0], status.BandwidthInfo)

    with mock.patch('wrolpi.status.psutil.net_io_counters') as mock_net_io_counters:
        # NO FALLBACK!
        mock_net_io_counters.side_effect = Exception('testing no psutil')
        await status.bandwidth_worker(1)
        bandwidths = await status.get_bandwidth_info()
        assert isinstance(bandwidths[0].bytes_recv, int)
        assert isinstance(bandwidths[0].bytes_sent, int)
        assert isinstance(bandwidths[0].elapsed, int)
        assert isinstance(bandwidths[0].speed, int)
        assert isinstance(bandwidths[0].name, str)
