"""repos.yaml imports by diffing its Repos against the database, and writing only the differences (see
wrolpi.config_import).  A Repo is keyed by its URL (`repo_url_key`)."""
import pytest
import yaml

from modules.repos import lib
from modules.repos.models import Repository
from wrolpi.config_version import get_config_version
from wrolpi.downloader import DownloadFrequency
from wrolpi.test.test_config_import import edit_config, statements, writes

ONE = 'https://github.com/a/one'
TWO = 'https://github.com/a/two'


@pytest.fixture
async def saved_repos(test_session, async_client, test_wrolpi_config, await_switches):
    """Repo `one` (tagged, daily) and `two` (a snapshot of a branch), saved to the config (which records its
    version)."""
    lib.create_repository(test_session, ONE, tag_name='software', description='One', frequency=DownloadFrequency.daily)
    lib.create_repository(test_session, TWO, mode='snapshot', branch='dev')
    await await_switches()
    config = lib.get_repos_config()
    config.dump_config()
    await await_switches()
    assert get_config_version(test_session, 'repos.yaml') is not None
    return config.get_file()


def edit_repo(path, repo_url, **values):
    def change(data):
        next(i for i in data["repos"] if i["url"] == repo_url).update(values)

    edit_config(path, change)


def repos(test_session) -> dict:
    test_session.expire_all()
    return {i.url: i for i in test_session.query(Repository)}


@pytest.mark.asyncio
async def test_unchanged_import_writes_nothing(test_session, saved_repos):
    """Importing a config the database already matches opens no write transaction."""
    config = lib.get_repos_config()
    with statements() as collected:
        config.import_config()

    assert config.successful_import is True
    assert writes(collected) == []
    # The version, then one snapshot of the Repos.
    assert len(collected) <= 3, collected


@pytest.mark.asyncio
async def test_same_repo_by_another_url_is_unchanged(test_session, saved_repos):
    """A URL of the same Repo (a `.git` suffix, the host's case) is that Repo."""
    edit_repo(saved_repos, TWO, url='https://GitHub.com/a/two.git')
    config = lib.get_repos_config()
    with statements() as collected:
        config.import_config()

    assert writes(collected) == []
    assert set(repos(test_session)) == {ONE, TWO}


@pytest.mark.asyncio
async def test_import_writes_only_the_differences(test_session, saved_repos):
    """A changed Repo is updated, a removed one is deleted (with its Download), an added one is created."""
    def change(data):
        one = next(i for i in data['repos'] if i['url'] == ONE)
        one.update(description='Changed', frequency='never', mode='snapshot', branch='main')
        data['repos'] = [one, dict(url='https://github.com/a/three', mode='full')]

    edit_config(saved_repos, change)
    config = lib.get_repos_config()
    config.import_config()

    assert config.successful_import is True
    found = repos(test_session)
    assert set(found) == {ONE, 'https://github.com/a/three'}
    one = found[ONE]
    assert (one.collection.description, one.mode, one.branch, one.download) == ('Changed', 'snapshot', 'main', None)
    assert found['https://github.com/a/three'].download.frequency == lib.DEFAULT_REPO_FREQUENCY
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_invalid_entry_is_kept(test_session, saved_repos):
    """A Repo whose entry is invalid is skipped, not deleted; the others are still imported."""
    edit_repo(saved_repos, TWO, mode='bogus')
    edit_repo(saved_repos, ONE, description='Changed')

    config = lib.get_repos_config()
    config.import_config()

    assert config.import_skipped == 1
    found = repos(test_session)
    assert set(found) == {ONE, TWO}
    assert (found[TWO].mode, found[ONE].collection.description) == ('snapshot', 'Changed')


@pytest.mark.asyncio
async def test_malformed_entry_is_skipped(test_session, saved_repos):
    """An entry that is not a mapping is skipped and counted; the rest of the file still imports."""
    edit_repo(saved_repos, ONE, description='Changed')
    edit_config(saved_repos, lambda data: data['repos'].insert(0, 'not a mapping'))

    config = lib.get_repos_config()
    config.import_config()

    assert config.successful_import is True
    assert config.import_skipped == 1
    found = repos(test_session)
    assert set(found) == {ONE, TWO}
    assert found[ONE].collection.description == 'Changed'


@pytest.mark.asyncio
async def test_only_malformed_entries_delete_nothing(test_session, saved_repos):
    """A file whose entries are all unreadable deletes no Repo (like an empty list)."""
    edit_config(saved_repos, lambda data: data.update(repos=['not a mapping', dict(url=['a', 'list'])]))

    config = lib.get_repos_config()
    config.import_config()

    assert config.import_skipped == 2
    assert set(repos(test_session)) == {ONE, TWO}


@pytest.mark.asyncio
async def test_failed_import_creates_nothing(test_session, saved_repos, monkeypatch):
    """A new Repo is created in the import's one write: a failure later in the write leaves nothing (each new Repo
    was committed on its own)."""
    edit_config(saved_repos, lambda data: data['repos'].append(dict(url='https://github.com/a/three')))
    edit_config(saved_repos, lambda data: data.update(repos=[i for i in data['repos'] if i['url'] != TWO]))

    def fail(*args, **kwargs):
        raise RuntimeError('Write failed')

    monkeypatch.setattr(lib, '_delete_repository', fail)
    with pytest.raises(RuntimeError):
        lib.get_repos_config().import_config()

    assert set(repos(test_session)) == {ONE, TWO}


@pytest.mark.asyncio
async def test_branch_url_is_its_repo(test_session, saved_repos):
    """A forge's branch URL (GitHub `/tree/<branch>`, GitLab `/-/tree/<branch>`) is its Repo, with that branch;
    the next import writes nothing."""
    edit_repo(saved_repos, TWO, url=f'{TWO}/tree/main', branch=None)
    edit_config(saved_repos, lambda data: data['repos'].append(
        dict(url='https://gitlab.com/group/sub/project/-/tree/dev')))

    config = lib.get_repos_config()
    config.import_config()

    assert config.successful_import is True
    found = repos(test_session)
    assert set(found) == {ONE, TWO, 'https://gitlab.com/group/sub/project'}
    assert (found[TWO].branch, found['https://gitlab.com/group/sub/project'].branch) == ('main', 'dev')
    with statements() as collected:
        config.import_config()
    assert writes(collected) == []


@pytest.mark.asyncio
async def test_invalid_branch_url_entry_is_kept(test_session, saved_repos):
    """An invalid entry named by its Repo's branch URL keeps that Repo."""
    edit_repo(saved_repos, TWO, url=f'{TWO}/tree/main', mode='bogus')

    config = lib.get_repos_config()
    config.import_config()

    assert config.import_skipped == 1
    assert set(repos(test_session)) == {ONE, TWO}
