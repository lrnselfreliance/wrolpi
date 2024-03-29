from decimal import Decimal
from unittest import mock

import pytest

from wrolpi import status


@pytest.mark.asyncio
async def test_get_load():
    """Test reading load information from /proc/loadavg."""
    load = await status.get_load()
    assert isinstance(load, status.SystemLoad)

    assert isinstance(load.minute_1, Decimal) and load.minute_1 >= 0
    assert isinstance(load.minute_5, Decimal) and load.minute_5 >= 0
    assert isinstance(load.minute_15, Decimal) and load.minute_15 >= 0


@pytest.mark.asyncio
async def test_get_cpu_info():
    """Minimum CPU info testing because this will fail in docker, etc."""
    info = await status.get_cpu_info()
    assert isinstance(info, status.CPUInfo)
    assert isinstance(info.percent, int)
    assert isinstance(info.temperature, int)
    assert isinstance(info.high_temperature, int)
    assert isinstance(info.critical_temperature, int)

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
    nic_bandwidths, disk_bandwidths = await status.get_bandwidth_info()
    assert nic_bandwidths == []
    assert disk_bandwidths == []

    await status.bandwidth_worker(2)
    nic_bandwidths, disk_bandwidths = await status.get_bandwidth_info()
    assert isinstance(nic_bandwidths, list)
    assert len(nic_bandwidths) > 0
    assert isinstance(nic_bandwidths[0], status.NICBandwidthInfo)
    assert isinstance(disk_bandwidths, list)
    assert len(disk_bandwidths) > 0
    assert isinstance(disk_bandwidths[0], status.DiskBandwidthInfo)

    with mock.patch('wrolpi.status.psutil.net_io_counters') as mock_net_io_counters:
        # NO FALLBACK!
        mock_net_io_counters.side_effect = Exception('testing no psutil')
        await status.bandwidth_worker(1)
        nic_bandwidths, disk_bandwidths = await status.get_bandwidth_info()
        assert isinstance(nic_bandwidths[0].bytes_recv, int)
        assert isinstance(nic_bandwidths[0].bytes_sent, int)
        assert isinstance(nic_bandwidths[0].elapsed, int)
        assert isinstance(nic_bandwidths[0].speed, int)
        assert isinstance(nic_bandwidths[0].name, str)
