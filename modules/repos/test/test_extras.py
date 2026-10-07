import io
import subprocess
import zipfile
from http import HTTPStatus

import pytest
from mock import mock

from modules.repos import lib
from modules.repos.models import Repository
from wrolpi.downloader import Download, DownloadStatus

# The repo the submodules belong to, and the (public) address its host resolved to.
REPO = lib.HostAddresses('git.example.com', 443, ['93.184.215.14'])


def git(directory, *args) -> str:
    return subprocess.run(['git', '-c', 'safe.directory=*', *args], cwd=directory, check=True,
                          capture_output=True).stdout.decode().strip()


async def update(test_session, repos_download_manager):
    download = test_session.query(Download).one()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    return test_session.query(Download).one()


@pytest.mark.asyncio
async def test_log(test_session, async_client, git_remote_factory, repos_download_manager):
    """The history of the checked out branch, newest first, a page at a time."""
    remote = git_remote_factory()
    second = remote.commit({'a.txt': 'a'}, 'Second')
    third = remote.commit({'b.txt': 'b'}, 'Third: with a | and a\ttab')
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    request, response = await async_client.get(f'/api/repos/{repo.id}/log?limit=2')
    assert response.status_code == HTTPStatus.OK
    assert response.json['total'] == 3
    assert [(i['sha'], i['message']) for i in response.json['commits']] == \
           [(third, 'Third: with a | and a\ttab'), (second, 'Second')]
    assert response.json['commits'][0]['author'] == 'WROLPi Test'
    assert response.json['commits'][0]['date']

    request, response = await async_client.get(f'/api/repos/{repo.id}/log?limit=2&offset=2')
    assert [i['message'] for i in response.json['commits']] == ['Initial commit']

    request, response = await async_client.get(f'/api/repos/{repo.id}/log?limit=nope')
    assert response.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_log_not_downloaded(test_session, async_client, test_wrolpi_config):
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    request, response = await async_client.get(f'/api/repos/{repo.id}/log')
    assert response.status_code == HTTPStatus.NOT_FOUND
    request, response = await async_client.get(f'/api/repos/{repo.id}/archive.zip')
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_archive(test_session, async_client, git_remote_factory, repos_download_manager):
    """A ZIP of the checked out commit; local changes and `.git` are not in it."""
    remote = git_remote_factory(files={'README.md': '# Example', 'src/main.c': 'int main;'})
    repo = lib.create_repository(test_session, remote.url, name='my "repo"\r\nX-Evil: 1')
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    (repo.directory / 'untracked.txt').write_text('local')

    request, response = await async_client.get(f'/api/repos/{repo.id}/archive.zip')
    assert response.status_code == HTTPStatus.OK
    assert response.headers['content-type'] == 'application/zip'
    # The name is safe in a header.
    name = f'my_repo_X-Evil_1-{repo.head_sha[:7]}'
    assert response.headers['content-disposition'] == f'attachment; filename="{name}.zip"'
    assert 'x-evil' not in response.headers

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [f'{name}/', f'{name}/README.md', f'{name}/src/', f'{name}/src/main.c']
        assert archive.read(f'{name}/src/main.c') == b'int main;'


@pytest.mark.asyncio
async def test_submodules(test_session, git_remote_factory, repos_download_manager):
    """Submodules are only downloaded when the Repo asks for them, and are removed when it no longer does."""
    library = git_remote_factory('library', files={'lib.c': 'v1'})
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library)

    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    submodule = repo.directory / 'vendor/library'
    assert not (submodule / 'lib.c').exists()

    lib.update_repository(test_session, repo.id, submodules=True)
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.complete
    assert (submodule / 'lib.c').read_text() == 'v1'
    # The submodule has its history, like the Repo.
    assert git(submodule, 'rev-list', '--count', 'HEAD') == '1'

    # A new submodule commit is checked out when the Repo points at it.
    library.commit({'lib.c': 'v2'}, 'v2')
    remote.git('update-index', '--cacheinfo', f'160000,{library.head},vendor/library')
    remote.git('commit', '--quiet', '-m', 'Bump library')
    await update(test_session, repos_download_manager)
    assert (submodule / 'lib.c').read_text() == 'v2'

    lib.update_repository(test_session, repo.id, submodules=False)
    await update(test_session, repos_download_manager)
    assert not (submodule / 'lib.c').exists()


@pytest.mark.asyncio
async def test_submodule_failure(test_session, git_remote_factory, repos_download_manager):
    """A submodule which cannot be downloaded (e.g. an ssh URL) does not stop the Repo from updating."""
    library = git_remote_factory('library')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library)
    # Rewrite the submodule's URL to one git may not use.
    (remote.path / '.gitmodules').write_text(
        '[submodule "vendor/library"]\n\tpath = vendor/library\n\turl = ssh://git@git.example.com/owner/library\n')
    (remote.path / 'new.txt').write_text('new')
    # Not `remote.commit`, whose `add --all` would delete the submodule (it is not checked out in the remote).
    remote.git('add', '.gitmodules', 'new.txt')
    remote.git('commit', '--quiet', '-m', 'ssh submodule')
    head = remote.head

    repo = lib.create_repository(test_session, remote.url, submodules=True)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'its submodules were not' in download.error
    # The Repo itself is current.
    assert repo.head_sha == head
    assert (repo.directory / 'new.txt').is_file()


@pytest.mark.asyncio
async def test_submodules_api_and_config(test_session, async_client, test_wrolpi_config, await_switches):
    body = '{"url": "https://github.com/a/b", "submodules": true}'
    request, response = await async_client.post('/api/repos', content=body)
    assert response.status_code == HTTPStatus.CREATED
    assert response.json['repo']['submodules'] is True
    repo_id = response.json['repo']['id']

    await await_switches()
    assert lib.get_repos_config().repos[0]['submodules'] is True

    request, response = await async_client.put(f'/api/repos/{repo_id}', content='{"submodules": false}')
    assert response.json['repo']['submodules'] is False

    # Restored from the config.
    config = lib.get_repos_config()
    data = config.read_config_file()
    data['repos'][0]['submodules'] = True
    data['version'] += 1
    config.write_config_data(data, config.get_file())
    config.import_config()
    test_session.expire_all()
    assert test_session.query(Repository).one().submodules is True


@pytest.mark.asyncio
async def test_archive_after_session_closes(test_session, async_client, git_remote_factory, repos_download_manager):
    """In production the request's session is closed once a streamed response starts; the ZIP must not need it."""
    from sanic import Request

    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    original_respond = Request.respond

    async def respond_and_close_session(self, *args, **kwargs):
        response = await original_respond(self, *args, **kwargs)
        test_session.expunge_all()
        return response

    with mock.patch.object(Request, 'respond', respond_and_close_session):
        request, response = await async_client.get(f'/api/repos/{repo.id}/archive.zip')
    assert response.status_code == HTTPStatus.OK
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert any(i.endswith('/README.md') for i in archive.namelist())


@pytest.mark.parametrize('url,resolved,allowed', [
    # Relative URLs are resolved by git (against the repo's remote) before they are checked.
    ('../library.git', None, False),
    ('./library', None, False),
    ('https://git.example.com/owner/library', None, True),  # The repo's own host.
    ('https://codeberg.org/owner/library', ['217.197.91.145'], True),
    ('https://localhost/library', ['127.0.0.1'], False),
    ('https://127.0.0.1/library', None, False),
    ('https://10.0.0.5/library', None, False),
    ('https://192.168.1.1:8443/library', None, False),
    ('https://[::1]/library', None, False),
    ('https://169.254.169.254/latest', None, False),
    ('https://gitea.lan/library', ['192.168.1.20'], False),
    ('https://mixed.example/library', ['93.184.215.14', '10.0.0.1'], False),
    ('https://unresolvable.example/library', OSError('no such host'), False),
    ('http://codeberg.org/owner/library', None, False),
    ('ssh://git@codeberg.org/owner/library', None, False),
    ('file:///etc', None, False),
    # URLs which parsers disagree about are refused.
    ('https://codeberg.org\\@10.0.0.5/library', ['217.197.91.145'], False),
    ('https://user@codeberg.org/owner/library', ['217.197.91.145'], False),
    ('https://10.0.0.5#@codeberg.org/library', ['217.197.91.145'], False),
    ('https://codeberg.org/owner/library?x=@10.0.0.5', ['217.197.91.145'], False),
    ('https://codeberg.org/owner/lib rary', ['217.197.91.145'], False),
    ('https://codeberg.org:443/owner/library', ['217.197.91.145'], True),
    ('../../evil@10.0.0.5/x', None, False),
    ('..\\evil', None, False),
])
def test_submodule_url_error(url, resolved, allowed):
    """A submodule URL comes from the (untrusted) repo; it may not make WROLPi fetch from its own network."""
    side_effect = resolved if isinstance(resolved, Exception) else None
    with mock.patch('modules.repos.lib.resolve_host_addresses', side_effect=side_effect,
                    return_value=resolved or []):
        error = lib.submodule_url_error(url, REPO)
    assert (error is None) is allowed, error


@pytest.mark.asyncio
async def test_submodule_to_private_address(test_session, git_remote_factory, repos_download_manager):
    """A submodule which points into WROLPi's network is never fetched; the repo itself still updates."""
    library = git_remote_factory('library')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library, url='https://10.0.0.5/admin/library')

    repo = lib.create_repository(test_session, remote.url, submodules=True)
    with mock.patch('modules.repos.lib.resolve_host_addresses', return_value=['93.184.215.14']) as resolve:
        await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'not a public address' in download.error
    assert repo.head_sha == remote.head
    assert not (repo.directory / 'vendor/library/README.md').exists()
    # Only the repo's own host was resolved; an IP address is checked without DNS.
    assert [i.args for i in resolve.call_args_list] == [('git.example.com',)]


@pytest.mark.asyncio
async def test_nested_submodule_to_private_address(test_session, git_remote_factory, repos_download_manager):
    """Each level of submodules is checked before it is fetched."""
    evil = git_remote_factory('evil')
    library = git_remote_factory('library')
    library.add_submodule('nested', evil, url='https://127.0.0.1/evil')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library)

    repo = lib.create_repository(test_session, remote.url, submodules=True)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'not a public address' in download.error
    # The first level (the repo's own host) was fetched; the nested submodule was not.
    assert (repo.directory / 'vendor/library/README.md').is_file()
    assert not (repo.directory / 'vendor/library/nested/README.md').exists()


@pytest.mark.parametrize('gitmodules', [
    # A space in the name must not hide the URL.
    '[submodule "a b"]\n\tpath = vendor/library\n\turl = https://10.0.0.5/library\n',
    # Nor a newline in the URL.
    '[submodule "library"]\n\tpath = vendor/library\n\turl = "https://10.0.0.5/library\\nsubmodule.x.path y"\n',
])
@pytest.mark.asyncio
async def test_submodule_url_cannot_hide(test_session, git_remote_factory, repos_download_manager, gitmodules):
    """Every submodule URL is checked, however the .gitmodules is written."""
    library = git_remote_factory('library')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library)
    (remote.path / '.gitmodules').write_text(gitmodules)
    remote.git('add', '.gitmodules')
    remote.git('commit', '--quiet', '-m', 'Tricky .gitmodules')

    repo = lib.create_repository(test_session, remote.url, submodules=True)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'Refusing' in download.error
    assert not (repo.directory / 'vendor/library/README.md').exists()



def test_submodule_fetch_config():
    """Checked hosts are pinned to the addresses that were checked, so DNS cannot change between the check and git's
    fetch."""
    with mock.patch('modules.repos.lib.resolve_host_addresses', return_value=['217.197.91.145', '2606:4700::1111']):
        config = lib.submodule_fetch_config(['https://codeberg.org/a/b', 'https://codeberg.org:8443/c/d',
                                             'https://git.example.com/own/host'], REPO)
    assert config == (
        'http.followRedirects=false',
        'http.curloptResolve=codeberg.org:443:217.197.91.145,[2606:4700::1111]',
        'http.curloptResolve=codeberg.org:8443:217.197.91.145,[2606:4700::1111]',
    )



@pytest.mark.parametrize('relative_url,allowed', [
    ('../library', True),  # https://git.example.com/owner/library
    ('../../../10.0.0.5/library', False),  # git resolves this to https://10.0.0.5/library
])
@pytest.mark.asyncio
async def test_relative_submodule_url(test_session, git_remote_factory, repos_download_manager, relative_url,
                                      allowed):
    """A relative submodule URL is checked where git resolves it, which may be another host."""
    library = git_remote_factory('library')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library, url=relative_url)

    repo = lib.create_repository(test_session, remote.url, submodules=True)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    download = test_session.query(Download).one()
    if allowed:
        assert download.status == DownloadStatus.complete, download.error
        assert (repo.directory / 'vendor/library/README.md').is_file()
    else:
        assert download.status == DownloadStatus.deferred
        assert 'Refusing to download submodule https://10.0.0.5/library' in download.error
        assert not (repo.directory / 'vendor/library/README.md').exists()


@pytest.mark.parametrize('address,public', [
    ('8.8.8.8', True),
    ('2606:4700::1111', True),
    ('64:ff9b::808:808', True),  # NAT64 of 8.8.8.8
    ('2002:808:808::1', True),  # 6to4 of 8.8.8.8
    ('10.0.0.5', False),
    ('100.64.0.1', False),  # Carrier-grade NAT
    ('127.0.0.1', False),
    ('169.254.169.254', False),
    ('224.0.0.1', False),  # Multicast
    ('255.255.255.255', False),
    ('0.0.0.0', False),
    ('::1', False),
    ('::', False),
    ('fe80::1', False),
    ('fc00::1', False),
    ('fec0::1', False),  # Deprecated site-local
    ('ff02::1', False),  # Multicast
    ('::ffff:169.254.169.254', False),
    ('64:ff9b::169.254.169.254', False),  # NAT64 of the metadata address
    ('64:ff9b::a9fe:a9fe', False),
    ('64:ff9b:1::808:808', False),  # Local-use NAT64
    ('2002:a00:5::1', False),  # 6to4 of 10.0.0.5
    ('2001:0:4136:e378:8000:63bf:3fff:fdd2', False),  # Teredo
])
def test_is_public_address(address, public):
    import ipaddress
    assert lib.is_public_address(ipaddress.ip_address(address)) is public


@pytest.mark.parametrize('url', [
    'https://[64:ff9b::169.254.169.254]/latest/meta-data',
    'https://[64:ff9b::a9fe:a9fe]/',
    'https://[fec0::1]/',
    'https://224.0.0.1/',
])
def test_submodule_url_error_rejects_non_public_literals(url):
    assert lib.submodule_url_error(url, REPO)



def test_submodule_on_repo_host():
    """The repo's own host is fetched from the addresses the repo was fetched from, never resolved again (so its
    DNS cannot change in between).  The same name on another port is checked like any other host."""
    lan_forge = lib.HostAddresses('git.lan', 443, ['192.168.1.20'])
    with mock.patch('modules.repos.lib.resolve_host_addresses', return_value=['127.0.0.1']) as resolve:
        # A LAN forge the user chose: its own submodules work.
        assert lib.submodule_url_error('https://git.lan/owner/library', lan_forge) is None
        assert lib.submodule_url_error('https://git.lan:443/owner/library', lan_forge) is None
        resolve.assert_not_called()
        # Another port on that name (e.g. a Docker API) is not the repo.
        assert 'not a public address' in lib.submodule_url_error('https://git.lan:2375/x', lan_forge)

    # A repo host which could not be resolved cannot vouch for anything.
    unresolved = lib.HostAddresses('git.lan', 443, None)
    assert lib.submodule_url_error('https://git.lan/owner/library', unresolved)
    # An address needs no DNS.
    literal = lib.HostAddresses('192.168.1.20', 443, None)
    assert lib.submodule_url_error('https://192.168.1.20/owner/library', literal) is None


@pytest.mark.parametrize('url,expected', [
    ('https://git.example.com/owner/repo', lib.HostAddresses('git.example.com', 443, ['93.184.215.14'])),
    ('https://git.example.com:8443/repo', lib.HostAddresses('git.example.com', 8443, ['93.184.215.14'])),
    ('https://192.168.1.20/repo', lib.HostAddresses('192.168.1.20', 443, None)),
])
def test_resolve_repo_addresses(url, expected):
    with mock.patch('modules.repos.lib.resolve_host_addresses', return_value=['93.184.215.14']):
        assert lib.resolve_repo_addresses(url) == expected
    assert lib.pin_config(lib.HostAddresses('h', 443, ['1.2.3.4', '2606:4700::1111'])) == \
           'http.curloptResolve=h:443:1.2.3.4,[2606:4700::1111]'
    assert lib.pin_config(lib.HostAddresses('h', 443, None)) is None


@pytest.mark.asyncio
async def test_repo_fetches_are_pinned(test_session, git_remote_factory, repos_download_manager):
    """Every git command which connects to the repo's host connects to the address resolved at the start."""
    from modules.repos.downloader import GitDownloader
    remote = git_remote_factory()
    remote.commit({'a.txt': 'a'}, 'Second')
    lib.create_repository(test_session, remote.url)

    commands = []
    original = GitDownloader.process_runner

    async def record(self, download, cmd, *args, **kwargs):
        commands.append([str(i) for i in cmd])
        return await original(self, download, cmd, *args, **kwargs)

    with mock.patch('modules.repos.lib.resolve_host_addresses', return_value=['93.184.215.14']), \
            mock.patch.object(GitDownloader, 'process_runner', record):
        await repos_download_manager.wait_for_all_downloads()
        await update(test_session, repos_download_manager)

    pin = 'http.curloptResolve=git.example.com:443:93.184.215.14'
    network = [i for i in commands if {'ls-remote', 'clone', 'fetch'} & set(i)]
    assert {'ls-remote', 'clone', 'fetch'} <= {j for i in network for j in i}
    assert all(pin in i for i in network), network
