"""The fallout simulator's climatology: the winds aloft of 30 real days of each month, the whole
world (built by wrolpi/scripts/build_fallout_climatology.py from NOAA's reanalysis).  With no
forecast to go on, the simulator runs a burst in each of a month's days and shows how often its
fallout lands where.

The month files are fetched once from the release download location, while there is the Internet,
and each is checked against the sha256 pinned here before it is kept.  From then on it is used
offline.
"""
import asyncio
import hashlib
from pathlib import Path
from typing import List, Optional

from modules.map.lib import get_map_directory
from wrolpi import flags
from wrolpi.api_utils import perpetual_signal
from wrolpi.common import aiohttp_get, logger, wrol_mode_enabled

logger = logger.getChild(__name__)

VERSION = 1
BASE_URL = f'https://wrolpi.nyc3.cdn.digitaloceanspaces.com/fallout/climatology-v{VERSION}'
# The sha256 of each month's file (wrolpi/scripts/build_fallout_climatology.py prints them).
MONTHS = {
    1: None, 2: None, 3: None, 4: None, 5: None, 6: None,
    7: None, 8: None, 9: None, 10: None, 11: None, 12: None,
}
TIMEOUT = 300
# How often (s) missing months are looked for.
CHECK_SECONDS = 3600


class ClimatologyError(Exception):
    """A month could not be fetched, or was not what it should be."""


def climatology_directory() -> Path:
    """Where the months are kept: a hidden directory, which the file lists and search skip."""
    directory = get_map_directory() / '.fallout-climatology' / f'v{VERSION}'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def month_name(month: int) -> str:
    return f'month-{month:02d}.bin.gz'


def month_path(month: int) -> Optional[Path]:
    """The kept file of `month`, or None."""
    if month not in MONTHS:
        return None
    path = climatology_directory() / month_name(month)
    return path if path.is_file() else None


def months_kept() -> List[int]:
    return [month for month in MONTHS if month_path(month)]


def status() -> dict:
    kept = months_kept()
    return dict(version=VERSION, months=kept, missing=[m for m in MONTHS if m not in kept],
                published=all(MONTHS.values()))


async def fetch_month(month: int) -> Path:
    """Fetch `month` from the release download location, check it, and keep it."""
    expected = MONTHS.get(month)
    if not expected:
        raise ClimatologyError(f'No sha256 is known for month {month}')
    url = f'{BASE_URL}/{month_name(month)}'
    try:
        async with aiohttp_get(url, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise ClimatologyError(f'{url} answered HTTP {response.status}')
            data = await response.read()
    except ClimatologyError:
        raise
    except Exception as e:
        raise ClimatologyError(f'Could not fetch {url}: {e}') from e
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ClimatologyError(f'{url} is not the file expected (sha256 {actual})')
    path = climatology_directory() / month_name(month)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
    logger.info(f'Kept the fallout climatology of month {month} ({len(data) / 1e6:.1f} MB)')
    return path


async def fetch_missing() -> List[int]:
    """Fetch every month not yet kept, one after another; the months fetched."""
    fetched = []
    for month in MONTHS:
        if month_path(month) or not MONTHS[month]:
            continue
        try:
            await fetch_month(month)
            fetched.append(month)
        except ClimatologyError as e:
            logger.warning(f'Could not fetch the fallout climatology: {e}')
            break
        # Spread out, as a courtesy to the download location.
        await asyncio.sleep(1)
    return fetched


@perpetual_signal(sleep=CHECK_SECONDS)
async def climatology_worker():
    """Fetch the months not yet kept, while there is the Internet (not in WROL Mode)."""
    if not flags.have_internet.is_set() or not flags.media_mounted.is_set() or wrol_mode_enabled():
        return
    if not any(MONTHS.values()) or not [m for m in MONTHS if not month_path(m)]:
        return
    await fetch_missing()
