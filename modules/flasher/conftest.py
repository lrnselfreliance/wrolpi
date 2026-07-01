import struct

import pytest

from modules.flasher.lib import ESP_IMAGE_MAGIC, APP_DESC_MAGIC, PARTITION_TABLE_MAGIC, read_esp_image_info


def build_esp_image(chip_id: int = 0x0000, kind: str = 'app', size: int = 2048) -> bytes:
    """Build a byte string with a realistic ESP image header for testing.

    The bytes are padded with 0xFF (like real flash) and contain the magic numbers at the offsets the flasher
    inspects, so tests exercise the same detection path as real firmware.

    @param chip_id: The value written to the extended image header (offset 0x0C).  See ESP_CHIP_IDS.
    @param kind: One of:
        - 'app':        application image (header + esp_app_desc magic at 0x20).
        - 'factory':    full merged image, ESP32-S3/C3 style (bootloader header at 0x0, partition table at 0x8000).
        - 'factory_s2': full merged image, ESP32/ESP32-S2 style (padding, bootloader header at 0x1000, PT at 0x8000).
        - 'bootloader': a bare second-stage bootloader (header at 0x0, no app descriptor, no partition table).
        - 'not_esp':    not an ESP image at all (no 0xE9 magic).
    """
    needs_partition_table = kind in ('factory', 'factory_s2')
    if needs_partition_table:
        size = max(size, 0x8100)

    if kind == 'not_esp':
        # Realistic non-ESP binary (e.g. a filesystem image or game data): varied bytes so it is detected as
        # binary, not text.  A uniform 0xFF fill is misdetected as text/plain by libmagic and breaks indexing.
        return bytes((i * 7 + 13) & 0xFF for i in range(size))

    # ESP images pad gaps with 0xFF like real flash; the image header makes them detect as binary.
    data = bytearray(b'\xff' * size)

    def write_image_header(base: int):
        data[base] = ESP_IMAGE_MAGIC
        data[base + 1] = 0x03  # segment_count
        data[base + 2] = 0x02  # spi_mode (dio)
        data[base + 3] = 0x2f  # spi_speed/size
        # entry_addr (4..7) left as 0xFF; chip_id is a uint16 little-endian at base + 0x0C.
        struct.pack_into('<H', data, base + 0x0C, chip_id)

    header_base = 0x1000 if kind == 'factory_s2' else 0x0
    write_image_header(header_base)

    if kind == 'app':
        # esp_app_desc magic follows the image + first segment header at 0x20.
        struct.pack_into('<I', data, 0x20, APP_DESC_MAGIC)
    elif needs_partition_table:
        # A full/merged image has the partition table at flash offset 0x8000.
        data[0x8000] = PARTITION_TABLE_MAGIC[0]
        data[0x8001] = PARTITION_TABLE_MAGIC[1]

    return bytes(data)


@pytest.fixture
def make_esp_image(test_directory):
    """Write a semi-real ESP firmware .bin (with correct header magic numbers) into the media directory.

    Usage: ``make_esp_image('software/fw.bin', chip_id=0x0002, kind='app')`` -> returns the created Path.
    """
    # The header reader is lru_cached; clear it so a reused path can't return a stale result across tests.
    read_esp_image_info.cache_clear()

    def _make(relative_path: str, chip_id: int = 0x0000, kind: str = 'app', size: int = 2048):
        path = test_directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_esp_image(chip_id=chip_id, kind=kind, size=size))
        return path

    return _make
