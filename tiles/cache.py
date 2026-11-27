"""Tiles already drawn, on the disk.

A phone taking an area offline asks for the same tiles a second phone will, and a block draws tiles beyond the
area asked for.  A tile is a file `<root>/<style id>/<z>/<x>/<y>.jpg`.  A new style (a map file was added,
replaced or removed) is a new directory; the others are removed.

Not on the media drive: there it would be indexed as files and copied by backups.  `/var/cache/wrolpi-tiles` by
default (systemd makes it, see wrolpi-tiles.service).  On a Raspberry Pi that is the SD card, so the cache is
small (`max_bytes`) and nothing is written when the disk is nearly full (`min_free_bytes`).
"""
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SUFFIX = '.jpg'
# Removing the oldest tiles when the cache is full takes it down to this much of `max_bytes`.
EVICT_TO = 0.8


class TileCache:

    def __init__(self, root: Path, max_bytes: int, min_free_bytes: int):
        self.root = root
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.style_id: Optional[str] = None
        self.size = 0
        self._lock = threading.Lock()
        self._evicting = False

    @property
    def enabled(self) -> bool:
        return self.max_bytes > 0

    def path(self, z: int, x: int, y: int) -> Path:
        return self.root / self.style_id / str(z) / str(x) / f'{y}{SUFFIX}'

    def use_style(self, style_id: str):
        """Serve tiles of this style; remove the tiles of every other."""
        self.style_id = style_id
        if not self.enabled:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for entry in self.root.iterdir():
                if entry.name != style_id:
                    shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink(missing_ok=True)
            self.size = sum(i.stat().st_size for i in (self.root / style_id).rglob(f'*{SUFFIX}')) \
                if (self.root / style_id).is_dir() else 0
        except OSError as e:
            logger.error(f'Tile cache {self.root} is not usable, tiles will not be kept', exc_info=e)
            self.max_bytes = 0

    def get(self, z: int, x: int, y: int) -> Optional[bytes]:
        if not self.enabled:
            return None
        try:
            return self.path(z, x, y).read_bytes()
        except OSError:
            return None

    def _disk_full(self) -> bool:
        try:
            return shutil.disk_usage(self.root).free < self.min_free_bytes
        except OSError:
            return True

    def put(self, z: int, tiles: Dict[Tuple[int, int], bytes], style_id: str):
        """Keep the tiles of a block.  Blocking; call it in a thread."""
        if not self.enabled or style_id != self.style_id or self._disk_full():
            return
        written = 0
        for (x, y), data in tiles.items():
            path = self.path(z, x, y)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}')
                temporary.write_bytes(data)
                temporary.replace(path)
                written += len(data)
            except OSError as e:
                logger.warning(f'Could not keep tile {z}/{x}/{y}: {e}')
                return
        with self._lock:
            self.size += written
            evict = self.size > self.max_bytes and not self._evicting
            self._evicting = self._evicting or evict
        if evict:
            try:
                self._evict()
            finally:
                self._evicting = False

    def _evict(self):
        """Remove the least recently written tiles until the cache is `EVICT_TO` of its size."""
        files = []
        for path in (self.root / self.style_id).rglob(f'*{SUFFIX}'):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((stat.st_mtime_ns, stat.st_size, path))
        files.sort()
        size = sum(i[1] for i in files)
        target = self.max_bytes * EVICT_TO
        for _, file_size, path in files:
            if size <= target:
                break
            path.unlink(missing_ok=True)
            size -= file_size
        with self._lock:
            self.size = size
        logger.info(f'Tile cache evicted down to {size // 2 ** 20} MiB')
