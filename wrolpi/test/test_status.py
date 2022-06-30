from decimal import Decimal

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


@pytest.mark.asyncio
async def test_get_cpu_info():
    """Minimum CPU info testing because this will fail in docker, etc."""
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
