from dataclasses import dataclass


@dataclass
class ConfigsRequest:
    file_name: str
    overwrite: bool = False


@dataclass
class ConfigUpdateRequest:
    config: dict


@dataclass
class ConfigBackupPreviewRequest:
    file_name: str
    backup_date: str
    mode: str


@dataclass
class ConfigBackupImportRequest:
    file_name: str
    backup_date: str
    mode: str
