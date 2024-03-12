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
class DomainDict:
    domain: str
    url_count: int
    size: int


@dataclass
class GetDomainsResponse:
    domains: List[DomainDict]


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
