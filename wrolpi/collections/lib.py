"""
Collection Library Functions

Provides generic operations for collections of any kind (domains, channels, etc.).
These functions are used by both the unified collection API and legacy endpoints.
"""
import asyncio
from typing import List, Optional, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from wrolpi import flags
from wrolpi.common import logger, get_relative_to_media_directory
from wrolpi.db import get_db_session
from wrolpi.errors import RefreshConflict
from wrolpi.errors import ValidationError
from wrolpi.events import Events
from wrolpi.tags import Tag
from .errors import UnknownCollection
from .models import Collection, validate_collection_directory

logger = logger.getChild(__name__)

__all__ = [
    'get_collections',
    'get_collection_with_stats',
    'get_domain_statistics',
    'update_collection',
    'refresh_collection',
    'tag_collection',
    'get_tag_info',
    'delete_collection',
    'search_collections',
]


def get_collections(session: Session, kind: Optional[str] = None) -> List[dict]:
    """
    Get all collections, optionally filtered by kind.

    Uses batch queries to fetch statistics for all collections at once,
    avoiding the N+1 query problem that occurs with per-collection queries.

    Args:
        session: Database session
        kind: Optional collection kind to filter by (e.g., 'domain', 'channel')

    Returns:
        List of collection dicts with statistics for each collection type
    """
    # Local imports to avoid circular import: collections -> archive/videos -> collections
    from modules.archive import Archive
    from modules.videos.models import Video, Channel
    from wrolpi.files.models import FileGroup

    query = session.query(Collection)

    if kind:
        query = query.filter(Collection.kind == kind)

    collections = query.order_by(Collection.name).all()

    if not collections:
        return []

    # Separate collections by kind for batch processing
    domain_ids = [c.id for c in collections if c.kind == 'domain']
    channel_ids = [c.id for c in collections if c.kind == 'channel']

    # Batch query: Get archive stats for all domain collections at once
    domain_stats_map = {}
    if domain_ids:
        domain_stats = session.query(
            Archive.collection_id,
            func.count(Archive.id).label('archive_count'),
            func.coalesce(func.sum(FileGroup.size), 0).label('size')
        ).outerjoin(
            FileGroup, FileGroup.id == Archive.file_group_id
        ).filter(
            Archive.collection_id.in_(domain_ids)
        ).group_by(Archive.collection_id).all()

        domain_stats_map = {s.collection_id: s for s in domain_stats}

    # Batch query: Get channel info and video stats for all channel collections at once
    channel_stats_map = {}
    if channel_ids:
        channel_stats = session.query(
            Channel.collection_id,
            Channel.id.label('channel_id'),
            func.count(Video.id).label('video_count'),
            func.coalesce(func.sum(FileGroup.size), 0).label('size')
        ).outerjoin(
            Video, Video.channel_id == Channel.id
        ).outerjoin(
            FileGroup, FileGroup.id == Video.file_group_id
        ).filter(
            Channel.collection_id.in_(channel_ids)
        ).group_by(Channel.collection_id, Channel.id).all()

        channel_stats_map = {s.collection_id: s for s in channel_stats}

    # Convert to JSON and merge batch statistics
    result = []
    for collection in collections:
        data = collection.__json__()

        # Compute minimum download frequency from all downloads
        if collection.downloads:
            # Filter to recurring downloads (frequency > 0) and get minimum
            recurring_frequencies = [d.frequency for d in collection.downloads if d.frequency and d.frequency > 0]
            data['min_download_frequency'] = min(recurring_frequencies) if recurring_frequencies else None
        else:
            data['min_download_frequency'] = None

        # Add type-specific statistics from batch query results
        if collection.kind == 'domain':
            stats = domain_stats_map.get(collection.id)
            data['archive_count'] = stats.archive_count if stats else 0
            data['size'] = int(stats.size) if stats else 0
            data['domain'] = data['name']  # Alias for backward compatibility

        elif collection.kind == 'channel':
            stats = channel_stats_map.get(collection.id)
            if stats:
                data['video_count'] = int(stats.video_count)
                data['total_size'] = int(stats.size)
                data['channel_id'] = stats.channel_id
            else:
                data['video_count'] = 0
                data['total_size'] = 0
                data['channel_id'] = None

        result.append(data)

    return result


def get_collection_with_stats(session: Session, collection_id: int) -> dict:
    """
    Get a single collection with type-specific statistics.

    Args:
        session: Database session
        collection_id: The collection ID

    Returns:
        Collection dict with statistics

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Get base collection data
    data = collection.__json__()

    # Add type-specific statistics
    # This can be extended for different collection types
    if collection.kind == 'domain':
        # Add archive statistics for domain collections
        # Use the detailed statistics function (similar to Channel.get_statistics())
        statistics = get_domain_statistics(session, collection_id)
        data['archive_count'] = statistics['archive_count']
        data['size'] = statistics['size']
        data['statistics'] = statistics
        data['domain'] = data['name']  # Alias for backward compatibility

    elif collection.kind == 'channel':
        # Add video statistics for channel collections
        # Local imports to avoid circular import: collections -> videos -> collections
        from modules.videos.models import Video, Channel
        from wrolpi.files.models import FileGroup

        # Get the Channel associated with this collection
        channel = session.query(Channel).filter(
            Channel.collection_id == collection_id
        ).one_or_none()

        if channel:
            stats_query = session.query(
                func.count(Video.id).label('video_count'),
                func.sum(FileGroup.size).label('size')
            ).outerjoin(
                FileGroup, FileGroup.id == Video.file_group_id
            ).filter(
                Video.channel_id == channel.id
            ).one()

            data['video_count'] = int(stats_query.video_count or 0)
            data['total_size'] = int(stats_query.size or 0)
        else:
            data['video_count'] = 0
            data['total_size'] = 0

    return data


def update_collection(
        session: Session,
        collection_id: int,
        directory: Optional[str] = None,
        tag_name: Optional[str] = None,
        description: Optional[str] = None,
) -> Collection:
    """
    Update a collection's properties.

    Args:
        session: Database session
        collection_id: The collection ID
        directory: New directory (relative or absolute path), or None to clear
        tag_name: New tag name, empty string to clear, or None to leave unchanged
        description: New description, or None to leave unchanged

    Returns:
        Updated Collection object

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If validation fails
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Update directory if provided
    if directory is not None:
        if directory:
            # Convert relative path to absolute with validation
            directory_path = validate_collection_directory(directory)
            collection.directory = directory_path
        else:
            collection.directory = None

    # Update description if provided
    if description is not None:
        collection.description = description

    # Update tag if provided
    if tag_name is not None:
        if tag_name:
            # Set or create tag
            if not collection.directory:
                raise ValidationError(
                    f"Collection '{collection.name}' has no directory. "
                    f"Set a directory before tagging."
                )
            tag = session.query(Tag).filter_by(name=tag_name).one_or_none()
            if not tag:
                tag = Tag(name=tag_name)
                session.add(tag)
                session.flush()
            collection.tag_id = tag.id
        elif tag_name == '':
            # Clear tag (empty string explicitly clears)
            collection.tag_id = None

    session.flush()

    # Trigger domain config save if this is a domain collection
    if collection.kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.lib import save_domains_config
        save_domains_config.activate_switch()

    return collection


def refresh_collection(collection_id: int, send_events: bool = True) -> None:
    """
    Refresh all files in a collection's directory.

    Args:
        collection_id: The collection ID
        send_events: Whether to send events about the refresh

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If collection has no directory
    """
    # Local import to avoid circular import: collections -> files -> collections
    from wrolpi.files.lib import refresh_files

    with get_db_session() as session:
        collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

        if not collection:
            raise UnknownCollection(f"Collection with ID {collection_id} not found")

        if not collection.directory:
            raise ValidationError(
                f"Collection '{collection.name}' has no directory. "
                f"Set a directory before refreshing."
            )

        directory = collection.directory

    # Refresh files asynchronously
    asyncio.ensure_future(refresh_files([directory], send_events=send_events))

    if send_events:
        relative_dir = get_relative_to_media_directory(directory)
        Events.send_directory_refresh(f'Refreshing: {relative_dir}')


async def tag_collection(
        session: Session,
        collection_id: int,
        tag_name: Optional[str] = None,
        directory: Optional[str] = None,
) -> Dict:
    """
    Tag a collection and optionally move files to a new directory, or remove a tag if no tag_name is provided.

    Args:
        session: Database session
        collection_id: The collection ID
        tag_name: Tag name to apply, or None to remove the tag
        directory: Optional new directory for the collection

    Returns:
        Dict with tag information and suggested directory

    Raises:
        UnknownCollection: If collection not found
        ValidationError: If tagging requirements not met
        RefreshConflict: If a file refresh is in progress and directory change is requested
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # Track old directory before any changes for potential file moving
    old_directory = collection.directory

    # If tag_name is None, remove the tag from the collection
    if tag_name is None:
        collection.tag_id = None

        # Update directory if provided (user may want to move files when removing tag)
        if directory:
            target_directory = validate_collection_directory(directory)
        else:
            target_directory = collection.directory

        # Check if we need to move files
        need_to_move = (
                target_directory is not None and
                old_directory is not None and
                target_directory != old_directory
        )

        if need_to_move and flags.refreshing.is_set():
            raise RefreshConflict('Refusing to move collection while file refresh is in progress')

        session.flush()

        # Trigger config save based on collection kind
        if collection.kind == 'domain':
            # Local import to avoid circular import: collections -> archive -> collections
            from modules.archive.lib import save_domains_config
            save_domains_config.activate_switch()
        elif collection.kind == 'channel':
            # Local import to avoid circular import: collections -> videos -> collections
            from modules.videos.lib import save_channels_config
            save_channels_config.activate_switch()

        # Move files if directory changed
        if need_to_move:
            target_directory.mkdir(parents=True, exist_ok=True)
            await collection.move_collection(target_directory, session, send_events=True)

        # Return info about the un-tagging operation
        relative_dir = get_relative_to_media_directory(target_directory) if target_directory else None
        return {
            'collection_id': collection.id,
            'collection_name': collection.name,
            'tag_name': None,
            'directory': str(relative_dir) if relative_dir else None,
            'will_move_files': need_to_move,
        }

    # Get or create the tag
    tag = session.query(Tag).filter_by(name=tag_name).one_or_none()
    if not tag:
        tag = Tag(name=tag_name)
        session.add(tag)
        session.flush()

    # Determine target directory
    if directory:
        # User specified a directory - validate it
        target_directory = validate_collection_directory(directory)
    elif collection.directory:
        # Use existing directory
        target_directory = collection.directory
    else:
        # No directory provided and collection has none - keep it that way
        # Collections can be tagged without a directory for UI search/filtering
        target_directory = None

    # Check if we need to move files
    need_to_move = (
            target_directory is not None and
            old_directory is not None and
            target_directory != old_directory
    )

    if need_to_move and flags.refreshing.is_set():
        raise RefreshConflict('Refusing to move collection while file refresh is in progress')

    # Apply the tag
    collection.tag_id = tag.id
    # Only update directory if we have a target (don't auto-generate for directory-less collections)
    # Note: directory update is handled by move_collection if need_to_move, otherwise set directly
    if target_directory is not None and not need_to_move:
        collection.directory = target_directory

    session.flush()

    # Trigger config save based on collection kind
    if collection.kind == 'domain':
        # Local import to avoid circular import: collections -> archive -> collections
        from modules.archive.lib import save_domains_config
        save_domains_config.activate_switch()
    elif collection.kind == 'channel':
        # Local import to avoid circular import: collections -> videos -> collections
        from modules.videos.lib import save_channels_config
        save_channels_config.activate_switch()

    # Move files if directory changed
    if need_to_move:
        target_directory.mkdir(parents=True, exist_ok=True)
        await collection.move_collection(target_directory, session, send_events=True)

    # Return info about the tagging operation
    relative_dir = get_relative_to_media_directory(target_directory) if target_directory else None
    return {
        'collection_id': collection.id,
        'collection_name': collection.name,
        'tag_name': tag_name,
        'directory': str(relative_dir) if relative_dir else None,
        'will_move_files': need_to_move,
    }


def get_tag_info(
        session: Session,
        collection_id: int,
        tag_name: Optional[str],
) -> Dict:
    """
    Get information about tagging a collection with a specific tag.

    Returns the suggested directory and checks for conflicts with existing collections.
    For collections without a directory, returns suggested_directory=None.

    Args:
        session: Database session
        collection_id: The collection ID
        tag_name: Tag name to check

    Returns:
        Dict with suggested_directory, conflict flag, and optional conflict_message

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    # For collections without a directory, return None - no directory suggestions needed
    if collection.directory is None:
        return {
            'suggested_directory': None,
            'conflict': False,
            'conflict_message': None,
        }

    # Use the collection's format_directory method to get the suggested directory
    suggested_directory = collection.format_directory(tag_name)

    # Check for directory conflicts with other domain collections
    conflict = False
    conflict_message = None

    # Only check for conflicts if this is a domain collection
    if collection.kind == 'domain':
        # Check if another domain collection already has this directory
        existing_domain = session.query(Collection).filter(
            Collection.directory == str(suggested_directory),
            Collection.kind == 'domain',
            Collection.id != collection_id
        ).first()

        if existing_domain:
            conflict = True
            conflict_message = (
                f"A domain collection '{existing_domain.name}' already uses this directory. "
                f"Choose a different tag or directory."
            )

    # Return relative path for the frontend
    relative_dir = get_relative_to_media_directory(suggested_directory)

    return {
        'suggested_directory': str(relative_dir),
        'conflict': conflict,
        'conflict_message': conflict_message,
    }


def delete_collection(
        session: Session,
        collection_id: int,
) -> Dict:
    """
    Delete a collection and orphan its child items.

    For domain collections:
    - Orphans child Archives (sets collection_id to NULL)
    - Deletes the Collection record
    - Triggers domain config save

    Args:
        session: Database session
        collection_id: The collection ID to delete

    Returns:
        Dict with collection information

    Raises:
        UnknownCollection: If collection not found
    """
    collection = session.query(Collection).filter_by(id=collection_id).one_or_none()

    if not collection:
        raise UnknownCollection(f"Collection with ID {collection_id} not found")

    collection_dict = {
        'id': collection.id,
        'name': collection.name,
        'kind': collection.kind,
    }

    # Orphan child Archives if this is a domain collection
    if collection.kind == 'domain':
        # Local imports to avoid circular import: collections -> archive -> collections
        from modules.archive.models import Archive
        from modules.archive.lib import save_domains_config
        archives = session.query(Archive).filter_by(collection_id=collection_id).all()
        for archive in archives:
            archive.collection_id = None
        session.flush()

        # Trigger domain config save
        save_domains_config.activate_switch()

    # Delete the collection
    session.delete(collection)
    session.flush()

    return collection_dict


def search_collections(
        session: Session,
        kind: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        search_str: Optional[str] = None,
) -> List[dict]:
    """
    Search collections by kind, tags, and search string.

    Args:
        session: Database session
        kind: Optional collection kind filter
        tag_names: Optional list of tag names to filter by
        search_str: Optional search string for collection names

    Returns:
        List of matching collection dicts
    """
    query = session.query(Collection)

    # Filter by kind
    if kind:
        query = query.filter(Collection.kind == kind)

    # Filter by tags
    if tag_names:
        query = query.join(Tag).filter(Tag.name.in_(tag_names))

    # Filter by search string
    if search_str:
        query = query.filter(Collection.name.ilike(f'%{search_str}%'))

    # Order by name
    query = query.order_by(Collection.name)

    collections = query.all()
    return [collection.__json__() for collection in collections]


def get_domain_statistics(session: Session, collection_id: int) -> Dict:
    """
    Get detailed statistics for a domain collection.

    Similar to Channel.get_statistics(), this returns comprehensive stats about
    a domain collection's archives.

    Args:
        session: Database session
        collection_id: The domain collection ID

    Returns:
        Dict with:
        - archive_count: Number of archives in the domain
        - size: Total size of all archive files
        - largest_archive: Size of the largest archive
        - archive_tags: Count of archives that have at least one tag
    """
    # Local imports to avoid circular import: collections -> archive -> collections
    from modules.archive.models import Archive
    from wrolpi.files.models import FileGroup
    from wrolpi.tags import TagFile

    # Use a single query with aggregate functions similar to Channel.get_statistics()
    stats_query = session.query(
        func.count(Archive.id).label('archive_count'),
        func.coalesce(func.sum(FileGroup.size), 0).label('size'),
        func.coalesce(func.max(FileGroup.size), 0).label('largest_archive'),
        func.count(Archive.id).filter(TagFile.file_group_id.isnot(None)).label('archive_tags')
    ).outerjoin(
        FileGroup, FileGroup.id == Archive.file_group_id
    ).outerjoin(
        TagFile, FileGroup.id == TagFile.file_group_id
    ).filter(
        Archive.collection_id == collection_id
    ).one()

    return {
        'archive_count': stats_query.archive_count or 0,
        'size': int(stats_query.size or 0),
        'largest_archive': int(stats_query.largest_archive or 0),
        'archive_tags': stats_query.archive_tags or 0,
    }
