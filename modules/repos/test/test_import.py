import json
import subprocess
from http import HTTPStatus

import pytest

from modules.repos import lib
from modules.repos.errors import InvalidRepo, RepoConflict
from modules.repos.models import Repository
from wrolpi.downloader import Download, DownloadStatus
from wrolpi.errors import UnknownDirectory, ValidationError
from wrolpi.files.models import FileGroup


def git(directory, *args) -> str:
    env = dict(GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t',
               PATH='/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin')
    return subprocess.run(['git', '-c', 'safe.directory=*', *args], cwd=directory, check=True, env=env,
                          capture_output=True).stdout.decode().strip()


@pytest.fixture
def user_clone(test_directory, git_remote_factory):
    """A clone the user made themselves, in their media directory, with an `origin`."""

    def factory(relative='code/kiwix-tools', remote=None):
        remote = remote or git_remote_factory('kiwix-tools', owner='kiwix', files={'README.md': '# Kiwix tools'})
        directory = test_directory / relative
        directory.parent.mkdir(parents=True, exist_ok=True)
        git(directory.parent, 'clone', '--quiet', str(remote.path), directory.name)
        git(directory, 'remote', 'set-url', 'origin', remote.url)
        return directory, remote

    return factory


@pytest.mark.parametrize('origin,expected', [
    ('https://github.com/kiwix/kiwix-tools', 'https://github.com/kiwix/kiwix-tools'),
    ('https://github.com/kiwix/kiwix-tools.git', 'https://github.com/kiwix/kiwix-tools.git'),
    ('git@github.com:kiwix/kiwix-tools.git', 'https://github.com/kiwix/kiwix-tools'),
    ('ssh://git@github.com:22/kiwix/kiwix-tools.git', 'https://github.com/kiwix/kiwix-tools'),
    ('git://github.com/kiwix/kiwix-tools', 'https://github.com/kiwix/kiwix-tools'),
    ('/home/user/kiwix-tools', None),
    ('../kiwix-tools', None),
])
def test_remote_https_url(origin, expected):
    assert lib.remote_https_url(origin) == expected


def test_remote_url_key():
    assert lib.remote_url_key('git@GitHub.com:kiwix/kiwix-tools.git') == \
           lib.remote_url_key('https://github.com/kiwix/kiwix-tools/') == 'github.com/kiwix/kiwix-tools'
    assert lib.remote_url_key('https://github.com/kiwix/other') != lib.remote_url_key('https://github.com/kiwix/x')
    assert lib.remote_url_key('/local/path') is None


@pytest.mark.asyncio
async def test_inspect_import(test_session, async_client, test_wrolpi_config, user_clone):
    """Inspecting a clone reports what an import would do, and changes nothing."""
    directory, remote = user_clone()
    git(directory, 'commit', '--quiet', '--allow-empty', '-m', 'Local work')
    config_before = (directory / '.git/config').read_text()

    request, response = await async_client.post('/api/repos/import/inspect',
                                                content=json.dumps(dict(directory='code/kiwix-tools')))
    assert response.status_code == HTTPStatus.OK, response.json
    info = response.json['inspection']
    assert info['directory'] == 'code/kiwix-tools'
    assert info['origin'] == remote.url
    assert info['url'] == remote.url
    assert info['name'] == 'kiwix-tools'
    assert info['branch'] == 'main'
    assert info['head_message'] == 'Local work'
    assert info['head_sha'] == git(directory, 'rev-parse', 'HEAD')
    assert info['head_date']
    assert info['local_commits'] == 1
    assert info['shallow'] is False
    # The clone stays where it is, where its files are indexed.
    assert info['ignored'] is False

    assert (directory / '.git/config').read_text() == config_before
    assert not (directory / '.git' / lib.REPO_MARKER).exists()

    # A clone in the Repos directory is ignored.
    user_clone('repos/other', remote=remote)
    assert lib.inspect_import(test_session, 'repos/other')['ignored'] is True


@pytest.mark.asyncio
async def test_inspect_import_refuses(test_session, test_directory, async_client, test_wrolpi_config, user_clone):
    (test_directory / 'not-git').mkdir()
    with pytest.raises(InvalidRepo):
        lib.inspect_import(test_session, 'not-git')
    with pytest.raises(UnknownDirectory):
        lib.inspect_import(test_session, 'missing')
    for directory in ('', '/etc', '../outside', 'config', 'tags', 'videos'):
        (test_directory / 'videos').mkdir(exist_ok=True)
        with pytest.raises((InvalidRepo, UnknownDirectory)):
            lib.inspect_import(test_session, directory)

    # `.git` must be the clone's own directory.
    (test_directory / 'gitfile').mkdir()
    (test_directory / 'gitfile/.git').write_text('gitdir: /etc\n')
    with pytest.raises(InvalidRepo):
        lib.inspect_import(test_session, 'gitfile')

    # A partial clone's missing objects would come from the network.
    directory, _ = user_clone('code/partial')
    git(directory, 'config', 'remote.origin.promisor', 'true')
    with pytest.raises(InvalidRepo, match='partial clone'):
        lib.inspect_import(test_session, 'code/partial')

    # Already a Repo, or inside one.
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    repo.directory.mkdir(parents=True)
    git(repo.directory, 'init', '--quiet')
    with pytest.raises(RepoConflict):
        lib.inspect_import(test_session, 'repos/b')


@pytest.mark.asyncio
async def test_import(test_session, test_directory, async_client, test_wrolpi_config, user_clone,
                      repos_download_manager, refresh_files):
    """An imported clone stays where it is, is owned by WROLPi, and is updated like any Repo."""
    directory, remote = user_clone()
    (directory / 'local-note.txt').write_text('untracked')
    with (directory / '.git/config').open('a') as fh:
        fh.write('[http]\n\tproxy = http://127.0.0.1:9\n[user]\n\tname = Someone\n')
    await refresh_files()
    indexed = test_session.query(FileGroup).filter(FileGroup.primary_path.contains('code/kiwix-tools')).count()
    assert indexed

    body = dict(directory='code/kiwix-tools', tag_name='Software', confirm=True, frequency=86400)
    request, response = await async_client.post('/api/repos/import', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CREATED, response.json
    imported = response.json['repo']
    assert imported['name'] == 'kiwix-tools'
    assert imported['url'] == remote.url
    assert imported['directory'] == 'code/kiwix-tools'
    assert imported['tag_name'] == 'Software'
    assert imported['frequency'] == 86400
    assert imported['branch'] is None  # Follows the default branch, like a new Repo.
    assert imported['head_sha'] == remote.head
    assert imported['readme_path'] == 'README.md'

    assert (directory / 'README.md').is_file()
    assert (directory / '.git' / lib.REPO_MARKER).is_file()
    config = (directory / '.git/config').read_text()
    assert 'proxy' not in config and 'Someone' not in config
    # It was not moved (or ignored); its files are still indexed.
    assert not (test_directory / 'repos').exists()
    await refresh_files()
    assert test_session.query(FileGroup).filter(FileGroup.primary_path.contains('code/kiwix-tools')).count()

    # From now on it is a mirror: an update fetches the origin, and discards local files.
    await repos_download_manager.wait_for_all_downloads()
    head = remote.commit({'new.txt': 'new'}, 'New upstream')
    download = test_session.query(Download).one()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.complete, download.error
    assert test_session.query(Repository).one().head_sha == head
    assert (directory / 'new.txt').is_file()
    assert not (directory / 'local-note.txt').exists()


@pytest.mark.asyncio
async def test_import_refuses(test_session, test_directory, async_client, test_wrolpi_config, user_clone,
                              git_remote_factory):
    directory, remote = user_clone()

    # Without confirmation.
    with pytest.raises(ValidationError):
        await lib.import_repository(test_session, 'code/kiwix-tools')
    # A URL which is not the clone's origin.
    with pytest.raises(InvalidRepo, match="not this clone's origin"):
        await lib.import_repository(test_session, 'code/kiwix-tools', url='https://github.com/evil/other',
                                    confirm=True)
    test_session.rollback()
    assert test_session.query(Repository).count() == 0
    assert not (directory / '.git' / lib.REPO_MARKER).exists()

    # Without an https origin, the URL must be given (and must still be the origin).
    other, _ = user_clone('code/ssh-clone', remote=git_remote_factory('library'))
    git(other, 'remote', 'set-url', 'origin', 'git@git.example.com:owner/library.git')
    assert lib.inspect_import(test_session, 'code/ssh-clone')['url'] == 'https://git.example.com/owner/library'
    git(other, 'remote', 'remove', 'origin')
    assert lib.inspect_import(test_session, 'code/ssh-clone')['url'] is None
    with pytest.raises(InvalidRepo, match='https:// URL'):
        await lib.import_repository(test_session, 'code/ssh-clone', confirm=True)
    repo = await lib.import_repository(test_session, 'code/ssh-clone', url='https://git.example.com/owner/library',
                                       confirm=True)
    assert repo.url == 'https://git.example.com/owner/library'
    assert repo.directory == other


@pytest.mark.asyncio
async def test_refused_import_changes_nothing(test_session, test_directory, async_client, test_wrolpi_config,
                                              user_clone):
    """Everything which can refuse an import is checked before the clone is changed."""
    directory, _ = user_clone()
    (directory / 'other').mkdir()
    (directory / 'other/.git').write_text(f'gitdir: {test_directory}\n')
    config_before = (directory / '.git/config').read_text()
    with pytest.raises(InvalidRepo, match='outside'):
        await lib.import_repository(test_session, 'code/kiwix-tools', confirm=True)
    test_session.rollback()
    assert (directory / '.git/config').read_text() == config_before
    assert not (directory / '.git' / lib.REPO_MARKER).exists()
    assert test_session.query(Repository).count() == 0


@pytest.mark.asyncio
async def test_inspect_never_reads_the_clones_config(test_session, test_directory, async_client, test_wrolpi_config,
                                                     user_clone):
    """Inspecting runs no git command with the clone's (unsanitized) config: one git refuses to read still inspects."""
    directory, remote = user_clone()
    with (directory / '.git/config').open('a') as fh:
        fh.write('[core]\n\trepositoryformatversion = 1\n[extensions]\n\tnotAnExtension = true\n'
                 f'[include]\n\tpath = {test_directory}/included.gitconfig\n')
    # git itself refuses this repository.
    assert subprocess.run(['git', '-c', 'safe.directory=*', 'rev-parse', 'HEAD'], cwd=directory,
                          capture_output=True).returncode != 0

    info = lib.inspect_import(test_session, 'code/kiwix-tools')
    assert info['head_sha'] == remote.head
    assert info['head_message'] == 'Initial commit'
    assert info['local_commits'] == 0


def test_working_tree_git_file_is_read_like_git(tmp_path):
    """git trims only the line ending from a `.git` file, not spaces; so does WROLPi."""
    repo = tmp_path / 'repo'
    (repo / '.git/modules/library/objects').mkdir(parents=True)
    (repo / '.git/modules/library/HEAD').write_text('ref: refs/heads/main\n')
    (repo / 'vendor/library').mkdir(parents=True)
    # git reads this as "<...>/library " (with the space): not the checked git directory.
    (repo / 'vendor/library/.git').write_text('gitdir: ../../.git/modules/library/../../../.. \n')
    assert lib.working_tree_git_error(repo)
    (repo / 'vendor/library/.git').write_text('gitdir: ../../.git/modules/library\r\n')
    assert lib.working_tree_git_error(repo) is None



@pytest.mark.asyncio
async def test_create_repository_in_a_directory(test_session, test_directory, async_client, test_wrolpi_config,
                                                git_remote_factory, repos_download_manager, refresh_files):
    """A Repo can be cloned into a directory the user chooses.  It is not ignored: its files are indexed."""
    remote = git_remote_factory(files={'README.md': '# Example', 'guide.md': 'A guide'})
    body = dict(url=remote.url, directory='projects/example', tag_name='Software')
    request, response = await async_client.post('/api/repos', content=json.dumps(body))
    assert response.status_code == HTTPStatus.CREATED, response.json
    assert response.json['repo']['directory'] == 'projects/example'
    await repos_download_manager.wait_for_all_downloads()

    directory = test_directory / 'projects/example'
    assert (directory / 'guide.md').is_file()
    await refresh_files()
    assert test_session.query(FileGroup).filter(FileGroup.primary_path.contains('projects/example')).count()


@pytest.mark.parametrize('directory,error', [
    ('/etc/example', 'relative'),
    ('../example', 'relative'),
    ('.', 'media directory'),
    ('videos', 'cannot be used'),
    ('config/example', 'cannot be used'),
    ('tags', 'cannot be used'),
    ('not-empty', 'not empty'),
    ('existing-repo/inside', 'Collection'),
])
@pytest.mark.asyncio
async def test_create_repository_directory_refused(test_session, test_directory, async_client, test_wrolpi_config,
                                                   directory, error):
    (test_directory / 'videos').mkdir()
    (test_directory / 'not-empty').mkdir()
    (test_directory / 'not-empty/file.txt').write_text('mine')
    lib.create_repository(test_session, 'https://github.com/a/existing', directory='existing-repo')

    body = dict(url='https://github.com/a/b', directory=directory)
    request, response = await async_client.post('/api/repos', content=json.dumps(body))
    assert response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.CONFLICT), response.json
    assert error in response.json['error'], response.json
    assert (test_directory / 'not-empty/file.txt').read_text() == 'mine'
