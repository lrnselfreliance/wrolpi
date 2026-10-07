import json
import os
from http import HTTPStatus

import pytest
from mock import mock

from modules.repos import lib
from modules.repos.errors import InvalidRepo, RepoConflict
from modules.repos.models import Repository
from wrolpi.collections.models import Collection
from wrolpi.common import get_wrolpi_config
from wrolpi.downloader import Download, DownloadFrequency
from wrolpi.errors import UnknownDirectory, ValidationError
from wrolpi.files.lib import get_normalized_ignored_directories
from wrolpi.files.models import FileGroup


@pytest.mark.parametrize('url,expected', [
    ('https://github.com/kiwix/kiwix-tools',
     lib.ParsedRepoURL('https://github.com/kiwix/kiwix-tools', 'github.com', 'kiwix', 'kiwix-tools')),
    ('https://GitHub.com/kiwix/kiwix-tools.git/',
     lib.ParsedRepoURL('https://github.com/kiwix/kiwix-tools.git', 'github.com', 'kiwix', 'kiwix-tools')),
    ('https://github.com/kiwix/kiwix-tools/tree/feature/x',
     lib.ParsedRepoURL('https://github.com/kiwix/kiwix-tools', 'github.com', 'kiwix', 'kiwix-tools', 'feature/x')),
    ('https://gitlab.com/group/sub/project/-/tree/dev',
     lib.ParsedRepoURL('https://gitlab.com/group/sub/project', 'gitlab.com', 'group/sub', 'project', 'dev')),
    ('https://git.example.com:8443/project',
     lib.ParsedRepoURL('https://git.example.com:8443/project', 'git.example.com', '', 'project')),
])
def test_parse_repo_url(url, expected):
    assert lib.parse_repo_url(url) == expected


@pytest.mark.parametrize('url', [
    'http://github.com/kiwix/kiwix-tools',
    'git@github.com:kiwix/kiwix-tools.git',
    'ssh://git@github.com/kiwix/kiwix-tools',
    'file:///etc',
    'https://user:token@github.com/kiwix/kiwix-tools',
    'https://github.com/kiwix/kiwix-tools?tab=readme',
    'https://github.com',
    'https://github.com/a/..',
    'https://github.com/../b',
    'https://github.com/a/./b',
    '',
])
def test_parse_repo_url_invalid(url):
    with pytest.raises(InvalidRepo):
        lib.parse_repo_url(url)


def test_repo_url_key():
    assert lib.repo_url_key('https://GitHub.com/a/b.git/') == lib.repo_url_key('https://github.com/a/b')
    assert lib.repo_url_key('https://github.com/a/b') != lib.repo_url_key('https://github.com/a/c')


def test_git_command_is_restricted():
    cmd = lib.git_command('clone', 'https://example.com/a')
    assert 'protocol.allow=never' in cmd
    assert 'protocol.https.allow=always' in cmd
    assert 'core.symlinks=false' in cmd
    assert 'core.hooksPath=/dev/null' in cmd
    assert cmd[-2:] == ('clone', 'https://example.com/a')
    assert lib.git_env()['GIT_TERMINAL_PROMPT'] == '0'


@pytest.mark.asyncio
async def test_create_repository(test_session, test_directory, test_wrolpi_config, async_client):
    repo = lib.create_repository(test_session, 'https://github.com/kiwix/kiwix-tools', tag_name='software')

    collection = test_session.query(Collection).one()
    assert collection.kind == 'repo'
    assert collection.name == 'kiwix-tools'
    assert collection.tag_name == 'software'
    assert collection.directory == test_directory / 'repos/software/kiwix-tools'
    assert repo.collection_id == collection.id
    assert (repo.url, repo.host, repo.owner, repo.mode, repo.branch) == \
           ('https://github.com/kiwix/kiwix-tools', 'github.com', 'kiwix', 'full', None)

    # Repos are always kept up to date; weekly by default.
    download = test_session.query(Download).one()
    assert download.url == repo.url
    assert download.downloader == 'git'
    assert download.frequency == DownloadFrequency.weekly
    assert download.collection_id == collection.id
    assert repo.download == download

    # Without a tag.
    repo = lib.create_repository(test_session, 'https://github.com/kiwix/libkiwix')
    assert repo.directory == test_directory / 'repos/libkiwix'


@pytest.mark.asyncio
async def test_create_repository_conflicts(test_session, test_wrolpi_config, async_client):
    lib.create_repository(test_session, 'https://github.com/a/utils')

    # The same repo, even with `.git`.
    with pytest.raises(RepoConflict):
        lib.create_repository(test_session, 'https://github.com/a/utils.git')

    # Another owner's repo with the same name; a new name is suggested.
    with pytest.raises(RepoConflict) as e:
        lib.create_repository(test_session, 'https://github.com/b/utils')
    assert "'b-utils'" in str(e.value)
    test_session.rollback()

    repo = lib.create_repository(test_session, 'https://github.com/b/utils', name='b-utils')
    assert repo.name == 'b-utils'
    assert test_session.query(Repository).count() == 2


@pytest.mark.asyncio
async def test_create_repository_invalid(test_session, test_wrolpi_config, async_client):
    with pytest.raises(InvalidRepo):
        lib.create_repository(test_session, 'http://github.com/a/b')
    with pytest.raises(Exception):
        lib.create_repository(test_session, 'https://github.com/a/b', mode='bare')
    # 0 is never updated.
    with pytest.raises(Exception):
        lib.create_repository(test_session, 'https://github.com/a/b', frequency=-1)


@pytest.mark.asyncio
async def test_repos_destination(test_session, test_directory, test_wrolpi_config, async_client):
    """The repos destination can use the repo's owner and host."""
    get_wrolpi_config().repos_destination = 'repos/%(repo_host)s/%(repo_owner)s/%(repo_name)s'
    repo = lib.create_repository(test_session, 'https://gitlab.com/group/sub/project')
    assert repo.directory == test_directory / 'repos/gitlab.com/group⧸sub/project'

    get_wrolpi_config().repos_destination = 'repos/%(tag_name)s/%(repo_name)s'
    repo = lib.create_repository(test_session, 'https://github.com/a/b', tag_name='Tag')
    assert repo.directory == test_directory / 'repos/Tag/b'


@pytest.mark.asyncio
async def test_update_repository(test_session, test_wrolpi_config, async_client):
    repo = lib.create_repository(test_session, 'https://github.com/a/b', branch='dev')
    lib.update_repository(test_session, repo.id, description='My repo', frequency=DownloadFrequency.daily,
                          mode='snapshot', branch='')
    assert repo.collection.description == 'My repo'
    assert repo.download.frequency == DownloadFrequency.daily
    assert repo.mode == 'snapshot'
    # An empty branch follows the default branch.
    assert repo.branch is None


@pytest.mark.asyncio
async def test_delete_repository(test_session, test_directory, test_wrolpi_config, await_background_tasks,
                                 async_client):
    keep = lib.create_repository(test_session, 'https://github.com/a/keep')
    delete = lib.create_repository(test_session, 'https://github.com/a/delete')
    for repo in (keep, delete):
        repo.directory.mkdir(parents=True)
        (repo.directory / 'README.md').write_text('readme')
    keep_directory, delete_directory = keep.directory, delete.directory

    await lib.delete_repository(test_session, keep.id)
    await lib.delete_repository(test_session, delete.id, delete_files=True)
    await await_background_tasks()

    assert test_session.query(Repository).count() == 0
    assert test_session.query(Collection).count() == 0
    assert test_session.query(Download).count() == 0
    # Files are kept by default.
    assert (keep_directory / 'README.md').is_file()
    assert not delete_directory.exists()


@pytest.mark.asyncio
async def test_list_repo_tree(test_session, test_directory, test_wrolpi_config, async_client):
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    with pytest.raises(UnknownDirectory):
        lib.list_repo_tree(repo)

    root = repo.directory
    (root / '.git').mkdir(parents=True)
    (root / 'src/lib').mkdir(parents=True)
    (root / 'src/Readme.rst').write_text('src')
    (root / 'README.md').write_text('# B')
    (root / 'a.txt').write_text('aaa')
    (root / 'Docs').mkdir()

    tree = lib.list_repo_tree(repo)
    assert tree == dict(
        path='',
        readme_path='README.md',
        entries=[
            dict(name='Docs', path='Docs', is_dir=True, size=None),
            dict(name='src', path='src', is_dir=True, size=None),
            dict(name='a.txt', path='a.txt', is_dir=False, size=3),
            dict(name='README.md', path='README.md', is_dir=False, size=3),
        ],
    )

    tree = lib.list_repo_tree(repo, '/src/')
    assert tree['path'] == 'src'
    assert tree['readme_path'] == 'src/Readme.rst'
    assert [i['path'] for i in tree['entries']] == ['src/lib', 'src/Readme.rst']

    with pytest.raises(InvalidRepo):
        lib.list_repo_tree(repo, '../..')
    with pytest.raises(UnknownDirectory):
        lib.list_repo_tree(repo, 'missing')


@pytest.mark.asyncio
async def test_repos_directory_is_ignored(test_session, test_directory, test_wrolpi_config, refresh_files):
    """Files in the repos directory are never indexed, even when an old config does not ignore it."""
    config = get_wrolpi_config()
    config.ignored_directories = ['config']
    config.import_config()
    assert 'repos' in config.ignored_directories

    (test_directory / 'repos/a/b').mkdir(parents=True)
    (test_directory / 'repos/a/b/README.md').write_text('# B')
    (test_directory / 'other.txt').write_text('other')
    await refresh_files()

    assert [i.primary_path.name for i in test_session.query(FileGroup)] == ['other.txt']


@pytest.mark.parametrize('branch,valid', [
    ('main', True),
    ('feature/x-1', True),
    ('release-1.2', True),
    ('--upload-pack=touch /tmp/pwned', False),
    ('-b', False),
    ('a..b', False),
    ('a b', False),
    ('a~1', False),
    ('a^', False),
    ('a:b', False),
    ('a?', False),
    ('a*', False),
    ('a[', False),
    ('a\\b', False),
    ('a@{1}', False),
    ('@', False),
    ('a/', False),
    ('/a', False),
    ('a//b', False),
    ('a.lock', False),
    ('a/.b', False),
    ('a.', False),
    ('a\x00b', False),
    ('', False),
])
def test_is_valid_branch(branch, valid):
    assert lib.is_valid_branch(branch) is valid


@pytest.mark.asyncio
async def test_invalid_branch_rejected(test_session, async_client, test_wrolpi_config):
    """A branch is passed to git, it must never be read as an option."""
    with pytest.raises(ValidationError):
        lib.create_repository(test_session, 'https://github.com/a/b', branch='--upload-pack=x')
    with pytest.raises(ValidationError):
        lib.create_repository(test_session, 'https://github.com/a/b/tree/a..b')
    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    with pytest.raises(ValidationError):
        lib.update_repository(test_session, repo.id, branch='-x')


@pytest.mark.asyncio
async def test_repo_directory_traversal(test_session, test_directory, async_client, test_wrolpi_config):
    """A Repo's directory is always strictly inside the media directory, and never escapes its template."""
    for name in ('..', '.', ' '):
        with pytest.raises(InvalidRepo):
            lib.create_repository(test_session, 'https://github.com/a/b', tag_name='tag', name=name)
        test_session.rollback()

    with pytest.raises(InvalidRepo):
        lib.create_repository(test_session, 'https://github.com/a/b', directory=test_directory / 'repos/../../etc')
    test_session.rollback()
    with pytest.raises(InvalidRepo):
        lib.create_repository(test_session, 'https://github.com/a/b', directory=test_directory)
    test_session.rollback()

    # The config can not move an existing Repo outside the media directory.
    lib.create_repository(test_session, 'https://github.com/a/b')
    with pytest.raises(InvalidRepo):
        lib.ReposConfig._import_repo(test_session, dict(url='https://github.com/a/b', directory='../outside'))
    test_session.rollback()
    assert test_session.query(Repository).one().directory == test_directory / 'repos/b'


def test_git_env_is_not_inherited():
    """The process environment cannot undo git_command's restrictions."""
    hostile = dict(
        GIT_ALLOW_PROTOCOL='file', GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='url.https://127.0.0.1/.insteadOf',
        GIT_CONFIG_VALUE_0='https://example.com/', GIT_CONFIG_PARAMETERS="'protocol.allow'='always'",
        GIT_SSL_NO_VERIFY='1', GIT_PROXY_COMMAND='evil', GIT_SSH_COMMAND='evil', HTTPS_PROXY='http://127.0.0.1:9',
        https_proxy='http://127.0.0.1:9', CURL_CA_BUNDLE='/tmp/evil.pem', GIT_DIR='/tmp/evil',
    )
    with mock.patch.dict(os.environ, dict(hostile, PATH='/usr/bin:/bin', SSL_CERT_FILE='/etc/ssl/cert.pem')):
        env = lib.git_env()
    assert not set(hostile) & set(env), set(hostile) & set(env)
    assert env['PATH'] == '/usr/bin:/bin'
    assert env['SSL_CERT_FILE'] == '/etc/ssl/cert.pem'
    assert env['GIT_TERMINAL_PROMPT'] == '0'


def test_git_command_ignores_hostile_environment(tmp_path):
    """With git's environment variables set against it, git still refuses file:// (only https is allowed)."""
    import subprocess
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', '--quiet', str(origin)], check=True)
    with mock.patch.dict(os.environ, dict(GIT_ALLOW_PROTOCOL='file')):
        result = subprocess.run(lib.git_command('ls-remote', f'file://{origin}'), env=lib.git_env(),
                                capture_output=True)
    assert result.returncode != 0
    assert b"transport 'file' not allowed" in result.stderr


@pytest.mark.parametrize('destination,error', [
    ('repos/%(repo_tag)s/%(repo_name)s', None),
    ('library/code/%(repo_owner)s/%(repo_name)s', None),
    ('repos/%(tag)s/%(name)s', None),
    ('%(repo_name)s', 'fixed directory'),  # Would put repos in the media directory itself.
    ('%(repo_tag)s/%(repo_name)s', 'fixed directory'),
    ('repos', 'repo name'),  # Every repo in one directory.
    ('repos/%(repo_tag)s', 'repo name'),
    ('repos/%(bogus)s/%(repo_name)s', 'Unknown variable'),
    ('repos/%(repo_name)d', 'Unknown variable'),
    ('/repos/%(repo_name)s', 'relative'),
    ('../repos/%(repo_name)s', '".."'),
    ('repos/./%(repo_name)s', '".."'),
    ('videos/%(repo_name)s', 'videos_destination'),
    ('archive/x/%(repo_name)s', 'archive_destination'),
    ('playlists/%(repo_name)s', 'playlists_destination'),
    ('tags/%(repo_name)s', 'tags directory'),
    ('config/%(repo_name)s', 'config directory'),
    ('', 'empty'),
])
@pytest.mark.asyncio
async def test_validate_repos_destination(async_client, test_wrolpi_config, destination, error):
    result = lib.validate_repos_destination(destination)
    if error is None:
        assert result == ''
    else:
        assert error in result, result


def test_repos_destination_root():
    assert lib.repos_destination_root('repos/%(repo_tag)s/%(repo_name)s') == 'repos'
    assert lib.repos_destination_root('library/code/%(repo_name)s') == 'library/code'
    assert lib.repos_destination_root('%(repo_name)s') == ''


@pytest.mark.asyncio
async def test_repos_destination_is_ignored(test_session, test_directory, async_client, test_wrolpi_config,
                                            refresh_files):
    """Wherever repos are saved, their files are not indexed."""
    body = dict(repos_destination='%(repo_name)s')
    request, response = await async_client.patch('/api/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    body = dict(repos_destination='library/code/%(repo_tag)s/%(repo_name)s')
    request, response = await async_client.patch('/api/settings', content=json.dumps(body))
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert str(test_directory / 'library/code') in get_normalized_ignored_directories()

    repo = lib.create_repository(test_session, 'https://github.com/a/b')
    assert repo.directory == test_directory / 'library/code/b'
    repo.directory.mkdir(parents=True)
    (repo.directory / 'README.md').write_text('# B')
    (test_directory / 'other.txt').write_text('other')
    await refresh_files()
    assert [i.primary_path.name for i in test_session.query(FileGroup)] == ['other.txt']

    # A hand-edited config which breaks the rules falls back to the default.
    config = get_wrolpi_config()
    config.save(overwrite=True)
    data = config.read_config_file()
    data['repos_destination'] = '%(repo_name)s'
    data['version'] = (data.get('version') or 0) + 1
    config.write_config_data(data, config.get_file())
    config.import_config()
    assert config.repos_destination == 'repos/%(repo_tag)s/%(repo_name)s'
