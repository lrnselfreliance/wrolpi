from dataclasses import dataclass
from typing import Optional

from wrolpi.errors import ValidationError


@dataclass
class ManifestRequest:
    after_id: int = 0
    limit: int = 500

    def __post_init__(self):
        self.after_id = int(self.after_id)
        self.limit = int(self.limit)
        if self.after_id < 0:
            raise ValidationError('after_id must not be negative')
        if not 1 <= self.limit <= 5000:
            raise ValidationError('limit must be between 1 and 5000')


@dataclass
class SyncRunRequest:
    # Import every synced config even if the primary's copy did not change.
    force: bool = False


@dataclass
class SyncSettingsRequest:
    role: Optional[str] = None
    sync_primary_url: Optional[str] = None
    sync_window_start: Optional[str] = None
    sync_window_end: Optional[str] = None
    # The mount point of the backup drive, and the UUID of the drive that must be mounted there ('' clears both).
    backup_directory: Optional[str] = None
    backup_device_uuid: Optional[str] = None

    def __post_init__(self):
        if self.role is not None and self.role not in ('primary', 'secondary'):
            raise ValidationError('role must be "primary" or "secondary"')
