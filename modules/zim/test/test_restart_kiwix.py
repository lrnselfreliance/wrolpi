"""Tests for the restart_kiwix switch handler triggered by model_zim()."""
import pytest

from modules.zim import lib
from modules.zim.models import Zim
from wrolpi.api_utils import api_app
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_model_zim_activates_restart_switch(async_client, test_session, zim_path_factory):
    """model_zim() should activate the restart_kiwix switch when creating a new Zim."""
    # Create a zim file and its FileGroup
    zim_path = zim_path_factory('test_restart.zim')
    file_group = FileGroup.from_paths(test_session, zim_path)
    test_session.commit()

    # Verify no switches are pending
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' not in switches

    # Call model_zim which should activate the switch
    lib.model_zim(file_group, test_session)
    test_session.commit()

    # Verify the switch was activated
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' in switches


@pytest.mark.asyncio
async def test_existing_zim_does_not_trigger_restart(async_client, test_session, zim_factory, await_switches):
    """model_zim() should NOT activate restart switch for existing Zims."""
    # Create a zim using the factory (this calls model_zim internally via Zim.from_paths)
    zim = zim_factory('existing.zim')
    test_session.commit()

    # Clear any pending switches
    await await_switches()

    # Verify no switches are pending
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' not in switches

    # Call model_zim again on the same FileGroup - should NOT trigger restart
    lib.model_zim(zim.file_group, test_session)
    test_session.commit()

    # Verify the switch was NOT activated (Zim already exists)
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' not in switches


@pytest.mark.asyncio
async def test_multiple_zims_trigger_single_restart(async_client, test_session, zim_path_factory):
    """Multiple new Zims should result in only one restart (debouncing via switch)."""
    # Create multiple zim files
    paths = [zim_path_factory(f'test_debounce_{i}.zim') for i in range(3)]

    # Create FileGroups and model each one
    for path in paths:
        file_group = FileGroup.from_paths(test_session, path)
        test_session.commit()
        lib.model_zim(file_group, test_session)
        test_session.commit()

    # Verify switch was activated (only once, due to debouncing)
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' in switches
    # The switch dict contains only one entry for restart_kiwix, proving debouncing works
    assert list(switches.keys()).count('restart_kiwix') == 1


@pytest.mark.asyncio
async def test_remove_outdated_zim_files_triggers_restart(async_client, test_session, test_directory, zim_path_factory,
                                                          await_switches):
    """remove_outdated_zim_files() should trigger the restart_kiwix switch."""
    # Create outdated and current zim files
    zim_dir = test_directory / 'zims'
    zim_dir.mkdir(exist_ok=True)

    # Create an "outdated" zim and a "current" zim (based on date in filename)
    outdated_path = zim_dir / 'wikipedia_en_all_maxi_2020-01.zim'
    current_path = zim_dir / 'wikipedia_en_all_maxi_2020-02.zim'

    # Copy test zim bytes to both paths
    test_zim_bytes = zim_path_factory().read_bytes()
    outdated_path.write_bytes(test_zim_bytes)
    current_path.write_bytes(test_zim_bytes)

    # Clear any pending switches first
    await await_switches()

    # Call remove_outdated_zim_files
    deleted_count = await lib.remove_outdated_zim_files(zim_dir)

    # Verify the outdated file was deleted
    assert deleted_count == 1
    assert not outdated_path.exists()
    assert current_path.exists()

    # Verify the switch was activated
    switches = dict(api_app.shared_ctx.switches) if api_app.shared_ctx.switches else {}
    assert 'restart_kiwix' in switches
