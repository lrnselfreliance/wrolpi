"""A Repo which is never updated: its clone is kept as it is (e.g. its upstream is gone), and only updated on
request."""
import json
import subprocess
from http import HTTPStatus

import pytest
import yaml

from modules.repos import lib
from modules.repos.models import Repository
from wrolpi.downloader import Download, DownloadFrequency, DownloadStatus


def edit_config(config, change):
    """Hand-edit each Repo in repos.yaml."""
    data = yaml.safe_load(config.get_file().read_text())
    data['repos'] = [change(i) for i in data['repos']]
    config.get_file().write_text(yaml.dump(data))


async def get_repo(async_client, repo_id: int) -> dict:
    request, response = await async_client.get(f'/api/repos/{repo_id}')
    assert response.status_code == HTTPStatus.OK, response.json
    return response.json['repo']


@pytest.mark.asyncio
async def test_never_stops_updates(test_session, test_directory, async_client, test_wrolpi_config,
                                   git_remote_factory, repos_download_manager):
    """Changing a Repo to Never deletes its recurring Download (and its error); its clone is kept."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    download = test_session.query(Download).one()
    download.error = 'fatal: repository not found'
    download.status = DownloadStatus.deferred
    test_session.commit()

    request, response = await async_client.put(f'/api/repos/{repo.id}', content=json.dumps(dict(frequency=0)))
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['repo']['frequency'] == 0
    assert response.json['repo']['download_error'] is None
    assert test_session.query(Download).count() == 0
    assert (repo.directory / '.git').is_dir()

    # Back to weekly.
    request, response = await async_client.put(f'/api/repos/{repo.id}',
                                               content=json.dumps(dict(frequency=DownloadFrequency.weekly)))
    assert response.status_code == HTTPStatus.OK, response.json
    assert response.json['repo']['frequency'] == DownloadFrequency.weekly
    download = test_session.query(Download).one()
    assert download.frequency == DownloadFrequency.weekly
    assert download.collection_id == repo.collection_id


@pytest.mark.asyncio
async def test_never_new_repo_clones_once(test_session, test_directory, async_client, test_wrolpi_config,
                                          git_remote_factory, repos_download_manager):
    """A new Repo which is never updated is cloned once."""
    remote = git_remote_factory()
    body = dict(url=remote.url, frequency=0)
    request, response = await async_client.post('/api/repos', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CREATED, response.json
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    repo = test_session.query(Repository).one()
    assert repo.head_sha == remote.head
    assert repo.download is None
    download = test_session.query(Download).one()
    assert download.frequency is None and download.collection_id is None
    assert download.status == DownloadStatus.complete
    assert (await get_repo(async_client, repo.id))['frequency'] == 0

    # Back to weekly; the clone's (one-time) Download becomes the recurring Download.
    request, response = await async_client.put(f'/api/repos/{repo.id}',
                                               content=json.dumps(dict(frequency=DownloadFrequency.weekly)))
    assert response.status_code == HTTPStatus.OK, response.json
    download = test_session.query(Download).one()
    assert download.frequency == DownloadFrequency.weekly
    assert download.collection_id == repo.collection_id


@pytest.mark.asyncio
async def test_never_update_now(test_session, test_directory, async_client, test_wrolpi_config,
                                git_remote_factory, repos_download_manager):
    """A Repo which is never updated is updated on request, as often as requested; a failure is shown."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url, frequency=0)
    await repos_download_manager.wait_for_all_downloads()

    for _ in range(2):
        head = remote.commit({'new.txt': remote.head}, 'New')
        request, response = await async_client.post(f'/api/repos/{repo.id}/update')
        assert response.status_code == HTTPStatus.NO_CONTENT, response.json
        await repos_download_manager.wait_for_all_downloads()
        test_session.expire_all()
        assert repo.head_sha == head
        assert repo.download is None

    # The upstream is gone.
    subprocess.run(['rm', '-rf', str(remote.path)], check=True)
    request, response = await async_client.post(f'/api/repos/{repo.id}/update')
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    data = await get_repo(async_client, repo.id)
    assert data['download_error']
    assert data['frequency'] == 0
    assert repo.head_sha == head


@pytest.mark.asyncio
async def test_never_import(test_session, test_directory, async_client, test_wrolpi_config, git_remote_factory,
                            repos_download_manager):
    """An imported clone which is never updated is never fetched."""
    remote = git_remote_factory()
    clone = test_directory / 'code/example'
    subprocess.run(['git', 'clone', '--quiet', str(remote.path), str(clone)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(clone), 'remote', 'set-url', 'origin', remote.url], check=True)
    await lib.import_repository(test_session, 'code/example', url=remote.url, confirm=True, frequency=0)
    test_session.commit()
    assert test_session.query(Download).count() == 0
    assert test_session.query(Repository).one().head_sha == remote.head


@pytest.mark.asyncio
async def test_never_config(test_session, test_directory, async_client, test_wrolpi_config, git_remote_factory,
                            repos_download_manager):
    """Never is saved in repos.yaml.  A restored Repo is cloned once if its clone is missing, and is otherwise left
    as it is."""
    kept, missing = git_remote_factory('kept'), git_remote_factory('missing')
    lib.create_repository(test_session, kept.url, frequency=0)
    lib.create_repository(test_session, missing.url, frequency=DownloadFrequency.daily)
    await repos_download_manager.wait_for_all_downloads()
    config = lib.get_repos_config()
    config.dump_config()
    assert {i['name']: i['frequency'] for i in config.repos} == {'kept': 'never', 'missing': DownloadFrequency.daily}

    # A Repo whose frequency is missing from the config is updated weekly.
    edit_config(config, lambda i: {k: v for k, v in i.items() if not (i['name'] == 'missing' and k == 'frequency')})

    # Lose the database, and one clone.
    for repo in test_session.query(Repository).all():
        lib._delete_repository(test_session, repo)
    for download in test_session.query(Download).all():
        test_session.delete(download)
    test_session.commit()
    subprocess.run(['rm', '-rf', str(test_directory / 'repos/missing')], check=True)

    config.import_config()
    test_session.expire_all()
    repos = {i.name: i for i in test_session.query(Repository)}
    assert repos['kept'].download is None
    assert repos['missing'].download.frequency == DownloadFrequency.weekly
    # Only the missing clone is downloaded.
    assert [i.url for i in test_session.query(Download)] == [repos['missing'].url]

    # Never, in a hand-edited config.
    edit_config(config, lambda i: dict(i, frequency='never'))
    config.import_config()
    test_session.expire_all()
    assert test_session.query(Download).count() == 0


@pytest.mark.asyncio
async def test_never_delete(test_session, test_directory, async_client, test_wrolpi_config, git_remote_factory,
                            repos_download_manager):
    """Deleting a Repo which is never updated deletes its one-time Download."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url, frequency=0)
    await repos_download_manager.wait_for_all_downloads()
    assert test_session.query(Download).count() == 1
    await lib.delete_repository(test_session, repo.id)
    assert test_session.query(Download).count() == 0
