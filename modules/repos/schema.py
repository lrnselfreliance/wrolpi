from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class RepoCreateRequest:
    url: str
    # Relative to the media directory; empty clones it into the Repos directory.
    directory: Optional[str] = None
    tag_name: Optional[str] = None
    frequency: Optional[int] = None
    mode: Optional[str] = None
    branch: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    submodules: bool = False


@dataclass
class RepoSearchRequest:
    search_str: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    limit: int = 20
    offset: int = 0


@dataclass
class RepoUpdateRequest:
    description: Optional[str] = None
    frequency: Optional[int] = None
    mode: Optional[str] = None
    branch: Optional[str] = None
    submodules: Optional[bool] = None


@dataclass
class RepoImportInspectRequest:
    directory: str
    name: Optional[str] = None
    tag_name: Optional[str] = None
    url: Optional[str] = None


@dataclass
class RepoImportRequest:
    directory: str
    confirm: bool = False
    url: Optional[str] = None
    tag_name: Optional[str] = None
    frequency: Optional[int] = None
    mode: Optional[str] = None
    branch: Optional[str] = None
    submodules: bool = False
    name: Optional[str] = None
    description: Optional[str] = None
