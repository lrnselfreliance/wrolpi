"""
Collection Reorganization Module

Provides functionality to reorganize files within Collections (Domains/Channels)
when the file_name_format config changes.

Example: User changes archive format from '%(title)s.%(ext)s' to '%(download_year)s/%(title)s.%(ext)s'
- Before: 'My Article.html'
- After: '2025/My Article.html'
"""
import pathlib
from dataclasses import dataclass
from typing import List, Tuple, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from wrolpi.common import logger, get_media_directory
from wrolpi.db import get_db_session
from wrolpi.files.lib import glob_shared_stem
from .errors import UnknownCollection
from .models import Collection

logger = logger.getChild(__name__)

__all__ = [
    'BatchReorganizationPreview',
    'ReorganizationPreview',
    'execute_batch_reorganization',
    'execute_reorganization',
    'get_batch_reorganization_preview',
    'get_batch_reorganization_status',
    'get_collections_needing_reorganization',
    'get_conflict_details_with_ffprobe',
    'get_reorganization_preview',
]

# Quality ranking weights for conflict resolution
# High-value metadata indicators (more rare/valuable)
RANK_HIGH_VALUE = 2
# Standard metadata indicators (more common)
RANK_STANDARD = 1


@dataclass
class ReorganizationPreview:
    """Preview of a collection reorganization operation.

    Note: For performance reasons, files_needing_move equals total_files.
    We assume all files need moving since computing actual moves for every
    file is expensive and would defeat the purpose of this preview.
    """
    collection_id: int
    collection_name: str
    total_files: int  # Total FileGroups in collection
    files_needing_move: int  # Equals total_files (assumed all need moving)
    sample_moves: List[dict]  # Sample of moves: [{old_path, new_path}, ...]
    new_file_format: str  # The format that will be applied
    current_file_format: Optional[str]  # The format currently stored on collection
    conflicts: List[dict] = None  # Destination conflicts with file details
    has_conflicts: bool = False  # Quick flag indicating if conflicts exist


@dataclass
class BatchReorganizationPreview:
    """Lightweight preview for batch overview - no conflict detection.

    Used by get_collections_needing_reorganization() for fast batch previews.
    For individual collection modals where conflict details are needed,
    use ReorganizationPreview via get_reorganization_preview() instead.

    Includes one sample_move to show users what the reorganization will do,
    but skips expensive full-mapping computation and conflict detection.
    """
    collection_id: int
    collection_name: str
    total_files: int
    files_needing_move: int
    new_file_format: str
    current_file_format: Optional[str] = None
    sample_move: Optional[dict] = None  # Single sample: {old_path, new_path}


def _get_format_required_variables(file_format: str) -> set:
    """Parse a format string and return the set of variable names it uses.

    Example: '%(upload_year)s/%(title)s.%(ext)s' -> {'upload_year', 'title', 'ext'}
    """
    import re
    # Match %(variable_name)s patterns
    return set(re.findall(r'%\(([^)]+)\)s', file_format))


def _video_has_required_metadata(video, file_format: str) -> bool:
    """Check if video has the metadata required by the format string.

    Returns False only if the format requires a variable that the video cannot provide.
    Uses get_video_metadata() for consistent fallback chain with format_video_filename().
    """
    from modules.videos.lib import get_video_metadata

    required = _get_format_required_variables(file_format)
    metadata = get_video_metadata(video)

    has_upload_date = bool(metadata['upload_date'])
    has_source_id = bool(metadata['source_id'])
    has_uploader = bool(metadata['uploader'])

    # Map format variables to their metadata availability
    # Variables that depend on upload_date
    date_vars = {'upload_year', 'upload_month', 'upload_date', 'upload_date>%Y', 'upload_date>%m'}
    # Variables that depend on source_id
    id_vars = {'id'}
    # Variables that depend on uploader
    uploader_vars = {'uploader', 'channel'}

    for var in required:
        if var in date_vars and not has_upload_date:
            return False
        if var in id_vars and not has_source_id:
            return False
        if var in uploader_vars and not has_uploader:
            return False

    return True


def _compute_new_path_for_video(
        video,
        collection_directory: pathlib.Path,
        file_format: str = None,
) -> Optional[pathlib.Path]:
    """Compute the new path for a video based on current config.

    Args:
        video: Video model instance
        collection_directory: Base directory for the collection
        file_format: Optional format string override, defaults to config value

    Returns None if the video lacks required metadata for the configured format.
    """
    from modules.videos.lib import format_video_filename, get_videos_downloader_config

    if file_format is None:
        config = get_videos_downloader_config()
        file_format = config.file_name_format

    if not _video_has_required_metadata(video, file_format):
        logger.info(f'Skipping video {video.id}: missing metadata required by format "{file_format}"')
        return None
    try:
        new_filename = format_video_filename(video, file_format)
        return collection_directory / new_filename
    except Exception as e:
        logger.warning(f'Failed to compute new path for video {video.id}: {e}')
        return None


def _archive_has_required_metadata(archive, file_format: str) -> bool:
    """Check if archive has the metadata required by the format string.

    Returns False only if the format requires a variable that the archive cannot provide.
    Archives have robust fallbacks for most variables (dates fallback to now(),
    title to 'untitled'). Only domain can be empty when URL is missing.
    """
    required = _get_format_required_variables(file_format)

    file_group = archive.file_group

    # Domain requires a URL
    has_domain = bool(file_group.url)

    # Domain-related variables
    domain_vars = {'domain'}

    for var in required:
        if var in domain_vars and not has_domain:
            return False

    # All other variables (title, download_*, ext) always have fallbacks
    return True


def _compute_new_path_for_archive(
        archive,
        collection_directory: pathlib.Path,
        file_format: str = None,
) -> Optional[pathlib.Path]:
    """Compute the new path for an archive based on current config.

    Args:
        archive: Archive model instance
        collection_directory: Base directory for the collection
        file_format: Optional format string override, defaults to config value

    Returns None if the archive lacks required metadata for the configured format.
    """
    from modules.archive.lib import format_archive_filename_from_archive, get_archive_downloader_config

    if file_format is None:
        config = get_archive_downloader_config()
        file_format = config.file_name_format

    if not _archive_has_required_metadata(archive, file_format):
        logger.info(f'Skipping archive {archive.id}: missing metadata required by format "{file_format}"')
        return None

    try:
        new_filename = format_archive_filename_from_archive(archive, file_format)
        return collection_directory / new_filename
    except Exception as e:
        logger.warning(f'Failed to compute new path for archive {archive.id}: {e}')
        return None


def get_reorganization_preview(
        collection_id: int,
        session: Session = None,
        sample_size: int = 10,
) -> ReorganizationPreview:
    """Get preview with sample of files to be renamed and detect conflicts.

    Builds full move mappings to detect destination conflicts.

    Args:
        collection_id: The collection to preview reorganization for
        session: Database session (optional, will create one if not provided)
        sample_size: Number of sample moves to include in preview

    Returns:
        ReorganizationPreview with counts, sample moves, and conflict details

    Raises:
        UnknownCollection: If collection not found
    """
    if session is None:
        with get_db_session() as session:
            return get_reorganization_preview(collection_id, session, sample_size)

    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    if not collection.directory:
        raise ValueError(f"Collection '{collection.name}' has no directory. Cannot reorganize.")

    # Get the current file format from config
    current_config_format = collection._get_current_file_format()

    sample_moves = []
    files_needing_move = 0
    total_files = 0

    move_mappings = []

    if collection.kind == 'channel':
        from modules.videos.models import Video, Channel

        # Get the channel for this collection
        channel = session.query(Channel).filter_by(collection_id=collection_id).one_or_none()
        if not channel:
            return ReorganizationPreview(
                collection_id=collection_id,
                collection_name=collection.name,
                total_files=0,
                files_needing_move=0,
                sample_moves=[],
                new_file_format=current_config_format or '',
                current_file_format=collection.file_format,
                conflicts=[],
                has_conflicts=False,
            )

        # Use COUNT for total_files (fast)
        total_files = session.query(func.count(Video.id)).filter_by(channel_id=channel.id).scalar()

        # Always build full move mappings (needed for conflict detection)
        move_mappings = _build_move_mappings_for_channel(collection, session)
        files_needing_move = len(move_mappings)

        # Build sample moves from the first N mappings
        media_dir = get_media_directory()
        for source_path, dest_path in move_mappings[:sample_size]:
            try:
                old_relative = str(source_path.relative_to(media_dir))
            except ValueError:
                old_relative = str(source_path)
            try:
                new_relative = str(dest_path.relative_to(media_dir))
            except ValueError:
                new_relative = str(dest_path)

            sample_moves.append({
                'old_path': old_relative,
                'new_path': new_relative,
            })

    elif collection.kind == 'domain':
        from modules.archive.models import Archive

        # Use COUNT for total_files (fast)
        total_files = session.query(func.count(Archive.id)).filter_by(collection_id=collection_id).scalar()

        # Always build full move mappings (needed for conflict detection)
        move_mappings = _build_move_mappings_for_domain(collection, session)
        files_needing_move = len(move_mappings)

        # Build sample moves from the first N mappings
        media_dir = get_media_directory()
        for source_path, dest_path in move_mappings[:sample_size]:
            try:
                old_relative = str(source_path.relative_to(media_dir))
            except ValueError:
                old_relative = str(source_path)
            try:
                new_relative = str(dest_path.relative_to(media_dir))
            except ValueError:
                new_relative = str(dest_path)

            sample_moves.append({
                'old_path': old_relative,
                'new_path': new_relative,
            })

    # Detect conflicts
    conflicts = _detect_conflicts_with_details(move_mappings, collection, session)

    return ReorganizationPreview(
        collection_id=collection_id,
        collection_name=collection.name,
        total_files=total_files,
        files_needing_move=files_needing_move,
        sample_moves=sample_moves,
        new_file_format=current_config_format or '',
        current_file_format=collection.file_format,
        conflicts=conflicts,
        has_conflicts=len(conflicts) > 0,
    )


def get_batch_reorganization_preview(
        collection_id: int,
        session: Session,
) -> BatchReorganizationPreview:
    """Get a lightweight preview for batch context - skips expensive conflict detection.

    Use this for the batch overview page where we need fast counts for many collections.
    For individual collection modals where conflict details are needed,
    use get_reorganization_preview() instead.

    Computes ONE sample move to show users what will happen, but avoids computing
    moves for ALL files (which is the expensive part).

    Args:
        collection_id: The collection to preview
        session: Database session

    Returns:
        BatchReorganizationPreview with counts and one sample move (no conflicts)

    Raises:
        UnknownCollection: If collection not found
    """
    from sqlalchemy.orm import joinedload

    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Get the current file format from config
    current_config_format = collection._get_current_file_format()

    collection_directory = pathlib.Path(collection.directory)
    if not collection_directory.is_absolute():
        collection_directory = get_media_directory() / collection_directory

    total_files = 0
    sample_move = None
    media_dir = get_media_directory()

    if collection.kind == 'channel':
        from modules.videos.models import Video, Channel

        # Get the channel for this collection
        channel = session.query(Channel).filter_by(collection_id=collection_id).one_or_none()
        if channel:
            # Fast COUNT query - no joins, no loading of related objects
            total_files = session.query(func.count(Video.id)).filter_by(channel_id=channel.id).scalar() or 0

            # Get ONE video for sample move (cheap - just one query with limit 1)
            sample_video = session.query(Video).options(
                joinedload(Video.file_group)
            ).filter_by(channel_id=channel.id).first()

            if sample_video and sample_video.file_group and sample_video.file_group.primary_path:
                current_path = pathlib.Path(sample_video.file_group.primary_path)
                new_path = _compute_new_path_for_video(sample_video, collection_directory)
                # Compare resolved paths to handle symlinks and path normalization
                if new_path and current_path.resolve() != new_path.resolve():
                    try:
                        old_relative = str(current_path.relative_to(media_dir))
                    except ValueError:
                        old_relative = str(current_path)
                    try:
                        new_relative = str(new_path.relative_to(media_dir))
                    except ValueError:
                        new_relative = str(new_path)
                    sample_move = {'old_path': old_relative, 'new_path': new_relative}

    elif collection.kind == 'domain':
        from modules.archive.models import Archive

        # Fast COUNT query
        total_files = session.query(func.count(Archive.id)).filter_by(collection_id=collection_id).scalar() or 0

        # Get ONE archive for sample move (cheap - just one query with limit 1)
        sample_archive = session.query(Archive).options(
            joinedload(Archive.file_group)
        ).filter_by(collection_id=collection_id).first()

        if sample_archive and sample_archive.file_group and sample_archive.file_group.primary_path:
            current_path = pathlib.Path(sample_archive.file_group.primary_path)
            new_path = _compute_new_path_for_archive(sample_archive, collection_directory)
            # Compare resolved paths to handle symlinks and path normalization
            if new_path and current_path.resolve() != new_path.resolve():
                try:
                    old_relative = str(current_path.relative_to(media_dir))
                except ValueError:
                    old_relative = str(current_path)
                try:
                    new_relative = str(new_path.relative_to(media_dir))
                except ValueError:
                    new_relative = str(new_path)
                sample_move = {'old_path': old_relative, 'new_path': new_relative}

    # For batch preview, assume all files need moving if collection needs reorganization
    # This avoids expensive _build_move_mappings calls
    files_needing_move = total_files if collection.needs_reorganization else 0

    return BatchReorganizationPreview(
        collection_id=collection_id,
        collection_name=collection.name,
        total_files=total_files,
        files_needing_move=files_needing_move,
        new_file_format=current_config_format or '',
        current_file_format=collection.file_format,
        sample_move=sample_move,
    )


def _build_move_mappings_for_channel(
        collection: Collection,
        session: Session,
) -> List[Tuple[pathlib.Path, pathlib.Path]]:
    """Build move mappings for a channel collection."""
    from modules.videos.models import Video, Channel

    collection_directory = pathlib.Path(collection.directory)
    if not collection_directory.is_absolute():
        collection_directory = get_media_directory() / collection_directory

    channel = session.query(Channel).filter_by(collection_id=collection.id).one_or_none()
    if not channel:
        return []

    move_mappings = []
    videos = session.query(Video).options(
        joinedload(Video.file_group)
    ).filter_by(channel_id=channel.id).all()

    for video in videos:
        if not video.file_group or not video.file_group.primary_path:
            continue

        current_path = pathlib.Path(video.file_group.primary_path)
        new_path = _compute_new_path_for_video(video, collection_directory)

        # Compare resolved paths to handle symlinks and path normalization
        if new_path and current_path.resolve() != new_path.resolve():
            move_mappings.append((current_path, new_path))

    return move_mappings


def _build_move_mappings_for_domain(
        collection: Collection,
        session: Session,
) -> List[Tuple[pathlib.Path, pathlib.Path]]:
    """Build move mappings for a domain collection."""
    from modules.archive.models import Archive

    collection_directory = pathlib.Path(collection.directory)
    if not collection_directory.is_absolute():
        collection_directory = get_media_directory() / collection_directory

    move_mappings = []
    archives = session.query(Archive).options(
        joinedload(Archive.file_group)
    ).filter_by(collection_id=collection.id).all()

    for archive in archives:
        if not archive.file_group or not archive.file_group.primary_path:
            continue

        current_path = pathlib.Path(archive.file_group.primary_path)
        new_path = _compute_new_path_for_archive(archive, collection_directory)

        # Compare resolved paths to handle symlinks and path normalization
        if new_path and current_path.resolve() != new_path.resolve():
            move_mappings.append((current_path, new_path))

    return move_mappings


def _get_largest_sizes_by_source_id(videos: list) -> dict:
    """Get the largest file size for each source_id among a set of videos.

    Videos that are larger are probably better quality, so larger videos get a rank bonus.
    """
    sizes = {}
    for video in videos:
        source_id = video.source_id
        if not source_id:
            continue
        old_size = sizes.get(source_id, 0)
        file_size = video.file_group.size if video.file_group else 0
        sizes[source_id] = max(old_size, file_size)
    return sizes


def _rank_video_quality(video, sizes_by_source_id: dict) -> int:
    """Returns a higher integer the more data and metadata the Video record is.

    A video with info_json is more valuable than one without, etc.
    Adapted from scripts/delete_similarly_named_videos.py.

    Uses RANK_HIGH_VALUE for rare/valuable metadata and RANK_STANDARD for common metadata.
    """
    from modules.videos.lib import parse_video_file_name

    rank = 0
    file_group = video.file_group

    # High-value metadata (rare/valuable indicators)
    if file_group and file_group.url:
        rank += RANK_HIGH_VALUE
    if video.source_id:
        rank += RANK_HIGH_VALUE
    if video.info_json_path and video.info_json_path.is_file():
        try:
            if video.info_json_path.stat().st_size > 0:
                rank += RANK_HIGH_VALUE
        except (OSError, IOError):
            pass
    # Check if video file matches channel info_json
    if video.source_id and video.channel:
        try:
            if entry := video.get_channel_entry():
                if entry.get('title') and entry['title'] in str(video.video_path):
                    rank += RANK_HIGH_VALUE
        except Exception:
            pass
    if video.get_comments():
        rank += RANK_HIGH_VALUE

    # Standard metadata (more common indicators)
    if video.channel_id:
        rank += RANK_STANDARD
    if video.caption_paths:
        rank += RANK_STANDARD
    if video.poster_path and video.poster_path.is_file():
        try:
            if video.poster_path.stat().st_size > 0:
                rank += RANK_STANDARD
        except (OSError, IOError):
            pass
    if video.ffprobe_json:
        rank += RANK_STANDARD

    # Largest file for source_id gets a bonus
    if video.source_id:
        largest_size = sizes_by_source_id.get(video.source_id)
        if largest_size and file_group and file_group.size == largest_size:
            rank += RANK_STANDARD

    # Title from JSON matches filename
    if video.video_path:
        try:
            _, _, _, video_title = parse_video_file_name(video.video_path)
            video_title = video_title.strip() if video_title else ''
            if file_group and file_group.title and file_group.title == video_title:
                rank += RANK_STANDARD
        except Exception:
            pass

    # Channel name in video path
    if video.channel_id and video.channel:
        try:
            channel_name = None
            if video.channel.info_json:
                channel_name = video.channel.info_json.get('channel')
            if channel_name and channel_name in str(video.video_path):
                rank += RANK_HIGH_VALUE
        except Exception:
            pass

    # Precise published datetime (not midnight) indicates better metadata
    if file_group and file_group.published_datetime:
        dt = file_group.published_datetime
        # Check if time is not midnight (has actual time precision)
        if dt.hour != 0 or dt.minute != 0 or dt.second != 0:
            rank += RANK_STANDARD

    # Bonus for videos with audio
    if video.ffprobe_json:
        if video.get_streams_by_codec_type('audio'):
            rank += RANK_HIGH_VALUE

    return rank


def _rank_archive_quality(archive) -> int:
    """Returns a higher integer the more quality the Archive record is.

    Archives with more complete metadata (readability files, timestamps,
    extracted content) receive higher ranks.

    Uses RANK_HIGH_VALUE for rare/valuable metadata and RANK_STANDARD for common metadata.
    """
    rank = 0
    file_group = archive.file_group

    # High-value metadata (rare/valuable indicators)
    if archive.readability_json_path and archive.readability_json_path.is_file():
        rank += RANK_HIGH_VALUE
    if file_group and file_group.url:
        rank += RANK_HIGH_VALUE

    # Standard metadata (more common indicators)
    if archive.readability_path and archive.readability_path.is_file():
        rank += RANK_STANDARD
    if archive.readability_txt_path and archive.readability_txt_path.is_file():
        rank += RANK_STANDARD
    if archive.screenshot_path and archive.screenshot_path.is_file():
        rank += RANK_STANDARD
    if file_group:
        if file_group.title:
            rank += RANK_STANDARD
        if file_group.author:
            rank += RANK_STANDARD
        if file_group.published_datetime:
            rank += RANK_STANDARD
        if file_group.download_datetime:
            rank += RANK_STANDARD
        if file_group.published_modified_datetime:
            rank += RANK_STANDARD
        if file_group.b_text:  # description
            rank += RANK_STANDARD
        if file_group.d_text:  # extracted article text
            rank += RANK_STANDARD
        if file_group.length and file_group.length > 0:
            rank += RANK_STANDARD
        # Precise published datetime (not midnight)
        if file_group.published_datetime:
            dt = file_group.published_datetime
            if dt.hour != 0 or dt.minute != 0 or dt.second != 0:
                rank += RANK_STANDARD

    return rank


def _check_for_destination_conflicts(
        move_mappings: List[Tuple[pathlib.Path, pathlib.Path]],
        collection_name: str,
) -> None:
    """Check for duplicate destination paths in move mappings.

    Raises:
        ReorganizationConflict: If two or more files would move to the same destination
    """
    from wrolpi.collections.errors import ReorganizationConflict

    dest_to_sources = {}
    for source, dest in move_mappings:
        if dest in dest_to_sources:
            dest_to_sources[dest].append(source)
        else:
            dest_to_sources[dest] = [source]

    conflicts = {dest: sources for dest, sources in dest_to_sources.items() if len(sources) > 1}

    if conflicts:
        conflict_details = []
        for dest, sources in conflicts.items():
            source_names = [str(s.name) for s in sources]
            conflict_details.append(f"  {dest.name} <- {', '.join(source_names)}")

        raise ReorganizationConflict(
            f"Reorganization of '{collection_name}' would cause {len(conflicts)} filename conflict(s):\n" +
            "\n".join(conflict_details)
        )


def _detect_conflicts_with_details(
        move_mappings: List[Tuple[pathlib.Path, pathlib.Path]],
        collection: Collection,
        session: Session,
) -> List[dict]:
    """Detect destination conflicts and return detailed info for UI display.

    Returns a list of conflict details, where each conflict contains:
    - destination_path: The path where multiple files would end up
    - conflicting_files: List of file info dicts with metadata for comparison

    For video conflicts, includes quality_rank based on metadata completeness
    and sorts files by rank (highest first).

    Args:
        move_mappings: List of (source_path, dest_path) tuples
        collection: The collection being reorganized
        session: Database session

    Returns:
        List of conflict detail dicts (empty if no conflicts)
    """
    from wrolpi.files.models import FileGroup

    # Build destination -> source paths mapping
    dest_to_sources = {}
    for source, dest in move_mappings:
        if dest in dest_to_sources:
            dest_to_sources[dest].append(source)
        else:
            dest_to_sources[dest] = [source]

    # Find conflicts (destinations with multiple sources)
    conflicts = {dest: sources for dest, sources in dest_to_sources.items() if len(sources) > 1}

    if not conflicts:
        return []

    media_dir = get_media_directory()
    conflict_details = []

    for dest_path, source_paths in conflicts.items():
        # Get relative destination path for display
        try:
            dest_relative = str(dest_path.relative_to(media_dir))
        except ValueError:
            dest_relative = str(dest_path)

        conflicting_files = []
        # Collect videos for ranking (only for channel collections)
        videos_for_ranking = []
        # Collect archives for ranking (only for domain collections)
        archives_for_ranking = []

        for source_path in source_paths:
            # Look up the FileGroup by its primary_path
            try:
                source_relative = str(source_path.relative_to(media_dir))
            except ValueError:
                source_relative = str(source_path)

            file_group = session.query(FileGroup).filter(
                FileGroup.primary_path == str(source_path)
            ).one_or_none()

            if not file_group:
                # FileGroup not found, add minimal info
                conflicting_files.append({
                    'file_group_id': None,
                    'current_path': source_relative,
                    'title': source_path.stem,
                    'model_type': collection.kind,
                    'size': 0,
                    'video_id': None,
                    'archive_id': None,
                    'poster_path': None,
                    'published_datetime': None,
                    'source_id': None,
                    'quality_rank': None,
                })
                continue

            # Get model-specific metadata
            file_info = {
                'file_group_id': file_group.id,
                'current_path': source_relative,
                'title': file_group.title or source_path.stem,
                'model_type': file_group.model or collection.kind,
                'size': file_group.size or 0,
                'video_id': None,
                'archive_id': None,
                'poster_path': None,
                'published_datetime': None,
                'source_id': None,
                'quality_rank': None,
            }

            # Add model-specific details
            if collection.kind == 'channel':
                from modules.videos.models import Video
                video = session.query(Video).filter_by(file_group_id=file_group.id).one_or_none()
                if video:
                    file_info['video_id'] = video.id
                    file_info['source_id'] = video.source_id
                    # Date is stored on file_group
                    if file_group.published_datetime:
                        file_info['published_datetime'] = file_group.published_datetime.isoformat()
                    # Get poster path
                    if video.poster_path:
                        try:
                            poster_relative = str(pathlib.Path(video.poster_path).relative_to(media_dir))
                        except ValueError:
                            poster_relative = video.poster_path
                        file_info['poster_path'] = poster_relative
                    # Collect video for ranking calculation
                    videos_for_ranking.append((file_info, video))

            elif collection.kind == 'domain':
                from modules.archive.models import Archive
                archive = session.query(Archive).filter_by(file_group_id=file_group.id).one_or_none()
                if archive:
                    file_info['archive_id'] = archive.id
                    # Archives don't have source_id, use file_group.url
                    if file_group.url:
                        file_info['source_id'] = file_group.url
                    if file_group.download_datetime:
                        file_info['published_datetime'] = file_group.download_datetime.isoformat()
                    # Get screenshot path for archives
                    if archive.screenshot_path:
                        try:
                            screenshot_relative = str(pathlib.Path(archive.screenshot_path).relative_to(media_dir))
                        except ValueError:
                            screenshot_relative = archive.screenshot_path
                        file_info['poster_path'] = screenshot_relative
                    # Collect archive for ranking calculation
                    archives_for_ranking.append((file_info, archive))

            conflicting_files.append(file_info)

        # Calculate quality rankings for videos
        if collection.kind == 'channel' and videos_for_ranking:
            # Get largest sizes by source_id for ranking bonus
            videos_only = [v for _, v in videos_for_ranking]
            sizes_by_source_id = _get_largest_sizes_by_source_id(videos_only)

            # Calculate rank for each video
            for file_info, video in videos_for_ranking:
                file_info['quality_rank'] = _rank_video_quality(video, sizes_by_source_id)

        # Calculate quality rankings for archives
        elif collection.kind == 'domain' and archives_for_ranking:
            # Calculate rank for each archive
            for file_info, archive in archives_for_ranking:
                file_info['quality_rank'] = _rank_archive_quality(archive)

        # Sort by quality_rank (highest first), then by size (works for both videos and archives)
        if videos_for_ranking or archives_for_ranking:
            conflicting_files.sort(
                key=lambda f: (f.get('quality_rank') or 0, f.get('size') or 0),
                reverse=True
            )

        conflict_details.append({
            'destination_path': dest_relative,
            'conflicting_files': conflicting_files,
        })

    return conflict_details


def execute_reorganization(
        collection_id: int,
        session: Session = None,
) -> str:
    """Execute reorganization, returns job_id for tracking.

    Iterates ALL FileGroups and queues moves to FileWorker.

    Args:
        collection_id: The collection to reorganize
        session: Database session (optional)

    Returns:
        job_id for tracking progress via FileWorker status

    Raises:
        UnknownCollection: If collection not found
    """
    from wrolpi.files.worker import file_worker

    if session is None:
        with get_db_session(commit=True) as session:
            return execute_reorganization(collection_id, session)

    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()
    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    if not collection.directory:
        raise ValueError(f"Collection '{collection.name}' has no directory. Cannot reorganize.")

    # Build move mappings based on collection kind
    if collection.kind == 'channel':
        move_mappings = _build_move_mappings_for_channel(collection, session)
    elif collection.kind == 'domain':
        move_mappings = _build_move_mappings_for_domain(collection, session)
    else:
        raise ValueError(f"Unsupported collection kind: {collection.kind}")

    # Check for filename conflicts before proceeding
    _check_for_destination_conflicts(move_mappings, collection.name)

    if not move_mappings:
        logger.info(f'No files need reorganization for collection {collection.name}')
        # Still update the file_format to current config
        current_format = collection._get_current_file_format()
        if current_format:
            collection.file_format = current_format
            session.commit()

            # Trigger config save
            if collection.kind == 'domain':
                from modules.archive.lib import save_domains_config
                save_domains_config.activate_switch()
            elif collection.kind == 'channel':
                from modules.videos.lib import save_channels_config
                save_channels_config.activate_switch()

        return ''

    logger.info(f'Queueing reorganization for collection {collection.name}: {len(move_mappings)} files')

    # Get the current file format to update AFTER successful completion
    # (deferred update enables retry on failure - file_format only updates on success)
    pending_file_format = collection._get_current_file_format()

    # Queue the reorganization with FileWorker
    # The pending_file_format will be set by handle_reorganize after successful completion
    job_id = file_worker.queue_reorganize(
        move_mappings,
        collection_id=collection_id,
        collection_kind=collection.kind,
        pending_file_format=pending_file_format,
    )

    return job_id


def get_reorganization_status(job_id: str) -> dict:
    """Get status of an in-flight reorganization.

    Args:
        job_id: The job ID returned by execute_reorganization

    Returns:
        Dict with status information:
        - status: 'pending' | 'running' | 'complete' | 'failed'
        - total: Total files to move
        - completed: Files moved so far
        - percent: Completion percentage
        - error: Error message if failed
    """
    from wrolpi.files.worker import file_worker

    try:
        job_status = file_worker.get_job_status(job_id)
    except RuntimeError:
        return {'status': 'unknown', 'error': f'Job {job_id} not found'}

    # Get current worker status if this job is running
    worker_status = file_worker.status

    if job_status == 'complete':
        return {
            'status': 'complete',
            'total': worker_status.get('operation_total', 0),
            'completed': worker_status.get('operation_total', 0),
            'percent': 100,
            'error': None,
        }
    elif job_status == 'pending':
        return {
            'status': 'pending',
            'total': 0,
            'completed': 0,
            'percent': 0,
            'error': None,
        }
    else:
        # Job is running
        return {
            'status': worker_status.get('status', 'running'),
            'total': worker_status.get('operation_total', 0),
            'completed': worker_status.get('operation_processed', 0),
            'percent': worker_status.get('operation_percent', 0),
            'error': worker_status.get('error'),
        }


# ============================================================================
# Batch Reorganization Functions
# ============================================================================


def get_collections_needing_reorganization(
        kind: str,
        session: Session = None,
) -> dict:
    """Get all collections of a kind that need reorganization with lightweight previews.

    Uses get_batch_reorganization_preview() for fast counts without expensive
    conflict detection or sample move generation.

    Args:
        kind: 'channel' or 'domain'
        session: Database session (optional)

    Returns:
        Dict with:
        - collections: List of collection info dicts
        - total_collections: Total count needing reorganization
        - total_files_needing_move: Sum of all files needing reorganization
        - new_file_format: The config format that will be applied
    """
    if session is None:
        with get_db_session() as session:
            return get_collections_needing_reorganization(kind, session)

    # Query all collections of this kind with directories
    collections = session.query(Collection).filter(
        Collection.kind == kind,
        Collection.directory.isnot(None),
    ).all()

    # Filter to only those needing reorganization
    collections_needing_reorg = [c for c in collections if c.needs_reorganization]

    # Get current config format
    current_format = ''
    if kind == 'channel':
        from modules.videos.lib import get_videos_downloader_config
        current_format = get_videos_downloader_config().file_name_format
    elif kind == 'domain':
        from modules.archive.lib import get_archive_downloader_config
        current_format = get_archive_downloader_config().file_name_format

    result_collections = []
    total_files_needing_move = 0

    for collection in collections_needing_reorg:
        # Use lightweight batch preview (skips expensive conflict detection)
        try:
            preview = get_batch_reorganization_preview(collection.id, session)
            result_collections.append({
                'collection_id': preview.collection_id,
                'collection_name': preview.collection_name,
                'total_files': preview.total_files,
                'files_needing_move': preview.files_needing_move,
                'sample_move': preview.sample_move,
            })
            total_files_needing_move += preview.files_needing_move
        except Exception as e:
            logger.warning(f'Failed to get preview for collection {collection.id}: {e}')
            result_collections.append({
                'collection_id': collection.id,
                'collection_name': collection.name,
                'total_files': 0,
                'files_needing_move': 0,
                'sample_move': None,
            })

    return {
        'collections': result_collections,
        'total_collections': len(result_collections),
        'total_files_needing_move': total_files_needing_move,
        'new_file_format': current_format,
    }


def execute_batch_reorganization(kind: str, session: Session = None) -> dict:
    """Execute batch reorganization for all collections of a kind that need it.

    This queues a batch reorganization job that processes collections sequentially.
    Each collection is reorganized one at a time to avoid system overload.
    If any collection fails, the batch stops and reports which collection failed.

    Args:
        kind: 'channel' or 'domain'
        session: Database session (optional)

    Returns:
        Dict with:
        - batch_job_id: Job ID for tracking progress
        - message: Status message
        - collection_count: Number of collections to process
    """
    from wrolpi.files.worker import file_worker

    if session is None:
        with get_db_session() as session:
            return execute_batch_reorganization(kind, session)

    # Get collections needing reorganization
    reorg_info = get_collections_needing_reorganization(kind, session)
    collections_to_process = reorg_info['collections']

    if not collections_to_process:
        logger.info(f'No {kind} collections need reorganization')
        return {
            'batch_job_id': '',
            'message': f'No {kind} collections need reorganization',
            'collection_count': 0,
        }

    # Extract collection IDs for the batch job
    collection_ids = [c['collection_id'] for c in collections_to_process]

    logger.info(f'Queueing batch reorganization for {len(collection_ids)} {kind} collections')

    # Queue the batch reorganization
    batch_job_id = file_worker.queue_batch_reorganize(collection_ids, kind)

    return {
        'batch_job_id': batch_job_id,
        'message': 'Batch reorganization started',
        'collection_count': len(collection_ids),
    }


def get_batch_reorganization_status(batch_job_id: str) -> dict:
    """Get status of a batch reorganization job.

    Args:
        batch_job_id: The batch job ID returned by execute_batch_reorganization

    Returns:
        Dict with:
        - status: 'pending' | 'running' | 'complete' | 'failed' | 'unknown'
        - total_collections: Total collections in batch
        - completed_collections: Number completed so far
        - current_collection: Info about currently processing collection (or None)
        - overall_percent: Overall completion percentage
        - completed: List of completed collection info
        - failed_collection: Info about failed collection (or None)
        - error: Error message if failed
    """
    from wrolpi.files.worker import file_worker

    try:
        job_status = file_worker.get_job_status(batch_job_id)
    except RuntimeError:
        return {
            'status': 'unknown',
            'error': f'Batch job {batch_job_id} not found',
            'total_collections': 0,
            'completed_collections': 0,
            'current_collection': None,
            'overall_percent': 0,
            'completed': [],
            'failed_collection': None,
        }

    # Get batch-specific status from worker
    worker_status = file_worker.status
    batch_status = worker_status.get('batch_status', {})

    if job_status == 'complete':
        completed_list = batch_status.get('completed', [])
        return {
            'status': 'complete',
            'total_collections': batch_status.get('total_collections', 0),
            'completed_collections': len(completed_list),
            'current_collection': None,
            'overall_percent': 100,
            'completed': completed_list,
            'failed_collection': None,
            'error': None,
        }
    elif job_status == 'pending':
        return {
            'status': 'pending',
            'total_collections': batch_status.get('total_collections', 0),
            'completed_collections': 0,
            'current_collection': None,
            'overall_percent': 0,
            'completed': [],
            'failed_collection': None,
            'error': None,
        }
    elif job_status == 'failed':
        completed_list = batch_status.get('completed', [])
        return {
            'status': 'failed',
            'total_collections': batch_status.get('total_collections', 0),
            'completed_collections': len(completed_list),
            'current_collection': None,
            'overall_percent': batch_status.get('overall_percent', 0),
            'completed': completed_list,
            'failed_collection': batch_status.get('failed_collection'),
            'error': batch_status.get('error'),
        }
    else:
        # Job is running
        completed_list = batch_status.get('completed', [])
        current = batch_status.get('current_collection')
        total = batch_status.get('total_collections', 1)

        # Get fresh file-level progress from worker status (not from batch_status which may be stale)
        current_percent = worker_status.get('operation_percent', 0)

        # Update current collection dict with fresh values if it exists
        if current:
            current = dict(current)  # Copy to avoid mutating the original
            current['percent'] = current_percent
            current['completed'] = worker_status.get('operation_processed', 0)
            current['total'] = worker_status.get('operation_total', 0)

        # Calculate overall percent: (completed + current_progress) / total
        completed_count = len(completed_list)
        overall_percent = int(((completed_count + current_percent / 100) / total) * 100) if total > 0 else 0

        return {
            'status': 'running',
            'total_collections': total,
            'completed_collections': completed_count,
            'current_collection': current,
            'overall_percent': overall_percent,
            'completed': completed_list,
            'failed_collection': None,
            'error': None,
        }


async def get_conflict_details_with_ffprobe(
        collection_id: int,
        session: Session,
) -> List[dict]:
    """Get conflict details, processing ffprobe for any videos missing it.

    This ensures accurate quality rankings (including audio stream bonus)
    when resolving conflicts. The +2 audio bonus in _rank_video_quality()
    only applies if video.ffprobe_json exists.

    Args:
        collection_id: The collection to get conflicts for
        session: Database session

    Returns:
        List of conflict detail dicts (empty if no conflicts)

    Raises:
        UnknownCollection: If collection not found
    """
    preview = get_reorganization_preview(collection_id, session)

    if not preview.conflicts:
        return []

    # Process ffprobe for videos missing it (only for channel collections)
    from modules.videos.models import Video

    videos_processed = 0
    for conflict in preview.conflicts:
        for file_info in conflict['conflicting_files']:
            if file_info.get('video_id'):
                video = session.query(Video).get(file_info['video_id'])
                if video and not video.ffprobe_json:
                    try:
                        await video.get_ffprobe_json()
                        videos_processed += 1
                    except Exception as e:
                        logger.warning(f'Failed to process ffprobe for video {video.id}: {e}')

    # Flush ffprobe data if any was processed (preserves caller's transaction control)
    if videos_processed > 0:
        session.flush()
        # Re-fetch preview to get updated quality rankings
        preview = get_reorganization_preview(collection_id, session)

    return preview.conflicts
