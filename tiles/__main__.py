"""Run the tile service: `python -m tiles` (see `tiles.service`)."""
import argparse
import logging
import os
from pathlib import Path

from tiles import maps
from tiles.cache import TileCache
from tiles.service import DEFAULT_MAX_ZOOM, TileService, create_app


def main():
    parser = argparse.ArgumentParser(description='WROLPi map tiles for ATAK and iTAK')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9088)
    parser.add_argument('--processes', type=int, default=int(os.environ.get('TILES_PROCESSES', 2)),
                        help='Render processes; each is about 250 MB (default 2, or TILES_PROCESSES)')
    parser.add_argument('--max-zoom', type=int, default=DEFAULT_MAX_ZOOM)
    parser.add_argument('--cache-directory', type=Path,
                        default=Path(os.environ.get('CACHE_DIRECTORY', '/var/cache/wrolpi-tiles')),
                        help='Where drawn tiles are kept (default: systemd CACHE_DIRECTORY)')
    parser.add_argument('--cache-mb', type=int, default=int(os.environ.get('TILES_CACHE_MB', 1024)),
                        help='Most the cache may hold, 0 to keep nothing (default 1024, or TILES_CACHE_MB)')
    parser.add_argument('--min-free-mb', type=int, default=2048,
                        help='Keep no tiles when the disk has less free than this (default 2048)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    cache = TileCache(args.cache_directory, args.cache_mb * 2 ** 20, args.min_free_mb * 2 ** 20)
    service = TileService(maps.get_map_directory(), cache, processes=args.processes, max_zoom=args.max_zoom)
    app = create_app(service)
    app.run(host=args.host, port=args.port, single_process=True, access_log=False, motd=False)


if __name__ == '__main__':
    main()
