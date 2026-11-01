import pytest

from modules.zim import lib
from modules.zim.models import Zim
from wrolpi.conftest import config_versions_lost
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_dump_and_import(test_session, test_directory, async_client, test_wrolpi_config, zim_factory,
                               await_switches):
    """zims.yaml is the source of truth for each Zim's auto_search; a lost database is rebuilt from it."""
    wikipedia = zim_factory('wikipedia_en_all_maxi_2026-02.zim')
    stackoverflow = zim_factory('stackoverflow.com_en_all_2022-11.zim')
    # A Zim named without a date is keyed by its file name.
    plants = zim_factory('edibleplantdb.zim')
    test_session.commit()
    assert all(i.auto_search for i in (wikipedia, stackoverflow, plants)), 'Search is enabled by default'

    # Turning off a Zim's search saves the config, keyed by the Zim's name without its date.
    request, response = await async_client.post(f'/api/zim/{stackoverflow.id}/auto_search',
                                                json=dict(auto_search=False))
    assert response.status_code == 204
    await await_switches()
    config = lib.get_zims_config()
    assert config.get_file().is_file()
    assert config.read_config_file()['auto_search'] == {
        'edibleplantdb': True,
        'stackoverflow.com_en_all': False,
        'wikipedia_en_all_maxi': True,
    }

    # Lose the database.
    test_session.query(Zim).delete()
    test_session.query(FileGroup).delete()
    test_session.commit()
    config_versions_lost(test_session)
    wikipedia = zim_factory('wikipedia_en_all_maxi_2026-02.zim')
    stackoverflow = zim_factory('stackoverflow.com_en_all_2022-11.zim')
    test_session.commit()
    assert stackoverflow.auto_search is True, 'The rebuilt row has the default'

    config.import_config()
    test_session.expire_all()
    assert stackoverflow.auto_search is False, 'The import restored the choice'
    assert wikipedia.auto_search is True

    # Removing a Zim from the file restores the default.
    await await_switches()  # The import without deletes saved the file; the versions are now in step.
    data = config.read_config_file()
    del data['auto_search']['stackoverflow.com_en_all']
    data['version'] += 1
    config.write_config_data(data, config.get_file())
    config.import_config()
    test_session.expire_all()
    assert stackoverflow.auto_search is True


@pytest.mark.asyncio
async def test_new_zim_version_keeps_the_setting(test_session, test_directory, async_client, test_wrolpi_config,
                                                 zim_path_factory):
    """A newer version of a Zim, modeled after its download, has the setting of the Zim it replaces."""
    config = lib.get_zims_config()
    config.write_config_data(dict(version=1, auto_search={'stackoverflow.com_en_all': False}), config.get_file())
    config.import_config()

    for name in ('stackoverflow.com_en_all_2023-05.zim', 'wikipedia_en_all_maxi_2026-02.zim'):
        file_group = FileGroup.from_paths(test_session, zim_path_factory(name))
        lib.model_zim(file_group, test_session)
    test_session.commit()

    zims = {lib.zim_config_name(i.path): i.auto_search for i in test_session.query(Zim)}
    assert zims == {'stackoverflow.com_en_all': False, 'wikipedia_en_all_maxi': True}


@pytest.mark.asyncio
async def test_older_file_saves_the_database(test_session, test_directory, async_client, test_wrolpi_config,
                                             zim_factory, await_switches):
    """A file older than the database (the database changed, WROLPi restarted before it was saved) does not undo
    the change; the database is saved instead."""
    zim = zim_factory('wikipedia_en_all_maxi_2026-02.zim')
    test_session.commit()
    config = lib.get_zims_config()
    config.dump_config()
    await await_switches()
    saved_version = config.read_config_file()['version']

    # The database changes (counted against the config's version) but is not saved.
    lib.set_zim_auto_search(test_session, zim.id, False)
    assert zim.auto_search is False

    # The file still says True, and is older.
    config.import_config()
    test_session.expire_all()
    assert zim.auto_search is False, 'The older file must not undo the database'
    await await_switches()
    data = config.read_config_file()
    assert data['auto_search'] == {'wikipedia_en_all_maxi': False}
    assert data['version'] > saved_version
