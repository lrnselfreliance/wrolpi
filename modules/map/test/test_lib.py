from unittest import mock

import pytest

from modules.map import lib
from wrolpi.common import get_wrolpi_config


def test_get_pmtiles_files_empty(test_directory):
    """No files returns an empty list."""
    assert lib.get_pmtiles_files() == []


def test_get_pmtiles_files(test_directory, make_files_structure):
    """PMTiles files are found, other files are ignored."""
    make_files_structure([
        'map/usa.pmtiles',
        'map/oregon.pmtiles',
        'map/old-data.osm.pbf',
        'map/readme.txt',
    ])

    files = lib.get_pmtiles_files()
    names = [f['name'] for f in files]
    assert 'oregon.pmtiles' in names
    assert 'usa.pmtiles' in names
    assert 'old-data.osm.pbf' not in names
    assert 'readme.txt' not in names

    # Each file has expected keys.
    for f in files:
        assert 'name' in f
        assert 'path' in f
        assert 'size' in f
        assert 'mtime' in f


def test_delete_pmtiles_file(test_directory, make_files_structure):
    """A PMTiles file can be deleted."""
    pmtiles_file, = make_files_structure(['map/oregon.pmtiles'])
    assert pmtiles_file.is_file()

    assert lib.delete_pmtiles_file('oregon.pmtiles') is True
    assert not pmtiles_file.is_file()


def test_delete_nonexistent_file(test_directory):
    """Deleting a nonexistent file returns False."""
    assert lib.delete_pmtiles_file('nonexistent.pmtiles') is False


def test_delete_path_traversal(test_directory, make_files_structure):
    """Path traversal is rejected."""
    make_files_structure(['map/safe.pmtiles'])

    with pytest.raises(ValueError):
        lib.delete_pmtiles_file('../../etc/passwd')


def test_get_map_catalog(test_directory):
    """Catalog returns predefined regions."""
    catalog = lib.get_map_catalog()
    assert len(catalog) > 0
    names = [r['name'] for r in catalog]
    assert 'Alaska' in names  # Verify a known region exists
    for region in catalog:
        assert 'name' in region
        assert 'region' in region
        assert 'size_estimate' in region


@pytest.mark.asyncio
async def test_subscribe(async_client, test_session, test_directory):
    """A subscription adds a region to the download settings."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    subs = lib.get_map_subscriptions(test_session)
    regions = [s['region'] for s in subs]
    assert 'us-alaska' in regions


@pytest.mark.asyncio
async def test_subscribe_multiple(async_client, test_session, test_directory):
    """Multiple subscriptions share one Download."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    await lib.subscribe(test_session, 'United States (West)', 'us-west')
    subs = lib.get_map_subscriptions(test_session)
    regions = [s['region'] for s in subs]
    assert 'us-alaska' in regions
    assert 'us-west' in regions


@pytest.mark.asyncio
async def test_subscribe_duplicate(async_client, test_session, test_directory):
    """Subscribing to the same region twice doesn't duplicate."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    subs = lib.get_map_subscriptions(test_session)
    assert len([s for s in subs if s['region'] == 'us-alaska']) == 1


@pytest.mark.asyncio
async def test_subscribe_invalid(async_client, test_session, test_directory):
    """Invalid region name raises ValueError."""
    with pytest.raises(ValueError):
        await lib.subscribe(test_session, 'Atlantis', 'atlantis')


@pytest.mark.asyncio
async def test_unsubscribe(async_client, test_session, test_directory):
    """Unsubscribing removes a region."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    await lib.subscribe(test_session, 'United States (West)', 'us-west')

    await lib.unsubscribe(test_session, 'us-alaska')
    subs = lib.get_map_subscriptions(test_session)
    regions = [s['region'] for s in subs]
    assert 'us-alaska' not in regions
    assert 'us-west' in regions


@pytest.mark.asyncio
async def test_unsubscribe_last_deletes_download(async_client, test_session, test_directory):
    """Unsubscribing the last region deletes the Download."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    await lib.unsubscribe(test_session, 'us-alaska')
    assert lib.get_map_subscriptions(test_session) == []
    assert lib._get_map_download(test_session) is None


@pytest.mark.asyncio
async def test_subscribe_renews_download(async_client, test_session, test_directory):
    """Subscribing renews the download so it runs immediately."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    download = lib._get_map_download(test_session)
    assert download.status == 'new'

    # Simulate the download completing.
    download.status = 'complete'
    test_session.commit()

    # Subscribe to another region — download should be renewed.
    await lib.subscribe(test_session, 'United States (West)', 'us-west')
    download = lib._get_map_download(test_session)
    assert download.status == 'new'


@pytest.mark.asyncio
async def test_subscribe_saves_config(async_client, test_session, test_directory):
    """Subscribing triggers a download config save."""
    with mock.patch('modules.map.lib.save_downloads_config') as mock_save:
        await lib.subscribe(test_session, 'Alaska', 'us-alaska')
        mock_save.activate_switch.assert_called_once()


@pytest.mark.asyncio
async def test_unsubscribe_saves_config(async_client, test_session, test_directory):
    """Unsubscribing triggers a download config save."""
    await lib.subscribe(test_session, 'Alaska', 'us-alaska')
    with mock.patch('modules.map.lib.save_downloads_config') as mock_save:
        await lib.unsubscribe(test_session, 'us-alaska')
        mock_save.activate_switch.assert_called_once()


def test_get_custom_map_directory(async_client, test_directory, test_wrolpi_config):
    """Custom directory can be used for map directory."""
    # Default location.
    assert lib.get_map_directory() == (test_directory / 'map')

    get_wrolpi_config().map_destination = 'custom/deep/map/directory'

    assert lib.get_map_directory() == (test_directory / 'custom/deep/map/directory')
    assert (test_directory / 'custom/deep/map/directory').is_dir()
