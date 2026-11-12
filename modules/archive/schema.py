from dataclasses import dataclass, field
from typing import List, Optional

from wrolpi.errors import ValidationError


@dataclass
class ArchiveDict:
    id: int
    url_id: int
    domain_id: int
    singlefile_path: str
    readability_path: str
    readability_json_path: str
    readability_txt_path: str
    screenshot_path: str
    title: str


@dataclass
class ArchiveSearchRequest:
    search_str: Optional[str] = None
    domain: Optional[str] = None
    offset: Optional[int] = None
    limit: Optional[int] = None
    order_by: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    headline: bool = False
    deep: bool = False  # When True, search all text including page contents (d_text)
    any_tag: bool = False  # When True, only Archives with at least one Tag.

    def __post_init__(self):
        if self.any_tag and self.tag_names:
            raise ValidationError('Cannot use both tag_names and any_tag.')


@dataclass
class ArchiveSearchResponse:
    file_groups: List[ArchiveDict]
    totals: dict


@dataclass
class ArchiveFileFormatRequest:
    archive_file_format: str


@dataclass
class ArchiveStatistics:
    archives: int
    week: int
    month: int
    year: int
    sum_size: int
    max_size: int


@dataclass
class DomainStatistics:
    domains: int
    tagged_domains: int


@dataclass
class ArchiveStatisticsResponse:
    archives: ArchiveStatistics
    domains: DomainStatistics
