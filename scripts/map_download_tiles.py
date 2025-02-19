#! /usr/bin/env python3
"""Used to download many map tiles from the Map service into the current directory.

Example:  To download all tiles of the US state of Kansas, run the script like so:

/opt/wrolpi/venv/bin/python /opt/wrolpi/scripts/map_download_tiles.py 40.011647534727125 -102.06383712982996 37.030883772380065 -94.61534551981345

The script will download zoom levels 6 to 12 by default, this will show most of a US state down to major streets.

Changing zoom levels can be exponential!
"""
import argparse
import pathlib
from math import log, tan, cos, pi

import requests
import urllib3
from tqdm import tqdm

# urllib3 reports a warning whenever you make an insecure request, the line below disables that functionality.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def latitude_to_tile_y(lat: float, zoom: int) -> int:
    return int((1.0 - log(tan(lat * pi / 180.0) + 1.0 / cos(lat * pi / 180.0)) / pi) / 2.0 * (1 << zoom))


def longitude_to_tile_x(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << zoom))


def get_tile(host: str, zoom: int, x: int, y: int) -> bytes:
    response = requests.get(f"{host}/{zoom}/{x}/{y}.png", verify=False, timeout=5 * 60)
    if response.status_code != 200:
        raise RuntimeError(f"Request failed with status code {response.status_code}")
    return response.content


def main(
        host: str,
        zoom_start: int,
        zoom_stop: int,
        west_latitude: float,
        west_longitude: float,
        east_latitude: float,
        east_longitude: float,
):
    grand_total = 0
    for zoom in range(zoom_start, zoom_stop + 1):
        west_y = latitude_to_tile_y(west_latitude, zoom)
        west_x = longitude_to_tile_x(west_longitude, zoom)
        east_y = latitude_to_tile_y(east_latitude, zoom)
        east_x = longitude_to_tile_x(east_longitude, zoom)
        grand_total += len(list(range(west_y, east_y))) * len(list(range(west_x, east_x)))
    print(f'Expecting to download {grand_total} tiles...')

    for zoom in range(zoom_start, zoom_stop + 1):
        west_y = latitude_to_tile_y(west_latitude, zoom)
        west_x = longitude_to_tile_x(west_longitude, zoom)
        east_y = latitude_to_tile_y(east_latitude, zoom)
        east_x = longitude_to_tile_x(east_longitude, zoom)
        total = len(list(range(west_y, east_y))) * len(list(range(west_x, east_x)))
        with tqdm(total=total) as pbar:
            pbar.set_description(f'zoom {zoom}')
            for x in range(west_x, east_x + 1):
                pathlib.Path(f'{zoom}/{x}').mkdir(parents=True, exist_ok=True)
                for y in range(west_y, east_y + 1):
                    pbar.update(1)
                    file = pathlib.Path(f'{zoom}/{x}/{y}.png')
                    if not file.exists() or file.stat().st_size == 0:
                        tile = get_tile(host, zoom, x, y)
                        file.write_bytes(tile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download map tiles from WROLPi")
    parser.add_argument('-H', '--host', type=str,
                        default='https://localhost:8084/hot',
                        help='The URL of your map tiles server',
                        )
    parser.add_argument('-a', '--zoom-start', type=int, default=0,
                        help='The highest zoom to download.  0 will display the entire planet, 6 will display display most of a US state.')
    parser.add_argument('-o', '--zoom-stop', type=int, default=12,
                        help='The lowest zoom to download.  12 will show major streets, 13 will show small streets, 14 will show walking paths.')
    parser.add_argument('west_latitude', type=float,
                        help='The west-most (leftmost) latitude of the square you want to download.  Example: 40.011647534727125',
                        )
    parser.add_argument('west_longitude', type=float,
                        help='The west-most (leftmost) longitude of the square you want to download.  Example: -102.06383712982996',
                        )
    parser.add_argument('east_latitude', type=float,
                        help='The west-most (leftmost) longitude of the square you want to download.  Example: 37.030883772380065',
                        )
    parser.add_argument('east_longitude', type=float,
                        help='The west-most (leftmost) longitude of the square you want to download.  Example: -94.61534551981345',
                        )
    args = parser.parse_args()

    main(
        host=args.host,
        zoom_start=args.zoom_start,
        zoom_stop=args.zoom_stop,
        west_latitude=args.west_latitude,
        west_longitude=args.west_longitude,
        east_latitude=args.east_latitude,
        east_longitude=args.east_longitude,
    )
