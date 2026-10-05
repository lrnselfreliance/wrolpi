#!/usr/bin/env python3
"""
Build the offline solar climatology used by the Solar calculator.

Downloads NASA POWER's 2001-2020 monthly climatology for the whole globe and packs it into
app/public/data/solar-climatology.bin, which the React app fetches when the Solar calculator opens.
This needs the Internet and is run by a developer; WROLPi never runs it.  The output only changes
when NASA publishes a new climatology period, so regenerating it should be rare.

    python3 scripts/build_solar_climatology.py

Downloaded tiles are cached (see --cache), so an interrupted run resumes where it stopped.

NASA POWER data is licensed CC BY 4.0.  The build also writes solar-climatology.LICENSE.txt beside the
data, crediting NASA as it asks (https://power.larc.nasa.gov/docs/referencing/), with the API version,
the date the data was downloaded, and how WROLPi changed it.

File format (all integers little-endian), decoded by app/src/components/calculators/solarData.js:

    bytes 0-3   b"WSOL"
    byte  4     format version (1)
    byte  5     number of parameters (4)
    bytes 6-7   reserved (0)
    then        uint8 values, [parameter][month][row][column]

Rows are 1° latitude bands centered on -89.5 ... 89.5 (south to north), columns are 1° longitude
bands centered on -179.5 ... 179.5 (west to east).  255 means no data.  Each parameter is stored as
round((value + offset) / step); see PARAMETERS.
"""
import argparse
import datetime
import json
import math
import pathlib
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO / 'app/public/data/solar-climatology.bin'
DEFAULT_CACHE = REPO / 'scripts/.solar_climatology_cache'

API = 'https://power.larc.nasa.gov/api/temporal/climatology/regional'
# The regional endpoint accepts at most a 10° x 10° box and one parameter per request.
TILE = 10
MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
ROWS, COLUMNS = 180, 360
MISSING = 255
VERSION = 1

# NASA's requested acknowledgment.  Must match CLIMATOLOGY_ACKNOWLEDGMENT in solarData.js.
ACKNOWLEDGMENT = ('The data was obtained from National Aeronautics and Space Administration (NASA) Langley '
                  'Research Center\'s Prediction Of Worldwide Energy Resources (POWER) project funded through the '
                  'NASA Earth Science Division.')
LICENSE = 'Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/'
# CC BY 4.0 requires saying what was changed.  Must match CLIMATOLOGY_CHANGES in solarData.js.
CHANGES = ('WROLPi modified the data: values are rounded to fit one byte each (0.04 kWh/m²/day for irradiance, '
           '0.004 for albedo, 0.5 °C for temperature), temperatures are averaged from NASA\'s 0.5° x 0.625° grid '
           'into 1° cells, and the calculator interpolates between cells.')

# (NASA parameter, offset, step).  Must match PARAMETERS in solarData.js, in the same order.
PARAMETERS = [
    ('ALLSKY_SFC_SW_DWN', 0, 0.04),  # global horizontal, kWh/m²/day, 0-10.16
    ('ALLSKY_SFC_SW_DIFF', 0, 0.04),  # diffuse horizontal, kWh/m²/day
    ('ALLSKY_SRF_ALB', 0, 0.004),  # surface albedo, 0-1.016
    ('T2M', 70, 0.5),  # air temperature at 2 m, °C, -70 to +57
]


def tile_url(parameter, lat_min, lon_min):
    query = urllib.parse.urlencode({
        'parameters': parameter,
        'community': 'RE',
        'latitude-min': lat_min,
        'latitude-max': lat_min + TILE,
        'longitude-min': lon_min,
        'longitude-max': lon_min + TILE,
        'format': 'JSON',
    })
    return f'{API}?{query}'


def tile_path(cache, parameter, lat_min, lon_min):
    return cache / f'{parameter}_{lat_min}_{lon_min}.json'


def fetch_tile(parameter, lat_min, lon_min, cache, pause, retries=8):
    """Return the tile's GeoJSON, from the cache when possible.

    NASA rate limits the API (HTTP 429); back off for up to 10 minutes rather than give up, since a
    full build is about 2,600 requests.
    """
    path = tile_path(cache, parameter, lat_min, lon_min)
    if path.is_file():
        return json.loads(path.read_text())

    delay = 30
    for attempt in range(retries):
        try:
            time.sleep(pause)
            with urllib.request.urlopen(tile_url(parameter, lat_min, lon_min), timeout=180) as response:
                data = json.loads(response.read())
            if 'features' not in data:
                raise ValueError(f'No features: {data.get("messages")}')
            path.write_text(json.dumps(data))
            return data
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if attempt == retries - 1:
                raise
            print(f'  retrying {parameter} {lat_min},{lon_min} in {delay}s: {e}', file=sys.stderr, flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 600)


def bin_points(points):
    """Average points into 1° cells.  `points` maps (lon, lat) to 12 monthly values.

    Solar parameters are already on the 1° grid (one point per cell).  Temperature comes on a finer
    0.5° x 0.625° grid, so several points average into each cell.
    """
    sums = {}
    for (lon, lat), values in points.items():
        row = min(ROWS - 1, max(0, math.floor(lat + 90)))
        column = math.floor(lon + 180) % COLUMNS
        cell = sums.setdefault((row, column), [[0.0, 0] for _ in MONTHS])
        for month, value in enumerate(values):
            if value is not None:
                cell[month][0] += value
                cell[month][1] += 1
    return {cell: [s / n if n else None for s, n in months] for cell, months in sums.items()}


def notice(api, accessed):
    """The attribution written beside the data.  `api` is like "POWER Climatology API v2.10.0"."""
    parameters = ', '.join(p for p, _, _ in PARAMETERS)
    return (
        'Solar climatology for the WROLPi Solar calculator\n'
        '\n'
        'Source: NASA POWER, https://power.larc.nasa.gov/\n'
        f'Data: 2001-2020 monthly climatology of {parameters}, on a 1° grid.\n'
        f'The data was obtained from the POWER Project\'s {api} version on {accessed:%Y/%m/%d}.\n'
        '\n'
        f'{ACKNOWLEDGMENT}\n'
        '\n'
        f'License: {LICENSE}\n'
        '\n'
        f'Changes: {CHANGES}\n'
    )


def quantize(value, offset, step):
    if value is None:
        return MISSING
    return max(0, min(MISSING - 1, round((value + offset) / step)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--cache', type=pathlib.Path, default=DEFAULT_CACHE)
    parser.add_argument('--workers', type=int, default=1, help='Concurrent requests; NASA rate limits the API.')
    parser.add_argument('--pause', type=float, default=1.0, help='Seconds to wait before each request.')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    tiles = [(lat, lon) for lat in range(-90, 90, TILE) for lon in range(-180, 180, TILE)]
    out = bytearray(b'WSOL' + struct.pack('<BBH', VERSION, len(PARAMETERS), 0))
    apis = set()

    for parameter, offset, step in PARAMETERS:
        print(f'{parameter}: {len(tiles)} tiles', flush=True)
        points = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch_tile, parameter, lat, lon, args.cache, args.pause) for lat, lon in tiles]
            for done, future in enumerate(as_completed(futures), 1):
                data = future.result()
                header = data.get('header')
                fill = header.get('fill_value', -999) if isinstance(header, dict) else -999
                if isinstance(header, dict) and 'api' in header:
                    apis.add(f'{header["api"]["name"]} {header["api"]["version"]}')
                for feature in data['features']:
                    lon, lat = feature['geometry']['coordinates'][:2]
                    monthly = feature['properties']['parameter'][parameter]
                    # Tiles share edges; a point on an edge arrives twice with the same value.
                    points[(lon, lat)] = [None if monthly[m] == fill else monthly[m] for m in MONTHS]
                if done % 50 == 0:
                    print(f'  {done}/{len(tiles)}', flush=True)

        cells = bin_points(points)
        grid = bytearray([MISSING]) * (12 * ROWS * COLUMNS)
        for (row, column), months in cells.items():
            for month, value in enumerate(months):
                grid[(month * ROWS + row) * COLUMNS + column] = quantize(value, offset, step)
        missing = grid.count(MISSING)
        print(f'  {len(points)} points into {len(cells)} cells; {missing} missing values')
        out += grid

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    print(f'Wrote {args.output} ({len(out):,} bytes)')

    # The access date is when the newest tile was downloaded, which a resumed build keeps honest.
    newest = max(tile_path(args.cache, p, lat, lon).stat().st_mtime
                 for p, _, _ in PARAMETERS for lat, lon in tiles)
    accessed = datetime.date.fromtimestamp(newest)
    license_path = args.output.with_name(args.output.stem + '.LICENSE.txt')
    license_path.write_text(notice(' / '.join(sorted(apis)), accessed), encoding='utf-8')
    print(f'Wrote {license_path}')


if __name__ == '__main__':
    main()
