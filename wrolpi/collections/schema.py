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


@dataclass
class ConflictFileInfo:
    """Info about a single file in a reorganization conflict."""
    file_group_id: int
    current_path: str
    title: str
    model_type: str  # 'video' or 'archive'
    size: int = 0
    video_id: Optional[int] = None
    archive_id: Optional[int] = None
    poster_path: Optional[str] = None
    published_datetime: Optional[str] = None
    source_id: Optional[str] = None
    quality_rank: Optional[int] = None  # Metadata quality score (videos only)


@dataclass
class ConflictDetail:
    """Details about a single destination path conflict."""
    destination_path: str
    conflicting_files: List[ConflictFileInfo]


@dataclass
class ReorganizationPreviewResponse:
    """Response for reorganization preview."""
    collection_id: int
    collection_name: str
    total_files: int
    files_needing_move: int
    sample_moves: List[dict]
    new_file_format: str
    current_file_format: Optional[str] = None
    conflicts: List[ConflictDetail] = field(default_factory=list)
    has_conflicts: bool = False


@dataclass
class ReorganizationExecuteResponse:
    """Response for reorganization execution."""
    job_id: str
    message: str


@dataclass
class ReorganizationStatusResponse:
    """Response for reorganization status."""
    status: str
    total: int
    completed: int
    percent: int
    error: Optional[str] = None


# ============================================================================
# Batch Reorganization Schemas
# ============================================================================


@dataclass
class BatchCollectionInfo:
    """Info about a single collection in batch reorganization."""
    collection_id: int
    collection_name: str
    total_files: int
    files_needing_move: int
    sample_move: Optional[dict] = None


@dataclass
class BatchReorganizationListResponse:
    """Response for listing collections needing batch reorganization."""
    collections: List[dict]
    total_collections: int
    total_files_needing_move: int
    new_file_format: str


@dataclass
class BatchReorganizationExecuteResponse:
    """Response for executing batch reorganization."""
    batch_job_id: str
    message: str
    collection_count: int


@dataclass
class BatchCollectionProgress:
    """Progress info for a single collection in batch reorganization."""
    id: int
    name: str
    status: str
    total: int = 0
    completed: int = 0
    percent: int = 0


@dataclass
class BatchReorganizationStatusResponse:
    """Response for batch reorganization status."""
    status: str
    total_collections: int
    completed_collections: int
    current_collection: Optional[dict]
    overall_percent: int
    completed: List[dict]
    failed_collection: Optional[dict]
    error: Optional[str] = None
