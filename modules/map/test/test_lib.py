from unittest import mock

import pytest

from modules.map import lib
from modules.map.config import get_maps_config
from modules.map.conftest import vector_metadata
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


def test_get_pmtiles_files_sub_directories(test_directory, make_pmtiles):
    """Files in sub-directories of the map directory are listed by their path within it.  Unfinished downloads
    (in a hidden directory) are not listed."""
    make_pmtiles('map/usa.pmtiles')
    make_pmtiles('map/extras/features.pmtiles', vector_metadata('towers', name='Features', type='overlay'))
    make_pmtiles('map/extras/deeper/satellite.pmtiles', dict(), tile_type=3)
    make_pmtiles('map/.partial/oregon.pmtiles')

    files = {i['map_path']: i for i in lib.get_pmtiles_files()}
    assert sorted(files) == ['extras/deeper/satellite.pmtiles', 'extras/features.pmtiles', 'usa.pmtiles']

    features = files['extras/features.pmtiles']
    assert features['name'] == 'features.pmtiles'
    assert features['path'] == 'map/extras/features.pmtiles'
    assert features['kind'] == 'overlay'
    assert features['title'] == 'Features'
    assert features['tile_type'] == 'mvt'
    assert [i['id'] for i in features['vector_layers']] == ['towers']
    assert features['visible'] is True

    assert files['usa.pmtiles']['kind'] == 'basemap'
    assert files['extras/deeper/satellite.pmtiles']['kind'] == 'overlay'
    assert files['extras/deeper/satellite.pmtiles']['tile_type'] == 'jpeg'


def test_get_pmtiles_files_unreadable(test_directory, make_files_structure):
    """A file which cannot be read is listed (so it can be deleted), as a file the map cannot draw."""
    make_files_structure(['map/empty.pmtiles'])
    file, = lib.get_pmtiles_files()
    assert file['kind'] == 'unknown'
    assert file['title'] is None
    assert file['vector_layers'] == []


def test_delete_pmtiles_file_sub_directory(test_directory, make_pmtiles):
    """A file in a sub-directory is deleted by its path within the map directory, with its search index."""
    pmtiles_file = make_pmtiles('map/extras/features.pmtiles')
    search_db = pmtiles_file.with_suffix('.search.db')
    search_db.touch()
    same_name = make_pmtiles('map/features.pmtiles')

    assert lib.delete_pmtiles_file('extras/features.pmtiles') is True
    assert not pmtiles_file.exists()
    assert not search_db.exists()
    # The file of the same name in the map directory is another file.
    assert same_name.is_file()


def test_set_pmtiles_file_visible(async_client, test_directory, make_pmtiles):
    """An ignored file is listed as not visible, in the maps config, until it is shown again."""
    make_pmtiles('map/extras/ignore-me.pmtiles')
    make_pmtiles('map/ignore-me.pmtiles')

    assert lib.set_pmtiles_file_visible('extras/ignore-me.pmtiles', False) is True
    assert get_maps_config().ignored_files == ['extras/ignore-me.pmtiles']
    visible = {i['map_path']: i['visible'] for i in lib.get_pmtiles_files()}
    assert visible == {'ignore-me.pmtiles': True, 'extras/ignore-me.pmtiles': False}

    assert lib.set_pmtiles_file_visible('extras/ignore-me.pmtiles', True) is True
    assert get_maps_config().ignored_files == []
    assert all(i['visible'] for i in lib.get_pmtiles_files())


def test_set_pmtiles_file_visible_unknown_file(async_client, test_directory, make_pmtiles):
    """Only a map file can be ignored."""
    make_pmtiles('map/usa.pmtiles')
    (test_directory / 'map/notes.txt').write_text('notes')

    assert lib.set_pmtiles_file_visible('missing.pmtiles', False) is False
    assert lib.set_pmtiles_file_visible('notes.txt', False) is False
    with pytest.raises(ValueError):
        lib.set_pmtiles_file_visible('../../etc/passwd', False)
    assert get_maps_config().ignored_files == []


def test_delete_pmtiles_file_forgets_ignored(async_client, test_directory, make_pmtiles):
    """A deleted file is no longer ignored, so a new file of the same name is drawn."""
    make_pmtiles('map/ignored-then-deleted.pmtiles')
    lib.set_pmtiles_file_visible('ignored-then-deleted.pmtiles', False)
    assert get_maps_config().ignored_files == ['ignored-then-deleted.pmtiles']

    assert lib.delete_pmtiles_file('ignored-then-deleted.pmtiles') is True
    assert get_maps_config().ignored_files == []

    make_pmtiles('map/ignored-then-deleted.pmtiles')
    file, = lib.get_pmtiles_files()
    assert file['visible'] is True


def test_sidecar_style(test_directory, make_pmtiles):
    """A style beside a map file says how it is drawn: its own, else the one its directory shares."""
    own = make_pmtiles('map/extras/own.pmtiles', vector_metadata('towers'))
    shared = make_pmtiles('map/extras/shared.pmtiles', vector_metadata('towers'))
    elsewhere = make_pmtiles('map/elsewhere.pmtiles', vector_metadata('towers'))
    assert lib.find_sidecar_style(own) is None

    (test_directory / 'map/extras/style.json').write_text('{}')
    (test_directory / 'map/extras/own.style.json').write_text('{}')
    assert lib.find_sidecar_style(own) == test_directory / 'map/extras/own.style.json'
    assert lib.find_sidecar_style(shared) == test_directory / 'map/extras/style.json'
    # A directory's style is not the style of the files in other directories.
    assert lib.find_sidecar_style(elsewhere) is None

    files = {i['map_path']: i for i in lib.get_pmtiles_files()}
    assert files['extras/own.pmtiles']['style_path'] == 'map/extras/own.style.json'
    # The style is also named within the map directory, for the viewer which is served only that.
    assert files['extras/own.pmtiles']['style_map_path'] == 'extras/own.style.json'
    assert files['extras/shared.pmtiles']['style_map_path'] == 'extras/style.json'
    assert files['elsewhere.pmtiles']['style_map_path'] is None
    assert files['extras/shared.pmtiles']['style_path'] == 'map/extras/style.json'
    assert files['elsewhere.pmtiles']['style_path'] is None


def test_sidecar_style_custom_map_directory(test_directory, make_pmtiles, test_wrolpi_config):
    """The style's path within the map directory does not depend on what the map directory is called."""
    get_wrolpi_config().map_destination = 'atlas'
    make_pmtiles('atlas/extras/features.pmtiles', vector_metadata('towers'))
    (test_directory / 'atlas/extras/style.json').write_text('{}')

    file, = lib.get_pmtiles_files()
    assert file['map_path'] == 'extras/features.pmtiles'
    assert file['style_path'] == 'atlas/extras/style.json'
    assert file['style_map_path'] == 'extras/style.json'
