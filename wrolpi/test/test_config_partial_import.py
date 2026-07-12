"""A partial (lossy) config import must not allow a dump to overwrite the config file.

The bug: importers that skip entries they cannot resolve (a file not yet indexed, a missing
Tag/Zim, an invalid domain) still mark the import successful.  A later `dump_config` regenerates
the YAML from the (incomplete) database and permanently drops the skipped entries.  After the
SQLite cutover the database is rebuilt from configs, so this would become permanent data loss.

The fix: `ConfigFile.import_skipped` counts entries skipped during import; `ConfigFile.save()`
refuses to overwrite an existing config while `import_skipped` is non-zero (unless
`overwrite=True`).  A later complete import resets the counter and dumps resume.
"""
from copy import deepcopy

import pytest

from modules.archive.lib import get_domains_config
from wrolpi.collections.config import get_playlists_config
from wrolpi.collections.models import Collection
from wrolpi.tags import get_tags_config, Tag


TAGS_YAML = '''version: 1
tags:
  important:
    color: '#ff0000'
tag_files:
- - important
  - docs/report.pdf
  - '2026-01-01T00:00:00'
tag_zims: []
'''


@pytest.mark.asyncio
async def test_tags_partial_import_blocks_dump(async_client, test_session, test_directory, test_tags_config,
                                               await_switches):
    """A tags.yaml entry for a file that is not indexed is skipped; dumps must not drop it."""
    config = get_tags_config()
    file = config.get_file()
    file.write_text(TAGS_YAML)

    # The tagged file does not exist, so the TagFile cannot be restored yet.
    config.import_config()
    assert config.successful_import is True
    assert config.import_skipped == 1
    # The Tag itself was imported.
    assert test_session.query(Tag).filter_by(name='important').count() == 1

    # A background dump (save_tags_config switch) must not overwrite the config.
    before = file.read_text()
    config.dump_config()
    await await_switches()
    assert file.read_text() == before, 'A dump after a partial import must not modify the config file'

    # A direct save also refuses.
    with pytest.raises(RuntimeError, match='skipped'):
        config.save()

    # The escape hatch still works.
    config.save(overwrite=True)


@pytest.mark.asyncio
async def test_tags_import_recovers_after_file_indexed(async_client, test_session, test_directory,
                                                       test_tags_config, await_switches):
    """Once the skipped file can be resolved, a re-import resets the counter and dumps resume."""
    config = get_tags_config()
    file = config.get_file()
    file.write_text(TAGS_YAML)

    config.import_config()
    assert config.import_skipped == 1

    # Create the file; a re-import (e.g. after a refresh) now resolves it.
    report = test_directory / 'docs/report.pdf'
    report.parent.mkdir(parents=True)
    report.write_bytes(b'%PDF-1.4 hello')
    config.import_config()
    assert config.import_skipped == 0
    assert config.successful_import is True

    # Dumps work again, and the previously-skipped entry is preserved.
    config.dump_config()
    await await_switches()
    data = config.read_config_file(file)
    assert ['important', 'docs/report.pdf'] in [i[:2] for i in data['tag_files']]


@pytest.fixture
def playlists_config(async_client):
    config = get_playlists_config()
    config._config = deepcopy(config.default_config)
    return config


PLAYLISTS_YAML = '''version: 1
playlists:
  - name: Survival
    items:
      - file: guide.pdf
      - url: /map?lat=1&lon=2&z=3
'''


@pytest.mark.asyncio
async def test_playlists_partial_import_blocks_dump(test_session, test_directory, playlists_config):
    """A playlist file item that is not indexed is skipped; dumps must not drop it."""
    file = playlists_config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(PLAYLISTS_YAML)

    playlists_config.import_config()
    assert playlists_config.successful_import is True
    assert playlists_config.import_skipped == 1
    collection = test_session.query(Collection).filter_by(name='Survival', kind='playlist').one()
    assert [i.item_kind for i in collection.items] == ['url']

    before = file.read_text()
    with pytest.raises(RuntimeError, match='skipped'):
        playlists_config.dump_config()
    assert file.read_text() == before, 'A dump after a partial import must not modify the config file'

    # Once the file is indexed, a re-import restores the item and dumps resume.
    from wrolpi.files.models import FileGroup
    pdf = test_directory / 'guide.pdf'
    pdf.write_bytes(b'%PDF-1.4 x')
    FileGroup.from_paths(test_session, pdf)
    test_session.commit()

    playlists_config.import_config()
    assert playlists_config.import_skipped == 0
    playlists_config.dump_config()
    data = playlists_config.read_config_file(file)
    items = data['playlists'][0]['items']
    assert dict(file='guide.pdf') in [dict(file=i['file']) for i in items if 'file' in i]


DOMAINS_YAML = '''version: 1
collections:
  - name: example.com
  - name: invaliddomain
'''


@pytest.mark.asyncio
async def test_domains_partial_import_blocks_dump(async_client, test_session, test_directory):
    """A domain entry with an invalid name is skipped; dumps must not drop it."""
    config = get_domains_config()
    file = config.get_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(DOMAINS_YAML)

    config.import_config()
    assert config.successful_import is True
    assert config.import_skipped == 1
    assert test_session.query(Collection).filter_by(kind='domain').count() == 1

    before = file.read_text()
    with pytest.raises(RuntimeError, match='skipped'):
        config.dump_config()
    assert file.read_text() == before, 'A dump after a partial import must not modify the config file'
