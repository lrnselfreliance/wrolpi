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
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import pytz

from wrolpi import dates
from wrolpi.common import ConfigFile, logger, get_media_directory
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


class RecentlyViewedConfig(ConfigFile):
    file_name = 'recently_viewed.yaml'
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
                file_groups = session.query(FileGroup) \
                    .filter(FileGroup.viewed.isnot(None)) \
                    .order_by(FileGroup.viewed.desc(), FileGroup.id) \
                    .limit(RECENTLY_VIEWED_LIMIT)
                files = list()
                for file_group in file_groups:
                    entry = dict(
                        path=str(file_group.primary_path.relative_to(media_directory)),
                        viewed=file_group.viewed.isoformat(),
                    )
                    if file_group.progress is not None:
                        entry['progress'] = file_group.progress
                    if file_group.position:
                        entry['position'] = file_group.position
                    files.append(entry)
            self.update({'files': files}, overwrite=overwrite)
        except Exception as e:
            message = f'Failed to save {self.get_relative_file()} config'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_save_failed(message)

    def import_config(self, file=None, send_events=False):
        """Apply the config to the database.  The newer `viewed` wins, so a file viewed while WROLPi was
        starting keeps its newer position."""
        super().import_config(file, send_events)
        try:
            # wrolpi.files.models imports this module.
            from wrolpi.files.lib import glob_shared_stem
            from wrolpi.files.models import FileGroup

            media_directory = get_media_directory()
            entries = [i for i in map(_parse_entry, self.files) if i]
            with get_db_session(commit=True) as session:
                absolute_paths = [media_directory / path for path, *_ in entries]
                file_groups = session.query(FileGroup).filter(FileGroup.primary_path.in_(absolute_paths))
                file_groups_by_path = {i.primary_path: i for i in file_groups}

                applied = 0
                for path, viewed, progress, position in entries:
                    absolute_path = media_directory / path
                    file_group = file_groups_by_path.get(absolute_path)
                    if not file_group:
                        if not absolute_path.is_file():
                            # The file was deleted; its history goes with it.
                            logger.debug(f'Not importing recently viewed file which does not exist: {path}')
                            continue
                        try:
                            file_group = FileGroup.from_paths(session, *glob_shared_stem(absolute_path))
                        except NoPrimaryFile:
                            logger.warning(f'Cannot import recently viewed file: {path}')
                            continue
                        session.add(file_group)
                        session.flush([file_group])
                        file_groups_by_path[absolute_path] = file_group

                    if file_group.viewed and file_group.viewed >= viewed:
                        continue
                    file_group.viewed = viewed
                    file_group.progress = progress
                    file_group.position = position
                    applied += 1

            logger.info(f'Imported {applied} of {len(entries)} recently viewed files')
            self.successful_import = True
        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {self.get_relative_file()} config'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_import_failed(message)
            raise


RECENTLY_VIEWED_CONFIG: RecentlyViewedConfig = RecentlyViewedConfig()


def get_recently_viewed_config() -> RecentlyViewedConfig:
    return RECENTLY_VIEWED_CONFIG


@register_switch_handler('save_recently_viewed_config')
def save_recently_viewed_config():
    get_recently_viewed_config().dump_config()


save_recently_viewed_config: ActivateSwitchMethod
