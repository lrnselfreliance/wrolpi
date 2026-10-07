import subprocess

import pytest

from modules.repos import lib
from wrolpi.downloader import Download, DownloadStatus


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
async def test_clone_is_marked(test_session, git_remote_factory, repos_download_manager):
    """WROLPi marks the clones it makes, so it never mistakes another clone for one of its own."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    test_session.expire_all()
    # The marker holds the Repo's own random token, which nothing else can know (unlike its URL).
    assert len(repo.clone_token) == 32
    assert (repo.directory / '.git' / lib.REPO_MARKER).read_text().strip() == repo.clone_token


@pytest.mark.asyncio
async def test_update_refuses_unmarked_clone(test_session, test_directory, git_remote_factory,
                                             repos_download_manager):
    """A clone WROLPi did not make (or made for another repo) is not updated, so it is never reset or cleaned."""
    remote = git_remote_factory()
    directory = test_directory / 'repos/example'
    directory.parent.mkdir(parents=True)
    git(directory.parent, 'clone', '--quiet', str(remote.path), str(directory))
    (directory / 'my-work.txt').write_text('uncommitted')

    lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'was not created by WROLPi' in download.error
    assert (directory / 'my-work.txt').read_text() == 'uncommitted'

    # A marker for another repo is not this repo's.
    (directory / '.git' / lib.REPO_MARKER).write_text('git.example.com/owner/other')
    download = await update(test_session, repos_download_manager)
    assert 'was not created by WROLPi' in download.error
    assert (directory / 'my-work.txt').exists()


@pytest.mark.asyncio
async def test_update_refuses_git_file(test_session, test_directory, git_remote_factory, repos_download_manager):
    """`.git` must be the repo's own directory, not a file or link which points elsewhere."""
    remote = git_remote_factory()
    directory = test_directory / 'repos/example'
    directory.mkdir(parents=True)
    (directory / '.git').write_text('gitdir: /somewhere/else\n')

    lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'not a git directory' in download.error


@pytest.mark.asyncio
async def test_update_fetches_the_repo_url(test_session, git_remote_factory, repos_download_manager):
    """The Repo's URL is fetched, whatever the clone's origin says."""
    remote = git_remote_factory()
    other = git_remote_factory('other')
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    git(repo.directory, 'config', 'remote.origin.url', other.url)
    head = remote.commit({'new.txt': 'new'}, 'New')
    await update(test_session, repos_download_manager)
    assert repo.head_sha == head
    assert git(repo.directory, 'config', 'remote.origin.url') == remote.url


@pytest.mark.asyncio
async def test_update_sanitizes_git_config(test_session, git_remote_factory, repos_download_manager):
    """Only the settings WROLPi needs survive in a clone's config; a planted setting cannot change what git does."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    config = repo.directory / '.git/config'
    config.write_text(config.read_text() + (
        '[url "https://127.0.0.1/"]\n\tinsteadOf = https://git.example.com/\n'
        '[http]\n\tproxy = http://127.0.0.1:9\n'
        '[include]\n\tpath = /etc/evil.gitconfig\n'
        '[core]\n\tsshCommand = evil\n\tworktree = /etc\n\tfsmonitor = evil\n'
        '[branch "main"]\n\tremote = https://127.0.0.1/evil\n'
    ))
    head = remote.commit({'new.txt': 'new'}, 'New')
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.complete, download.error
    assert repo.head_sha == head

    keys = set(git(repo.directory, 'config', '--local', '--name-only', '--list').splitlines())
    assert {'remote.origin.url', 'remote.origin.fetch', 'core.repositoryformatversion'} <= keys
    assert not {'url.https://127.0.0.1/.insteadof', 'http.proxy', 'include.path', 'core.sshcommand',
                'core.worktree', 'core.fsmonitor', 'branch.main.remote'} & keys


def test_sanitize_git_config_submodules(tmp_path):
    """A submodule's config may point its work tree inside the repo, and nowhere else."""
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    module = git_dir / 'modules/library'
    module.mkdir(parents=True)
    (repo / 'vendor/library').mkdir(parents=True)
    (git_dir / 'config').write_text('[core]\n\trepositoryformatversion = 0\n\tbare = false\n')
    (module / 'config').write_text('[core]\n\trepositoryformatversion = 0\n\tworktree = ../../../vendor/library\n'
                                   '[remote "origin"]\n\turl = https://git.example.com/owner/library\n')
    evil = git_dir / 'modules/evil'
    evil.mkdir()
    (evil / 'config').write_text('[core]\n\tworktree = /etc\n')
    for gitdir in (module, evil):
        (gitdir / 'HEAD').write_text('ref: refs/heads/main\n')
        (gitdir / 'objects').mkdir()

    lib.sanitize_git_config(repo)
    assert 'worktree = ../../../vendor/library' in (module / 'config').read_text()
    assert 'worktree' not in (evil / 'config').read_text()


@pytest.mark.asyncio
async def test_update_with_duplicate_and_option_like_settings(test_session, git_remote_factory,
                                                             repos_download_manager):
    """Planted extra or option-like values in the kept settings cannot break or redirect an update."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()

    config = repo.directory / '.git/config'
    config.write_text(config.read_text() + (
        '[remote "origin"]\n\turl = --file=/tmp/evil\n\turl = https://127.0.0.1/evil\n'
        '\tfetch = +refs/heads/*:refs/heads/*\n'
        '[submodule "lib"]\n\turl = "quoted \\"value\\" \\\\ and\\ttab"\n'
    ))
    head = remote.commit({'new.txt': 'new'}, 'New')
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.complete, download.error
    assert repo.head_sha == head
    assert git(repo.directory, 'config', '--get-all', 'remote.origin.url') == remote.url
    assert git(repo.directory, 'config', '--get-all', 'remote.origin.fetch') == '+refs/heads/*:refs/remotes/origin/*'


def test_sanitized_config_round_trips(tmp_path):
    """Kept values are written back exactly, whatever they contain."""
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    values = ['--file=/tmp/evil', 'a "quoted" value', 'back\\slash', 'tab\there', ' leading space', 'semi;colon#hash']
    subprocess.run(['git', 'config', '--file', str(repo / '.git/config'), 'http.proxy', 'evil'], check=True)
    for value in values:
        subprocess.run(['git', 'config', '--file', str(repo / '.git/config'), '--add', 'submodule.lib.url', value],
                       check=True)
    lib.sanitize_git_config(repo)
    result = git(repo, 'config', '--file', '.git/config', '--get-all', 'submodule.lib.url')
    assert result.split('\n') == values
    assert 'proxy' not in (repo / '.git/config').read_text()


def test_marker_and_config_do_not_follow_links(tmp_path):
    """A clone (e.g. one being imported) can hold links; WROLPi never writes through them."""
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    git_dir.mkdir(parents=True)
    victim = tmp_path / 'victim.txt'
    victim.write_text('precious')

    (git_dir / lib.REPO_MARKER).symlink_to(victim)
    lib.mark_clone(repo, 'a1b2c3')
    assert victim.read_text() == 'precious'
    assert not (git_dir / lib.REPO_MARKER).is_symlink()
    assert (git_dir / lib.REPO_MARKER).read_text().strip() == 'a1b2c3'

    # A git directory holding any link is refused.
    (git_dir / 'config').write_text('[http]\n\tproxy = evil\n[core]\n\tbare = false\n')
    (git_dir / 'config.wrolpi').symlink_to(victim)
    with pytest.raises(ValueError, match='link'):
        lib.sanitize_git_config(repo)
    assert victim.read_text() == 'precious'
    (git_dir / 'config.wrolpi').unlink()
    lib.sanitize_git_config(repo)
    assert 'proxy' not in (git_dir / 'config').read_text()

    # A config which is a link is refused.
    (git_dir / 'config').unlink()
    (git_dir / 'config').symlink_to(victim)
    with pytest.raises(ValueError):
        lib.sanitize_git_config(repo)
    assert victim.read_text() == 'precious'


@pytest.mark.asyncio
async def test_import_refuses_linked_config(test_session, test_directory, async_client, test_wrolpi_config):
    from modules.repos.errors import InvalidRepo
    directory = test_directory / 'code/linked'
    git(test_directory, 'init', '--quiet', 'code/linked')
    (directory / '.git/config').unlink()
    (directory / '.git/config').symlink_to(test_directory / 'elsewhere')
    with pytest.raises(InvalidRepo, match='config'):
        lib.inspect_import(test_session, 'code/linked')



@pytest.mark.asyncio
async def test_import_directory_is_not_an_oracle(test_session, test_directory, async_client, test_wrolpi_config,
                                                tmp_path_factory):
    """A link in the media directory cannot reveal whether a path outside it exists."""
    from modules.repos.errors import InvalidRepo
    outside = tmp_path_factory.mktemp('outside')
    (outside / 'exists').mkdir()
    (test_directory / 'code').mkdir()
    (test_directory / 'code/link').symlink_to(outside)
    for directory in ('code/link/exists', 'code/link/missing'):
        with pytest.raises(InvalidRepo, match='must be in the media directory'):
            lib.resolve_import_directory(test_session, directory)


def test_git_command_disables_automatic_programs():
    cmd = lib.git_command('rev-parse', 'HEAD')
    for setting in ('gc.auto=0', 'maintenance.auto=false', 'core.alternateRefsCommand=', 'core.fsmonitor=false',
                    'core.hooksPath=/dev/null'):
        assert setting in cmd, setting


@pytest.mark.parametrize('planted', ['commondir', 'objects/info/alternates'])
@pytest.mark.asyncio
async def test_clone_cannot_borrow_another_git_directory(test_session, test_directory, async_client,
                                                         test_wrolpi_config, git_remote_factory,
                                                         repos_download_manager, planted):
    """`.git/commondir` makes git read another directory's config (bypassing the sanitized one), and alternates
    read its objects; neither is in a clone WROLPi makes, so neither is imported or updated."""
    from modules.repos.errors import InvalidRepo
    elsewhere = test_directory / 'elsewhere'
    elsewhere.mkdir()

    # Import.
    git(test_directory, 'init', '--quiet', 'code/borrowing')
    (test_directory / 'code/borrowing/.git' / planted).write_text(f'{elsewhere}\n')
    with pytest.raises(InvalidRepo, match='another git directory'):
        lib.inspect_import(test_session, 'code/borrowing')

    # Update.
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    (repo.directory / '.git' / planted).write_text(f'{elsewhere}\n')
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.deferred
    assert 'another git directory' in download.error


@pytest.mark.parametrize('plant', ['config-link', 'commondir', 'alternates', 'modules-link', 'gitdir-link'])
def test_submodule_git_directories_are_checked_too(tmp_path, plant):
    """A submodule's git directory is held to the same rules as the repo's: no linked config, no borrowing."""
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'config').write_text('[core]\n\tbare = false\n')
    victim = tmp_path / 'victim'
    victim.mkdir()
    (victim / 'config').write_text('[core]\n\tfsmonitor = evil\n')

    module = git_dir / 'modules/library'
    (module / 'objects').mkdir(parents=True)
    (module / 'HEAD').write_text('ref: refs/heads/main\n')
    (module / 'config').write_text('[core]\n\tbare = false\n')
    # A ref named HEAD is not a git directory.
    (module / 'refs/remotes/origin').mkdir(parents=True)
    (module / 'refs/remotes/origin/HEAD').write_text('ref: refs/remotes/origin/main\n')

    if plant == 'config-link':
        (module / 'config').unlink()
        (module / 'config').symlink_to(victim / 'config')
    elif plant == 'commondir':
        (module / 'commondir').write_text(f'{victim}\n')
    elif plant == 'alternates':
        (module / 'objects/info').mkdir()
        (module / 'objects/info/alternates').write_text(f'{victim}\n')
    elif plant == 'modules-link':
        import shutil
        shutil.rmtree(git_dir / 'modules')
        (git_dir / 'modules').symlink_to(victim)
    elif plant == 'gitdir-link':
        (git_dir / 'modules/other').symlink_to(victim)

    with pytest.raises(ValueError):
        lib.sanitize_git_config(repo)
    assert (victim / 'config').read_text() == '[core]\n\tfsmonitor = evil\n'


def test_submodule_git_directories_pass(tmp_path):
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    module = git_dir / 'modules/library'
    (module / 'objects').mkdir(parents=True)
    (module / 'HEAD').write_text('ref: refs/heads/main\n')
    (module / 'config').write_text('[core]\n\tbare = false\n[http]\n\tproxy = evil\n')
    (module / 'refs/remotes/origin').mkdir(parents=True)
    (module / 'refs/remotes/origin/HEAD').write_text('ref: refs/remotes/origin/main\n')
    (git_dir / 'config').write_text('[core]\n\tbare = false\n')
    lib.sanitize_git_config(repo)
    assert 'proxy' not in (module / 'config').read_text()


@pytest.mark.parametrize('name', ['library', 'refs', 'vendor/library'])
def test_submodule_git_directory_without_objects_is_refused(tmp_path, name):
    """A git directory which borrows another (commondir) has no objects of its own; it is refused, not skipped,
    whatever the submodule is named."""
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    module = git_dir / 'modules' / name
    module.mkdir(parents=True)
    (git_dir / 'config').write_text('[core]\n\tbare = false\n')
    (module / 'HEAD').write_text('ref: refs/heads/main\n')
    (module / 'commondir').write_text(f'{tmp_path}\n')
    with pytest.raises(ValueError):
        lib.sanitize_git_config(repo)


def test_nested_submodule_git_directories(tmp_path):
    """A nested submodule's git directory is checked too; refs and logs named HEAD are not git directories."""
    repo = tmp_path / 'repo'
    git_dir = repo / '.git'
    (git_dir).mkdir(parents=True)
    (git_dir / 'config').write_text('[core]\n\tbare = false\n')
    outer = git_dir / 'modules/library'
    inner = outer / 'modules/nested'
    for gitdir in (outer, inner):
        (gitdir / 'objects').mkdir(parents=True)
        (gitdir / 'HEAD').write_text('ref: refs/heads/main\n')
        (gitdir / 'config').write_text('[core]\n\tbare = false\n[http]\n\tproxy = evil\n')
        (gitdir / 'refs/remotes/origin').mkdir(parents=True)
        (gitdir / 'refs/remotes/origin/HEAD').write_text('ref: refs/remotes/origin/main\n')
        (gitdir / 'logs').mkdir()
        (gitdir / 'logs/HEAD').write_text('0000 1111 t <t@t> 0 +0000\tclone\n')
    lib.sanitize_git_config(repo)
    assert 'proxy' not in (outer / 'config').read_text()
    assert 'proxy' not in (inner / 'config').read_text()

    (inner / 'commondir').write_text(f'{tmp_path}\n')
    with pytest.raises(ValueError):
        lib.sanitize_git_config(repo)



@pytest.mark.asyncio
async def test_copied_clone_is_not_owned(test_session, test_directory, git_remote_factory, repos_download_manager):
    """A clone with a marker WROLPi did not write (e.g. copied from another WROLPi, or made by hand) is not owned:
    the marker must hold this Repo's own token."""
    remote = git_remote_factory()
    directory = test_directory / 'repos/example'
    directory.parent.mkdir(parents=True)
    git(directory.parent, 'clone', '--quiet', str(remote.path), str(directory))
    # What a marker used to hold, which anyone could write.
    (directory / '.git' / lib.REPO_MARKER).write_text(lib.repo_url_key(remote.url))
    (directory / 'my-work.txt').write_text('uncommitted')

    lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'was not created by WROLPi' in download.error
    assert (directory / 'my-work.txt').exists()


@pytest.mark.asyncio
async def test_clone_token_survives_the_config(test_session, async_client, git_remote_factory,
                                               repos_download_manager, await_switches):
    """The token is in repos.yaml, so a Repo restored from the config still owns its clone."""
    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    await await_switches()
    token = repo.clone_token
    config = lib.get_repos_config()
    assert config.repos[0]['clone_token'] == token

    # Lose the database, restore it from the config.
    lib._delete_repository(test_session, repo)
    test_session.commit()
    config.import_config()
    test_session.expire_all()
    restored = test_session.query(lib.Repository).one()
    assert restored.clone_token == token

    head = remote.commit({'new.txt': 'new'}, 'New')
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.complete, download.error
    assert test_session.query(lib.Repository).one().head_sha == head


@pytest.mark.parametrize('plant', ['outside', 'directory', 'link', 'garbage'])
def test_working_tree_git_files(tmp_path, plant):
    """A submodule's `.git` (in the working tree) decides which git directory git uses for it; it must be a file
    pointing inside the repo's own .git/modules."""
    repo = tmp_path / 'repo'
    _real_submodule_git_dir(repo / '.git/modules/library')
    (repo / 'vendor/library').mkdir(parents=True)
    (repo / 'vendor/library/.git').write_text('gitdir: ../../.git/modules/library\n')
    assert lib.working_tree_git_error(repo) is None

    evil = tmp_path / 'evil'
    evil.mkdir()
    (repo / 'other').mkdir()
    target = repo / 'other/.git'
    if plant == 'outside':
        target.write_text(f'gitdir: {evil}\n')
    elif plant == 'directory':
        target.mkdir()
    elif plant == 'link':
        target.symlink_to(evil)
    elif plant == 'garbage':
        target.write_text('not a gitdir line\n')
    assert lib.working_tree_git_error(repo)


@pytest.mark.parametrize('submodules', [True, False])
@pytest.mark.asyncio
async def test_update_refuses_planted_submodule_git_file(test_session, test_directory, git_remote_factory,
                                                         repos_download_manager, submodules):
    """Submodule commands (update, and deinit when submodules are turned off) never use a git directory outside
    the repo."""
    library = git_remote_factory('library')
    remote = git_remote_factory()
    remote.add_submodule('vendor/library', library)
    repo = lib.create_repository(test_session, remote.url, submodules=True)
    await repos_download_manager.wait_for_all_downloads()
    assert (repo.directory / 'vendor/library/lib.c').exists() or (repo.directory / 'vendor/library/README.md').exists()

    evil = test_directory / 'evil-gitdir'
    evil.mkdir()
    (repo.directory / 'vendor/library/.git').write_text(f'gitdir: {evil}\n')
    lib.update_repository(test_session, repo.id, submodules=submodules)
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.deferred
    assert 'outside' in download.error
    assert list(evil.iterdir()) == []


def _real_submodule_git_dir(path):
    (path / 'objects').mkdir(parents=True)
    (path / 'refs').mkdir()
    (path / 'HEAD').write_text('ref: refs/heads/main\n')
    (path / 'config').write_text('[core]\n\tbare = false\n')


def test_planted_head_does_not_hide_a_submodule_git_dir(tmp_path):
    """git finds a submodule's git directory at .git/modules/<name>, however deep; a git directory planted on a path
    prefix (or anywhere else) cannot hide it from being sanitized."""
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    (repo / '.git/config').write_text('[core]\n\tbare = false\n')
    _real_submodule_git_dir(repo / '.git/modules/vendor')
    real = repo / '.git/modules/vendor/library'
    _real_submodule_git_dir(real)
    (real / 'config').write_text('[protocol "file"]\n\tallow = always\n[url "file:///tmp/evil/"]\n'
                                 '\tinsteadOf = https://example.com/\n')
    hidden = repo / '.git/modules/vendor/refs/library'
    _real_submodule_git_dir(hidden)
    (hidden / 'config').write_text('[http]\n\tproxy = evil\n')

    lib.sanitize_git_config(repo)
    assert 'protocol' not in (real / 'config').read_text()
    assert 'insteadOf' not in (real / 'config').read_text()
    assert 'proxy' not in (hidden / 'config').read_text()

    # A submodule's `.git` must point at one of the (sanitized) git directories.
    (repo / 'vendor/library').mkdir(parents=True)
    (repo / 'vendor/library/.git').write_text('gitdir: ../../.git/modules/vendor/library\n')
    assert lib.working_tree_git_error(repo) is None
    (repo / 'vendor/library/.git').write_text('gitdir: ../../.git/modules/vendor/library/objects\n')
    assert lib.working_tree_git_error(repo)


@pytest.mark.parametrize('link', ['objects', 'refs', 'logs', 'packed-refs', 'refs/remotes', 'objects/pack'])
@pytest.mark.asyncio
async def test_links_in_git_dir_are_refused(test_session, test_directory, async_client, test_wrolpi_config,
                                            git_remote_factory, repos_download_manager, link):
    """git writes through a link in a git directory (fetch writes objects, refs and logs), so a git directory
    holding one is neither imported nor updated."""
    from modules.repos.errors import InvalidRepo
    import shutil

    def plant(git_dir):
        target = git_dir / link
        outside = test_directory / f'outside-{link.replace("/", "-")}-{git_dir.parent.name}'
        if target.exists():
            shutil.move(target, outside)
        else:
            outside.write_text('')
        target.symlink_to(outside)

    git(test_directory, 'init', '--quiet', 'code/linked')
    git(test_directory / 'code/linked', 'commit', '--quiet', '--allow-empty', '-m', 'x')
    git(test_directory / 'code/linked', 'pack-refs', '--all')
    git(test_directory / 'code/linked', 'gc', '--quiet')
    plant(test_directory / 'code/linked/.git')
    with pytest.raises(InvalidRepo, match='link'):
        lib.inspect_import(test_session, 'code/linked')

    remote = git_remote_factory()
    repo = lib.create_repository(test_session, remote.url)
    await repos_download_manager.wait_for_all_downloads()
    git(repo.directory, 'pack-refs', '--all')
    git(repo.directory, 'gc', '--quiet')
    plant(repo.directory / '.git')
    download = await update(test_session, repos_download_manager)
    assert download.status == DownloadStatus.deferred
    assert 'link' in download.error


@pytest.mark.asyncio
async def test_control_characters_in_directories_are_refused(test_session, test_directory, async_client,
                                                             test_wrolpi_config):
    """A newline would split a line git reads (e.g. alternates)."""
    from modules.repos.errors import InvalidRepo
    for directory in ('foo\n/tmp/abs', 'foo\rbar', 'tab\there'):
        with pytest.raises(InvalidRepo, match='character'):
            lib.resolve_new_repo_directory(test_session, directory)


@pytest.mark.parametrize('link_at', ['directory', 'parent'])
@pytest.mark.asyncio
async def test_clone_refuses_links_made_after_adding(test_session, test_directory, async_client, test_wrolpi_config,
                                                     git_remote_factory, repos_download_manager, tmp_path_factory,
                                                     link_at):
    """A repo's directory (or a parent) which became a link after the repo was added is not cloned into."""
    remote = git_remote_factory()
    lib.create_repository(test_session, remote.url, directory='projects/example')
    outside = tmp_path_factory.mktemp('outside')
    if link_at == 'directory':
        (test_directory / 'projects').mkdir()
        (test_directory / 'projects/example').symlink_to(outside)
    else:
        (test_directory / 'projects').symlink_to(outside)
    await repos_download_manager.wait_for_all_downloads()

    download = test_session.query(Download).one()
    assert download.status == DownloadStatus.deferred
    assert 'link' in download.error
    assert list(outside.iterdir()) == []


@pytest.mark.asyncio
async def test_refused_sanitize_changes_nothing(test_session, test_directory, async_client, test_wrolpi_config):
    """Every refusal is found before any config is rewritten."""
    from modules.repos.errors import InvalidRepo
    git(test_directory, 'init', '--quiet', 'code/clone')
    directory = test_directory / 'code/clone'
    git(directory, 'commit', '--quiet', '--allow-empty', '-m', 'x')
    git(directory, 'remote', 'add', 'origin', 'https://git.example.com/owner/clone')
    with (directory / '.git/config').open('a') as fh:
        fh.write('[http]\n\tproxy = http://127.0.0.1:9\n')
    module = directory / '.git/modules/library'
    _real_submodule_git_dir(module)
    # Found only after the clone's own config was checked.
    (module / 'commondir').write_text('../..\n')
    before = (directory / '.git/config').read_text()

    with pytest.raises(InvalidRepo):
        await lib.import_repository(test_session, 'code/clone', confirm=True)
    assert (directory / '.git/config').read_text() == before
