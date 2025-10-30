"""
Collection API Schemas

Request and response schemas for the unified collection API endpoints.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CollectionUpdateRequest:
    """Request body for updating a collection."""
    directory: Optional[str] = None
    tag_name: Optional[str] = None
    description: Optional[str] = None


@dataclass
class CollectionTagRequest:
    """Request body for tagging a collection."""
    tag_name: Optional[str] = None
    directory: Optional[str] = None


@dataclass
class CollectionSearchRequest:
    """Request body for searching collections."""
    kind: Optional[str] = None
    tag_names: List[str] = field(default_factory=list)
    search_str: Optional[str] = None


@dataclass
class CollectionTagResponse:
    """Response for tagging operation."""
    collection_id: int
    collection_name: str
    tag_name: str
    directory: str
    will_move_files: bool


@dataclass
class CollectionTagInfoRequest:
    """Request body for getting tag info."""
    tag_name: Optional[str] = None


@dataclass
class CollectionTagInfoResponse:
    """Response for tag info operation."""
    suggested_directory: str
    conflict: bool
    conflict_message: Optional[str] = None
