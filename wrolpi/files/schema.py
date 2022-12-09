from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FilesRequest:
    directories: List[str] = field(default_factory=list)


@dataclass
class DeleteRequest:
    file: str


@dataclass
class FilesSearchRequest:
    search_str: Optional[str] = None
    limit: Optional[int] = 20
    offset: Optional[int] = 0
    mimetypes: List[str] = field(default_factory=list)
    model: Optional[str] = None


@dataclass
class DirectoryRefreshRequest:
    directory: str = None


@dataclass
class FilesRefreshListRequest:
    files: List[str] = None
    include_files_near: bool = True


@dataclass
class DirectoriesRequest:
    search_str: Optional[str] = ''


@dataclass
class DirectoriesResponse:
    directories: List[str]
