from dataclasses import dataclass, field
from datetime import datetime
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
    archive_datetime: datetime


@dataclass
class DomainDict:
    id: int
    domain: str


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
