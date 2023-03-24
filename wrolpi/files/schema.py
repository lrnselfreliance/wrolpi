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
    tag_names: List[str] = field(default_factory=list)


@dataclass
class FilesRefreshRequest:
    paths: Optional[List[str]] = None


@dataclass
class DirectoriesRequest:
    search_str: Optional[str] = ''


@dataclass
class DirectoriesResponse:
    directories: List[str]


@dataclass
class TagFileGroupPost:
    file_group_id: int
    tag_name: str
