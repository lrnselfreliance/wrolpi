from dataclasses import dataclass
from typing import List, Optional

from wrolpi.errors import ValidationError


@dataclass
class SyncDirectoriesRequest:
    # The folder whose sub-folders are listed, relative to the media directory ('' is the media directory).
    path: str = ''
    # 'local' lists this WROLPi's media directory, 'primary' lists its primary's.
    source: str = 'local'

    def __post_init__(self):
        if self.source not in ('local', 'primary'):
            raise ValidationError("source must be 'local' or 'primary'")


@dataclass
class SyncSettingsRequest:
    role: Optional[str] = None
    sync_primary_url: Optional[str] = None
    sync_window_start: Optional[str] = None
    sync_window_end: Optional[str] = None
    # The mount point of the backup drive, and the UUID of the drive that must be mounted there ('' clears both).
    backup_directory: Optional[str] = None
    backup_device_uuid: Optional[str] = None
    backup_window_start: Optional[str] = None
    backup_window_end: Optional[str] = None
    # Days a secondary keeps a file its primary deleted or replaced; -1 never deletes.
    sync_delete_after_days: Optional[int] = None
    # Days the backup drive keeps a file deleted or replaced in the media directory; -1 never deletes.
    backup_delete_after_days: Optional[int] = None
    # Folders, relative to the media directory, never copied ([] clears).
    sync_excluded_directories: Optional[List[str]] = None
    backup_excluded_directories: Optional[List[str]] = None

    def __post_init__(self):
        if self.role is not None and self.role not in ('primary', 'secondary'):
            raise ValidationError('role must be "primary" or "secondary"')
        for key in ('sync_delete_after_days', 'backup_delete_after_days'):
            if (value := getattr(self, key)) is not None and not -1 <= int(value) <= 3650:
                raise ValidationError(f'{key} must be between 0 and 3650, or -1 to never delete')
