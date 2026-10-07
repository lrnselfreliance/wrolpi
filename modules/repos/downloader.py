import asyncio
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from wrolpi.common import logger
from wrolpi.dates import now
from wrolpi.downloader import Downloader, Download, DownloadContext, DownloadResult, make_progress_callback
from wrolpi.errors import DownloadError
from .lib import git_command, git_env, find_readme, get_repo_size, is_valid_branch, read_readme_text, \
    submodule_fetch_config, resolve_repo_addresses, pin_config, HostAddresses, clone_ownership_error, mark_clone, \
    sanitize_git_config, new_clone_token, working_tree_git_error, repo_directory_error, get_repository_by_url
from .models import Repository

__all__ = ['GitDownloader', 'git_downloader', 'PreparedRepo', 'ExecutedRepo', 'parse_git_progress']

logger = logger.getChild(__name__)

# e.g. "Receiving objects:  45% (123/456), 1.20 MiB | 1.00 MiB/s"
GIT_PROGRESS_RE = re.compile(r'^(?:remote: )?(?P<stage>[A-Za-z ]+):\s+(?P<percent>\d+)%')

# Submodules of submodules are checked out this many levels deep.
MAXIMUM_SUBMODULE_DEPTH = 5

# Full mode keeps every branch of the remote as `origin/<branch>`.
FULL_REFSPEC = '+refs/heads/*:refs/remotes/origin/*'


def parse_git_progress(line: str) -> Optional[dict]:
    if match := GIT_PROGRESS_RE.match(line):
        return dict(stage=match.group('stage').strip(), percent=int(match.group('percent')))
    return None


@dataclass
class PreparedRepo:
    repository_id: int
    url: str
    directory: pathlib.Path
    mode: str
    branch: Optional[str]
    submodules: bool = False
    clone_token: Optional[str] = None
    # The repo's host, resolved once by execute_download; every fetch from it connects to these addresses.
    addresses: Optional[HostAddresses] = None


@dataclass
class ExecutedRepo:
    repository_id: int
    default_branch: Optional[str]
    head_sha: str
    head_date: datetime
    head_message: str
    size: int
    readme_path: Optional[str]
    readme_text: Optional[str]
    # The repo was updated, but its submodules were not.
    submodules_error: Optional[str] = None


class GitCancelled(Exception):
    """A git command was cancelled; carries the cancel_wrapper's DownloadResult."""

    def __init__(self, result: DownloadResult):
        super().__init__(result.error)
        self.result = result


class GitDownloader(Downloader):
    """Clones a git repo into its Repo's directory, or updates the existing clone.

    Repos are mirrors: local changes are discarded by every update.  Upstream disappearing never deletes the
    local copy; the download is deferred with git's error."""
    name = 'git'
    pretty_name = 'Git'
    # Repos are added on the Repos page, not the generic download form.
    listable = False

    def prepare_download(self, session: Session, download: Download) -> PreparedRepo:
        if download.collection_id:
            repo = Repository.get_by_collection_id(session, download.collection_id)
        else:
            # The one-time Download of a Repo which is never updated.
            repo = get_repository_by_url(session, download.url)
        if not repo:
            raise DownloadError(f'No Repo for this download, add it on the Repos page: {download.url}')
        directory = repo.collection.get_or_set_directory(session)
        if not repo.clone_token:
            repo.clone_token = new_clone_token()
        return PreparedRepo(repository_id=repo.id, url=repo.url, directory=directory, mode=repo.mode,
                            branch=repo.branch, submodules=repo.submodules, clone_token=repo.clone_token)

    async def _git(self, download: Download, ctx: DownloadContext, cwd: pathlib.Path, *args,
                   config: tuple = (), progress: bool = False, check: bool = True,
                   prepared: PreparedRepo = None) -> str:
        """Run a git command, return its output (stdout and stderr).

        Pass `prepared` for a command which connects to the repo's host, so it connects to the resolved addresses."""
        if prepared and prepared.addresses and (pin := pin_config(prepared.addresses)):
            config = (pin, *config)
        cmd = git_command(*args, config=config)
        stdout_callback = make_progress_callback(ctx.report_progress, parse_git_progress) if progress else None
        result = await self.process_runner(download, cmd, cwd, env=git_env(), merge_stderr=True,
                                           stdout_callback=stdout_callback, start_new_session=True, ctx=ctx)
        if isinstance(result, DownloadResult):
            raise GitCancelled(result)
        output = result.stdout.decode(errors='replace').strip()
        if check and result.return_code != 0:
            raise DownloadError(f'git {args[0]} failed ({result.return_code}): {output}')
        return output

    async def _default_branch(self, download: Download, ctx: DownloadContext, prepared: PreparedRepo) -> str:
        """Ask the remote for its default branch.  This fails quickly when the upstream is gone."""
        output = await self._git(download, ctx, prepared.directory.parent, 'ls-remote', '--symref', prepared.url,
                                 'HEAD', prepared=prepared)
        for line in output.splitlines():
            if line.startswith('ref: refs/heads/') and line.endswith('\tHEAD'):
                return line[len('ref: refs/heads/'):-len('\tHEAD')]
        raise DownloadError(f'Repo has no default branch (is it empty?): {prepared.url}')

    async def _clone(self, download: Download, ctx: DownloadContext, prepared: PreparedRepo, branch: str):
        directory = prepared.directory
        if directory.is_dir() and any(directory.iterdir()):
            raise DownloadError(f'Refusing to clone into a directory which is not empty: {directory}')
        directory.mkdir(parents=True, exist_ok=True)

        args = ['clone', '--progress', '--branch', branch]
        if prepared.mode == 'snapshot':
            args.extend(['--depth', '1', '--single-branch', '--no-tags'])
        args.extend(['--', prepared.url, str(directory)])
        await self._git(download, ctx, directory.parent, *args, progress=True, prepared=prepared)
        mark_clone(directory, prepared.clone_token)

    async def _update(self, download: Download, ctx: DownloadContext, prepared: PreparedRepo, branch: str):
        directory = prepared.directory
        git = lambda *args, **kwargs: self._git(download, ctx, directory, *args, prepared=prepared,  # noqa: E731
                                                **kwargs)

        # Only a clone WROLPi made (or imported) for this Repo is reset and cleaned; its config cannot change what
        # git runs or where it connects, and it is fetched from the Repo's URL, whatever its origin says.
        if error := clone_ownership_error(directory, prepared.clone_token):
            raise DownloadError(error)
        try:
            await asyncio.to_thread(sanitize_git_config, directory)
        except ValueError as e:
            raise DownloadError(str(e))
        await git('config', '--replace-all', 'remote.origin.url', prepared.url)
        refspec = FULL_REFSPEC if prepared.mode == 'full' else f'+refs/heads/{branch}:refs/remotes/origin/{branch}'
        await git('config', '--replace-all', 'remote.origin.fetch', refspec)

        old_head = await git('rev-parse', '--verify', '--quiet', 'HEAD', check=False)
        if prepared.mode == 'snapshot':
            await git('fetch', '--progress', '--depth', '1', '--no-tags', 'origin', branch, progress=True)
            target = 'FETCH_HEAD'
        else:
            # Fetch every branch and tag.  Branches deleted upstream are kept (no --prune).
            args = ['fetch', '--progress', '--tags', '--force', 'origin']
            if (directory / '.git/shallow').exists():
                # This was a snapshot; get the whole history.
                args.insert(1, '--unshallow')
            await git(*args, progress=True)
            target = f'refs/remotes/origin/{branch}'

        new_head = await git('rev-parse', '--verify', target)
        if prepared.mode == 'full' and old_head and old_head != new_head:
            if not await self._is_ancestor(download, ctx, directory, old_head, new_head):
                # Upstream rewrote history (force push).  Keep what we had.
                backup = f'refs/wrolpi/backup/{now().strftime("%Y%m%d%H%M%S")}'
                await git('update-ref', backup, old_head)
                logger.warning(f'Repo {prepared.url} history was rewritten; saved old HEAD as {backup}')

        await git('checkout', '--force', '-B', branch, new_head)
        await git('clean', '-ffdx')
        if prepared.mode == 'snapshot':
            # Shallow fetches leave the previous commits behind; drop them.
            await git('gc', '--prune=now', '--quiet',
                      config=('gc.reflogExpire=now', 'gc.reflogExpireUnreachable=now'))

    async def _update_submodules(self, download: Download, ctx: DownloadContext, prepared: PreparedRepo) \
            -> Optional[str]:
        """Check out (or remove) the submodules of the checked out commit.  Returns an error, if any.

        Submodules are fetched with the same restrictions as the repo (`git_command` options are inherited by the
        git commands that git runs)."""
        directory = prepared.directory
        git = lambda *args, **kwargs: self._git(download, ctx, directory, *args, **kwargs)  # noqa: E731
        # Every submodule command uses the git directory a submodule's `.git` names; it must be one that was checked.
        if (error := await asyncio.to_thread(working_tree_git_error, directory)) and (
                prepared.submodules or (directory / '.git/modules').is_dir()):
            return error
        if not prepared.submodules:
            if (directory / '.git/modules').is_dir():
                # Submodules were turned off; the repo is a mirror of only its own files now.
                await git('submodule', 'deinit', '--all', '--force', check=False)
            return None
        if not (directory / '.gitmodules').is_file():
            return None

        try:
            await self._check_out_submodules(download, ctx, directory, prepared)
        except DownloadError as e:
            logger.warning(f'Failed to update submodules of {prepared.url}', exc_info=e)
            return str(e)
        return None

    async def _check_out_submodules(self, download: Download, ctx: DownloadContext, directory: pathlib.Path,
                                    prepared: PreparedRepo, depth: int = 0):
        """Check out the submodules of the repo in `directory`, then theirs, one level at a time.

        Each level's URLs are checked before git fetches them (git's `--recursive` would fetch nested submodules
        unchecked)."""
        if not (directory / '.gitmodules').is_file():
            return
        if depth >= MAXIMUM_SUBMODULE_DEPTH:
            raise DownloadError(f'Submodules are nested more than {MAXIMUM_SUBMODULE_DEPTH} levels deep')
        git = lambda *args, **kwargs: self._git(download, ctx, directory, *args, prepared=prepared,  # noqa: E731
                                                **kwargs)

        paths = await self._git_config_values(download, ctx, directory, '.path', '--file', '.gitmodules')

        # git resolves each submodule's URL (a relative URL is resolved against this repo's remote, and may be
        # another host) into this repo's config.  Those are the URLs git fetches, so those are checked.
        await git('submodule', 'init')
        await git('submodule', 'sync')
        urls = await self._git_config_values(download, ctx, directory, '.url', '--local')
        try:
            fetch_config = await asyncio.to_thread(submodule_fetch_config, urls, prepared.addresses)
        except ValueError as e:
            raise DownloadError(str(e))

        args = ['submodule', 'update', '--force', '--progress']
        if prepared.mode == 'snapshot':
            args.extend(['--depth', '1'])
        await git(*args, progress=True, config=fetch_config)

        for path in paths:
            submodule = (directory / path).resolve()
            if submodule.is_dir() and directory.resolve() in submodule.parents:
                await self._check_out_submodules(download, ctx, submodule, prepared, depth + 1)

    async def _git_config_values(self, download: Download, ctx: DownloadContext, directory: pathlib.Path,
                                 suffix: str, *source: str) -> list:
        """The values of the `submodule.<name><suffix>` keys in a git config.  Refuses anything it cannot read."""
        # NUL-delimited: a submodule's name and URL can contain spaces and newlines.  Each record is "key\nvalue".
        output = await self._git(download, ctx, directory, 'config', *source, '-z', '--get-regexp',
                                 rf'^submodule\..*\{suffix}$', check=False)
        values = []
        for record in output.split('\0'):
            if not record:
                continue
            key, newline, value = record.partition('\n')
            if not newline or not key.startswith('submodule.') or not key.endswith(suffix):
                raise DownloadError(f'Refusing to download submodules, cannot read their config: {record!r}')
            values.append(value)
        return values

    async def _is_ancestor(self, download: Download, ctx: DownloadContext, directory: pathlib.Path,
                           ancestor: str, descendant: str) -> bool:
        cmd = git_command('merge-base', '--is-ancestor', ancestor, descendant)
        result = await self.process_runner(download, cmd, directory, env=git_env(), merge_stderr=True, ctx=ctx)
        if isinstance(result, DownloadResult):
            raise GitCancelled(result)
        return result.return_code == 0

    async def execute_download(self, prepared: PreparedRepo, ctx: DownloadContext,
                               download: Download = None) -> ExecutedRepo | DownloadResult:
        download = download if download is not None else Download(url=prepared.url)
        directory = prepared.directory
        if error := repo_directory_error(directory):
            raise DownloadError(error)
        directory.parent.mkdir(parents=True, exist_ok=True)

        # Resolved once; the repo and its same-host submodules are all fetched from these addresses, so a DNS
        # answer cannot change in between.
        prepared.addresses = await asyncio.to_thread(resolve_repo_addresses, prepared.url)
        try:
            default_branch = await self._default_branch(download, ctx, prepared)
            branch = prepared.branch or default_branch
            # The remote chooses its default branch's name, and branches are passed to git as arguments.
            if not is_valid_branch(branch):
                raise DownloadError(f'Invalid branch name: {branch!r}')
            if (directory / '.git').exists() or (directory / '.git').is_symlink():
                await self._update(download, ctx, prepared, branch)
            else:
                await self._clone(download, ctx, prepared, branch)
            submodules_error = await self._update_submodules(download, ctx, prepared)

            head = await self._git(download, ctx, directory, 'log', '-1', '--format=%H%x00%cI%x00%s')
        except GitCancelled as e:
            return e.result
        finally:
            ctx.clear_progress()

        head_sha, head_date, head_message = head.split('\x00', 2)
        size = await asyncio.to_thread(get_repo_size, directory)
        readme_path = find_readme(directory)
        readme_text = await asyncio.to_thread(read_readme_text, directory / readme_path) if readme_path else None
        return ExecutedRepo(
            repository_id=prepared.repository_id,
            default_branch=default_branch,
            head_sha=head_sha,
            head_date=datetime.fromisoformat(head_date),
            head_message=head_message,
            size=size,
            readme_path=readme_path,
            readme_text=readme_text,
            submodules_error=submodules_error,
        )

    def finalize_download(self, session: Session, download: Download, executed: ExecutedRepo) -> DownloadResult:
        repo = session.query(Repository).filter_by(id=executed.repository_id).one_or_none()
        if not repo:
            return DownloadResult(success=False, error='Repo was deleted while downloading')
        repo.default_branch = executed.default_branch
        repo.head_sha = executed.head_sha
        repo.head_date = executed.head_date
        repo.head_message = executed.head_message
        repo.size = executed.size
        repo.readme_path = executed.readme_path
        if repo.readme_text != executed.readme_text:
            # Only write a changed README; every write re-indexes it.
            repo.readme_text = executed.readme_text
        repo.last_fetch = now()
        logger.info(f'Updated repo {repo.url} to {executed.head_sha}')
        if executed.submodules_error:
            # The repo is current, but the download is retried so its submodules are too.
            return DownloadResult(success=False, location=repo.location,
                                  error='The repo was updated, but its submodules were not: '
                                        f'{executed.submodules_error}')
        return DownloadResult(success=True, location=repo.location)


git_downloader = GitDownloader()
