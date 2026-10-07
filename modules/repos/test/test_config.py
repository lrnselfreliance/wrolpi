import pytest

from modules.repos import lib
from modules.repos.models import Repository
from wrolpi.collections.models import Collection
from wrolpi.downloader import Download, DownloadFrequency


@pytest.mark.asyncio
async def test_dump_and_import(test_session, test_directory, async_client, test_wrolpi_config, await_switches):
    """repos.yaml is the source of truth; a lost database is rebuilt from it."""
    lib.create_repository(test_session, 'https://github.com/kiwix/kiwix-tools', tag_name='software',
                          description='Tools', frequency=DownloadFrequency.daily)
    lib.create_repository(test_session, 'https://github.com/a/b', mode='snapshot', branch='dev')
    await await_switches()

    config = lib.get_repos_config()
    assert config.get_file().is_file()
    # Each Repo's random clone token is kept, so a restored Repo still owns its clone.
    dumped = [dict(i) for i in config.repos]
    assert all(len(i.pop('clone_token')) == 32 for i in dumped)
    assert dumped == [
        dict(name='b', url='https://github.com/a/b', directory='repos/b', tag_name=None, description=None,
             mode='snapshot', branch='dev', submodules=False, frequency=DownloadFrequency.weekly),
        dict(name='kiwix-tools', url='https://github.com/kiwix/kiwix-tools', directory='repos/software/kiwix-tools',
             tag_name='software', description='Tools', mode='full', branch=None, submodules=False,
             frequency=DownloadFrequency.daily),
    ]

    # Lose the database.
    for repo in test_session.query(Repository).all():
        lib._delete_repository(test_session, repo)
    test_session.commit()
    assert test_session.query(Collection).count() == 0

    config.import_config()
    test_session.expire_all()
    repos = {i.name: i for i in test_session.query(Repository)}
    assert repos['kiwix-tools'].directory == test_directory / 'repos/software/kiwix-tools'
    assert repos['kiwix-tools'].tag_name == 'software'
    assert repos['kiwix-tools'].collection.description == 'Tools'
    assert repos['kiwix-tools'].download.frequency == DownloadFrequency.daily
    assert (repos['b'].mode, repos['b'].branch) == ('snapshot', 'dev')
    assert {i.downloader for i in test_session.query(Download)} == {'git'}

    # A repo removed from the config is deleted.
    data = config.read_config_file()
    data['repos'] = data['repos'][1:]
    data['version'] += 1
    config.write_config_data(data, config.get_file())
    config.import_config()
    test_session.expire_all()
    assert [i.name for i in test_session.query(Repository)] == ['kiwix-tools']
    assert test_session.query(Download).count() == 1


@pytest.mark.asyncio
async def test_import_links_existing_download(test_session, async_client, test_wrolpi_config):
    """A Repo imported after download_manager.yaml re-uses its Download."""
    lib.create_repository(test_session, 'https://github.com/a/b')
    test_session.query(Repository).delete()
    test_session.query(Collection).delete()
    test_session.commit()
    download = test_session.query(Download).one()
    assert download.collection_id is None

    config = lib.get_repos_config()
    config.write_config_data(dict(version=1, repos=[dict(name='b', url='https://github.com/a/b', frequency=3600)]),
                             config.get_file())
    config.import_config()
    test_session.expire_all()

    repo = test_session.query(Repository).one()
    assert test_session.query(Download).one().id == download.id
    assert download.collection_id == repo.collection_id
    assert download.frequency == 3600


@pytest.mark.asyncio
async def test_delete_last_repo(test_session, async_client, test_wrolpi_config, await_switches):
    """Deleting the last Repo empties the config, so it does not return on the next import."""
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    await await_switches()
    config = lib.get_repos_config()
    assert len(config.read_config_file()['repos']) == 1

    request, response = await async_client.delete(f'/api/repos/{repo.id}')
    assert config.read_config_file()['repos'] == []

    config.import_config()
    assert test_session.query(Repository).count() == 0
