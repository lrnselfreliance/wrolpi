import dataclasses
from typing import Optional


@dataclasses.dataclass
class DocSearchRequest:
    search_str: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    language: Optional[str] = None
    mimetype: Optional[str] = None
    tag_names: Optional[list] = dataclasses.field(default_factory=list)
    order_by: Optional[str] = 'published_datetime'
    limit: int = 20
    offset: int = 0
    deep: bool = False  # When True, search all text including document contents (d_text)


@dataclasses.dataclass
class DocSearchResponse:
    file_groups: list = dataclasses.field(default_factory=list)
    totals: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class DocStatisticsResponse:
    statistics: dict = dataclasses.field(default_factory=dict)
