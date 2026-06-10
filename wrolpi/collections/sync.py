"""On-disk synchronization of playlist collections.

Each playlist (kind='playlist') is materialized into a per-playlist subdirectory of the configured
playlists directory.  A tagged playlist is namespaced under its tag (like channel tags), an untagged
one lives directly under the playlists directory:

    <media>/playlists/<tag>/<name>/    tagged playlist
    <media>/playlists/<name>/          untagged playlist

Items are ordered by a position prefix within the subdirectory:

    0001_<file>          hard links of a FileGroup's files (file item)
    0002_<title>.html    a stub redirecting to a Zim article (zim item)
    0003_<title>.html    a stub redirecting to a URL (url item)

This gives an offline-browsable, ordered view of the playlist.  The playlists directory is excluded
from indexing (see ``WROLPiConfig.import_config``), so these managed files are not re-indexed.

Only files matching the ``NNNN_`` position prefix are managed here; anything else a user puts in the
directory is left untouched.

Deletion safety: a managed file is only removed if it is one of our generated HTML stubs, or it still
has another hard link outside the playlists directory (``st_nlink > 1``).  We never delete a file
that would lose its last copy -- mirroring the Tags Directory behaviour.
"""
import html
import pathlib
import re
import shutil
import urllib.parse

from wrolpi.common import get_media_directory, get_wrolpi_config, escape_file_name, logger
from wrolpi.db import get_db_session
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)

__all__ = ['sync_playlists_directory', 'get_playlists_directory', 'validate_playlists_destination',
           'cleanup_playlist_directory']

# Files we create are prefixed with a zero-padded 1-based position, e.g. "0001_".
MANAGED_NAME = re.compile(r'^\d{4}_')
README_NAME = 'README.txt'
# Embedded in generated stub HTML so we can recognize (and therefore safely delete) our own stubs,
# even though a stub is not a hard link.
STUB_MARKER = '<!--wrolpi-playlist-stub-->'


def get_playlists_directory() -> pathlib.Path:
    return get_media_directory() / get_wrolpi_config().playlists_destination


def validate_playlists_destination(destination: str, config=None) -> str:
    """Validate a playlists_destination value, returning an error message (empty string if valid).

    The sync deletes loose files at the destination's root and prunes empty directories beneath it,
    so the destination must be a plain relative directory inside the media directory which does not
    overlap (equal/ancestor/descendant) any other content destination.
    """
    config = config or get_wrolpi_config()
    parts = pathlib.PurePosixPath(destination or '').parts
    if not parts:
        return 'Playlists directory cannot be empty'
    if pathlib.PurePosixPath(destination).is_absolute():
        return 'Playlists directory must be relative to media directory'
    if '..' in parts or '.' in parts:
        return 'Playlists directory cannot contain ".." or "."'

    others = {
        'videos_destination': config.videos_destination,
        'archive_destination': config.archive_destination,
        'map_destination': config.map_destination,
        'zims_destination': config.zims_destination,
        'tags directory': 'tags',  # Fixed path, see wrolpi.tags.get_tags_directory.
    }
    for name, other in others.items():
        if not other:
            continue
        # Destinations like 'videos/%(channel_tag)s/...' are templates; any directory can match a
        # template segment, so only the static prefix is comparable.
        other_parts = []
        for part in pathlib.PurePosixPath(other).parts:
            if '%(' in part:
                break
            other_parts.append(part)
        if not other_parts:
            continue
        other_parts = tuple(other_parts)
        # Reject equality or any ancestor/descendant relationship: the sync would delete or prune
        # files belonging to the other destination.
        overlap = min(len(parts), len(other_parts))
        if parts[:overlap] == other_parts[:overlap]:
            return f'Playlists directory cannot overlap {name} ({other!r})'
    return ''


def _position_prefix(position: int) -> str:
    return f'{position:04d}_'


def _safe_redirect_url(url: str) -> str:
    """Neutralize dangerous URL schemes for use in a stub's href/meta-refresh.

    Allows http(s) and scheme-less (relative) URLs like ``/api/...`` or ``/map?...``; anything else
    (``javascript:``, ``data:``, ...) becomes ``about:blank`` so opening a stub cannot run script.
    """
    url = (url or '').strip()
    # Strip control characters that could smuggle a scheme past the check (e.g. "java\tscript:").
    url = ''.join(c for c in url if ord(c) >= 0x20 and c != '\x7f')
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme and scheme not in ('http', 'https'):
        return 'about:blank'
    return url


def _stub_html(title: str, url: str) -> str:
    """A tiny HTML file that redirects to (and links to) a local URL."""
    safe_url = html.escape(_safe_redirect_url(url), quote=True)
    safe_title = html.escape(title or url or 'link')
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f'{STUB_MARKER}'
        f'<meta http-equiv="refresh" content="0; url={safe_url}">'
        f'<title>{safe_title}</title></head>\n'
        f'<body><p>Opening <a href="{safe_url}">{safe_title}</a> &hellip;</p></body></html>\n'
    )


def _zim_entry_url(zim_id: int, zim_entry: str) -> str:
    return f'/api/zim/{zim_id}/entry/{urllib.parse.quote(zim_entry or "")}'


def _item_title(item) -> str:
    if item.title:
        return item.title
    if item.item_kind == 'url':
        return item.url or 'link'
    if item.item_kind == 'zim':
        return (item.zim_entry or 'article').split('/')[-1]
    return 'item'


def _hardlink_or_copy(source: pathlib.Path, link: pathlib.Path):
    """Hard-link source to link (replacing a stale link); fall back to copy across filesystems."""
    if link.exists():
        try:
            if link.stat().st_ino == source.stat().st_ino:
                return  # Already the correct hardlink.
        except FileNotFoundError:
            pass
        link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.hardlink_to(source)
    except OSError:
        # Cross-filesystem (EXDEV) or other link failure -> copy instead.
        shutil.copy2(source, link)


def _default_playlist_subdir(playlists_directory: pathlib.Path, collection) -> pathlib.Path:
    """The managed location for a playlist: tagged playlists are namespaced under their tag
    (``<playlists>/<tag>/<name>``), untagged playlists live directly under the playlists
    directory (``<playlists>/<name>``).  Ignores any explicit custom directory."""
    base = playlists_directory
    if collection.tag_name:
        base = base / escape_file_name(collection.tag_name)
    return base / escape_file_name(collection.name)


def _playlist_subdir(playlists_directory: pathlib.Path, collection) -> pathlib.Path:
    """The directory a playlist's files live in.

    A playlist with an explicit custom ``directory`` uses it as-is (it may live anywhere in the
    media directory); otherwise the managed location is used.
    """
    if collection.directory:
        return pathlib.Path(collection.directory)
    return _default_playlist_subdir(playlists_directory, collection)


def _is_stub(path: pathlib.Path) -> bool:
    """True if this file is one of our generated HTML stubs (carries STUB_MARKER)."""
    try:
        with path.open('rb') as fh:
            return STUB_MARKER.encode() in fh.read(512)
    except OSError:
        return False


def _safe_unlink_managed(path: pathlib.Path) -> bool:
    """Delete a managed playlist file only when it is safe to do so.

    Safe means: it is one of our generated stubs, or it still has another hard link outside the
    playlists directory (``st_nlink > 1``).  A file that would lose its last copy is never deleted
    (we warn instead).  Returns True if the file is gone afterward.
    """
    try:
        st = path.stat()
    except FileNotFoundError:
        return True
    if _is_stub(path) or st.st_nlink > 1:
        logger.debug(f'Removing playlist file: {path}')
        path.unlink()
        return True
    logger.warning(f'Refusing to delete playlist file without another hardlink: {path}')
    return False


def cleanup_playlist_directory(directory: pathlib.Path):
    """Clean up a directory a playlist no longer occupies (deleted, moved, or re-pointed).

    Custom playlist directories live outside the playlists root, so the orphan pruning in
    ``sync_playlists_directory`` never sees them -- the mutation that abandons the directory calls
    this instead.  Managed (``NNNN_``) files are removed with the usual stub/hardlink safety, then
    the directory is deleted only if it is empty; user files are never touched.
    """
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return
    for child in list(directory.iterdir()):
        if child.is_file() and MANAGED_NAME.match(child.name):
            _safe_unlink_managed(child)
    if next(directory.iterdir(), None) is None:
        logger.debug(f'Removing abandoned playlist directory: {directory}')
        directory.rmdir()
    else:
        logger.warning(f'Keeping abandoned playlist directory with remaining files: {directory}')


def _sync_one_playlist(playlists_directory: pathlib.Path, collection) -> pathlib.Path:
    """Materialize a single playlist's items into its subdirectory.  Returns the subdir."""
    directory = _playlist_subdir(playlists_directory, collection)
    directory.mkdir(parents=True, exist_ok=True)

    desired = set()  # Names (relative to `directory`) we should have created.
    for item in collection.items:  # Ordered by position.
        prefix = _position_prefix(item.position)
        if item.item_kind == 'file' and item.file_group and item.file_group.files:
            for source in item.file_group.my_paths():
                if not source.is_file():
                    continue
                name = f'{prefix}{source.name}'
                _hardlink_or_copy(source, directory / name)
                desired.add(name)
        elif item.item_kind == 'zim':
            name = f'{prefix}{escape_file_name(_item_title(item))}.html'
            (directory / name).write_text(_stub_html(_item_title(item),
                                                      _zim_entry_url(item.zim_id, item.zim_entry)))
            desired.add(name)
        elif item.item_kind == 'url':
            name = f'{prefix}{escape_file_name(_item_title(item))}.html'
            (directory / name).write_text(_stub_html(_item_title(item), item.url))
            desired.add(name)

    # Remove our previously-managed files that are no longer wanted (safely; only NNNN_ files).
    for path in directory.iterdir():
        if path.is_file() and MANAGED_NAME.match(path.name) and path.name not in desired:
            _safe_unlink_managed(path)

    return directory


def _write_readme(playlists_directory: pathlib.Path):
    playlists_directory.mkdir(parents=True, exist_ok=True)
    readme = playlists_directory / README_NAME
    if not readme.is_file():
        readme.write_text(
            'This directory contains your playlists as ordered files.\n\n'
            'WARNING: This directory is controlled by WROLPi.  Managed files (named like 0001_*)\n'
            'are created and deleted automatically, and any loose file placed directly in this\n'
            'directory will be removed.\n'
        )


def _delete_stray_root_files(playlists_directory: pathlib.Path):
    """Remove loose files at the playlists root.

    Only the README and playlist (or tag) subdirectories belong at the root of this
    WROLPi-managed directory, so any other file a user drops in (e.g. ``playlists/foo``) is deleted.
    """
    for path in playlists_directory.iterdir():
        if path.is_file() and path.name != README_NAME:
            logger.debug(f'Removing stray file from playlists root: {path}')
            path.unlink()


def _prune_orphan_dirs(playlists_directory: pathlib.Path, wanted_subdirs):
    """Remove playlist directories (and now-empty tag directories) that are no longer wanted.

    Managed files inside an orphaned directory are removed with the same safety as item removal
    (stub or another-hardlink only).  A directory with surviving files -- because it holds
    non-managed files, or files we refused to delete -- is kept.
    """
    wanted = set(wanted_subdirs)
    # Keep wanted playlist dirs and the tag directories that contain them.
    keep = set(wanted)
    for directory in wanted:
        for parent in directory.parents:
            if parent == playlists_directory:
                break
            keep.add(parent)

    # Deepest first, so a playlist leaf dir is emptied before we try to remove its tag dir.
    all_dirs = sorted((p for p in playlists_directory.rglob('*') if p.is_dir()),
                      key=lambda p: len(p.parts), reverse=True)
    for path in all_dirs:
        if path in keep:
            continue
        for child in list(path.iterdir()):
            if child.is_file() and MANAGED_NAME.match(child.name):
                _safe_unlink_managed(child)
        if next(path.iterdir(), None) is None:
            logger.debug(f'Removing orphaned playlist directory: {path}')
            path.rmdir()
        else:
            logger.warning(f'Refusing to delete playlist directory with remaining files: {path}')


@register_switch_handler('sync_playlists_directory')
def sync_playlists_directory():
    """Synchronize all playlist collections to the playlists directory."""
    from .models import Collection

    # The sync deletes files; refuse to run against a destination that escapes the media directory
    # or overlaps another content destination (e.g. a hand-edited wrolpi.yaml).
    if error := validate_playlists_destination(get_wrolpi_config().playlists_destination):
        message = f'Refusing to sync playlists directory: {error}'
        logger.error(message)
        raise RuntimeError(message)

    playlists_directory = get_playlists_directory()
    media_directory = get_media_directory().resolve()
    resolved = playlists_directory.resolve()
    if resolved == media_directory or not resolved.is_relative_to(media_directory):
        message = f'Refusing to sync playlists directory outside media directory: {resolved}'
        logger.error(message)
        raise RuntimeError(message)

    with get_db_session() as session:
        try:
            collections = session.query(Collection).filter_by(kind='playlist').all()
            if not collections and not playlists_directory.is_dir():
                # No playlists and no directory: nothing to materialize or clean up.  Don't create
                # an empty managed directory (with its README) on systems that use no playlists.
                return
            _write_readme(playlists_directory)
            wanted_subdirs = {_sync_one_playlist(playlists_directory, c) for c in collections}
            _prune_orphan_dirs(playlists_directory, wanted_subdirs)
            _delete_stray_root_files(playlists_directory)
        except Exception as e:
            logger.error('Failed to sync playlists directory', exc_info=e)
            raise


sync_playlists_directory: ActivateSwitchMethod
