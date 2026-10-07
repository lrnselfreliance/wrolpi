import os
import pathlib
import subprocess
from typing import Callable

import pytest
from mock import mock

from modules.repos import lib
from modules.repos.downloader import GitDownloader
from wrolpi.downloader import DownloadManager

# Commits made by the tests have a fixed identity and do not read the developer's git config.
TEST_GIT_ENV = dict(
    GIT_AUTHOR_NAME='WROLPi Test', GIT_AUTHOR_EMAIL='test@example.com',
    GIT_COMMITTER_NAME='WROLPi Test', GIT_COMMITTER_EMAIL='test@example.com',
    GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
)


class GitRemote:
    """A local repo which the Repos module sees as `https://git.example.com/<owner>/<name>`."""

    def __init__(self, path: pathlib.Path, url: str):
        self.path = path
        self.url = url

    def git(self, *args: str) -> str:
        env = dict(os.environ, **TEST_GIT_ENV)
        result = subprocess.run(['git', *args], cwd=self.path, env=env, check=True, capture_output=True)
        return result.stdout.decode().strip()

    def commit(self, files: dict, message: str = 'Commit') -> str:
        """Write `files` ({relative path: contents}), commit them, return the commit's sha."""
        for name, contents in files.items():
            file = self.path / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(contents)
        self.git('add', '--all')
        self.git('commit', '--quiet', '-m', message)
        return self.git('rev-parse', 'HEAD')

    @property
    def head(self) -> str:
        return self.git('rev-parse', 'HEAD')

    def add_submodule(self, path: str, submodule: 'GitRemote', url: str = None) -> str:
        """Add `submodule` (at its current commit) at `path`, and commit it.  `url` overrides the submodule's URL."""
        gitmodules = self.path / '.gitmodules'
        existing = gitmodules.read_text() if gitmodules.exists() else ''
        gitmodules.write_text(f'{existing}[submodule "{path}"]\n\tpath = {path}\n\turl = {url or submodule.url}\n')
        self.git('update-index', '--add', '--cacheinfo', f'160000,{submodule.head},{path}')
        self.git('add', '.gitmodules')
        self.git('commit', '--quiet', '-m', f'Add submodule {path}')
        return self.head


@pytest.fixture
def git_remote_factory(tmp_path_factory) -> Callable[..., GitRemote]:
    """Create local git repos which are cloned over `https://git.example.com/...` URLs.

    git's `url.<base>.insteadOf` rewrites the https URL to the local path, and `file://` is allowed for the test,
    so the Repos module runs the same commands it runs in production."""
    remotes = dict()
    # Outside the media directory (which is `tmp_path`).
    remotes_directory = tmp_path_factory.mktemp('remotes')

    def git_env():
        env = original_git_env()
        env['GIT_CONFIG_COUNT'] = str(len(remotes))
        for idx, (url, path) in enumerate(remotes.items()):
            env[f'GIT_CONFIG_KEY_{idx}'] = f'url.file://{path}.insteadOf'
            env[f'GIT_CONFIG_VALUE_{idx}'] = url
        return env

    original_git_env = lib.git_env

    def factory(name: str = 'example', owner: str = 'owner', branch: str = 'main',
                files: dict = None) -> GitRemote:
        path = remotes_directory / owner / name
        path.mkdir(parents=True)
        url = f'https://git.example.com/{owner}/{name}'
        remote = GitRemote(path, url)
        remote.git('init', '--quiet', f'--initial-branch={branch}')
        remote.commit(files or {'README.md': f'# {name}\n\nThe {name} repo.\n'}, 'Initial commit')
        remotes[url] = path
        return remote

    def resolve_host_addresses(host):
        # The remotes' host has a fixed public address; no test uses real DNS.
        if host == 'git.example.com':
            return ['93.184.215.14']
        raise OSError(f'Unknown host {host}')

    with mock.patch('modules.repos.lib.ALLOWED_PROTOCOLS', ('https', 'file')), \
            mock.patch('modules.repos.downloader.git_env', git_env), \
            mock.patch('modules.repos.lib.resolve_host_addresses', resolve_host_addresses):
        yield factory


@pytest.fixture
def repos_download_manager(test_download_manager) -> DownloadManager:
    test_download_manager.register_downloader(GitDownloader())
    yield test_download_manager
