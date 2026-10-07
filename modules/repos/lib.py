import asyncio
import contextlib
import html
import ipaddress
import os
import pathlib
import re
import hmac
import secrets
import shutil
import socket
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from wrolpi import fts
from wrolpi.cmd import GIT_BIN, run_command
from wrolpi.collections.models import Collection
from wrolpi.common import ConfigFile, get_media_directory, get_relative_to_media_directory, logger, \
    escape_file_name, background_task, get_wrolpi_config
from wrolpi.db import get_db_session
from wrolpi.downloader import Download, DownloadFrequency, download_manager, save_downloads_config
from wrolpi.errors import UnknownDirectory, ValidationError
from wrolpi.events import Events
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.tags import Tag
from wrolpi.vars import FILE_MAX_TEXT_SIZE
from .errors import InvalidRepo, RepoConflict
from .models import Repository, REPO_MODES

logger = logger.getChild(__name__)

__all__ = ['ParsedRepoURL', 'parse_repo_url', 'repo_url_key', 'git_command', 'git_env', 'REPO_MARKER',
           'clone_ownership_error', 'mark_clone', 'sanitize_git_config', 'working_tree_git_error',
           'create_repository', 'remote_url_key', 'remote_https_url', 'resolve_import_directory', 'inspect_import',
           'import_repository', 'update_repository', 'delete_repository', 'get_repositories', 'list_repo_tree',
           'find_readme', 'repos_destination_root', 'validate_repos_destination', 'is_valid_branch',
           'submodule_url_error', 'HostAddresses', 'resolve_repo_addresses', 'pin_config', 'is_public_address',
           'submodule_fetch_config', 'read_readme_text', 'search_repos', 'count_repos', 'search_repos_by_name',
           'get_repo_log', 'get_repo_root', 'repo_archive_name', 'stream_repo_archive', 'ReposConfig',
           'repos_config', 'get_repos_config', 'save_repos_config', 'import_repos_config', 'DEFAULT_REPO_FREQUENCY']

DEFAULT_REPO_FREQUENCY = DownloadFrequency.weekly.value
# A Repo which is never updated (e.g. its upstream is gone) keeps its clone as it is; it is only updated on request.
NEVER = 0
NEVER_CONFIG = 'never'

# The only transports git may use.  Submodules and redirects cannot reach `file://`, `ext::`, ssh, etc.
ALLOWED_PROTOCOLS = ('https',)

# README files in the order they are preferred; matched case-insensitively.
README_NAMES = ('readme.md', 'readme.markdown', 'readme.rst', 'readme.txt', 'readme')

# A forge's web URL of a branch: GitHub `/owner/repo/tree/<branch>`, GitLab `/group/repo/-/tree/<branch>`.
TREE_URL_RE = re.compile(r'^(?P<repo>/.+?)(?:/-)?/tree/(?P<branch>[^?#]+)$')


@dataclass
class ParsedRepoURL:
    url: str
    host: str
    owner: str
    name: str
    branch: Optional[str] = None


def parse_repo_url(url: str) -> ParsedRepoURL:
    """Validate an https git URL and split it into its parts.

    A forge's branch URL (e.g. `https://github.com/owner/repo/tree/dev`) becomes the repo URL and its branch."""
    url = (url or '').strip()
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_PROTOCOLS:
        raise InvalidRepo('Only https:// repo URLs are supported')
    if parsed.username or parsed.password:
        # Credentials would be saved in the configs.
        raise InvalidRepo('Repo URL must not contain a username or password')
    if not parsed.hostname:
        raise InvalidRepo('Repo URL must have a host')
    if parsed.query or parsed.fragment:
        raise InvalidRepo('Repo URL must not contain a query or fragment')

    path = parsed.path.rstrip('/')
    branch = None
    if match := TREE_URL_RE.match(path):
        path, branch = match.group('repo'), match.group('branch')

    parts = [i for i in path.split('/') if i]
    if not parts:
        raise InvalidRepo('Repo URL must have a path')
    if any(i in ('.', '..') for i in parts):
        # The name and owner are used in the Repo's directory.
        raise InvalidRepo('Repo URL must not contain "." or ".." in its path')
    name = parts[-1].removesuffix('.git')
    if not name:
        raise InvalidRepo('Repo URL must have a name')
    owner = '/'.join(parts[:-1])

    host = parsed.hostname.lower()
    netloc = f'{host}:{parsed.port}' if parsed.port else host
    return ParsedRepoURL(url=f'{parsed.scheme}://{netloc}{path}', host=host, owner=owner, name=name, branch=branch)


# Characters git forbids in a ref name (`git check-ref-format`), plus whitespace.
INVALID_BRANCH_CHARACTERS_RE = re.compile(r'[\x00-\x20\x7f~^:?*\[\\]')


def is_valid_branch(branch: str) -> bool:
    """Is `branch` a valid git branch name (the rules of `git check-ref-format --branch`)?

    Branch names are passed to git as arguments, so a name starting with `-` (an option) is never valid."""
    if not branch or not isinstance(branch, str):
        return False
    if branch.startswith('-') or branch == '@' or '@{' in branch or '..' in branch:
        return False
    if INVALID_BRANCH_CHARACTERS_RE.search(branch):
        return False
    if branch.startswith('/') or branch.endswith('/') or '//' in branch or branch.endswith('.'):
        return False
    for component in branch.split('/'):
        if component.startswith('.') or component.endswith('.lock'):
            return False
    return True


def _validate_branch(branch: Optional[str]):
    if branch is not None and not is_valid_branch(branch):
        raise ValidationError(f'Invalid branch name: {branch!r}')


def resolve_host_addresses(host: str) -> List[str]:
    """The IP addresses `host` resolves to."""
    return list({i[4][0] for i in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


# IPv6 ranges which carry an IPv4 address, or are not public.
NAT64_NETWORK = ipaddress.ip_network('64:ff9b::/96')
LOCAL_NAT64_NETWORK = ipaddress.ip_network('64:ff9b:1::/48')
TEREDO_NETWORK = ipaddress.ip_network('2001::/32')
SITE_LOCAL_NETWORK = ipaddress.ip_network('fec0::/10')


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Is `address` a public (globally routed) unicast address?

    `is_global` alone is not enough: it accepts multicast, deprecated site-local, and IPv6 addresses which carry a
    private IPv4 address (e.g. NAT64 `64:ff9b::169.254.169.254`, the metadata address)."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return is_public_address(address.ipv4_mapped)
        if address in NAT64_NETWORK:
            return is_public_address(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
        if address.sixtofour:
            return is_public_address(address.sixtofour)
        if address in LOCAL_NAT64_NETWORK or address in TEREDO_NETWORK or address in SITE_LOCAL_NETWORK:
            return False
    return address.is_global and not (
            address.is_multicast or address.is_reserved or address.is_link_local or address.is_loopback
            or address.is_private or address.is_unspecified)


# Submodule URLs must have a shape that every URL parser (Python's, git's, curl's) reads the same way: no userinfo,
# backslashes, queries, fragments or whitespace.
ABSOLUTE_SUBMODULE_URL_RE = re.compile(
    r'^https://(?P<host>[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])'
    r'(?::(?P<port>[0-9]{1,5}))?'
    r'(?:/[A-Za-z0-9._~%!$&\'()*+,;=:/-]*)?$')


class HostAddresses(NamedTuple):
    """A host and port, and the addresses its name resolved to (None for an IP address, or a failed lookup)."""
    host: str
    port: int
    addresses: Optional[List[str]]


def resolve_repo_addresses(url: str) -> HostAddresses:
    """Resolve the host of a Repo's URL, once per download.  Every fetch from the host is pinned to the result."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    port = parsed.port or 443
    if _is_ip_address(host):
        return HostAddresses(host, port, None)
    try:
        return HostAddresses(host, port, sorted(resolve_host_addresses(host)))
    except OSError:
        return HostAddresses(host, port, None)


def pin_config(pin: HostAddresses) -> Optional[str]:
    """git config which makes git connect to `pin.host` at exactly `pin.addresses`."""
    if not pin.addresses:
        return None
    addresses = ','.join(f'[{i}]' if ':' in i else i for i in pin.addresses)
    return f'http.curloptResolve={pin.host}:{pin.port}:{addresses}'


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip('[]'))
        return True
    except ValueError:
        return False


def _check_submodule_url(url: str, repo: HostAddresses) -> Tuple[Optional[str], Optional[HostAddresses]]:
    """Returns why the URL must not be fetched (or None), and the host to pin it to (or None).

    `url` must be absolute: git resolves relative submodule URLs (which can climb to another host, e.g.
    `../../../10.0.0.1/x`), and the result is checked."""
    match = ABSOLUTE_SUBMODULE_URL_RE.match(url)
    if not match:
        return 'only plain https:// submodule URLs can be downloaded', None
    host = match.group('host').lower()
    port = int(match.group('port') or 443)
    if (host, port) == (repo.host, repo.port):
        # The host the user chose (it may be on their network).  It is fetched from the addresses the repo was
        # fetched from (`pin_config(repo)` is part of every repo fetch), so it is not resolved again.
        if repo.addresses or _is_ip_address(host):
            return None, None
        return f'could not resolve {host}', None
    if _is_ip_address(host):
        addresses = [ipaddress.ip_address(host.strip('[]'))]
        pin = None  # An address needs no DNS.
    else:
        try:
            addresses = [ipaddress.ip_address(i.split('%')[0]) for i in resolve_host_addresses(host)]
        except (OSError, ValueError):
            return f'could not resolve {host}', None
        pin = HostAddresses(host, port, [str(i) for i in addresses])
    if not addresses or not all(is_public_address(i) for i in addresses):
        return f'{host} is not a public address', None
    return None, pin


def submodule_url_error(url: str, repo: HostAddresses) -> Optional[str]:
    """Why a submodule URL must not be fetched, or None when it may be.

    A submodule's URL is chosen by whoever controls the repo, so it may not make WROLPi fetch from its own network
    (e.g. `https://localhost:8443/...` or `https://10.0.0.1/...`).  Allowed: the repo's own host and port (which
    the user chose), and hosts with only public addresses.  A relative URL must first be resolved by git."""
    return _check_submodule_url(url, repo)[0]


def submodule_fetch_config(urls: List[str], repo: HostAddresses) -> tuple:
    """git config for fetching submodules with these URLs.  Raises ValueError if any URL must not be fetched.

    Each checked host is pinned to the addresses that were checked, so its DNS cannot change before git fetches it,
    and redirects are not followed, so a checked host cannot send git elsewhere.  (The repo's own host is pinned by
    `pin_config(repo)`.)"""
    config = ['http.followRedirects=false']
    pinned = set()
    for url in urls:
        error, pin = _check_submodule_url(url, repo)
        if error:
            raise ValueError(f'Refusing to download submodule {url}: {error}')
        if pin and (pin.host, pin.port) not in pinned:
            pinned.add((pin.host, pin.port))
            config.append(pin_config(pin))
    return tuple(config)


def repo_url_key(url: str) -> str:
    """Two URLs of the same repo have the same key (`.git` suffix and case of the host are ignored)."""
    parsed = urlparse(url.strip())
    return f'{(parsed.hostname or "").lower()}{parsed.path.rstrip("/").removesuffix(".git")}'


def git_command(*args, config: tuple = ()) -> tuple:
    """Build a git command that is safe to run against an untrusted remote repo."""
    if not GIT_BIN:
        raise InvalidRepo('git is not installed')
    safety = [
        '-c', 'protocol.allow=never',
        *(i for p in ALLOWED_PROTOCOLS for i in ('-c', f'protocol.{p}.allow=always')),
        # Never run the repo's hooks.
        '-c', 'core.hooksPath=/dev/null',
        # A symlink in a repo could point outside the repo (e.g. /etc/shadow), and media files are served.
        # Symlinks are checked out as plain files containing the link's target.
        '-c', 'core.symlinks=false',
        '-c', 'core.fsmonitor=false',
        '-c', 'core.alternateRefsCommand=',
        # Never start maintenance (which runs in the background) on WROLPi's behalf.
        '-c', 'gc.auto=0',
        '-c', 'maintenance.auto=false',
        # The media directory may be owned by another user (e.g. a Docker volume).
        '-c', 'safe.directory=*',
        '-c', 'credential.helper=',
        '-c', 'submodule.recurse=false',
    ]
    for i in config:
        safety.extend(['-c', i])
    return GIT_BIN, *safety, *args


# The only parts of WROLPi's environment git may see.  Anything else (GIT_ALLOW_PROTOCOL, GIT_CONFIG_COUNT and
# GIT_CONFIG_KEY_*/VALUE_*, GIT_CONFIG_PARAMETERS, GIT_SSL_NO_VERIFY, proxies, ...) could undo `git_command`'s
# restrictions.
GIT_ENV_ALLOWED = ('PATH', 'HOME', 'TMPDIR', 'TZ', 'SSL_CERT_FILE', 'SSL_CERT_DIR')


def git_env() -> dict:
    """Environment for git: never prompt for credentials, ignore the user's and system's git configs, and inherit
    nothing that changes how git connects."""
    env = {k: v for k, v in os.environ.items() if k in GIT_ENV_ALLOWED}
    env.update(
        GIT_TERMINAL_PROMPT='0',
        GIT_ASKPASS='true',
        SSH_ASKPASS='true',
        GIT_CONFIG_NOSYSTEM='1',
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_LFS_SKIP_SMUDGE='1',
        LC_ALL='C',
    )
    return env


# WROLPi marks the clones it makes (and imports) with this file in `.git`; it holds the Repo's `clone_token`.
REPO_MARKER = 'wrolpi-repo'


def new_clone_token() -> str:
    return secrets.token_hex(16)

# The only settings kept in a clone's config: anything else (include.path, url.*.insteadOf, http.proxy,
# core.sshCommand, ...) could change what git runs or where it connects.
ALLOWED_GIT_CONFIG_RE = re.compile(
    r'^(core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase|precomposeunicode|symlinks)'
    r'|extensions\.objectformat|remote\.origin\.(url|fetch)'
    r'|submodule\..+\.(url|active))$', re.IGNORECASE)


# Files which make git use another directory: commondir (its config, refs and objects, so the sanitized config would
# not be the one read) and alternates (its objects).  A clone WROLPi makes has neither.
BORROWING_GIT_FILES = ('commondir', 'objects/info/alternates', 'objects/info/http-alternates')


def _borrowing_git_file(git_dir: pathlib.Path) -> Optional[str]:
    for name in BORROWING_GIT_FILES:
        if (git_dir / name).exists() or (git_dir / name).is_symlink():
            return name
    return None


def git_dir_link_error(git_dir: pathlib.Path) -> Optional[str]:
    """Why a git directory holding a link (anywhere, even a dangling one) must not be used, or None.  git writes
    through links (a fetch writes objects, refs, packed-refs and logs), and reads what they point to."""
    if git_dir.is_symlink():
        return f'{git_dir} is a link'
    for dir_path, dir_names, file_names in os.walk(git_dir):
        for name in (*dir_names, *file_names):
            if os.path.islink(os.path.join(dir_path, name)):
                return f'{os.path.join(dir_path, name)} is a link'
    return None


def clone_ownership_error(directory: pathlib.Path, clone_token: Optional[str]) -> Optional[str]:
    """Why the clone in `directory` must not be updated as the Repo with `clone_token`, or None.

    WROLPi resets and cleans its clones, so it only updates the ones it made (or imported) for this Repo."""
    git_dir = directory / '.git'
    if git_dir.is_symlink() or not git_dir.is_dir():
        return f'{directory} is not a git directory'
    if borrowed := _borrowing_git_file(git_dir):
        return f'{directory} uses another git directory (.git/{borrowed})'
    if error := git_dir_link_error(git_dir):
        return error
    marker = git_dir / REPO_MARKER
    if not clone_token or not marker.is_file() \
            or not hmac.compare_digest(marker.read_text()[:100].strip(), clone_token):
        return f'{directory} was not created by WROLPi.  Import it from the Repos page'
    return None


def mark_clone(directory: pathlib.Path, clone_token: str):
    marker = directory / '.git' / REPO_MARKER
    # The clone may hold a link here (e.g. one being imported); never write through it.
    if marker.is_symlink():
        marker.unlink()
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w') as fh:
        fh.write(f'{clone_token}\n')


def _git_config_entries(config_file: pathlib.Path) -> List[Tuple[str, str]]:
    """The entries of a git config file (its includes are not followed)."""
    result = subprocess.run(git_command('config', '--file', str(config_file), '--null', '--list'), env=git_env(),
                            capture_output=True, check=True)
    entries = []
    for record in result.stdout.decode(errors='replace').split('\0'):
        if record:
            key, _, value = record.partition('\n')
            entries.append((key, value))
    return entries


def _quote_git_config(value: str) -> str:
    """A git config value (or subsection), quoted so git reads it back exactly."""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
    return f'"{escaped}"'


def _format_git_config(entries: List[Tuple[str, str]]) -> str:
    """Write git config entries ("section[.subsection].name", value) as a config file.

    Written here (not with `git config`), so no value is ever read as an argument."""
    sections = {}
    for key, value in entries:
        section, _, rest = key.partition('.')
        subsection, _, name = rest.rpartition('.')
        sections.setdefault((section, subsection), []).append((name, value))
    lines = []
    for (section, subsection), values in sections.items():
        lines.append(f'[{section} {_quote_git_config(subsection)}]' if subsection else f'[{section}]')
        lines.extend(f'\t{name} = {_quote_git_config(value)}' for name, value in values)
    return '\n'.join(lines) + '\n'


def _sanitized_config(config_file: pathlib.Path, worktree_root: Optional[pathlib.Path] = None) -> Optional[str]:
    """The sanitized contents of a git config file, or None if it needs no change.  Changes nothing."""
    if config_file.is_symlink() or not config_file.is_file():
        raise ValueError(f'{config_file} is not a file')
    try:
        entries = _git_config_entries(config_file)
    except subprocess.CalledProcessError:
        raise ValueError(f'{config_file} is not a git config')
    keep = []
    for key, value in entries:
        if ALLOWED_GIT_CONFIG_RE.match(key):
            keep.append((key, value))
        elif worktree_root and key.lower() == 'core.worktree':
            # A submodule's work tree, which must be inside the repo.
            worktree = (config_file.parent / value).resolve()
            if worktree == worktree_root or worktree_root in worktree.parents:
                keep.append((key, value))
    if len(keep) == len(entries):
        return None
    logger.warning(f'Removing {len(entries) - len(keep)} unexpected settings from {config_file}')
    return _format_git_config(keep)


def _write_config(config_file: pathlib.Path, content: str):
    # An unpredictable, newly created file: the directory may hold links (e.g. a clone being imported).
    fd, new = tempfile.mkstemp(dir=config_file.parent, prefix=f'{config_file.name}.wrolpi-')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(content)
        os.replace(new, config_file)
    except BaseException:
        pathlib.Path(new).unlink(missing_ok=True)
        raise


def is_git_dir(path: pathlib.Path) -> bool:
    """Could git use `path` as a git directory (if a `.git` file pointed to it)?  Its objects may be its own, or
    another directory's (commondir).  A HEAD in refs or logs is not enough."""
    return (path / 'HEAD').is_file() and ((path / 'objects').is_dir() or (path / 'commondir').exists())


def submodule_git_dirs(directory: pathlib.Path) -> List[pathlib.Path]:
    """Every directory in the repo's .git/modules which git could use as a git directory, however deep (in another
    git directory's refs, objects, ...).  A submodule's name may contain `/`, so there is no telling them apart."""
    modules = directory / '.git' / 'modules'
    if modules.is_symlink() or not modules.is_dir():
        return []
    return [pathlib.Path(dir_path) for dir_path, _, _ in os.walk(modules) if is_git_dir(pathlib.Path(dir_path))]


def sanitize_git_config(directory: pathlib.Path):
    """Keep only the settings WROLPi needs in the configs of the repo in `directory`, and of its submodules.

    Every git directory (the repo's, and each one in .git/modules) is held to the same rules: no links, a regular
    config file, and nothing which makes git use another directory.  Raises ValueError otherwise, before any config
    is changed."""
    git_dir = directory / '.git'
    root = directory.resolve()
    if error := git_dir_link_error(git_dir):
        # git would follow it out of the repo.
        raise ValueError(error)

    changes = [(git_dir / 'config', _sanitized_config(git_dir / 'config'))]
    for submodule_git_dir in submodule_git_dirs(directory):
        if borrowed := _borrowing_git_file(submodule_git_dir):
            raise ValueError(f'{submodule_git_dir} uses another git directory ({borrowed})')
        config = submodule_git_dir / 'config'
        if config.exists():
            changes.append((config, _sanitized_config(config, worktree_root=root)))
    for config, content in changes:
        if content is not None:
            _write_config(config, content)


def working_tree_git_error(directory: pathlib.Path) -> Optional[str]:
    """Why a `.git` in the repo's working tree (below its top) must not be used, or None.

    A submodule's `.git` file names the git directory git uses for it.  It must point inside the repo's own
    .git/modules, which is what `sanitize_git_config` checks; a link, a directory, or a file pointing elsewhere could
    make git use a config which was never checked."""
    root = directory.resolve()
    modules = root / '.git' / 'modules'
    git_dirs = {i.resolve() for i in submodule_git_dirs(root)}
    for dir_path, dir_names, file_names in os.walk(root):
        here = pathlib.Path(dir_path)
        if '.git' in dir_names:
            dir_names.remove('.git')  # Never walk into a git directory.
            if here != root:
                return f'{here / ".git"} is a directory, not a submodule\'s link'
            continue
        if '.git' not in file_names:
            continue
        git_file = here / '.git'
        if git_file.is_symlink():
            return f'{git_file} is a link'
        # Read as git does: only the line ending is trimmed.
        content = git_file.read_text(errors='replace')[:4096].rstrip('\r\n')
        if not content.startswith('gitdir: ') or '\n' in content or '\r' in content:
            return f'{git_file} is not a submodule\'s link'
        target = (here / content[len('gitdir: '):]).resolve()
        if modules not in target.parents:
            return f'{git_file} points outside the repo\'s submodules'
        if target not in git_dirs:
            return f'{git_file} does not point to a submodule\'s git directory'
    return None


def find_readme(directory: pathlib.Path) -> Optional[str]:
    """Return the name of the preferred README file in `directory`, if any."""
    try:
        files = {i.name.lower(): i.name for i in directory.iterdir() if i.is_file() and not i.is_symlink()}
    except FileNotFoundError:
        return None
    for name in README_NAMES:
        if name in files:
            return files[name]
    return None


MARKDOWN_SUFFIXES = ('.md', '.markdown')
# A README is untrusted; every pattern here must run in linear time.  Each bracketed run stops at the next
# opening bracket, so scans from different starting points never overlap.
INLINE_MARKDOWN_PATTERNS = [
    (re.compile(r'<[^<>\n]*>'), ' '),  # HTML tags.
    (re.compile(r'!\[([^\[\]\n]*)\]\([^()\n]*\)'), r'\1'),  # Images (and badges) become their alt text.
    (re.compile(r'\[([^\[\]\n]*)\]\([^()\n]*\)'), r'\1'),  # Links become their text.
    (re.compile(r'[*`|]+'), ' '),  # Emphasis, inline code, table cells.
    (re.compile(r'[ \t]+'), ' '),
]
HEADING_RE = re.compile(r'#{1,6}(?=\s|$)')
LINK_REFERENCE_RE = re.compile(r'\[[^\[\]]+\]:\s')
TABLE_SEPARATOR_CHARACTERS = set('|:- \t')


def _remove_html_comments(text: str) -> str:
    parts, position = [], 0
    while (comment := text.find('<!--', position)) != -1:
        parts.append(text[position:comment])
        end = text.find('-->', comment + 4)
        if end == -1:
            return ''.join(parts)
        parts.append(' ')
        position = end + 3
    parts.append(text[position:])
    return ''.join(parts)


def markdown_to_text(text: str) -> str:
    """Remove markdown syntax so search snippets read as plain text."""
    lines = []
    for line in _remove_html_comments(text).splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')) or LINK_REFERENCE_RE.match(stripped):
            continue
        if '-' in stripped and set(stripped) <= TABLE_SEPARATOR_CHARACTERS:
            continue  # A table separator row, or a horizontal rule.
        stripped = stripped.lstrip('>').strip()
        if heading := HEADING_RE.match(stripped):
            stripped = stripped[heading.end():].strip()
        for pattern, replacement in INLINE_MARKDOWN_PATTERNS:
            stripped = pattern.sub(replacement, stripped)
        if stripped := stripped.strip():
            lines.append(stripped)
    return '\n'.join(lines)


def read_readme_text(path: pathlib.Path) -> Optional[str]:
    """Read a README as plain text for search; markdown syntax is removed so snippets read well.

    A symlink is never followed (it could point outside the repo)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, 'rb') as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            return None
        text = fh.read(FILE_MAX_TEXT_SIZE).decode(errors='replace')
    if path.suffix.lower() in MARKDOWN_SUFFIXES:
        text = markdown_to_text(text)
    return text.strip() or None


# The variables a `repos_destination` may use (see Collection.format_destination).
REPOS_DESTINATION_VARIABLES = ('repo_name', 'repo_tag', 'repo_owner', 'repo_host', 'tag_name', 'name', 'tag')


def repos_destination_root(destination: str) -> str:
    """The fixed directory at the start of a `repos_destination` (before any variable).  It is never indexed."""
    parts = []
    for part in (destination or '').split('/'):
        if '%(' in part:
            break
        parts.append(part)
    return '/'.join(i for i in parts if i)


def validate_repos_destination(destination: str, config=None) -> str:
    """An error message for an invalid `repos_destination`, or an empty string.

    Every repo must live under the destination's fixed directory, which is ignored (repo files are never indexed),
    and that directory must not hold any other kind of WROLPi content."""
    config = config or get_wrolpi_config()
    if not destination:
        return 'Repos directory cannot be empty'
    if destination.startswith('/'):
        return 'Repos directory must be relative to the media directory'
    if any(i in ('..', '.') for i in destination.split('/')):
        return 'Repos directory cannot contain ".." or "."'
    try:
        destination % {i: 'x' for i in REPOS_DESTINATION_VARIABLES}
    except (KeyError, ValueError, TypeError):
        return f'Unknown variable in Repos directory, use: {", ".join(REPOS_DESTINATION_VARIABLES)}'
    if '%(repo_name)s' not in destination and '%(name)s' not in destination:
        return 'Repos directory must contain the repo name: %(repo_name)s'
    root = repos_destination_root(destination)
    if not root:
        return 'Repos directory must start with a fixed directory, like repos/'

    others = {
        'videos_destination': config.videos_destination,
        'archive_destination': config.archive_destination,
        'map_destination': config.map_destination,
        'zims_destination': config.zims_destination,
        'playlists_destination': config.playlists_destination,
        'tags directory': 'tags',
        'config directory': 'config',
    }
    root_parts = tuple(root.split('/'))
    for name, other in others.items():
        other_parts = tuple(repos_destination_root(other).split('/')) if other else ()
        if not other_parts or other_parts == ('',):
            continue
        overlap = min(len(root_parts), len(other_parts))
        if root_parts[:overlap] == other_parts[:overlap]:
            return f'Repos directory cannot overlap the {name} ({other!r})'
    return ''


def format_repo_destination(name: str, tag_name: str = None, owner: str = None, host: str = None) -> pathlib.Path:
    """The directory a Repo with this name, Tag, owner and host is saved in (see `repos_destination`)."""
    name = escape_file_name(name) if name else ''
    tag_name = tag_name or ''
    variables = dict(
        name=name, repo_name=name,
        tag=tag_name, repo_tag=tag_name, tag_name=tag_name,
        repo_owner=escape_file_name(owner) if owner else '',
        repo_host=escape_file_name(host) if host else '',
    )
    destination = get_wrolpi_config().repos_destination % variables
    return get_media_directory() / destination.lstrip('/')


def format_collection_destination(collection: Collection, tag_name: str = None) -> pathlib.Path:
    """The directory of a Repo's Collection (its owner and host are on its Repository)."""
    session = Session.object_session(collection)
    repo = Repository.get_by_collection_id(session, collection.id) if session and collection.id else None
    return format_repo_destination(collection.name, tag_name, repo.owner if repo else None,
                                   repo.host if repo else None)


def get_repository_by_url(session: Session, url: str) -> Optional[Repository]:
    key = repo_url_key(url)
    for id_, repo_url in session.query(Repository.id, Repository.url):
        if repo_url_key(repo_url) == key:
            return session.query(Repository).filter_by(id=id_).one()
    return None


def _validate_mode(mode: str):
    if mode not in REPO_MODES:
        raise ValidationError(f'Repo mode must be one of {", ".join(REPO_MODES)}')


def _validate_directory(directory: pathlib.Path):
    """A Repo's directory is strictly inside the media directory; it is cloned into, and may be deleted."""
    media_directory = get_media_directory()
    directory = pathlib.Path(directory)
    if '..' in directory.parts or not directory.is_absolute():
        raise InvalidRepo(f'Invalid repo directory: {directory}')
    try:
        relative = directory.relative_to(media_directory)
    except ValueError:
        raise InvalidRepo('Repo directory must be in the media directory')
    if not relative.parts:
        raise InvalidRepo('Repo directory can not be the media directory')


def _validate_frequency(frequency: int):
    if not isinstance(frequency, int) or isinstance(frequency, bool) or frequency < 0:
        raise ValidationError('Repo frequency must be a number of seconds, or 0 (never)')


def create_repository(session: Session, url: str, tag_name: str = None, frequency: int = DEFAULT_REPO_FREQUENCY,
                      mode: str = 'full', branch: str = None, name: str = None, description: str = None,
                      directory: pathlib.Path = None, submodules: bool = False,
                      clone_token: str = None) -> Repository:
    """Create a Repo (Collection + Repository + recurring Download).  The download clones it.

    `directory` (relative to the media directory) is where the user chose to clone it; otherwise it is in the
    Repos directory."""
    _validate_frequency(frequency)
    if isinstance(directory, str):
        directory = resolve_new_repo_directory(session, directory)
    repo = _create_repository_records(session, url, tag_name, mode, branch, name, description, directory, submodules,
                                      clone_token)
    _create_repository_download(session, repo, frequency, clone=True)
    return repo


def _set_repository_download(session: Session, repo: Repository, frequency: int, clone: bool = False):
    """Create (or change) the recurring Download which keeps the Repo up to date.  A Repo which is never updated
    (`frequency` is NEVER) has none; with `clone`, it is cloned once if its clone is missing."""
    if not frequency:
        if download := repo.download:
            session.delete(download)
        if clone and not (repo.directory / '.git').exists():
            request_repository_update(session, repo)
        return

    once = repo.once_download
    download = repo.collection.get_or_create_download(session, repo.url, frequency, downloader_name='git')
    # The Download may already exist (e.g. imported from download_manager.yaml, or the Repo's one-time Download).
    download.frequency = frequency
    if once:
        # It may be complete, so it would never be renewed.
        download.renew(reset_attempts=True)


def _create_repository_download(session: Session, repo: Repository, frequency: int, clone: bool = False):
    """Create the Repo's Download (see `_set_repository_download`), and save the Repo."""
    _set_repository_download(session, repo, frequency, clone)
    session.commit()

    save_repos_config.activate_switch()
    save_downloads_config.activate_switch()


def _create_repository_records(session: Session, url: str, tag_name: str, mode: str, branch: Optional[str],
                               name: Optional[str], description: Optional[str], directory: Optional[pathlib.Path],
                               submodules: bool, clone_token: str = None) -> Repository:
    """Create (but do not commit) a Repo's Collection and Repository, in their directory."""
    parsed = parse_repo_url(url)
    _validate_mode(mode)
    branch = branch or parsed.branch or None
    _validate_branch(branch)
    name = (name or parsed.name).strip()
    if name in ('', '.', '..'):
        raise InvalidRepo(f'Invalid repo name: {name!r}')

    if get_repository_by_url(session, parsed.url):
        raise RepoConflict(f'A repo with this URL already exists: {parsed.url}')
    if session.query(Collection).filter_by(kind='repo', name=name).one_or_none():
        suggestion = f'{parsed.owner.replace("/", "-")}-{name}' if parsed.owner else f'{parsed.host}-{name}'
        raise RepoConflict(f'A repo named {name!r} already exists.  Try the name {suggestion!r}')

    tag = Tag.get_or_create_tag(session, tag_name) if tag_name else None
    collection = Collection(kind='repo', name=name, description=description, tag=tag)
    session.add(collection)
    session.flush([collection])
    repo = Repository(url=parsed.url, host=parsed.host, owner=parsed.owner, mode=mode, branch=branch,
                      submodules=bool(submodules), clone_token=clone_token or new_clone_token(),
                      collection=collection)
    repo.update_search_name()
    session.add(repo)
    session.flush([repo])

    directory = directory or collection.format_destination(tag_name)
    _validate_directory(directory)
    if session.query(Collection).filter(Collection.directory == directory, Collection.id != collection.id).first():
        relative = get_relative_to_media_directory(directory)
        raise RepoConflict(f'Another collection already uses the directory {relative}')
    collection.directory = directory
    return repo


def remote_url_key(url: str) -> Optional[str]:
    """`host/path` of a git remote URL in any form (https://, ssh://, git://, or `user@host:path`), to compare remotes.
    None for a local path."""
    url = (url or '').strip()
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', url):
        parsed = urlparse(url)
        host, path = parsed.hostname, parsed.path
    elif match := re.match(r'^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>[^/].*)$', url):
        host, path = match.group('host'), match.group('path')
    else:
        return None
    if not host:
        return None
    return f'{host.lower()}/{path.strip("/").removesuffix(".git")}'


def remote_https_url(url: str) -> Optional[str]:
    """The https:// URL of a git remote URL (e.g. `git@codeberg.org:owner/repo.git`), if it has one."""
    url = (url or '').strip()
    if url.startswith('https://'):
        return url
    if url.startswith(('ssh://', 'git://')) or re.match(r'^(?:[^@/]+@)?[^:/]+:[^/]', url):
        key = remote_url_key(url)
        return f'https://{key}' if key else None
    return None


CONTROL_CHARACTERS_RE = re.compile(r'[\x00-\x1f\x7f]')


def repo_directory_error(directory: pathlib.Path) -> Optional[str]:
    """Why a Repo's directory must not be cloned into (or updated) now, or None.  It was checked when the Repo was
    added, but a link could have been made since: at the directory, or any directory between it and the media
    directory, which would make git write somewhere else."""
    media_directory = get_media_directory()
    directory = pathlib.Path(directory)
    if CONTROL_CHARACTERS_RE.search(str(directory)):
        return f'{directory!r} contains control characters'
    try:
        relative = directory.relative_to(media_directory)
    except ValueError:
        return f'{directory} is not in the media directory'
    if not relative.parts or '..' in relative.parts:
        return f'{directory} is not a directory a Repo can use'
    path = media_directory
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            return f'{path} is a link'
    if directory.resolve() != media_directory.resolve() / relative:
        return f'{directory} is not in the media directory'
    return None


def _resolve_repo_directory(session: Session, directory: str) -> pathlib.Path:
    """A directory (relative to the media directory) a Repo may use: in the media directory, not WROLPi's own
    directories, and not overlapping another Collection's.  It does not have to be ignored."""
    media_directory = get_media_directory().resolve()
    relative = pathlib.Path((directory or '').strip())
    if not str(relative) or relative.is_absolute() or '..' in relative.parts:
        raise InvalidRepo('The directory must be relative to the media directory')
    if CONTROL_CHARACTERS_RE.search(str(relative)):
        # A newline would split a line git reads (e.g. alternates).
        raise InvalidRepo('The directory cannot contain control characters')
    # Resolved (and confined to the media directory) before anything about it is reported, so a link cannot reveal
    # what exists elsewhere.
    path = (media_directory / relative).resolve()
    if path == media_directory or media_directory not in path.parents:
        raise InvalidRepo('The directory must be in the media directory')

    from wrolpi.files.lib import get_special_directories
    for special in get_special_directories():
        special = special.resolve()
        if special != media_directory and (path == special or path in special.parents):
            raise InvalidRepo(f'{get_relative_to_media_directory(special)} cannot be used')
    for managed in (media_directory / 'config', media_directory / 'tags'):
        # WROLPi manages everything in these.
        if path == managed or managed in path.parents or path in managed.parents:
            raise InvalidRepo(f'{get_relative_to_media_directory(managed)} cannot be used')

    for other in session.query(Collection.directory).filter(Collection.directory.isnot(None)):
        other = pathlib.Path(other[0]).resolve()
        if path == other or other in path.parents or path in other.parents:
            raise RepoConflict(f'{directory} is (or holds, or is in) the directory of a Collection')
    return path


def resolve_new_repo_directory(session: Session, directory: str) -> pathlib.Path:
    """The directory a new Repo chose to be cloned into.  It must be empty (or not exist yet)."""
    path = _resolve_repo_directory(session, directory)
    if path.exists():
        if not path.is_dir() or path.is_symlink():
            raise InvalidRepo(f'{directory} is not a directory')
        if next(path.iterdir(), None) is not None:
            raise RepoConflict(f'{directory} is not empty.  To keep a clone which is already there, import it')
    return path


def is_ignored_directory(path: pathlib.Path) -> bool:
    """Are the files in `path` ignored (never indexed)?"""
    from wrolpi.files.lib import get_normalized_ignored_directories
    path = str(path.resolve())
    return any(path == i or path.startswith(f'{i}/') for i in get_normalized_ignored_directories())


def resolve_import_directory(session: Session, directory: str) -> pathlib.Path:
    """The absolute directory of a git clone in the media directory which may be imported as a Repo."""
    path = _resolve_repo_directory(session, directory)
    if not path.is_dir():
        raise UnknownDirectory(f'No directory {directory!r}')

    git_dir = path / '.git'
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise InvalidRepo(f'{directory} is not a git clone (it has no .git directory)')
    config = git_dir / 'config'
    if config.is_symlink() or not config.is_file():
        raise InvalidRepo(f'{directory} cannot be imported: its .git/config is not a file')
    if borrowed := _borrowing_git_file(git_dir):
        raise InvalidRepo(f'{directory} cannot be imported: it uses another git directory (.git/{borrowed})')
    if error := git_dir_link_error(git_dir):
        raise InvalidRepo(f'{directory} cannot be imported: {error}')
    return path


@contextlib.contextmanager
def _read_only_git_dir(directory: pathlib.Path):
    """A throwaway git directory with the clone's HEAD, refs and objects, but none of its config (which has not been
    sanitized, and could include anything).  The clone's objects are only read, through alternates."""
    git_dir = directory / '.git'
    objects = git_dir / 'objects'
    if objects.is_symlink() or not objects.is_dir():
        raise InvalidRepo(f'{objects} is not a directory')
    # alternates is read line by line: it must name only the clone's own objects.
    objects = str(objects.resolve())
    if CONTROL_CHARACTERS_RE.search(objects):
        raise InvalidRepo(f'{objects!r} contains control characters')
    with tempfile.TemporaryDirectory(prefix='wrolpi-inspect-') as temporary:
        view = pathlib.Path(temporary)
        (view / 'objects/info').mkdir(parents=True)
        (view / 'objects/info/alternates').write_text(f'{objects}\n')
        config = '[core]\n\trepositoryformatversion = 0\n\tbare = true\n'
        entries = _git_config_entries(git_dir / 'config')
        object_format = [v for k, v in entries if k.lower() == 'extensions.objectformat']
        if object_format and object_format[0] in ('sha1', 'sha256'):
            config = f'[core]\n\trepositoryformatversion = 1\n\tbare = true\n[extensions]\n' \
                     f'\tobjectformat = {object_format[0]}\n'
        (view / 'config').write_text(config)
        for name in ('HEAD', 'packed-refs', 'shallow'):
            source = git_dir / name
            if source.is_file() and not source.is_symlink():
                shutil.copyfile(source, view / name)
        if (git_dir / 'refs').is_dir() and not (git_dir / 'refs').is_symlink():
            shutil.copytree(git_dir / 'refs', view / 'refs', symlinks=True,
                            ignore=lambda d, names: [i for i in names if (pathlib.Path(d) / i).is_symlink()])
        else:
            (view / 'refs').mkdir()
        yield view


def _git_output_sync(directory: pathlib.Path, *args) -> Optional[str]:
    result = subprocess.run(git_command(*args), cwd=directory, env=git_env(), capture_output=True)
    return result.stdout.decode(errors='replace').strip() if result.returncode == 0 else None


def _read_head_commit(directory: pathlib.Path) -> dict:
    """The sha, date and message of a clone's HEAD.  Reads the commit object itself (`git log` could run programs
    from the clone's config, e.g. gpg)."""
    sha = _git_output_sync(directory, 'rev-parse', '--verify', '--quiet', 'HEAD^{commit}')
    if not sha:
        return dict(head_sha=None, head_date=None, head_message=None)
    raw = _git_output_sync(directory, 'cat-file', 'commit', sha) or ''
    headers, _, message = raw.partition('\n\n')
    head_date = None
    for line in headers.splitlines():
        if line.startswith('committer ') and (match := re.search(r' (\d+) ([+-])(\d\d)(\d\d)$', line)):
            offset = (int(match.group(3)) * 60 + int(match.group(4))) * (1 if match.group(2) == '+' else -1)
            head_date = datetime.fromtimestamp(int(match.group(1)), timezone(timedelta(minutes=offset)))
    return dict(head_sha=sha, head_date=head_date, head_message=message.strip().split('\n')[0] or None)


def inspect_import(session: Session, directory: str, name: str = None, tag_name: str = None,
                   url_override: str = None) -> dict:
    """What importing the git clone in `directory` as a Repo would do.  Changes nothing.

    The clone stays in `directory`.  `url_override` is the URL the import will use, which must match the clone's
    origin; without it, the URL comes from the origin."""
    path = resolve_import_directory(session, directory)
    entries = _git_config_entries(path / '.git/config')
    keys = {key.lower() for key, _ in entries}
    if 'core.bare' in keys and any(k.lower() == 'core.bare' and v.lower() == 'true' for k, v in entries):
        raise InvalidRepo(f'{directory} is a bare repository')
    if 'extensions.partialclone' in keys or any(re.match(r'^remote\..+\.promisor$', k, re.I) for k in keys):
        # Its missing objects would have to be fetched from the network.
        raise InvalidRepo(f'{directory} is a partial clone, which cannot be imported')
    origins = [v for k, v in entries if k.lower() == 'remote.origin.url']
    origin = origins[0] if len(origins) == 1 else None

    url = remote_https_url(origin) if origin else None
    parsed = None
    origin_url = None
    if url:
        try:
            parsed = parse_repo_url(url)
            url = origin_url = parsed.url
        except InvalidRepo:
            url = None
    if given := (url_override or '').strip():
        try:
            parsed = parse_repo_url(given)
        except InvalidRepo:
            parsed = None
    name = (name or (parsed.name if parsed else path.name)).strip()

    head = (path / '.git/HEAD').read_text(errors='replace').strip() if (path / '.git/HEAD').is_file() else ''
    branch = head[len('ref: refs/heads/'):] if head.startswith('ref: refs/heads/') else None
    # git never runs with the clone's own config here: it has not been sanitized yet.
    with _read_only_git_dir(path) as view:
        local_commits = _git_output_sync(view, 'rev-list', '--count', 'HEAD', '--not', '--remotes')
        head_commit = _read_head_commit(view)
    return dict(
        directory=str(get_relative_to_media_directory(path)),
        origin=origin,
        url=origin_url,
        name=name,
        branch=branch if branch and is_valid_branch(branch) else None,
        **head_commit,
        local_commits=int(local_commits) if local_commits and local_commits.isdigit() else None,
        shallow=(path / '.git/shallow').is_file(),
        # The clone stays where it is; unless it is ignored, its files are indexed (searchable).
        ignored=is_ignored_directory(path),
    )


async def import_repository(session: Session, directory: str, url: str = None, confirm: bool = False,
                            tag_name: str = None, frequency: int = DEFAULT_REPO_FREQUENCY, mode: str = 'full',
                            branch: str = None, submodules: bool = False, name: str = None,
                            description: str = None) -> Repository:
    """Import the git clone in `directory` as a Repo.  It stays where it is, and from then on is a mirror of `url`
    (which must be the clone's origin).  Local changes and commits are discarded by its updates."""
    _validate_frequency(frequency)
    info = inspect_import(session, directory, name, tag_name, url)
    source = resolve_import_directory(session, directory)
    url = (url or info['url'] or '').strip()
    if not url:
        raise InvalidRepo("Enter the repo's https:// URL")
    parsed = parse_repo_url(url)
    if info['origin'] and remote_url_key(info['origin']) != remote_url_key(parsed.url):
        raise InvalidRepo(f"The URL is not this clone's origin ({info['origin']})")
    if not confirm:
        raise ValidationError('Confirm that this clone will become a mirror, and its local changes discarded')

    # Like a new Repo, an imported one follows the remote's default branch unless a branch is chosen.
    repo = _create_repository_records(session, parsed.url, tag_name, mode, branch, info['name'], description, source,
                                      submodules)

    # Everything which can refuse the import happens before the clone is changed.
    if error := await asyncio.to_thread(working_tree_git_error, source):
        raise InvalidRepo(f'{directory} cannot be imported: {error}')
    try:
        await asyncio.to_thread(sanitize_git_config, source)
    except ValueError as e:
        raise InvalidRepo(f'{directory} cannot be imported: {e}')
    await asyncio.to_thread(_git_output_sync, source, 'config', '--replace-all', 'remote.origin.url', parsed.url)
    mark_clone(source, repo.clone_token)

    for key, value in _read_head_commit(source).items():
        setattr(repo, key, value)
    repo.readme_path = find_readme(source)
    repo.readme_text = read_readme_text(source / repo.readme_path) if repo.readme_path else None
    repo.size = await asyncio.to_thread(get_repo_size, source)
    _create_repository_download(session, repo, frequency)
    return repo


def request_repository_update(session: Session, repo: Repository) -> Download:
    """Update (or clone) the Repo now.  A Repo which is never updated has a one-time Download for this.  The caller
    commits."""
    if not (download := repo.download or repo.once_download):
        # The user asked for this; it is never skipped.
        download, = download_manager.create_downloads(session, [repo.url], downloader_name='git', override_skip=True)
    download.renew(reset_attempts=True)
    save_downloads_config.activate_switch()
    return download


def update_repository(session: Session, repo_id: int, description: str = None, frequency: int = None,
                      mode: str = None, branch: str = None, submodules: bool = None) -> Repository:
    """Change a Repo's settings.  An empty `branch` follows the remote's default branch."""
    repo = Repository.find_by_id(session, repo_id)
    if description is not None:
        repo.collection.description = description or None
    if mode is not None:
        _validate_mode(mode)
        repo.mode = mode
    if branch is not None:
        branch = branch.strip() or None
        _validate_branch(branch)
        repo.branch = branch
    if submodules is not None:
        repo.submodules = bool(submodules)
    if frequency is not None:
        _validate_frequency(frequency)
        _set_repository_download(session, repo, frequency)
    session.commit()

    save_repos_config.activate_switch()
    save_downloads_config.activate_switch()
    return repo


def _delete_repository(session: Session, repo: Repository):
    collection = repo.collection
    if once := repo.once_download:
        session.delete(once)
    for download in list(collection.downloads):
        session.delete(download)
    session.delete(collection)
    session.flush()


async def delete_repository(session: Session, repo_id: int, delete_files: bool = False) -> dict:
    """Delete a Repo and its Download.  The repo's files are kept unless `delete_files`."""
    repo = Repository.find_by_id(session, repo_id)
    directory = repo.directory
    result = dict(id=repo.id, name=repo.name, directory=str(get_relative_to_media_directory(directory)))
    _delete_repository(session, repo)
    session.commit()

    if delete_files and directory and directory.is_dir():
        media_directory = get_media_directory().resolve()
        if directory.resolve() == media_directory or media_directory not in directory.resolve().parents:
            raise InvalidRepo('Refusing to delete a directory outside the media directory')
        background_task(_delete_directory(directory))

    save_repos_config.activate_switch()
    save_downloads_config.activate_switch()
    return result


async def _delete_directory(directory: pathlib.Path):
    await asyncio.to_thread(shutil.rmtree, directory)
    logger.info(f'Deleted repo directory {directory}')


def get_repositories(session: Session) -> List[dict]:
    repos = session.query(Repository).options(*Repository.json_options()) \
        .join(Collection, Collection.id == Repository.collection_id) \
        .order_by(func.lower(Collection.name)).all()
    return [i.__json__() for i in repos]


def _repo_search_sql(search_str: Optional[str], tag_names: Optional[List[str]]) \
        -> Optional[Tuple[str, str, dict, bool]]:
    """The FROM and WHERE of a Repo search by name/README and Tag, its params, and whether it uses FTS.

    Returns None when nothing can match."""
    tag_names = tag_names or []
    if len(tag_names) > 1:
        # A Repo has one Tag.
        return None
    search = fts.repository_search_join(search_str, start=HIGHLIGHT_START, stop=HIGHLIGHT_STOP) \
        if search_str else None
    if search is None and (search_str and search_str.strip() or not tag_names):
        # Nothing usable to search, or nothing to filter by.
        return None

    from_sql = 'repository r JOIN collection c ON c.id = r.collection_id'
    where, params = [], {}
    if search:
        from_sql = f'{from_sql} {search.join}'
        params.update(search.params)
    if tag_names:
        from_sql = f'{from_sql} JOIN tag t ON t.id = c.tag_id'
        where.append('t.name = :tag_name')
        params['tag_name'] = tag_names[0]
    return from_sql, (f"WHERE {' AND '.join(where)}" if where else ''), params, search is not None


def search_repos(session: Session, search_str: str = None, tag_names: List[str] = None, limit: int = 20,
                 offset: int = 0) -> Tuple[List[dict], int]:
    """Find Repos by their name and README (and/or their Tag).  Returns the Repos (best match first, each with a
    `readme_headline`) and the total count."""
    query = _repo_search_sql(search_str, tag_names)
    if query is None:
        return [], 0
    from_sql, where, params, is_fts = query
    select = 'r.id, fts.readme_headline' if is_fts else 'r.id, NULL'
    order_by = 'fts.ts_rank DESC, LOWER(c.name)' if is_fts else 'LOWER(c.name)'
    rows = session.execute(text(
        f'SELECT {select}, COUNT(*) OVER() FROM {from_sql} {where} ORDER BY {order_by} LIMIT :limit OFFSET :offset'
    ), dict(params, limit=limit, offset=offset)).fetchall()
    if not rows:
        return [], 0

    repos = session.query(Repository).options(*Repository.json_options()) \
        .filter(Repository.id.in_([i[0] for i in rows])).all()
    repos = {i.id: i for i in repos}
    results = [dict(repos[id_].__json__(), readme_headline=_safe_headline(headline))
               for id_, headline, _ in rows if id_ in repos]
    return results, rows[0][2]


# Highlight markers which cannot be confused with HTML.  See `_safe_headline`.
HIGHLIGHT_START, HIGHLIGHT_STOP = '\x02', '\x03'


def _safe_headline(headline: Optional[str]) -> Optional[str]:
    """A README is untrusted and its headline is rendered as HTML: escape it, then mark the matches with <b>."""
    if not headline:
        return headline
    return html.escape(headline).replace(HIGHLIGHT_START, '<b>').replace(HIGHLIGHT_STOP, '</b>')


def count_repos(session: Session, search_str: str = None, tag_names: List[str] = None) -> int:
    """The number of Repos `search_repos` would find."""
    query = _repo_search_sql(search_str, tag_names)
    if query is None:
        return 0
    from_sql, where, params, _ = query
    return session.execute(text(f'SELECT COUNT(*) FROM {from_sql} {where}'), params).scalar()


async def search_repos_by_name(session: Session, name: str, limit: int = 5) -> List[dict]:
    """Repos whose name contains `name`, for the search suggestions."""
    if not name:
        return []
    repos = session.query(Repository).options(*Repository.json_options()) \
        .join(Collection, Collection.id == Repository.collection_id) \
        .filter(Collection.name.ilike(f'%{name}%')) \
        .order_by(func.lower(Collection.name)) \
        .limit(limit).all()
    return [dict(id=i.id, name=i.name, tag_name=i.tag_name, location=i.location) for i in repos]


# Fields of one commit, and the end of a commit, in `git log` output.
LOG_FIELD, LOG_RECORD = '\x1f', '\x1e'
LOG_FORMAT = LOG_FIELD.join(('%H', '%an', '%cI', '%s')) + LOG_RECORD
MAXIMUM_LOG_LIMIT = 100


def get_repo_root(repo: Repository) -> pathlib.Path:
    directory = repo.directory
    if not repo.head_sha or not directory or not (directory / '.git').exists():
        raise UnknownDirectory('Repo has not been downloaded')
    return directory


async def _git_output(directory: pathlib.Path, *args) -> Optional[str]:
    """Run a read-only git command in a Repo; None when it fails."""
    result = await run_command(git_command(*args), cwd=directory, timeout=60, env=git_env(), log_command=False)
    if result.return_code != 0:
        logger.warning(f'git {args[0]} failed in {directory}: {result.stderr.decode(errors="replace")}')
        return None
    return result.stdout.decode(errors='replace')


async def get_repo_log(repo: Repository, limit: int = 50, offset: int = 0) -> dict:
    """The commits of the checked out branch, newest first: {commits: [{sha, author, date, message}], total}."""
    directory = get_repo_root(repo)
    limit = min(max(int(limit), 1), MAXIMUM_LOG_LIMIT)
    offset = max(int(offset), 0)

    output = await _git_output(directory, 'log', f'--max-count={limit}', f'--skip={offset}',
                               f'--format={LOG_FORMAT}', 'HEAD', '--')
    total = await _git_output(directory, 'rev-list', '--count', 'HEAD', '--')
    commits = []
    for record in (output or '').split(LOG_RECORD):
        record = record.strip('\n')
        if not record:
            continue
        sha, author, date, message = record.split(LOG_FIELD, 3)
        commits.append(dict(sha=sha, author=author, date=date, message=message))
    return dict(commits=commits, total=int(total.strip()) if total else len(commits))


def repo_archive_name(repo: Repository) -> str:
    """The name of a Repo's ZIP (without `.zip`), safe for a header and as the directory in the ZIP."""
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', repo.name or 'repo').strip('._') or 'repo'
    return f'{name}-{repo.head_sha[:7]}' if repo.head_sha else name


async def stream_repo_archive(directory: pathlib.Path, name: str, send) -> None:
    """Stream a ZIP of the checked out commit of the repo in `directory` to `send` (an async callable taking
    bytes).  The ZIP's files are in the directory `name`.

    Takes no Repository: the request's session is closed once a streamed response starts.  git writes the ZIP as
    it reads the repo, so a large repo is never held in memory."""
    cmd = git_command('archive', '--format=zip', f'--prefix={name}/', 'HEAD')
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=directory, env=git_env(), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    try:
        while chunk := await proc.stdout.read(64 * 1024):
            await send(chunk)
        await proc.wait()
    finally:
        if proc.returncode is None:
            # The client went away.
            proc.kill()
            await proc.wait()


@dataclass
class RepoTreeEntry:
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None

    def __json__(self) -> dict:
        return dict(name=self.name, path=self.path, is_dir=self.is_dir, size=self.size)


def list_repo_tree(repo: Repository, path: str = '') -> dict:
    """List one directory of a Repo's checked out files, directories first.  `.git` is hidden."""
    root = repo.directory
    if not root or not root.is_dir():
        raise UnknownDirectory('Repo has not been downloaded')
    root = root.resolve()

    path = (path or '').strip('/')
    directory = (root / path).resolve()
    if directory != root and root not in directory.parents:
        raise InvalidRepo('Path is not in the repo')
    if not directory.is_dir():
        raise UnknownDirectory(f'No directory {path!r} in repo')

    entries = []
    for entry in directory.iterdir():
        if entry.name == '.git' or entry.is_symlink():
            continue
        relative = str(entry.relative_to(root))
        if entry.is_dir():
            entries.append(RepoTreeEntry(name=entry.name, path=relative, is_dir=True))
        else:
            entries.append(RepoTreeEntry(name=entry.name, path=relative, is_dir=False, size=entry.stat().st_size))
    entries.sort(key=lambda i: (not i.is_dir, i.name.lower()))

    readme = find_readme(directory)
    return dict(
        path=path,
        entries=[i.__json__() for i in entries],
        readme_path=str((directory / readme).relative_to(root)) if readme else None,
    )


def get_repo_size(directory: pathlib.Path) -> int:
    """Total size of every file in the repo, including `.git`."""
    total = 0
    for dir_path, _, file_names in os.walk(directory):
        for name in file_names:
            try:
                total += os.lstat(os.path.join(dir_path, name)).st_size
            except FileNotFoundError:
                pass
    return total


@dataclass
class ReposConfigValidator:
    version: int = 0
    repos: List[dict] = field(default_factory=list)


class ReposConfig(ConfigFile):
    """Config file for git Repos (Collections with kind='repo').

    Format:
        repos:
          - name: kiwix-tools
            url: https://github.com/kiwix/kiwix-tools
            directory: repos/software/kiwix-tools
            tag_name: software
            mode: full
            branch: null
            submodules: false
            frequency: 604800
    """
    file_name = 'repos.yaml'
    validator = ReposConfigValidator
    default_config = dict(version=0, repos=[])
    width = 120

    @property
    def repos(self) -> List[dict]:
        return self._config.get('repos', [])

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Import Repos from the config into the database."""
        file = file or self.get_file()
        file_str = str(self.get_relative_file())

        # A missing config is not an empty config; never delete Repos because a file is lost.
        if not file.is_file():
            logger.info(f'No repos config file, skipping import: {file_str}')
            self.successful_import = True
            return

        super().import_config(file, send_events)
        repos_data = self._config.get('repos', [])

        # An empty repos list never deletes DB records.  Deleting all repos is done through the API.
        if not repos_data:
            logger.info(f'No repos in config, preserving existing DB repos: {file_str}')
            self.successful_import = True
            return

        try:
            with get_db_session(commit=True) as session:
                imported_ids = set()
                for data in repos_data:
                    try:
                        repo = self._import_repo(session, data)
                    except Exception as e:
                        logger.error(f'Failed to import repo from config: {data}', exc_info=e)
                        self.import_skipped += 1
                        continue
                    imported_ids.add(repo.id)

                for repo in session.query(Repository).all():
                    if repo.id not in imported_ids:
                        logger.info(f'Deleting repo {repo.name!r} (no longer in config)')
                        _delete_repository(session, repo)

            logger.info(f'Imported {len(imported_ids)} repos from {file_str}')
            self.successful_import = True
        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {file_str} config!'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_import_failed(message)
            raise

    @staticmethod
    def _import_repo(session: Session, data: dict) -> Repository:
        parsed = parse_repo_url(data['url'])
        name = data.get('name') or parsed.name
        mode = data.get('mode') or 'full'
        _validate_mode(mode)
        frequency = data.get('frequency')
        frequency = NEVER if frequency in (NEVER_CONFIG, NEVER) else (frequency or DEFAULT_REPO_FREQUENCY)
        _validate_frequency(frequency)
        directory = data.get('directory')
        directory = get_media_directory() / directory if directory else None
        if directory:
            _validate_directory(directory)
        tag_name = data.get('tag_name')

        repo = get_repository_by_url(session, parsed.url)
        if not repo:
            return create_repository(session, parsed.url, tag_name=tag_name, frequency=frequency, mode=mode,
                                     branch=data.get('branch'), name=name, description=data.get('description'),
                                     directory=directory, submodules=bool(data.get('submodules')),
                                     clone_token=data.get('clone_token'))

        collection = repo.collection
        collection.name = name
        repo.update_search_name()
        collection.description = data.get('description')
        collection.tag = Tag.get_or_create_tag(session, tag_name) if tag_name else None
        if directory:
            collection.directory = directory
        repo.mode = mode
        repo.submodules = bool(data.get('submodules'))
        if data.get('clone_token'):
            repo.clone_token = data['clone_token']
        branch = data.get('branch') or None
        _validate_branch(branch)
        repo.branch = branch
        _set_repository_download(session, repo, frequency)
        session.flush()
        return repo

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all Repos to the config file."""
        with get_db_session() as session:
            repos = session.query(Repository).options(*Repository.json_options()) \
                .join(Collection, Collection.id == Repository.collection_id) \
                .order_by(func.lower(Collection.name)).all()
            data = []
            for repo in repos:
                download = repo.download
                entry = dict(
                    name=repo.name,
                    url=repo.url,
                    directory=str(get_relative_to_media_directory(repo.directory)) if repo.directory else None,
                    tag_name=repo.tag_name,
                    description=repo.collection.description,
                    mode=repo.mode,
                    branch=repo.branch,
                    submodules=repo.submodules,
                    frequency=download.frequency if download else NEVER_CONFIG,
                    # Restoring a Repo from the config keeps its clone.
                    clone_token=repo.clone_token,
                )
                data.append(entry)

        self._config['repos'] = data
        logger.info(f'Dumping {len(data)} repos to config')
        self.save(file, send_events, overwrite)

    def preview_backup_import(self, backup_date: str, mode: str) -> dict:
        """Preview which Repos a backup import would add/remove (keyed by URL)."""
        backup_data = self.read_config_file(self._get_backup_file(backup_date))
        current_data = self.read_config_file() if self.get_file().is_file() else dict(repos=[], version=0)

        backup_repos = {repo_url_key(i['url']): i for i in backup_data.get('repos', []) if i.get('url')}
        current_repos = {repo_url_key(i['url']): i for i in current_data.get('repos', []) if i.get('url')}

        add = [dict(type='repo', name=i.get('name', ''), url=i['url'])
               for key, i in backup_repos.items() if key not in current_repos]
        unchanged = len([i for i in backup_repos if i in current_repos])
        remove = []
        if mode == 'overwrite':
            remove = [dict(type='repo', name=i.get('name', ''), url=i['url'])
                      for key, i in sorted(current_repos.items()) if key not in backup_repos]
        return dict(mode=mode, add=add, remove=remove, unchanged=unchanged)

    def import_backup(self, backup_date: str, mode: str, send_events: bool = False):
        """Restore Repos from a dated backup of repos.yaml ('overwrite' or 'merge' by URL)."""
        self._preserve_current_config()
        backup_file = self._get_backup_file(backup_date)
        config_file = self.get_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)

        if mode == 'overwrite':
            shutil.copy2(backup_file, config_file)
        elif mode == 'merge':
            backup_data = self.read_config_file(backup_file)
            current_data = self.read_config_file() if config_file.is_file() else dict(repos=[], version=0)
            current_keys = {repo_url_key(i['url']) for i in current_data.get('repos', []) if i.get('url')}
            merged = list(current_data.get('repos', []))
            merged.extend(i for i in backup_data.get('repos', [])
                          if i.get('url') and repo_url_key(i['url']) not in current_keys)
            self.write_config_data(dict(repos=merged, version=current_data.get('version', 0) + 1), config_file)

        self.import_config(send_events=send_events)
        save_downloads_config.activate_switch()


repos_config = ReposConfig()


def get_repos_config() -> ReposConfig:
    return repos_config


@register_switch_handler('save_repos_config')
def save_repos_config():
    """Save the repos config when the switch is activated."""
    repos_config.background_dump.activate_switch()


save_repos_config: ActivateSwitchMethod


def import_repos_config():
    logger.info('Importing repos config')
    repos_config.import_config()
