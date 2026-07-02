"""Inspect ESP firmware images so the Flasher can filter files by the connected device's chip.

An Espressif firmware image begins with a one-byte magic (0xE9) followed by an image header.  The extended
header records which chip the image was built for (``chip_id`` at offset 0x0C).  We read only the first few KB
of a file to determine its target chip and what kind of image it is, without loading the whole firmware.
"""
import functools
import pathlib
from typing import List, Optional, Tuple

from wrolpi.common import get_media_directory, logger

logger = logger.getChild(__name__)

# esptool ``chip_id`` (extended image header, offset 0x0C) -> chip name.  Names match esptool-js so the value
# reported by the browser after connecting can be compared directly.
ESP_CHIP_IDS = {
    0x0000: 'ESP32',
    0x0002: 'ESP32-S2',
    0x0005: 'ESP32-C3',
    0x0009: 'ESP32-S3',
    0x000C: 'ESP32-C2',
    0x000D: 'ESP32-C6',
    0x0010: 'ESP32-H2',
    0x0011: 'ESP32-C5',
    0x0012: 'ESP32-P4',
}

ESP_IMAGE_MAGIC = 0xE9  # First byte of an ESP image header (app or bootloader).
APP_DESC_MAGIC = 0xABCD5432  # esp_app_desc_t magic, sits at 0x20 in an application image.
PARTITION_TABLE_MAGIC = (0xAA, 0x50)  # First two bytes of a partition-table entry, always at flash offset 0x8000.

# Read enough to cover: an app/bootloader header at 0x0, the ESP32/ESP32-S2 "factory" bootloader at 0x1000, and
# the partition table at 0x8000 (which distinguishes a full/merged "factory" image from a bare app or bootloader).
_HEADER_READ_SIZE = 0x8100


def _u16(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


def _u32(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16) | (data[offset + 3] << 24)


@functools.lru_cache(maxsize=10_000)
def read_esp_image_info(path: pathlib.Path) -> dict:
    """Read an ESP firmware image's header to determine its target chip and kind.

    Returns a dict: ``{'is_esp_image': bool, 'chip': str|None, 'chip_id': int|None, 'kind': str}`` where ``kind``
    is one of ``app`` (application image), ``factory`` (full flashable image with a partition table),
    ``bootloader`` (a bare second-stage bootloader), or ``not_esp_image``.

    Only the first few KB of the file are read.  Cached because firmware files are immutable in practice and this
    is called for many files per request.
    """
    result = dict(is_esp_image=False, chip=None, chip_id=None, kind='not_esp_image')
    try:
        with open(path, 'rb') as fh:
            head = fh.read(_HEADER_READ_SIZE)
    except OSError as e:
        logger.debug(f'Could not read firmware header from {path}: {e}')
        return result

    # The image header is at 0x0 for an app/bootloader (and for factory images on chips whose bootloader lives
    # at 0x0, e.g. ESP32-S3/C3).  On the ESP32 and ESP32-S2 a "factory" merged image pads 0x0..0x1000 and puts
    # the bootloader header at 0x1000.
    base = None
    if len(head) > 0x0D and head[0] == ESP_IMAGE_MAGIC:
        base = 0x0
    elif len(head) > 0x100D and head[0x1000] == ESP_IMAGE_MAGIC:
        base = 0x1000
    if base is None:
        return result

    chip_id = _u16(head, base + 0x0C)
    result['is_esp_image'] = True
    result['chip_id'] = chip_id
    result['chip'] = ESP_CHIP_IDS.get(chip_id)

    # An application image carries the esp_app_desc magic right after its header (only true for app-only images;
    # in a factory image offset 0x20 is bootloader/padding).  A full/merged image instead has the partition
    # table at 0x8000.  Check app-desc first so a coincidental byte pattern at 0x8000 can't mislabel an app.
    has_app_desc = len(head) >= 0x24 and _u32(head, 0x20) == APP_DESC_MAGIC
    has_partition_table = (len(head) >= 0x8002
                           and head[0x8000] == PARTITION_TABLE_MAGIC[0]
                           and head[0x8001] == PARTITION_TABLE_MAGIC[1])
    if has_app_desc:
        result['kind'] = 'app'
    elif has_partition_table:
        result['kind'] = 'factory'
    else:
        result['kind'] = 'bootloader'
    return result


def _resolve_media_path(primary_path) -> pathlib.Path:
    """Resolve a search result's primary_path (relative or absolute) to an absolute path on disk."""
    path = pathlib.Path(primary_path)
    return path if path.is_absolute() else get_media_directory() / path


def search_esp_firmware(chip: Optional[str] = None, path: Optional[str] = None,
                        limit: int = 1000) -> Tuple[List[dict], int]:
    """Search for ``.bin`` firmware and return only ESP images, annotated with their detected chip/kind.

    @param chip: If provided, only return images built for this chip (e.g. "ESP32-S2").
    @param path: Case-insensitive partial match against the file path (same as file search).
    @param limit: Maximum number of candidate .bin files to inspect.
    """
    from wrolpi.files.lib import search_files

    file_groups, _ = search_files(None, limit, 0, suffix='.bin', path=path)

    results = []
    for file_group in file_groups:
        info = read_esp_image_info(_resolve_media_path(file_group['primary_path']))
        if not info['is_esp_image']:
            # Skip non-ESP .bin files (filesystem images, game installers, STM32 firmware, etc.).
            continue
        if chip and info['chip'] != chip:
            continue
        results.append({
            **file_group,
            'esp_chip': info['chip'],
            'esp_chip_id': info['chip_id'],
            'esp_kind': info['kind'],
        })
    return results, len(results)
