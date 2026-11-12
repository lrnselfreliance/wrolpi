import dataclasses
from typing import Optional

from wrolpi.errors import ValidationError


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
    any_tag: bool = False  # When True, only Docs with at least one Tag.

    def __post_init__(self):
        if self.any_tag and self.tag_names:
            raise ValidationError('Cannot use both tag_names and any_tag.')


@dataclasses.dataclass
class DocSearchResponse:
    file_groups: list = dataclasses.field(default_factory=list)
    totals: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class DocStatisticsResponse:
    statistics: dict = dataclasses.field(default_factory=dict)
