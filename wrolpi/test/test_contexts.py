"""Tests for shared context initialization."""
from copy import deepcopy

import pytest

from wrolpi.common import MultiFileConfig, write_config_data
from wrolpi.test.common import SharedDict, config_classes


def write_config_files(config, version: int):
    """Write a valid config file (or, for a MultiFileConfig, one entity's file) at `version`."""
    if isinstance(config, MultiFileConfig):
        file = config.get_file('one')
        data = {**deepcopy(config.default_entity), 'version': version, 'slug': 'one', 'name': 'One'}
    else:
        file = config.get_file()
        data = {**deepcopy(config.default_config), 'version': version}
    file.parent.mkdir(parents=True, exist_ok=True)
    write_config_data(data, file)


def test_domains_config_in_shared_context():
    """Verify domains_config is initialized in shared context.

    This is critical for multi-process deployments. Without proper initialization,
    domains_config.version won't be shared across processes, causing config save failures.

    The bug this catches: domains_config was missing from attach_shared_contexts() and
    initialize_configs_contexts() in wrolpi/contexts.py, causing version tracking to fail
    in production multi-process environment.
    """
    from sanic import Sanic
    from wrolpi.contexts import attach_shared_contexts, initialize_configs_contexts

    # Create a fresh Sanic app for this test to avoid polluting global state
    test_app = Sanic(f"test_context_{id(test_domains_config_in_shared_context)}")

    # Initialize shared contexts as done in production
    attach_shared_contexts(test_app)
    initialize_configs_contexts(test_app)

    # Verify domains_config has a shared context
    assert hasattr(test_app.shared_ctx, 'domains_config'), \
        "domains_config not found in shared_ctx - add it to attach_shared_contexts() in contexts.py"

    # Verify all other expected configs are also present
    expected_configs = [
        'wrolpi_config',
        'tags_config',
        'inventories_config',
        'channels_config',
        'download_manager_config',
        'videos_downloader_config',
        'domains_config',
    ]
    for config_name in expected_configs:
        assert hasattr(test_app.shared_ctx, config_name), \
            f"{config_name} not found in shared_ctx"


def test_all_configs_in_shared_context():
    """Every config keeps its in-memory data in shared memory.  Switches save configs in the perpetual process, which
    does not import the files; a config with process-local data would save a stale version there."""
    from multiprocessing.managers import DictProxy

    from sanic import Sanic
    from wrolpi.common import get_all_configs
    from wrolpi.contexts import attach_shared_contexts, initialize_configs_contexts

    test_app = Sanic(f"test_context_{id(test_all_configs_in_shared_context)}")
    attach_shared_contexts(test_app)
    initialize_configs_contexts(test_app)

    not_shared = sorted(name for name, config in get_all_configs().items()
                        if not isinstance(getattr(config, '_config', None), DictProxy))
    assert not_shared == [], 'Add these configs to attach_shared_contexts() and initialize_configs_contexts()'


@pytest.mark.parametrize('config_class', config_classes(), ids=lambda i: i.__name__)
def test_initialize_keeps_the_shared_config(test_directory, restore_switch_handlers, config_class):
    """Each Sanic process initializes the configs it shares with the others, while the others already serve, import
    and save them.  Initializing must never show the others anything but the file's data: a config which showed its
    defaults (version 0) for a moment had that version recorded by a concurrent import."""
    config = config_class()
    write_config_files(config, 7)
    shared = SharedDict()
    config.initialize(shared)  # The first process.
    loaded = deepcopy(dict(shared))
    assert loaded

    shared.readable.clear()
    config.initialize(shared)  # Another process.
    assert shared.readable, 'Initializing did not set the shared config'
    assert all(i == loaded for i in shared.readable), 'Another process could read something other than the file'
