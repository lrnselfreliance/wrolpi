import dataclasses
from typing import Optional


@dataclasses.dataclass
class AISearchRequest:
    search_str: Optional[str] = None
    limit: int = 5
    offset: int = 0
    mimetypes: Optional[list] = None
    tag_names: Optional[list] = None


@dataclasses.dataclass
class AIVideoSearchRequest:
    search_str: Optional[str] = None
    limit: int = 5
    offset: int = 0
    channel_id: Optional[int] = None
    tag_names: Optional[list] = None


@dataclasses.dataclass
class AIArchiveSearchRequest:
    search_str: Optional[str] = None
    limit: int = 5
    offset: int = 0
    domain: Optional[str] = None
    tag_names: Optional[list] = None


@dataclasses.dataclass
class AIDocSearchRequest:
    search_str: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    language: Optional[str] = None
    mimetype: Optional[str] = None
    limit: int = 5
    offset: int = 0
    tag_names: Optional[list] = None


@dataclasses.dataclass
class AIZimSearchRequest:
    search_str: Optional[str] = None
    zim_id: Optional[int] = None
    limit: int = 5
    offset: int = 0


@dataclasses.dataclass
class AIHelpSearchRequest:
    search_str: Optional[str] = None
    limit: int = 5


@dataclasses.dataclass
class AISearchResponse:
    results: list = dataclasses.field(default_factory=list)
    total: int = 0


@dataclasses.dataclass
class AIPagedTextResponse:
    content: str = ''
    next_offset: Optional[int] = None
    total_chars: int = 0
