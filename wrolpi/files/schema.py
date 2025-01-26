from dataclasses import dataclass, field
from typing import List, Optional

from wrolpi.errors import ValidationError


@dataclass
class FilesRequest:
    directories: List[str] = field(default_factory=list)


@dataclass
class FileRequest:
    file: str


@dataclass
class DeleteRequest:
    paths: List[str] = field(default_factory=list)


@dataclass
class FilesSearchRequest:
    search_str: Optional[str] = None
    limit: Optional[int] = 20
    offset: Optional[int] = 0
    mimetypes: List[str] = field(default_factory=list)
    model: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    headline: bool = False
    months: Optional[List[int]] = None
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    any_tag: bool = False
    order: Optional[str] = None

    def __post_init__(self):
        if self.any_tag and self.tag_names:
            raise ValidationError('Cannot use both tag_names and any_tag.')


@dataclass
class FilesRefreshRequest:
    paths: Optional[List[str]] = None


@dataclass
class DirectoriesRequest:
    search_str: Optional[str] = ''


@dataclass
class DirectoriesSearchRequest:
    path: str


@dataclass
class DirectoriesResponse:
    directories: List[str]


@dataclass
class TagFileGroupPost:
    tag_name: Optional[str] = None
    tag_id: Optional[int] = None
    file_group_id: Optional[int] = None
    file_group_primary_path: Optional[str] = None


@dataclass
class Directory:
    path: str


@dataclass
class Move:
    destination: str
    paths: List[str] = field(default_factory=list)


@dataclass
class Rename:
    path: str
    new_name: str
