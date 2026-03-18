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


@dataclasses.dataclass
class DocSearchResponse:
    file_groups: list = dataclasses.field(default_factory=list)
    totals: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class DocStatistics:
    doc_count: int = 0
    epub_count: int = 0
    pdf_count: int = 0
    other_count: int = 0
    total_size: int = 0
    author_count: int = 0
    subject_count: int = 0


@dataclasses.dataclass
class DocStatisticsResponse:
    statistics: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class DocFileFormatRequest:
    name: str = ''
    model_tag: str = 'docs'
