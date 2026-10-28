"""How far the User is through a file, and the recently viewed files config.

`FileGroup.progress` is the fraction consumed (0.0 to 1.0, where 1.0 is finished), and `FileGroup.position`
is where to resume.  A position is a dict with a `kind`:

    {"kind": "time", "seconds": 512.3}            video and audio
    {"kind": "epub", "cfi": "epubcfi(/6/14!/4/2)"}  EPUB
    {"kind": "page", "page": 12}                  comic books (0-based)

The client may add `updated_at` (milliseconds since the epoch) so it can compare the server's position with
one it holds locally.

The database is the working store.  `recently_viewed.yaml` holds the most recently viewed files so viewing
history and positions survive a database rebuild.
"""
import math
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import pytz

from wrolpi import dates
from sqlalchemy.orm import Session

from wrolpi.common import ConfigFile, logger, get_media_directory, get_paths_in_media_directory, chunks
from wrolpi.config_import import ConfigSection
from wrolpi.db import get_db_session
from wrolpi.errors import ValidationError, NoPrimaryFile
from wrolpi.events import Events
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)

# A file this far through is finished; the rest is credits, an end screen, or an index.
FINISHED_PROGRESS = 0.95
# A position this close to the start is not worth resuming.
MINIMUM_SECONDS = 10
MINIMUM_PROGRESS = 0.01
MAXIMUM_CFI_LENGTH = 1_000

# The most recently viewed files kept in the config.  The database keeps every `viewed`.
RECENTLY_VIEWED_LIMIT = 1_000


def _number(value, name: str) -> float:
    # bool is an int; reject it so `true` is not a position.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f'{name} must be a number')
    return value


def validate_position(position: Optional[dict]) -> Optional[dict]:
    """Return a clean copy of `position`, or raise ValidationError."""
    if position is None:
        return None
    if not isinstance(position, dict):
        raise ValidationError('position must be an object')

    kind = position.get('kind')
    if kind == 'time':
        clean = dict(kind=kind, seconds=float(_number(position.get('seconds'), 'seconds')))
        if clean['seconds'] < 0:
            raise ValidationError('seconds cannot be negative')
    elif kind == 'page':
        page = position.get('page')
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValidationError('page must be a non-negative integer')
        clean = dict(kind=kind, page=page)
    elif kind == 'epub':
        cfi = position.get('cfi')
        if not isinstance(cfi, str) or not cfi.startswith('epubcfi(') or len(cfi) > MAXIMUM_CFI_LENGTH:
            raise ValidationError('cfi must be an epubcfi')
        clean = dict(kind=kind, cfi=cfi)
    else:
        raise ValidationError(f'Unknown position kind: {kind!r}')

    if (updated_at := position.get('updated_at')) is not None:
        clean['updated_at'] = int(_number(updated_at, 'updated_at'))
    return clean


def normalize_progress(progress, position: Optional[dict]) -> Tuple[float, Optional[dict]]:
    """Apply the progress rules: a finished file has no position, nor does one barely started.

    @return: (progress, position) to store.
    """
    progress = min(max(float(_number(progress, 'progress')), 0.0), 1.0)
    position = validate_position(position)

    if progress >= FINISHED_PROGRESS:
        return 1.0, None

    too_early = progress < MINIMUM_PROGRESS
    if position and position['kind'] == 'time':
        too_early = too_early or position['seconds'] < MINIMUM_SECONDS
    elif position and position['kind'] == 'page':
        too_early = too_early or position['page'] == 0
    if too_early:
        return 0.0, None

    return progress, position


@dataclass
class RecentlyViewedConfigValidator:
    version: int = None
    files: list = field(default_factory=list)


def _parse_entry(entry) -> Optional[Tuple[str, datetime, Optional[float], Optional[dict]]]:
    """Return (path, viewed, progress, position) from a config entry, or None if it is malformed."""
    if not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or not entry.get('viewed'):
        return None
    try:
        viewed = entry['viewed']
        if isinstance(viewed, datetime):
            # YAML parses an unquoted timestamp (a hand edit) into a naive UTC datetime.
            viewed = viewed if viewed.tzinfo else viewed.replace(tzinfo=pytz.UTC)
        else:
            viewed = dates.strptime_ms(viewed)
        progress, position = None, None
        if entry.get('progress') is not None:
            progress, position = normalize_progress(entry['progress'], entry.get('position'))
        return entry['path'], viewed, progress, position
    except Exception as e:
        logger.warning(f'Ignoring invalid recently viewed entry {entry!r}: {e}')
        return None


def _viewed_row(viewed, progress, position) -> dict:
    return dict(viewed=viewed, progress=progress, position=position or None)


def _entry_keys(paths: List[str]) -> Dict[str, str]:
    """{entry path: its path relative to the media directory}, without those outside it (an absolute `path` replaces
    the media directory in the join, and `..` can leave it)."""
    media_directory = get_media_directory()
    absolute_paths = {i: pathlib.Path(os.path.normpath(media_directory / i)) for i in paths}
    inside = set(get_paths_in_media_directory(list(absolute_paths.values())))
    return {i: str(j.relative_to(media_directory)) for i, j in absolute_paths.items() if j in inside}


def _malformed_keys(config: dict) -> set:
    paths = [i['path'] for i in config.get('files') or []
             if isinstance(i, dict) and isinstance(i.get('path'), str) and not _parse_entry(i)]
    return set(_entry_keys(paths).values())


class ViewedSection(ConfigSection):
    """recently_viewed.yaml's files, keyed by path (relative to the media directory), comparing when each was viewed,
    and how far it was read or watched.  Only the newest views are saved (`RECENTLY_VIEWED_LIMIT`); older ones are
    not in the database's rows."""
    name = 'viewed'

    def file_rows(self, config: dict) -> Tuple[Dict[str, dict], Set[str]]:
        # Malformed entries are not counted as skipped: recently viewed is saved after every view, and a skipped
        # entry would stop that.  (`prepare` keeps their history.)
        rows = dict()
        entries = list(filter(None, map(_parse_entry, config.get('files') or [])))
        keys = _entry_keys([i[0] for i in entries])
        for path, viewed, progress, position in entries:
            if not (key := keys.get(path)):
                logger.warning(f'Not importing recently viewed file outside the media directory: {path}')
                continue
            # The first (newest) entry of a file wins.
            rows.setdefault(key, _viewed_row(viewed, progress, position))
        return rows, set()

    def db_rows(self, session: Session) -> Dict[str, dict]:
        # wrolpi.files.models imports this module.
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        query = session.query(FileGroup.primary_path, FileGroup.viewed, FileGroup.progress, FileGroup.position) \
            .filter(FileGroup.viewed.isnot(None)) \
            .order_by(FileGroup.viewed.desc(), FileGroup.id) \
            .limit(RECENTLY_VIEWED_LIMIT)
        rows = query.all()
        # A row outside the media directory is not saved (see `dump_config`).
        inside = set(get_paths_in_media_directory([i[0] for i in rows]))
        return {str(path.relative_to(media_directory)): _viewed_row(*values)
                for path, *values in rows if path in inside}

    def upsert(self, session: Session, rows: Dict[str, dict]):
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        file_groups = dict()
        for paths in chunks([str(media_directory / i) for i in rows], 500):
            file_groups.update((str(i.primary_path.relative_to(media_directory)), i) for i in
                               session.query(FileGroup).filter(FileGroup.primary_path.in_(paths)))
        for key, row in rows.items():
            if not (file_group := file_groups.get(key)):
                if not row.get('files'):
                    continue
                try:
                    file_group = FileGroup.from_paths(session, *row['files'])
                except NoPrimaryFile:
                    logger.warning(f'Cannot import recently viewed file: {key}')
                    continue
                session.add(file_group)
            file_group.viewed, file_group.progress, file_group.position = \
                row['viewed'], row['progress'], row['position']
        session.flush()

    def delete(self, session: Session, keys: Set[str]):
        """A file removed from the config was not viewed."""
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        for paths in chunks([str(media_directory / i) for i in keys], 500):
            for file_group in session.query(FileGroup).filter(FileGroup.primary_path.in_(paths)):
                file_group.viewed = file_group.progress = file_group.position = None


class RecentlyViewedConfig(ConfigFile):
    file_name = 'recently_viewed.yaml'
    sections = (ViewedSection(),)
    default_config = dict(
        version=0,
        files=[],
    )
    validator = RecentlyViewedConfigValidator
    width = 500

    @property
    def files(self) -> List[dict]:
        return list(self._config.get('files', []))

    def dump_config(self, file=None, send_events=False, overwrite=False):
        if self.get_file().exists() and not self.successful_import and not overwrite:
            # Dumping now would replace history the import has not yet applied.
            logger.debug(f'Not dumping {self.file_name} because it has not been imported')
            return

        try:
            # wrolpi.files.models imports this module.
            from wrolpi.files.models import FileGroup
            media_directory = get_media_directory()
            with get_db_session() as session:
                version = self.db_version_for_dump(session)
                file_groups = session.query(FileGroup) \
                    .filter(FileGroup.viewed.isnot(None)) \
                    .order_by(FileGroup.viewed.desc(), FileGroup.id) \
                    .limit(RECENTLY_VIEWED_LIMIT)
                files = list()
                for file_group in file_groups:
                    if not get_paths_in_media_directory([file_group.primary_path]):
                        # One bad row must not stop every later save.
                        logger.warning(f'Not saving recently viewed file outside the media directory:'
                                       f' {file_group.primary_path}')
                        continue
                    entry = dict(
                        path=str(file_group.primary_path.relative_to(media_directory)),
                        viewed=file_group.viewed.isoformat(),
                    )
                    if file_group.progress is not None:
                        entry['progress'] = file_group.progress
                    if file_group.position:
                        entry['position'] = file_group.position
                    files.append(entry)
            self.update({'files': files, 'version': version}, overwrite=overwrite)
        except Exception as e:
            message = f'Failed to save {self.get_relative_file()} config'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_save_failed(message)

    def prepare(self, diffs: dict):
        diff, db_rows = diffs['viewed'], self.import_db_rows['viewed']
        file_rows = ViewedSection().file_rows(self.import_file_config)[0]

        # Only views at least as recent as the oldest entry of the file are removed: an older view fell off the end
        # of the saved window.  A malformed entry keeps its file's history.
        if diff.removed:
            oldest = min(i['viewed'] for i in file_rows.values()) if file_rows else None
            malformed = _malformed_keys(self.import_file_config)
            diff.removed = {i for i in diff.removed
                            if oldest and db_rows[i]['viewed'] >= oldest and i not in malformed}

        # New entries which are in the database (outside the newest views), and which are not.
        from wrolpi.files.lib import glob_shared_stem
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        known = dict()
        with get_db_session() as session:
            for paths in chunks([str(media_directory / i) for i in diff.added], 500):
                known.update((str(path.relative_to(media_directory)), _viewed_row(*values)) for path, *values in
                             session.query(FileGroup.primary_path, FileGroup.viewed, FileGroup.progress,
                                           FileGroup.position).filter(FileGroup.primary_path.in_(paths)))

        # Without deletes (no database version), progress written after the config is kept; a newer plain view keeps
        # its `viewed`, but it is not a newer place to resume.  This applies to a file that fell out of the newest
        # views too.
        if not self.import_deletes:
            for rows, current in ((diff.changed, db_rows), (diff.added, known)):
                for key, row in list(rows.items()):
                    if key in current and current[key]['viewed'] and current[key]['viewed'] >= row['viewed']:
                        if current[key]['progress'] is not None:
                            del rows[key]
                        else:
                            rows[key] = dict(row, viewed=current[key]['viewed'])

        # The files of new entries which are not yet in the database; a deleted file's history goes with it.
        for key, row in list(diff.added.items()):
            absolute_path = media_directory / key
            if key in known:
                continue
            if absolute_path.is_file():
                row['files'] = glob_shared_stem(absolute_path)
            else:
                logger.debug(f'Not importing recently viewed file which does not exist: {absolute_path}')
                del diff.added[key]


RECENTLY_VIEWED_CONFIG: RecentlyViewedConfig = RecentlyViewedConfig()


def get_recently_viewed_config() -> RecentlyViewedConfig:
    return RECENTLY_VIEWED_CONFIG


@register_switch_handler('save_recently_viewed_config')
def save_recently_viewed_config():
    get_recently_viewed_config().dump_config()


save_recently_viewed_config: ActivateSwitchMethod
