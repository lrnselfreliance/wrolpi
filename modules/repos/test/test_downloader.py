import shutil
import subprocess

import pytest
from mock import mock

from modules.repos import lib
from modules.repos.downloader import parse_git_progress
from modules.repos.models import Repository
from wrolpi.downloader import Download, DownloadStatus


def git(directory, *args) -> str:
    return subprocess.run(['git', '-c', 'safe.directory=*', *args], cwd=directory, check=True,
                          capture_output=True).stdout.decode().strip()


@pytest.mark.asyncio
async def test_clone_full(test_session, test_directory, git_remote_factory, repos_download_manager):
    """A new Repo is cloned with its whole history, and the Repo describes the checked out commit."""
    remote = git_remote_factory('kiwix-tools', owner='kiwix', files={'README.md': '# Kiwix\n', 'src/main.c': 'int'})
    remote.commit({'CHANGELOG': 'v2'}, 'Second commit')
    remote.git('tag', 'v2')

    repo = lib.create_repository(test_session, remote.url, tag_name='software')
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    directory = test_directory / 'repos/software/kiwix-tools'
    assert repo.directory == directory
    assert (directory / 'README.md').read_text() == '# Kiwix\n'
    assert (directory / 'src/main.c').is_file()
    # Full mode has all the history and tags.
    assert git(directory, 'rev-list', '--count', 'HEAD') == '2'
    assert git(directory, 'tag') == 'v2'
    assert not (directory / '.git/shallow').exists()

    assert repo.head_sha == remote.head
    assert repo.head_message == 'Second commit'
    assert repo.head_date is not None
    assert repo.default_branch == 'main'
    assert repo.readme_path == 'README.md'
    assert repo.size > 0
    assert repo.last_fetch is not None

    download, = test_session.query(Download).all()
    assert download.status == DownloadStatus.complete
    assert download.location == f'/repos/{repo.id}'
    assert download.error is None


@pytest.mark.asyncio
async def test_update(test_session, test_directory, git_remote_factory, repos_download_manager):
    """An update fetches new commits, and discards local changes (a Repo is a mirror)."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    directory = repo.directory

    # Local changes.
    (directory / 'README.md').write_text('local change')
    (directory / 'untracked.txt').write_text('untracked')

    new_head = remote.commit({'new.txt': 'new'}, 'New file')
    download, = test_session.query(Download).all()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    assert (directory / 'new.txt').read_text() == 'new'
    assert (directory / 'README.md').read_text() == '# example\n\nThe example repo.\n'
    assert not (directory / 'untracked.txt').exists()
    assert repo.head_sha == new_head
    assert repo.head_message == 'New file'


@pytest.mark.asyncio
async def test_update_keeps_history(test_session, git_remote_factory, repos_download_manager):
    """Branches deleted upstream are kept, and history rewritten by a force push is saved in a backup ref."""
    remote = git_remote_factory()
    remote.git('branch', 'feature')
    old_head = remote.commit({'a.txt': 'a'}, 'Will be rewritten')
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    directory = repo.directory
    assert 'origin/feature' in git(directory, 'branch', '--remotes')

    # Upstream deletes a branch, and rewrites main.
    remote.git('branch', '--delete', 'feature')
    remote.git('reset', '--hard', 'HEAD~1')
    new_head = remote.commit({'b.txt': 'b'}, 'Rewritten')

    download, = test_session.query(Download).all()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    assert repo.head_sha == new_head
    assert 'origin/feature' in git(directory, 'branch', '--remotes')
    backups = git(directory, 'for-each-ref', '--format=%(objectname)', 'refs/wrolpi/backup/')
    assert backups == old_head


@pytest.mark.asyncio
async def test_snapshot(test_session, git_remote_factory, repos_download_manager):
    """A snapshot only has the latest commit; switching to full fetches the whole history."""
    remote = git_remote_factory()
    remote.commit({'a.txt': 'a'}, 'Second')
    repo = lib.create_repository(test_session, remote.url, mode='snapshot')
    await repos_download_manager.wait_for_all_downloads()
    directory = repo.directory
    assert (directory / '.git/shallow').is_file()
    assert git(directory, 'rev-list', '--count', 'HEAD') == '1'

    # Snapshot updates stay shallow.
    remote.commit({'b.txt': 'b'}, 'Third')
    download, = test_session.query(Download).all()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    assert (directory / 'b.txt').is_file()
    assert git(directory, 'rev-list', '--count', 'HEAD') == '1'

    lib.update_repository(test_session, repo.id, mode='full')
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    assert not (directory / '.git/shallow').exists()
    assert git(directory, 'rev-list', '--count', 'HEAD') == '3'


@pytest.mark.asyncio
async def test_branch(test_session, git_remote_factory, repos_download_manager):
    """A Repo can follow a branch other than the default branch."""
    remote = git_remote_factory()
    remote.git('checkout', '--quiet', '-b', 'dev')
    dev_head = remote.commit({'dev.txt': 'dev'}, 'Dev')
    remote.git('checkout', '--quiet', 'main')

    repo = lib.create_repository(test_session, f'{remote.url}/tree/dev')
    assert repo.branch == 'dev'
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    assert repo.head_sha == dev_head
    assert repo.default_branch == 'main'
    assert git(repo.directory, 'branch', '--show-current') == 'dev'


@pytest.mark.asyncio
async def test_upstream_gone(test_session, git_remote_factory, repos_download_manager):
    """When the upstream disappears the download is deferred with git's error; the local copy is kept."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    directory = repo.directory
    head = repo.head_sha

    shutil.rmtree(remote.path)
    download, = test_session.query(Download).all()
    download.renew()
    test_session.commit()
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()

    assert download.status == DownloadStatus.deferred
    assert 'git ls-remote failed' in download.error
    assert (directory / 'README.md').is_file()
    assert repo.head_sha == head


@pytest.mark.asyncio
async def test_symlinks_are_not_followed(test_session, git_remote_factory, repos_download_manager):
    """A symlink in a repo is checked out as a plain file, so it cannot expose files outside the repo."""
    remote = git_remote_factory()
    (remote.path / 'shadow').symlink_to('/etc/passwd')
    remote.git('add', 'shadow')
    remote.git('commit', '--quiet', '-m', 'Symlink')

    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    shadow = repo.directory / 'shadow'
    assert not shadow.is_symlink()
    assert shadow.read_text() == '/etc/passwd'


@pytest.mark.asyncio
async def test_refuses_non_empty_directory(test_session, test_directory, git_remote_factory, repos_download_manager):
    """A Repo is never cloned over existing files."""
    remote = git_remote_factory()
    directory = test_directory / 'repos/example'
    directory.mkdir(parents=True)
    (directory / 'important.txt').write_text('important')

    lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    download, = test_session.query(Download).all()
    assert download.status == DownloadStatus.deferred
    assert 'not empty' in download.error
    assert (directory / 'important.txt').read_text() == 'important'
    assert test_session.query(Repository).one().head_sha is None


def test_parse_git_progress():
    assert parse_git_progress('Receiving objects:  45% (123/456), 1.20 MiB | 1.00 MiB/s') == \
           dict(stage='Receiving objects', percent=45)
    assert parse_git_progress('remote: Counting objects: 100% (5/5), done.') == \
           dict(stage='Counting objects', percent=100)
    assert parse_git_progress("Cloning into 'example'...") is None


@pytest.mark.asyncio
async def test_invalid_remote_default_branch(test_session, git_remote_factory, repos_download_manager):
    """The remote chooses its default branch name; an invalid one is never passed to git."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    with mock.patch('modules.repos.downloader.GitDownloader._default_branch', return_value='--upload-pack=x'):
        await repos_download_manager.wait_for_all_downloads()

    download, = test_session.query(Download).all()
    assert download.status == DownloadStatus.deferred
    assert 'Invalid branch' in download.error
    assert not repo.directory.exists()
