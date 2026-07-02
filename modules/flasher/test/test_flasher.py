import pathlib
from http import HTTPStatus

import pytest

from modules.flasher.lib import read_esp_image_info, search_esp_firmware


@pytest.mark.parametrize('chip_id,kind,expected_chip,expected_kind', [
    (0x0000, 'app', 'ESP32', 'app'),
    (0x0002, 'app', 'ESP32-S2', 'app'),
    (0x0009, 'app', 'ESP32-S3', 'app'),
    (0x0005, 'app', 'ESP32-C3', 'app'),
    (0x000D, 'app', 'ESP32-C6', 'app'),
    (0x0000, 'factory_s2', 'ESP32', 'factory'),  # ESP32/S2 layout: bootloader at 0x1000
    (0x0009, 'factory', 'ESP32-S3', 'factory'),  # S3 layout: bootloader at 0x0, partition table at 0x8000
    (0x0000, 'bootloader', 'ESP32', 'bootloader'),
])
def test_read_esp_image_info(make_esp_image, chip_id, kind, expected_chip, expected_kind):
    """The header reader identifies the target chip and image kind from realistic header bytes."""
    path = make_esp_image('software/fw.bin', chip_id=chip_id, kind=kind)
    info = read_esp_image_info(path)
    assert info['is_esp_image'] is True
    assert info['chip'] == expected_chip
    assert info['chip_id'] == chip_id
    assert info['kind'] == expected_kind


def test_read_esp_image_info_not_esp(make_esp_image):
    """A .bin that is not an ESP image (no 0xE9 magic) is reported as such."""
    path = make_esp_image('software/data.bin', kind='not_esp')
    info = read_esp_image_info(path)
    assert info == dict(is_esp_image=False, chip=None, chip_id=None, kind='not_esp_image')


def test_read_esp_image_info_unknown_chip(make_esp_image):
    """An ESP image with an unrecognized chip_id is still detected as an image, with chip=None."""
    path = make_esp_image('software/fw.bin', chip_id=0x7777, kind='app')
    info = read_esp_image_info(path)
    assert info['is_esp_image'] is True
    assert info['chip'] is None
    assert info['chip_id'] == 0x7777


@pytest.mark.asyncio
async def test_search_esp_firmware_filters_by_chip(async_client, test_session, make_esp_image, refresh_files):
    """search_esp_firmware returns only ESP images matching the requested chip, annotated with chip/kind."""
    make_esp_image('software/esp32-app.bin', chip_id=0x0000, kind='app')
    make_esp_image('software/s2-app.bin', chip_id=0x0002, kind='app')
    make_esp_image('software/s3-factory.bin', chip_id=0x0009, kind='factory')
    make_esp_image('software/s3-app.bin', chip_id=0x0009, kind='app')
    # A non-ESP .bin (e.g. a filesystem image or game installer) must never be returned.
    make_esp_image('software/littlefs.bin', kind='not_esp')

    await refresh_files()

    def names(results):
        # search_esp_firmware (lib layer) returns primary_path as an absolute Path; compare by basename.
        return sorted(pathlib.Path(r['primary_path']).name for r in results)

    # Filter to ESP32-S3: only the two S3 images, never the non-ESP file.
    s3, total = search_esp_firmware(chip='ESP32-S3')
    assert total == 2
    assert names(s3) == ['s3-app.bin', 's3-factory.bin']
    assert {r['esp_chip'] for r in s3} == {'ESP32-S3'}
    assert {r['esp_kind'] for r in s3} == {'app', 'factory'}

    # Filter to ESP32-S2: just the one.
    s2, total = search_esp_firmware(chip='ESP32-S2')
    assert total == 1
    assert names(s2) == ['s2-app.bin']

    # No chip: all ESP images, excluding the non-ESP .bin.
    all_esp, total = search_esp_firmware()
    assert total == 4
    assert 'littlefs.bin' not in names(all_esp)

    # A chip with no matching firmware returns nothing.
    _, total = search_esp_firmware(chip='ESP32-H2')
    assert total == 0


@pytest.mark.asyncio
async def test_flasher_search_api(async_client, test_session, make_esp_image, refresh_files):
    """The /api/flasher/search endpoint filters by chip and supports the path filter."""
    make_esp_image('software/marauder/esp32.bin', chip_id=0x0000, kind='app')
    make_esp_image('software/marauder/s3.bin', chip_id=0x0009, kind='app')
    make_esp_image('software/other/s3.bin', chip_id=0x0009, kind='app')

    await refresh_files()

    # Filter by chip.
    request, response = await async_client.post('/api/flasher/search', json=dict(chip='ESP32-S3'))
    assert response.status_code == HTTPStatus.OK
    got = sorted(fg['primary_path'] for fg in response.json['file_groups'])
    assert got == ['software/marauder/s3.bin', 'software/other/s3.bin']
    assert response.json['totals']['file_groups'] == 2

    # Filter by chip AND path (the flasher's detect + folder filter combined).
    request, response = await async_client.post('/api/flasher/search',
                                                json=dict(chip='ESP32-S3', path='marauder'))
    assert response.status_code == HTTPStatus.OK
    got = [fg['primary_path'] for fg in response.json['file_groups']]
    assert got == ['software/marauder/s3.bin']
    assert response.json['file_groups'][0]['esp_chip'] == 'ESP32-S3'


@pytest.mark.asyncio
async def test_flasher_saved_configs_api(async_client, test_session, test_directory):
    """Saved firmware configurations can be created, listed, replaced, deleted, and are persisted to YAML."""
    # Initially empty.
    request, response = await async_client.get('/api/flasher/configs')
    assert response.status_code == HTTPStatus.OK
    assert response.json['configurations'] == []

    # Save a multi-part configuration (like a Meshtastic T-Deck).
    body = dict(name='T-Deck MUI', erase_all=True, files=[
        dict(path='software/firmware-t-deck-tft.bin', address='0x0', name='firmware-t-deck-tft.bin', size=100),
        dict(path='software/littlefs-t-deck-tft.bin', address='0xc90000', name='littlefs-t-deck-tft.bin', size=200),
    ])
    request, response = await async_client.post('/api/flasher/configs', json=body)
    assert response.status_code == HTTPStatus.CREATED

    # It is listed with its files and offsets.
    request, response = await async_client.get('/api/flasher/configs')
    configs = response.json['configurations']
    assert len(configs) == 1
    assert configs[0]['name'] == 'T-Deck MUI'
    assert configs[0]['erase_all'] is True
    assert [f['address'] for f in configs[0]['files']] == ['0x0', '0xc90000']

    # It is persisted to flasher.yaml.
    assert (test_directory / 'config/flasher.yaml').is_file()

    # Saving the same name replaces it (still one configuration).
    body2 = dict(name='T-Deck MUI', files=[dict(path='software/other.bin', address='0x0')])
    request, response = await async_client.post('/api/flasher/configs', json=body2)
    assert response.status_code == HTTPStatus.CREATED
    request, response = await async_client.get('/api/flasher/configs')
    configs = response.json['configurations']
    assert len(configs) == 1
    assert [f['path'] for f in configs[0]['files']] == ['software/other.bin']

    # An empty name is rejected.
    request, response = await async_client.post('/api/flasher/configs', json=dict(name='  ', files=[]))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Delete it (name is URL-encoded).
    request, response = await async_client.delete('/api/flasher/configs/T-Deck%20MUI')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/flasher/configs')
    assert response.json['configurations'] == []

    # Deleting a missing configuration 404s.
    request, response = await async_client.delete('/api/flasher/configs/nope')
    assert response.status_code == HTTPStatus.NOT_FOUND
