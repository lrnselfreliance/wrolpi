import json
from http import HTTPStatus

import pytest

from modules.repos import lib
from modules.repos.models import Repository
from wrolpi.conftest import await_file_worker
from wrolpi.downloader import Download, DownloadFrequency, DownloadStatus
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_repos_crud(test_session, test_directory, async_client, test_wrolpi_config):
    body = dict(url='https://github.com/kiwix/kiwix-tools', tag_name='software', frequency=DownloadFrequency.daily)
    request, response = await async_client.post('/api/repos', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CREATED, response.json
    repo = response.json['repo']
    assert repo['name'] == 'kiwix-tools'
    assert repo['tag_name'] == 'software'
    assert repo['directory'] == 'repos/software/kiwix-tools'
    assert repo['mode'] == 'full'
    assert repo['frequency'] == DownloadFrequency.daily
    assert repo['download_status'] == DownloadStatus.new
    assert repo['location'] == f'/repos/{repo["id"]}'
    repo_id = repo['id']

    request, response = await async_client.post('/api/repos', content=json.dumps(dict(url='https://github.com/a/b')))
    assert response.status_code == HTTPStatus.CREATED

    request, response = await async_client.get('/api/repos')
    assert response.status_code == HTTPStatus.OK
    assert [i['name'] for i in response.json['repos']] == ['b', 'kiwix-tools']

    body = dict(description='Kiwix tools', mode='snapshot', branch='dev', frequency=DownloadFrequency.weekly)
    request, response = await async_client.put(f'/api/repos/{repo_id}', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK, response.json
    request, response = await async_client.get(f'/api/repos/{repo_id}')
    repo = response.json['repo']
    assert (repo['description'], repo['mode'], repo['branch'], repo['frequency']) == \
           ('Kiwix tools', 'snapshot', 'dev', DownloadFrequency.weekly)

    request, response = await async_client.delete(f'/api/repos/{repo_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get(f'/api/repos/{repo_id}')
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json['code'] == 'UNKNOWN_REPO'


@pytest.mark.asyncio
async def test_create_repo_errors(test_session, async_client, test_wrolpi_config):
    request, response = await async_client.post('/api/repos', content=json.dumps(dict(url='git@github.com:a/b')))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json['code'] == 'INVALID_REPO'

    request, response = await async_client.post('/api/repos', content=json.dumps(dict(url='https://github.com/a/b')))
    assert response.status_code == HTTPStatus.CREATED
    request, response = await async_client.post('/api/repos',
                                                content=json.dumps(dict(url='https://github.com/a/b.git')))
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json['code'] == 'REPO_CONFLICT'


@pytest.mark.asyncio
async def test_repo_tree_and_update(test_session, async_client, git_remote_factory, repos_download_manager):
    remote = git_remote_factory(files={'README.md': '# Example', 'docs/guide.md': 'guide'})
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    request, response = await async_client.get(f'/api/repos/{repo.id}/tree')
    assert response.status_code == HTTPStatus.OK
    assert response.json['readme_path'] == 'README.md'
    assert [i['path'] for i in response.json['entries']] == ['docs', 'README.md']

    request, response = await async_client.get(f'/api/repos/{repo.id}/tree?path=docs')
    assert [i['path'] for i in response.json['entries']] == ['docs/guide.md']

    request, response = await async_client.get(f'/api/repos/{repo.id}/tree?path=../..')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # "Update now" renews the download.
    new_head = remote.commit({'new.txt': 'new'}, 'New')
    request, response = await async_client.post(f'/api/repos/{repo.id}/update')
    assert response.status_code == HTTPStatus.NO_CONTENT
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    assert test_session.query(Repository).one().head_sha == new_head


@pytest.mark.asyncio
async def test_tag_repo_moves_clone(test_session, test_directory, async_client, git_remote_factory,
                                    repos_download_manager, await_background_tasks):
    """Tagging a Repo (through the collections API) moves the whole clone, including `.git`.  Its files are not
    indexed (repos/ is ignored), even ones the file mover could not group."""
    remote = git_remote_factory(files={'README.md': '# Example', 'web/.npmrc': 'a', 'web/.gitignore': 'b'})
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    old_directory = test_directory / 'repos/example'
    assert (old_directory / '.git').is_dir()

    body = dict(tag_name='software', directory='repos/software/example')
    request, response = await async_client.post(f'/api/collections/{repo.collection_id}/tag',
                                                content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK, response.json
    await await_background_tasks()
    test_session.expire_all()

    new_directory = test_directory / 'repos/software/example'
    assert repo.directory == new_directory
    assert repo.tag_name == 'software'
    assert (new_directory / '.git').is_dir()
    assert (new_directory / 'README.md').is_file()
    assert (new_directory / 'web/.npmrc').is_file()
    assert not old_directory.exists()
    assert test_session.query(Download).one().destination == new_directory
    assert test_session.query(FileGroup).count() == 0

    # The moved clone still updates.
    new_head = remote.commit({'new.txt': 'new'}, 'New')
    download = test_session.query(Download).one()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    assert repo.head_sha == new_head
    assert (new_directory / 'new.txt').is_file()


@pytest.mark.asyncio
async def test_tag_repo_in_custom_directory(test_session, test_directory, async_client, git_remote_factory,
                                            repos_download_manager, await_background_tasks, refresh_files):
    """A Repo in a directory which is not ignored is indexed where it is moved to, and not where it was."""
    remote = git_remote_factory(files={'README.md': '# Example', 'guide.md': 'A guide'})
    repo = lib.create_repository(test_session, remote.url, directory='projects/example')
    await repos_download_manager.wait_for_all_downloads()
    await refresh_files()
    old_directory = test_directory / 'projects/example'
    assert test_session.query(FileGroup).filter(FileGroup.primary_path == str(old_directory / 'guide.md')).count()

    body = dict(tag_name='software', directory='projects/moved')
    request, response = await async_client.post(f'/api/collections/{repo.collection_id}/tag',
                                                content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK, response.json
    await await_background_tasks()
    await await_file_worker()
    test_session.expire_all()

    new_directory = test_directory / 'projects/moved'
    assert repo.directory == new_directory
    assert (new_directory / '.git').is_dir()
    assert not old_directory.exists()
    paths = {i.primary_path for i in test_session.query(FileGroup)}
    assert new_directory / 'guide.md' in paths
    assert not [i for i in paths if old_directory in i.parents]


@pytest.mark.parametrize('directory', ['../escape/example', 'repos/../../escape/example', '{media}/../escape/example',
                                       'linked/example'])
@pytest.mark.asyncio
async def test_tag_repo_cannot_leave_media_directory(test_session, test_directory, async_client, git_remote_factory,
                                                     repos_download_manager, await_background_tasks,
                                                     tmp_path_factory, directory):
    """Tagging cannot move a Repo's clone out of the media directory, by `..` or through a link."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    outside = tmp_path_factory.mktemp('outside')
    (test_directory / 'linked').symlink_to(outside)

    body = dict(tag_name='software', directory=directory.format(media=test_directory))
    request, response = await async_client.post(f'/api/collections/{repo.collection_id}/tag',
                                                content=json.dumps(body))
    await await_background_tasks()
    test_session.expire_all()

    assert (test_directory / 'repos/example/.git').is_dir()
    assert repo.directory == test_directory / 'repos/example'
    assert not (test_directory.parent / 'escape').exists()
    assert list(outside.iterdir()) == []


@pytest.mark.asyncio
async def test_repos_destination_setting(async_client, test_wrolpi_config):
    request, response = await async_client.get('/api/settings')
    assert response.json['repos_destination'] == 'repos/%(repo_tag)s/%(repo_name)s'

    body = dict(repos_destination='/repos')
    request, response = await async_client.patch('/api/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    body = dict(repos_destination='repos/%(repo_owner)s/%(repo_name)s')
    request, response = await async_client.patch('/api/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    request, response = await async_client.get('/api/settings')
    assert response.json['repos_destination'] == 'repos/%(repo_owner)s/%(repo_name)s'


@pytest.mark.asyncio
async def test_repo_changes_wait_for_config_import(test_session, test_directory, async_client, git_remote_factory,
                                                   repos_download_manager, test_wrolpi_config):
    """Until repos.yaml is imported (e.g. while WROLPi starts), Repos cannot change; the import would undo it."""
    remote = git_remote_factory()
    other = git_remote_factory('other')
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    config = lib.get_repos_config()
    config.dump_config()
    assert config.get_file().is_file()
    config.successful_import = False

    requests = [
        ('post', '/api/repos', dict(url=other.url)),
        ('post', '/api/repos/import', dict(directory='repos/example', confirm=True)),
        ('put', f'/api/repos/{repo.id}', dict(description='changed')),
        ('delete', f'/api/repos/{repo.id}', None),
        ('post', f'/api/collections/{repo.collection_id}/tag', dict(tag_name='software',
                                                                     directory='repos/software/example')),
        ('put', f'/api/collections/{repo.collection_id}', dict(description='changed')),
        ('delete', f'/api/collections/{repo.collection_id}', None),
    ]
    for method, url, body in requests:
        kwargs = dict(content=json.dumps(body)) if body else {}
        request, response = await getattr(async_client, method)(url, **kwargs)
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE, (url, response.json)
        assert response.json['code'] == 'CONFIG_NOT_IMPORTED'
    test_session.expire_all()
    assert test_session.query(Repository).count() == 1
    assert repo.collection.description is None
    assert repo.tag_name is None
    assert (test_directory / 'repos/example/.git').is_dir()

    # Once imported, Repos can change again.
    lib.import_repos_config()
    request, response = await async_client.put(f'/api/repos/{repo.id}', content=json.dumps(dict(description='x')))
    assert response.status_code == HTTPStatus.OK, response.json
