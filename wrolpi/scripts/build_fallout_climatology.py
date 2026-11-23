#!/usr/bin/env python3
"""Build the fallout simulator's climatology: the winds aloft of 30 real days of each month, the
whole world, for running a burst in each and counting where its fallout lands how often.

Usage:
    python wrolpi/scripts/build_fallout_climatology.py <output_dir> [--cache DIR] [--months 1,2,...]

Run by the maintainers, once (and when the period changes), on a machine with the Internet.  It
writes month-01.bin.gz ... month-12.bin.gz and manifest.json to <output_dir>, for the release
download location (fallout/climatology-v1/).  The sha256 of each file is then pinned in
modules/map/climatology.py; WROLPi fetches them from there.

Source: NCEP/NCAR Reanalysis 1 (NOAA PSL; public domain), through PSL's OPeNDAP server, one small
binary request for each day and wind component, spaced out:
  - the days: for each month, one day from each year 1991-2020 (30 days), spread across the month,
    at 12Z; which year gets which day is shuffled with a fixed seed;
  - u and v (m/s) at 14 pressure levels (1000-50 hPa), 2.5 degrees;
  - the heights of the levels: the 1991-2020 monthly mean geopotential height.

A month's file (before gzip): b'WFCL', version (uint16 LE), header length (uint32 LE), the header
(JSON: month, levels, the grid, the days, the source), then the heights (int16 LE, [level][lat][lon],
m), then each day's u and v (int8, [level][lat][lon], m/s rounded; |wind| <= 127).
"""
import argparse
import calendar
import gzip
import hashlib
import json
import random
import struct
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

VERSION = 1
BASE = 'https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis'
HEIGHTS = f'{BASE}/Monthlies/pressure/hgt.mon.ltm.1991-2020.nc'
LEVELS = (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50)  # the first 14 of 17
YEARS = range(1991, 2021)
SEED = 20261122
NLAT, NLON = 73, 144  # 90 to -90, 0 to 357.5, every 2.5 degrees
# Between two requests (s): PSL's server is shared.
PAUSE = 2
USER_AGENT = 'WROLPi'


def days_of_month(month: int):
    """The 30 sampled days of `month`: one in each year, spread across the month."""
    rng = random.Random(SEED + month)
    years = list(YEARS)
    rng.shuffle(years)
    out = []
    for k, year in enumerate(years):
        length = calendar.monthrange(year, month)[1]
        day = 1 + (k * length) // len(years)
        out.append(f'{year}-{month:02d}-{day:02d}')
    return sorted(out)


def fetch(url: str, cache: Path) -> bytes:
    """`url`'s body, from the cache if it has it."""
    path = cache / hashlib.sha256(url.encode()).hexdigest()
    if path.exists():
        return path.read_bytes()
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
            break
        except Exception as e:  # noqa: BLE001 - retried, then raised
            if attempt == 4:
                raise
            print(f'  retrying in {PAUSE * 2 ** (attempt + 2)} s: {e}', file=sys.stderr)
            time.sleep(PAUSE * 2 ** (attempt + 2))
    time.sleep(PAUSE)
    path.write_bytes(body)
    return body


def dods_array(body: bytes, shape) -> np.ndarray:
    """The one Float32 array of an OPeNDAP binary (.dods) response for `var.var[...]`."""
    at = body.index(b'\nData:\n') + len(b'\nData:\n')
    n, n2 = struct.unpack('>II', body[at:at + 8])
    if n != n2 or n != int(np.prod(shape)):
        raise ValueError(f'Expected {np.prod(shape)} values, got {n}')
    return np.frombuffer(body[at + 8:at + 8 + 4 * n], dtype='>f4').astype(np.float32).reshape(shape)


def day_winds(day: str, cache: Path):
    year = int(day[:4])
    # The index of 12Z of `day` in its year's 6-hourly file.
    t = int((np.datetime64(day) - np.datetime64(f'{year}-01-01')).astype(int)) * 4 + 2
    shape = (len(LEVELS), NLAT, NLON)
    out = []
    for var in ('uwnd', 'vwnd'):
        url = f'{BASE}/pressure/{var}.{year}.nc.dods?{var}.{var}[{t}][0:{len(LEVELS) - 1}][0:{NLAT - 1}][0:{NLON - 1}]'
        out.append(dods_array(fetch(url, cache), (1,) + shape)[0])
    return out


def build_month(month: int, heights: np.ndarray, cache: Path, output: Path) -> dict:
    days = days_of_month(month)
    header = dict(
        version=VERSION, month=month, levels_hpa=list(LEVELS),
        lat=[90.0, -2.5, NLAT], lon=[0.0, 2.5, NLON], days=days, hour_utc=12,
        source='NCEP/NCAR Reanalysis 1, NOAA PSL (public domain); heights: 1991-2020 monthly mean geopotential height',
        seed=SEED, wind='int8 m/s, rounded', height='int16 m',
    )
    head = json.dumps(header, separators=(',', ':')).encode()
    parts = [b'WFCL', struct.pack('<HI', VERSION, len(head)), head,
             np.round(heights[month - 1]).astype('<i2').tobytes()]
    largest = 0
    for k, day in enumerate(days):
        u, v = day_winds(day, cache)
        largest = max(largest, float(np.abs(u).max()), float(np.abs(v).max()))
        parts += [np.clip(np.round(u), -127, 127).astype(np.int8).tobytes(),
                  np.clip(np.round(v), -127, 127).astype(np.int8).tobytes()]
        print(f'  {day} ({k + 1}/{len(days)})', file=sys.stderr)
    data = gzip.compress(b''.join(parts), 9)
    name = f'month-{month:02d}.bin.gz'
    (output / name).write_bytes(data)
    print(f'{name}: {len(data) / 1e6:.1f} MB, fastest wind {largest:.0f} m/s', file=sys.stderr)
    return dict(name=name, sha256=hashlib.sha256(data).hexdigest(), size=len(data), days=days)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output')
    parser.add_argument('--cache', default=None, help='Where fetched responses are kept (default: <output>/.cache)')
    parser.add_argument('--months', default=','.join(str(m) for m in range(1, 13)))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache) if args.cache else output / '.cache'
    cache.mkdir(parents=True, exist_ok=True)
    heights = dods_array(fetch(f'{HEIGHTS}.dods?hgt.hgt[0:11][0:{len(LEVELS) - 1}][0:{NLAT - 1}][0:{NLON - 1}]', cache),
                         (12, len(LEVELS), NLAT, NLON))
    files = [build_month(int(m), heights, cache, output) for m in args.months.split(',')]
    manifest = dict(version=VERSION, files=files)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps({f['name']: f['sha256'] for f in files}, indent=1))


if __name__ == '__main__':
    main()
