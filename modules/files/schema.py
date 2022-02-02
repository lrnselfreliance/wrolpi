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
    search_str: str
    limit: Optional[int] = 20
    offset: Optional[int] = 0
