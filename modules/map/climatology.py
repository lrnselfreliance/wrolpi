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
    1: '245d5eed9b7ca292e88f99885a93d9fe0ddb67ff7b7d8efea2eae038426892d6',
    2: '6b54b071357f50bfa35949242e80198248ef8e64d687ce76e4a82af631c439bd',
    3: 'bc116ea3477aac20b557e704702248edb4160eaadd4abbea3cab4f0a21bfb4b1',
    4: '22662792dd7afe4ebbceb821c507aaafc3b0c87429f792c6e32990f4d041df46',
    5: '48a4d9bbaaec72b1b8b91f81c9710c9f170bd099a0bb93267df9b57f950da6c2',
    6: '5da9c91788d89f31e0443e966e8258049495eb8f65c70d621a355205e74a8d4b',
    7: '371d0959c7b14d3f3fb96001b73535dc40f52a83651ce1e507b786c32fcd7996',
    8: '6cd5de2d9bdbf8156a8cc78b4c84b2eed8cb4690cbf5234a9751d28b676dc213',
    9: 'b12b75249fc56d1bd3e63440588a75ceb35e95dacf20d941345d410ed1c8a8d3',
    10: '23c58a03d7e0f1eb8db92de36d43a6623c32cfa6ebfd230ccfd737c42b94aea3',
    11: '7adb5825f4330d8e82f79cd05b7b41291308f754025766ef69289a2684a5ec1b',
    12: 'd76941dccfac0e997b6cd804b43efd05e5d09ae333efe3380df2bef6eb645784',
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


# The kept files found to be what is expected: path -> (size, mtime) when hashed.
_checked = dict()


def month_path(month: int) -> Optional[Path]:
    """The kept file of `month`, or None if there is none, or it is not the file expected (it is then
    fetched again).  A file is hashed again only after it changes."""
    expected = MONTHS.get(month)
    if not expected:
        return None
    path = climatology_directory() / month_name(month)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    if _checked.get(path) == (stat.st_size, stat.st_mtime_ns):
        return path
    with path.open('rb') as fh:
        actual = hashlib.file_digest(fh, 'sha256').hexdigest()
    if actual != expected:
        _checked.pop(path, None)
        logger.warning(f'{path} is not the climatology expected (sha256 {actual}); it will be fetched again')
        return None
    _checked[path] = (stat.st_size, stat.st_mtime_ns)
    return path


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
    """Fetch the months not yet kept, once there is the Internet and the drive (not in WROL Mode).

    Waits for the flags, rather than returning, so a new WROLPi fetches as soon as it is online, not an hour
    after startup."""
    if not any(MONTHS.values()):
        return
    async with flags.have_internet.wait_for():
        pass
    async with flags.media_mounted.wait_for():
        pass
    if wrol_mode_enabled() or not [m for m in MONTHS if MONTHS[m] and not month_path(m)]:
        return
    await fetch_missing()
