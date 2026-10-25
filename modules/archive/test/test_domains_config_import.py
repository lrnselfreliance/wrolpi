"""domains.yaml imports by diffing its domain Collections against the database, and writing only the differences
(see wrolpi.config_import).  A domain removed from the file is deleted, unless it has Archives: then it is reset to
its default settings (a refresh of its Archives would re-create it)."""
import pytest
import yaml

from modules.archive.lib import get_domains_config, import_domains_config
from modules.archive.models import Archive
from wrolpi.collections import Collection
from wrolpi.config_version import get_config_version
from wrolpi.downloader import Download
from wrolpi.test.test_config_import import edit_config, statements, writes


@pytest.fixture
async def saved_domains(test_session, test_directory, async_client, archive_factory, tag_factory, await_switches):
    """`example.com` (tagged, in a custom directory), `other.org`, and `archived.net` (which has an Archive and a
    description), saved to the config (which records its version)."""
    tag = await tag_factory('news')
    archive_factory(domain='archived.net', url='https://archived.net/a')
    test_session.commit()
    archived = test_session.query(Collection).filter_by(name='archived.net', kind='domain').one()
    archived.description = 'Has archives'
    test_session.add_all([
        Collection(name='example.com', kind='domain', description='Example', tag_id=tag.id,
                   directory=test_directory / 'archive/news/example.com'),
        Collection(name='other.org', kind='domain'),
    ])
    test_session.commit()
    get_domains_config().dump_config()
    await await_switches()
    assert get_config_version(test_session, 'domains.yaml') is not None
    return get_domains_config().get_file()


def domains(test_session) -> dict:
    test_session.expire_all()
    return {i.name: i for i in test_session.query(Collection).filter_by(kind='domain')}


def edit_domain(path, name, **values):
    def change(data):
        next(i for i in data['collections'] if i['name'] == name).update(values)

    edit_config(path, change)


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_domains):
    """Importing a config the database already matches opens no write transaction, nor does linking Downloads when
    there are none to link."""
    config = get_domains_config()
    with statements() as collected:
        import_domains_config()

    assert config.successful_import is True
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, test_directory, saved_domains):
    """A changed domain is updated, a removed one (without Archives) is deleted, an added one is created; the next
    import writes nothing."""
    def change(data):
        data['collections'] = [i for i in data['collections'] if i['name'] != 'other.org']
        data['collections'].append(dict(name='new.com', kind='domain', description='New'))
        example = next(i for i in data['collections'] if i['name'] == 'example.com')
        example.update(description='Changed', tag_name=None, directory='archive/example.com')

    edit_config(saved_domains, change)
    config = get_domains_config()
    config.import_config()

    assert config.successful_import is True
    found = domains(test_session)
    assert set(found) == {'example.com', 'archived.net', 'new.com'}
    example = found['example.com']
    assert (example.description, example.tag_id, example.directory) == \
           ('Changed', None, test_directory / 'archive/example.com')
    assert found['new.com'].description == 'New'
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_removed_domain_with_archives_is_reset(test_session, saved_domains, await_switches):
    """A domain with Archives that is removed from the config keeps its Archives, and is reset to its default
    settings; the config is saved with it, so the next import writes nothing."""
    edit_config(saved_domains, lambda data: data.update(
        collections=[i for i in data['collections'] if i['name'] != 'archived.net']))

    config = get_domains_config()
    config.import_config()
    await await_switches()

    archived = domains(test_session)['archived.net']
    assert archived.description is None
    assert test_session.query(Archive).filter_by(collection_id=archived.id).count() == 1
    assert 'archived.net' in saved_domains.read_text()
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_invalid_entries_are_kept(test_session, saved_domains):
    """An entry with an invalid name or directory is skipped (counted), and its domain is not deleted."""
    edit_domain(saved_domains, 'other.org', directory='../outside')
    edit_config(saved_domains, lambda data: data['collections'].append(dict(name='nodot', kind='domain')))

    config = get_domains_config()
    config.import_config()

    assert config.import_skipped == 2
    assert set(domains(test_session)) == {'example.com', 'other.org', 'archived.net'}


@pytest.mark.asyncio
async def test_unknown_tag_is_dropped(test_session, saved_domains, test_tags_config, await_switches):
    """Once tags.yaml is imported, a domain's Tag that no longer exists is dropped and the config is saved without
    it: the next import writes nothing."""
    from wrolpi.tags import get_tags_config
    get_tags_config().dump_config()
    get_tags_config().import_config()
    edit_domain(saved_domains, 'other.org', tag_name='gone')

    config = get_domains_config()
    config.import_config()
    await await_switches()

    assert domains(test_session)['other.org'].tag_id is None
    assert 'gone' not in saved_domains.read_text()
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_downloads_are_linked(test_session, saved_domains, await_switches):
    """After the import, an RSS archive Download of a domain is linked to it (the domains are read once, not once
    per Download), and the config is saved with it."""
    test_session.add_all([
        Download(url='https://other.org/feed.xml', downloader='rss', sub_downloader='archive', frequency=86400),
        Download(url='https://example.com/feed.xml', downloader='rss', sub_downloader='archive', frequency=86400),
    ])
    test_session.commit()

    with statements() as collected:
        import_domains_config()
    await await_switches()

    found = domains(test_session)
    assert {i.url: i.collection_id for i in test_session.query(Download)} == {
        'https://other.org/feed.xml': found['other.org'].id,
        'https://example.com/feed.xml': found['example.com'].id,
    }
    assert len([i for i in collected if 'FROM collection' in i and 'WHERE collection.name' in i]) == 0
    assert 'https://other.org/feed.xml' in saved_domains.read_text()
