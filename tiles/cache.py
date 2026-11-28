"""Tiles already drawn, on the disk.

A phone taking an area offline asks for the same tiles a second phone will, and a block draws tiles beyond the
area asked for.  A tile is a file `<root>/<style id>/<z>/<x>/<y>.jpg`.  A new style (a map file was added,
replaced or removed) is a new directory; the others are removed.

Not on the media drive: there it would be indexed as files and copied by backups.  `/var/cache/wrolpi-tiles` by
default (systemd makes it, see wrolpi-tiles.service).  On a Raspberry Pi that is the SD card, so the cache is
small (`max_bytes`) and nothing is written when the disk is nearly full (`min_free_bytes`).

The cache is measured as the disk measures it (`du`), in the blocks its files take: a tile of a few kilobytes
takes a whole block (4 KiB), and counted by its bytes a full cache of 1 GB was 1.7 GB of the disk.

Tiles are removed by renaming their directory out of the way (`.trash-...`) and deleting it in a thread of the
lowest priority, a little at a time: a phone's download leaves 100,000 files and more, which take most of a minute
to delete from an SD card and load the Raspberry Pi while they are.  A deletion cut short (a restart) is finished
when the service next starts.
"""
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SUFFIX = '.jpg'
# Removing the oldest tiles when the cache is full takes it down to this much of `max_bytes`.
EVICT_TO = 0.8
TRASH_PREFIX = '.trash-'
# Deleting pauses this long after every DELETE_BATCH files, so it does not keep the disk from everything else.
DELETE_BATCH = 500
DELETE_PAUSE = 0.02


def disk_size(stat: os.stat_result) -> int:
    """What a file takes of the disk: its blocks (512 bytes each, whatever the filesystem's block size is)."""
    blocks = getattr(stat, 'st_blocks', None)
    return blocks * 512 if blocks is not None else stat.st_size


def _lower_priority():
    """Make the calling thread the least important to the scheduler (Linux gives each thread its own priority)."""
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)
    except (OSError, AttributeError):
        pass


def _delete_slowly(path: Path):
    _lower_priority()
    deleted = 0
    for root, directories, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.unlink(os.path.join(root, name))
            except OSError:
                pass
            deleted += 1
            if deleted % DELETE_BATCH == 0:
                time.sleep(DELETE_PAUSE)
        for name in directories:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)
    logger.info(f'Deleted {deleted} old tiles')


class TileCache:

    def __init__(self, root: Path, max_bytes: int, min_free_bytes: int):
        self.root = root
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.style_id: Optional[str] = None
        self.size = 0
        self._lock = threading.Lock()
        self._evicting = False
        self._deleting: list = []

    @property
    def enabled(self) -> bool:
        return self.max_bytes > 0

    def path(self, z: int, x: int, y: int) -> Path:
        return self.root / self.style_id / str(z) / str(x) / f'{y}{SUFFIX}'

    def _discard(self, path: Path):
        """Remove a directory of tiles: at once from the cache, from the disk in the background."""
        trash = path if path.name.startswith(TRASH_PREFIX) else \
            path.with_name(f'{TRASH_PREFIX}{path.name}-{uuid.uuid4().hex[:8]}')
        try:
            if trash != path:
                path.rename(trash)
        except FileNotFoundError:
            return
        except OSError as e:
            logger.warning(f'Could not move {path} aside, deleting it now: {e}')
            shutil.rmtree(path, ignore_errors=True)
            return
        thread = threading.Thread(target=_delete_slowly, args=(trash,), name='tile-cache-delete', daemon=True)
        self._deleting = [i for i in self._deleting if i.is_alive()] + [thread]
        thread.start()

    def wait_for_deletes(self, timeout: float = None):
        """Wait for directories being deleted in the background (for tests)."""
        for thread in list(self._deleting):
            thread.join(timeout)

    def _measure(self, directory: Path) -> int:
        size = 0
        for path in directory.rglob(f'*{SUFFIX}'):
            try:
                size += disk_size(path.stat())
            except OSError:
                pass
        return size

    def use_style(self, style_id: str):
        """Serve tiles of this style; remove the tiles of every other (and any deletion left unfinished)."""
        self.style_id = style_id
        if not self.enabled:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for entry in self.root.iterdir():
                if entry.name == style_id:
                    continue
                if entry.is_dir():
                    self._discard(entry)
                else:
                    entry.unlink(missing_ok=True)
            current = self.root / style_id
            size = self._measure(current) if current.is_dir() else 0
            with self._lock:
                self.size = size
        except OSError as e:
            logger.error(f'Tile cache {self.root} is not usable, tiles will not be kept', exc_info=e)
            self.max_bytes = 0

    def clear(self) -> int:
        """Remove every kept tile at once (they are deleted from the disk in the background); return how much of
        the disk that frees.  Tiles are drawn again when next asked for."""
        if not self.enabled or not self.style_id:
            return 0
        with self._lock:
            freed, self.size = self.size, 0
        self._discard(self.root / self.style_id)
        logger.info(f'Tile cache cleared ({freed // 2 ** 20} MiB)')
        return freed

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
        added = 0
        for (x, y), data in tiles.items():
            path = self.path(z, x, y)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}')
                temporary.write_bytes(data)
                new = disk_size(temporary.stat())
                try:
                    old = disk_size(path.stat())  # a tile drawn again replaces itself
                except FileNotFoundError:
                    old = 0
                temporary.replace(path)
                added += new - old
            except OSError as e:
                logger.warning(f'Could not keep tile {z}/{x}/{y}: {e}')
                return
        with self._lock:
            self.size += added
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
            files.append((stat.st_mtime_ns, disk_size(stat), path))
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
