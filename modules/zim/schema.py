from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class ZimSearchRequest:
    search_str: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    offset: Optional[int] = 0
    limit: Optional[int] = 10


@dataclass
class ZimAutoSearchRequest:
    auto_search: bool


@dataclass
class ZimMetadata:
    path: str
    creator: str
    description: str
    name: str
    publisher: str
    tags: str
    title: str


@dataclass
class Zim:
    id: int
    path: str
    file_group_id: int
    metadata: ZimMetadata
    size: int


@dataclass
class GetZimsResponse:
    zims: List[Zim]


@dataclass
class ZimSearchHeadline:
    headline: str
    rank: float


@dataclass
class ZimSearchResult:
    path: str
    metadata: ZimMetadata
    search: List[ZimSearchHeadline]


@dataclass
class ZimSearchResponse:
    zim: ZimSearchResult


@dataclass
class TagZimEntry:
    tag_name: str
    zim_id: int
    zim_entry: str


@dataclass
class ZimSubscription:
    id: int
    name: str
    language: str
    download_id: int
    download_url: str


@dataclass
class ZimProject:
    name: str
    languages: List[str]
    size: int


@dataclass
class ZimSubscriptions:
    subscriptions: Dict[str, ZimSubscription]
    catalog: List[ZimProject]
    iso_639_codes: Dict[str, str]


@dataclass
class ZimSubscribeRequest:
    name: str
    language: str


@dataclass
class OutdatedZims:
    outdated: List[str]
    current: List[str]


@dataclass
class SearchEstimateRequest:
    search_str: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    any_tag: bool = False
