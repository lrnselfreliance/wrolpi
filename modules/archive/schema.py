from dataclasses import dataclass, field
from typing import List, Optional


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
